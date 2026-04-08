# Task 5 — Regional Hub Network: OOP Skeleton

## Design rationale

The physical network for Task 5 consists of:

- **Nodes** — candidate regional hub locations, each anchored to a county (identified in Tasks 3/4) with geographic, physical-infrastructure, and freight-demand attributes.
- **Links** — directed or undirected edges between pairs of hubs, characterized by road travel time, distance, and observed/estimated freight interaction. The connectivity constraint from §2.3 is that neighboring hubs must be reachable within 5.5 hours.
- **NetworkManager** — owns the full graph, enforces constraints, provides selection/optimization entry points, and produces outputs consumed by Tasks 6–8.

The design keeps every attribute grounded in data already available or expected from Tasks 1–4 (FAF O-D flows, county FIPS, CoStar candidate sites, clustering output from Task 3).

---

## Class definitions

```python
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Constants (from §2.3 and project key parameters)
# ---------------------------------------------------------------------------

MAX_NEIGHBOR_TRAVEL_TIME_H: float = 5.5   # hours — connectivity constraint between neighboring hubs
REGION_TARGET: int = 50                    # approximate number of regions / regional hubs


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """
    Represents a single candidate regional hub location within the NE megaregion.

    A Node corresponds to one candidate hub identified during Task 4 (CoStar screening
    and proximity-to-infrastructure analysis).  It carries geographic coordinates, the
    county and region it belongs to, physical-infrastructure attributes, and freight
    demand metrics derived from the Task 1 O-D matrix.

    Attributes
    ----------
    node_id : str
        Unique identifier for this hub candidate.  Convention: ``"HUB_<county_fips>_<seq>"``,
        e.g. ``"HUB_34023_01"`` for the first candidate in Middlesex County, NJ.
    county_fips : str
        5-digit FIPS code of the county this hub candidate sits in.  Links the node
        back to the freight flow records in ``Data/Task1/raw.parquet``.
    region_id : Optional[str]
        Cluster label assigned by Task 3 (K-means region clustering).  ``None`` until
        clustering output is joined.
    lat : float
        WGS-84 latitude of the candidate facility or centroid.
    lon : float
        WGS-84 longitude of the candidate facility or centroid.
    name : str
        Human-readable label (e.g. city name or CoStar property address).
    hub_tier : str
        Tier designation: ``"regional"`` for this task; later tasks may introduce
        ``"gateway"`` nodes.  Defaults to ``"regional"``.

    Physical infrastructure attributes
    -----------------------------------
    interstate_access : bool
        True if the site is within a practical distance of an interstate on-ramp
        (threshold to be defined in Task 4 screening, typically ≤ 2 miles).
    rail_access : bool
        True if the site has direct or adjacent rail yard access.
    available_area_sqft : Optional[float]
        Available warehouse / truck-terminal floor area in square feet as reported
        by CoStar.  ``None`` if the site is a proxy location (open land / in-construction).
    is_proxy : bool
        True when no qualifying CoStar facility exists in the county and the site
        is a proxy (open land plot or in-construction building), per §2.5 fallback logic.

    Freight demand attributes (from Task 1 O-D matrix)
    ----------------------------------------------------
    inbound_tons_2025 : float
        Total inbound truck tonnage (thousand short tons) to this county in 2025,
        aggregated from ``Data/Task1/raw.parquet`` filtered to this county as destination.
    outbound_tons_2025 : float
        Total outbound truck tonnage (thousand short tons) from this county in 2025.
    inbound_tons_2030 : float
        Forecasted inbound tonnage in 2030.
    outbound_tons_2030 : float
        Forecasted outbound tonnage in 2030.

    Derived / computed attributes
    ------------------------------
    throughput_2025 : float
        ``max(inbound_tons_2025, outbound_tons_2025)`` — the larger of inbound/outbound
        volumes; used for hub sizing and set-cover weighting.  Computed on construction.
    is_selected : bool
        Whether this hub has been chosen by the hub-selection algorithm in Task 5.
        ``False`` until ``NetworkManager.select_hubs()`` is called.
    covered_by : Optional[str]
        ``node_id`` of the selected hub that "covers" this candidate, if applicable
        in a set-cover formulation.  ``None`` if this node itself is selected.
    """

    # Identity & geography
    node_id: str
    county_fips: str
    region_id: Optional[str]
    lat: float
    lon: float
    name: str
    hub_tier: str = "regional"

    # Physical infrastructure
    interstate_access: bool = False
    rail_access: bool = False
    available_area_sqft: Optional[float] = None
    is_proxy: bool = False

    # Freight demand (from Task 1 aggregation)
    inbound_tons_2025: float = 0.0
    outbound_tons_2025: float = 0.0
    inbound_tons_2030: float = 0.0
    outbound_tons_2030: float = 0.0

    # Selection state (set by NetworkManager)
    is_selected: bool = field(default=False, init=False)
    covered_by: Optional[str] = field(default=None, init=False)

    # ------------------------------------------------------------------
    # Derived property
    # ------------------------------------------------------------------

    @property
    def throughput_2025(self) -> float:
        """
        Peak-side tonnage for 2025: the larger of inbound and outbound volumes.

        This mirrors the peak-demand logic in §2.1 (use the dominant side of
        freight flow) and is the primary sizing metric for hub selection.
        """
        return max(self.inbound_tons_2025, self.outbound_tons_2025)

    @property
    def throughput_2030(self) -> float:
        """
        Peak-side tonnage for 2030 (same convention as ``throughput_2025``).
        """
        return max(self.inbound_tons_2030, self.outbound_tons_2030)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def haversine_distance_km(self, other: Node) -> float:
        """
        Great-circle distance (km) between this node and *other*.

        Used as a fast straight-line approximation when road-network data is
        unavailable.  For constraint checking (5.5 h travel time), use
        ``Link.travel_time_h`` instead, which reflects actual road distance.

        Parameters
        ----------
        other : Node
            The second hub location.

        Returns
        -------
        float
            Euclidean approximation of distance in kilometres via the
            Haversine formula.
        """
        R = 6371.0
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(other.lat), math.radians(other.lon)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return R * 2 * math.asin(math.sqrt(a))

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        status = "SELECTED" if self.is_selected else "candidate"
        return (
            f"Node({self.node_id!r}, fips={self.county_fips}, "
            f"region={self.region_id}, [{self.lat:.4f}, {self.lon:.4f}], "
            f"throughput_2025={self.throughput_2025:.1f}k-tons, {status})"
        )


# ---------------------------------------------------------------------------
# Link
# ---------------------------------------------------------------------------

@dataclass
class Link:
    """
    Represents a directed or undirected physical connection between two hub nodes.

    Links encode the road-network relationship between a pair of candidate hubs.
    They carry travel-time and distance attributes (from a routing engine or
    highway-network GIS layer) as well as the observed freight interaction derived
    from the Task 1 O-D matrix.  The primary role of a Link is to:

    1. Enforce the 5.5-hour neighboring-hub connectivity constraint (§2.3).
    2. Provide edge weights for graph algorithms used in hub selection (e.g. set
       cover, minimum spanning tree, p-median).
    3. Carry forecast tonnage for flow assignment in Task 8.

    Attributes
    ----------
    link_id : str
        Unique identifier.  Convention: ``"<origin_node_id>--<dest_node_id>"``.
    origin_node_id : str
        ``node_id`` of the origin (or "from") hub.
    dest_node_id : str
        ``node_id`` of the destination (or "to") hub.
    is_directed : bool
        If ``True``, the link is directional (origin → destination only).
        Defaults to ``False`` (undirected), which is appropriate for road
        links where travel in either direction is equally feasible.

    Physical network attributes
    ---------------------------
    road_distance_km : Optional[float]
        Shortest-path road distance in kilometres between the two hubs, derived
        from highway-network routing (e.g. via OSMnx or OSRM).  ``None`` if
        only straight-line approximation is available.
    travel_time_h : Optional[float]
        Estimated truck travel time in hours under free-flow or off-peak
        conditions.  This is the primary attribute checked against the
        5.5-hour constraint.  ``None`` until populated from routing data.
    primary_highway : Optional[str]
        Name or number of the dominant interstate / US highway corridor
        connecting the two nodes (e.g. ``"I-95"``, ``"I-78"``).  Informational;
        used for network map labelling in Task 7.
    passes_through_regions : List[str]
        List of ``region_id`` labels for intermediate regions the corridor
        passes through.  Populated during Task 7 multi-tier integration.

    Freight interaction attributes (from Task 1 O-D matrix)
    ---------------------------------------------------------
    freight_tons_2025 : float
        Observed (or estimated) freight flow between the two endpoint counties
        in 2025 (thousand short tons, truck mode).  Aggregated from
        ``Data/Task1/raw.parquet`` for the relevant county pair.
    freight_tons_2030 : float
        Forecasted freight flow in 2030.
    flow_type : str
        Characterises whether the link carries ``"internal"`` (NE→NE),
        ``"inbound"``, or ``"outbound"`` flows, mirroring Task 1 classification.

    Selection / constraint state
    -----------------------------
    satisfies_time_constraint : bool
        ``True`` when ``travel_time_h`` is not ``None`` and does not exceed
        ``MAX_NEIGHBOR_TRAVEL_TIME_H`` (5.5 h).  Updated automatically when
        ``travel_time_h`` is set via ``update_travel_time()``.
    is_active : bool
        Whether this link is included in the final selected network (both
        endpoints must be selected hubs).  ``False`` until
        ``NetworkManager.build_active_network()`` is called.
    """

    # Identity
    link_id: str
    origin_node_id: str
    dest_node_id: str
    is_directed: bool = False

    # Physical network
    road_distance_km: Optional[float] = None
    travel_time_h: Optional[float] = None
    primary_highway: Optional[str] = None
    passes_through_regions: List[str] = field(default_factory=list)

    # Freight interaction (from Task 1)
    freight_tons_2025: float = 0.0
    freight_tons_2030: float = 0.0
    flow_type: str = "internal"  # "internal" | "inbound" | "outbound"

    # Constraint / selection state
    satisfies_time_constraint: bool = field(default=False, init=False)
    is_active: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Re-evaluate time constraint if travel_time_h was provided at construction."""
        self._recheck_constraint()

    # ------------------------------------------------------------------
    # Constraint helpers
    # ------------------------------------------------------------------

    def update_travel_time(self, travel_time_h: float) -> None:
        """
        Set or update the truck travel time for this link and recheck the
        5.5-hour connectivity constraint.

        Parameters
        ----------
        travel_time_h : float
            New travel time estimate in hours.
        """
        self.travel_time_h = travel_time_h
        self._recheck_constraint()

    def _recheck_constraint(self) -> None:
        """Internal helper: update ``satisfies_time_constraint`` flag."""
        if self.travel_time_h is not None:
            self.satisfies_time_constraint = self.travel_time_h <= MAX_NEIGHBOR_TRAVEL_TIME_H
        else:
            self.satisfies_time_constraint = False

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        tt = f"{self.travel_time_h:.2f}h" if self.travel_time_h is not None else "??h"
        ok = "OK" if self.satisfies_time_constraint else "VIOLATES_CONSTRAINT"
        return (
            f"Link({self.origin_node_id!r} -> {self.dest_node_id!r}, "
            f"travel={tt} [{ok}], "
            f"freight_2025={self.freight_tons_2025:.1f}k-tons)"
        )


# ---------------------------------------------------------------------------
# NetworkManager
# ---------------------------------------------------------------------------

class NetworkManager:
    """
    Owns and manages the full regional hub network graph for Task 5.

    Responsibilities
    ----------------
    - Store all candidate ``Node`` objects and ``Link`` objects.
    - Enforce the physical connectivity constraint (≤ 5.5 h between neighboring
      hubs, §2.3) when links are registered.
    - Provide the entry point for hub-selection algorithms (set-cover or
      equivalent heuristic / optimization).
    - Expose graph-level queries: neighbors, reachable hubs, shortest paths.
    - Produce outputs (selected hub list, active link list) consumed by Tasks 6–8.

    Internal data structures
    ------------------------
    _nodes : Dict[str, Node]
        Map from ``node_id`` to ``Node`` instance.
    _links : Dict[str, Link]
        Map from ``link_id`` to ``Link`` instance.
    _adjacency : Dict[str, Set[str]]
        Adjacency list: maps each ``node_id`` to the set of ``node_id``s it is
        linked to (undirected representation; both directions stored for
        undirected links).

    Parameters
    ----------
    name : str
        Descriptive label for this network instance (e.g. ``"NE_regional_hub_network"``).
    """

    def __init__(self, name: str = "NE_regional_hub_network") -> None:
        self.name: str = name
        self._nodes: Dict[str, Node] = {}
        self._links: Dict[str, Link] = {}
        self._adjacency: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """
        Register a candidate hub node.

        Parameters
        ----------
        node : Node
            The ``Node`` instance to add.  Duplicate ``node_id`` values raise
            ``ValueError``.

        Raises
        ------
        ValueError
            If a node with the same ``node_id`` is already registered.
        """
        if node.node_id in self._nodes:
            raise ValueError(f"Node '{node.node_id}' is already registered.")
        self._nodes[node.node_id] = node
        self._adjacency.setdefault(node.node_id, set())

    def get_node(self, node_id: str) -> Node:
        """
        Retrieve a node by its ID.

        Parameters
        ----------
        node_id : str
            The ``node_id`` to look up.

        Returns
        -------
        Node
            The corresponding ``Node`` instance.

        Raises
        ------
        KeyError
            If no node with the given ID exists.
        """
        return self._nodes[node_id]

    @property
    def nodes(self) -> List[Node]:
        """All registered candidate hub nodes as a list."""
        return list(self._nodes.values())

    @property
    def selected_nodes(self) -> List[Node]:
        """Subset of nodes marked as selected (``is_selected == True``)."""
        return [n for n in self._nodes.values() if n.is_selected]

    # ------------------------------------------------------------------
    # Link management
    # ------------------------------------------------------------------

    def add_link(self, link: Link, enforce_constraint: bool = True) -> None:
        """
        Register a link between two nodes, optionally enforcing the travel-time
        connectivity constraint.

        Both endpoint nodes must be registered before a link can be added.

        Parameters
        ----------
        link : Link
            The ``Link`` instance to add.
        enforce_constraint : bool
            If ``True`` (default), a warning is logged when the link violates
            the 5.5-hour neighboring-hub constraint.  The link is still added
            so that constraint-violating links can be inspected or filtered
            later during hub selection.

        Raises
        ------
        KeyError
            If either endpoint node is not registered.
        ValueError
            If a link with the same ``link_id`` is already registered.
        """
        if link.origin_node_id not in self._nodes:
            raise KeyError(f"Origin node '{link.origin_node_id}' not found. Register it first.")
        if link.dest_node_id not in self._nodes:
            raise KeyError(f"Destination node '{link.dest_node_id}' not found. Register it first.")
        if link.link_id in self._links:
            raise ValueError(f"Link '{link.link_id}' is already registered.")

        self._links[link.link_id] = link

        # Update adjacency list
        self._adjacency[link.origin_node_id].add(link.dest_node_id)
        if not link.is_directed:
            self._adjacency[link.dest_node_id].add(link.origin_node_id)

        if enforce_constraint and not link.satisfies_time_constraint:
            import warnings
            warnings.warn(
                f"Link '{link.link_id}' has travel_time_h={link.travel_time_h} "
                f"which exceeds the {MAX_NEIGHBOR_TRAVEL_TIME_H}h constraint.",
                stacklevel=2,
            )

    def get_link(self, link_id: str) -> Link:
        """
        Retrieve a link by its ID.

        Parameters
        ----------
        link_id : str
            The ``link_id`` to look up.

        Returns
        -------
        Link
            The corresponding ``Link`` instance.

        Raises
        ------
        KeyError
            If no link with the given ID exists.
        """
        return self._links[link_id]

    @property
    def links(self) -> List[Link]:
        """All registered links as a list."""
        return list(self._links.values())

    @property
    def active_links(self) -> List[Link]:
        """Subset of links whose both endpoints are selected hubs."""
        return [lk for lk in self._links.values() if lk.is_active]

    def neighbors(self, node_id: str) -> List[Node]:
        """
        Return all nodes directly connected to *node_id* by a registered link.

        Parameters
        ----------
        node_id : str
            ID of the hub whose neighbours are requested.

        Returns
        -------
        List[Node]
            Neighboring ``Node`` objects (undirected: both link directions
            included for undirected links).
        """
        return [self._nodes[nid] for nid in self._adjacency.get(node_id, set())]

    # ------------------------------------------------------------------
    # Hub selection
    # ------------------------------------------------------------------

    def select_hubs(
        self,
        method: str = "set_cover",
        region_ids: Optional[List[str]] = None,
    ) -> List[Node]:
        """
        Run the hub-selection algorithm and mark chosen nodes as selected.

        This is the primary Task 5 entry point.  The method parameter controls
        which algorithm is used:

        - ``"set_cover"`` — greedy weighted set-cover heuristic: iteratively pick
          the candidate that covers the most uncovered demand (weighted by
          ``throughput_2025``), subject to the 5.5-hour connectivity constraint.
        - ``"p_median"`` — p-median integer programme (requires an LP/ILP solver
          such as PuLP or OR-Tools to be installed); minimises total weighted
          travel distance from demand counties to their assigned hub.
        - ``"mst_prune"`` — build a minimum spanning tree on selected links
          (weighted by inverse freight interaction) and prune low-demand leaves.

        After this method returns, ``node.is_selected`` and ``node.covered_by``
        are updated for every registered node, and ``build_active_network()`` is
        called automatically.

        Parameters
        ----------
        method : str
            Algorithm selector.  Defaults to ``"set_cover"``.
        region_ids : Optional[List[str]]
            If provided, restrict selection to nodes belonging to these
            ``region_id`` clusters (for partial / incremental runs).

        Returns
        -------
        List[Node]
            The list of selected hub nodes (those with ``is_selected == True``
            after the run).

        Raises
        ------
        NotImplementedError
            Until the algorithm body is filled in.
        """
        raise NotImplementedError(
            f"Hub selection method '{method}' has not been implemented yet. "
            "Implement the greedy set-cover body here in Task 5."
        )

    def build_active_network(self) -> None:
        """
        Mark every link as active or inactive based on the current selection state.

        A link is active when **both** its origin and destination nodes are selected
        hubs.  Call this after ``select_hubs()`` (it is also called automatically by
        ``select_hubs()`` on completion).
        """
        selected_ids: Set[str] = {n.node_id for n in self.selected_nodes}
        for link in self._links.values():
            link.is_active = (
                link.origin_node_id in selected_ids
                and link.dest_node_id in selected_ids
            )

    # ------------------------------------------------------------------
    # Constraint validation
    # ------------------------------------------------------------------

    def validate_connectivity(self) -> List[Tuple[str, str, float]]:
        """
        Check every registered link against the 5.5-hour travel-time constraint.

        Returns
        -------
        List[Tuple[str, str, float]]
            A list of ``(origin_node_id, dest_node_id, travel_time_h)`` tuples
            for **violating** links.  An empty list means all links satisfy the
            constraint (or have no travel time set).
        """
        violations = []
        for link in self._links.values():
            if link.travel_time_h is not None and not link.satisfies_time_constraint:
                violations.append(
                    (link.origin_node_id, link.dest_node_id, link.travel_time_h)
                )
        return violations

    def missing_travel_times(self) -> List[str]:
        """
        Return a list of ``link_id``s for which ``travel_time_h`` has not yet
        been populated.  Used to identify which routing lookups still need to run.

        Returns
        -------
        List[str]
            IDs of links with ``travel_time_h == None``.
        """
        return [lk.link_id for lk in self._links.values() if lk.travel_time_h is None]

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    def to_node_dataframe(self):
        """
        Export the full node table as a ``pandas.DataFrame``.

        Columns mirror the ``Node`` dataclass attributes plus the derived
        ``throughput_2025`` and ``throughput_2030`` fields.  Suitable for
        saving to CSV or joining back to GIS data.

        Returns
        -------
        pandas.DataFrame
            One row per registered node.
        """
        import pandas as pd
        records = []
        for n in self._nodes.values():
            records.append({
                "node_id": n.node_id,
                "county_fips": n.county_fips,
                "region_id": n.region_id,
                "lat": n.lat,
                "lon": n.lon,
                "name": n.name,
                "hub_tier": n.hub_tier,
                "interstate_access": n.interstate_access,
                "rail_access": n.rail_access,
                "available_area_sqft": n.available_area_sqft,
                "is_proxy": n.is_proxy,
                "inbound_tons_2025": n.inbound_tons_2025,
                "outbound_tons_2025": n.outbound_tons_2025,
                "throughput_2025": n.throughput_2025,
                "inbound_tons_2030": n.inbound_tons_2030,
                "outbound_tons_2030": n.outbound_tons_2030,
                "throughput_2030": n.throughput_2030,
                "is_selected": n.is_selected,
                "covered_by": n.covered_by,
            })
        return pd.DataFrame(records)

    def to_link_dataframe(self):
        """
        Export the full link table as a ``pandas.DataFrame``.

        Columns mirror the ``Link`` dataclass attributes.  Suitable for
        saving to CSV or loading into a network visualisation tool.

        Returns
        -------
        pandas.DataFrame
            One row per registered link.
        """
        import pandas as pd
        records = []
        for lk in self._links.values():
            records.append({
                "link_id": lk.link_id,
                "origin_node_id": lk.origin_node_id,
                "dest_node_id": lk.dest_node_id,
                "is_directed": lk.is_directed,
                "road_distance_km": lk.road_distance_km,
                "travel_time_h": lk.travel_time_h,
                "primary_highway": lk.primary_highway,
                "freight_tons_2025": lk.freight_tons_2025,
                "freight_tons_2030": lk.freight_tons_2030,
                "flow_type": lk.flow_type,
                "satisfies_time_constraint": lk.satisfies_time_constraint,
                "is_active": lk.is_active,
            })
        return pd.DataFrame(records)

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"NetworkManager(name={self.name!r}, "
            f"nodes={len(self._nodes)}, links={len(self._links)}, "
            f"selected={len(self.selected_nodes)})"
        )
```

---

## Design notes

### Why `@dataclass` for `Node` and `Link`

Both classes are primarily value-holding containers with a small number of derived properties and helpers.  `@dataclass` eliminates `__init__` boilerplate, keeps attribute documentation co-located with the definition, and makes it straightforward to add `__eq__` / `__hash__` later if nodes need to be used as dict keys or in sets.

### Physical grounding of each attribute

| Attribute | Physical basis | Data source |
|---|---|---|
| `county_fips` | Links the hub back to O-D freight records | `Data/Task1/raw.parquet` |
| `region_id` | Connects hub to its demand-balanced cluster | Task 3 K-means output |
| `lat` / `lon` | Facility or county centroid coordinates | CoStar / Task 4 |
| `interstate_access` | Proximity to on-ramp — primary criterion in §2.3 | Highway GIS layer |
| `rail_access` | Adjacency to railroad yard | NTAD rail network |
| `available_area_sqft` | CoStar available space; gateway threshold ≥ 20,000 ft² (used in Task 6) | CoStar DB |
| `inbound_tons_2025` / `outbound_tons_2025` | County-level aggregation of truck flows | `raw.parquet` filtered by `county_fips` |
| `travel_time_h` on Link | Truck travel time under free-flow; checked against 5.5 h limit | OSMnx / OSRM routing |
| `freight_tons_2025` on Link | County-pair O-D flow (truck mode) | `raw.parquet` origin/dest pair lookup |

### `select_hubs()` stub

The method is left as `NotImplementedError` intentionally.  The three named strategies (greedy set-cover, p-median, MST-prune) map directly onto the §2.3 description and the project's `~50 regions` target.  The greedy set-cover body should:

1. Initialise uncovered demand from all nodes' `throughput_2025`.
2. At each iteration, pick the candidate that covers the most uncovered demand within a 5.5 h travel-time radius (using `travel_time_h` on existing links or a distance-proxy).
3. Mark the chosen node `is_selected = True` and all reachable nodes `covered_by = chosen_node.node_id`.
4. Terminate when all nodes are covered or the target hub count is reached.

### Integration with downstream tasks

- **Task 6 (Gateway Hub Design):** `selected_nodes` provides the anchoring regional hubs; `covered_by` tells Task 6 which counties fall under each hub's territory.
- **Task 7 (Multi-Tier Integration):** `to_node_dataframe()` and `to_link_dataframe()` feed directly into the unified network GeoDataFrame.
- **Task 8 (Flow Assignment):** `active_links` with `freight_tons_2025` / `freight_tons_2030` seed the minimum-cost multi-commodity network flow formulation (§2.6).
