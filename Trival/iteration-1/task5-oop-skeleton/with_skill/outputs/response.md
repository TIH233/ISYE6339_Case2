# Task 5 — Regional Hub Network: OOP Skeleton

## Step 0 — Context loaded

**Task 5 objective (from `Doc/Task.md`):**
> Apply set-cover or equivalent optimization/heuristic to select hubs; define network links using travel time and freight interaction.

**Physical constraints (from `CLAUDE.md` and `Doc/Paper.md §2.3`):**
- Travel time between neighboring regional hubs ≤ 5.5 h
- Hub clusters sized by freight flow throughput
- Connectivity criterion: proximity to interstates, railroads, freight corridors

**Input files confirmed:**
- `Data/Task1/raw.parquet` — O-D demand (cols: `origin_county_fips`, `dest_county_fips`, `mode`, `tons_2025`, `tons_2030`)
- `Data/Task2/task2_*_interface_nodes_final.csv` — interface nodes (cols: `node_name`, `state_name`, `node_type`, `interface_class`, `tons_2025`, `tons_2030`)

---

## OOP Skeleton

```python
# Task5/task5_notebook.ipynb  — cell: class definitions
# Interpreter: ~/.venvs/general/bin/python3

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """
    A candidate regional hub facility in the freight network.

    Physical grounding
    ------------------
    Each Node corresponds to a real or proxy location identified from the
    CoStar industrial property database (Task 4) or from Task 2 interface
    node CSVs.  Attributes are named to mirror the paper's hub-selection
    criteria (§2.3): proximity to interstates / rail, available floor area,
    and freight throughput demand.

    Attributes
    ----------
    fac_id : str
        Unique facility identifier (e.g. CoStar property ID, or a
        constructed key like ``"FIPS42101-001"`` for proxy locations).
    county_fips : int
        5-digit FIPS code of the host county.  Links this node back to
        the O-D demand in ``Data/Task1/raw.parquet``.
    lon : float
        WGS-84 longitude of the facility centroid (decimal degrees).
    lat : float
        WGS-84 latitude of the facility centroid (decimal degrees).
    area_sqft : float
        Available leasable/usable floor area in square feet.
        Gateway-hub threshold: ≥ 20,000 ft² (§2.5); regional hubs are
        screened by throughput rather than a hard area floor, but area
        remains a tiebreaker.
    demand_ton_2025 : float
        County-level peak daily demand (thousand short tons, 2025)
        attributed to this node.  Derived from ``raw.parquet`` truck flows
        after applying the TTI × TMC peak-day factor.
    demand_ton_2030 : float
        Same metric for the 2030 forecast year.
    node_type : str
        Physical category of the facility.  Expected values:
        ``"warehouse"``, ``"truck_terminal"``, ``"distribution_center"``,
        ``"manufacturing"``, ``"proxy"`` (open land / in-construction),
        ``"seaport"``, ``"cargo_airport"``, ``"border_crossing"``,
        ``"external_domestic_hub"``.
    interface_class : Optional[str]
        Interface tier if this node was drawn from Task 2 outputs:
        ``"global"``, ``"continental"``, ``"national"``, or ``None`` for
        purely internal regional hubs.
    near_interstate : bool
        True when the facility is within a project-defined buffer of an
        interstate highway (default buffer = 5 miles; set during Task 4
        screening).
    near_rail : bool
        True when the facility is within a project-defined buffer of an
        active Class I railroad.
    region_id : Optional[int]
        Region cluster assignment (populated after Task 3 clustering).
        ``None`` until the node is assigned to a region.
    selected : bool
        True when this node has been chosen as an active regional hub by
        the set-cover / optimization step in Task 5.  Defaults to False.
    """

    fac_id: str
    county_fips: int
    lon: float
    lat: float
    area_sqft: float
    demand_ton_2025: float
    demand_ton_2030: float
    node_type: str
    interface_class: Optional[str] = None
    near_interstate: bool = False
    near_rail: bool = False
    region_id: Optional[int] = None
    selected: bool = False

    # ------------------------------------------------------------------
    # Derived geometry helpers
    # ------------------------------------------------------------------

    @property
    def coords(self) -> np.ndarray:
        """Return ``[lon, lat]`` as a float64 numpy array.

        Use this when entering the compute layer (e.g. feeding a distance
        matrix computation with scipy.spatial).
        """
        return np.array([self.lon, self.lat], dtype=np.float64)

    @property
    def demand_growth_pct(self) -> float:
        """Percentage demand growth from 2025 to 2030.

        Returns 0.0 if 2025 demand is zero (avoids ZeroDivisionError for
        proxy nodes with no current attributed demand).
        """
        if self.demand_ton_2025 == 0.0:
            return 0.0
        return (self.demand_ton_2030 - self.demand_ton_2025) / self.demand_ton_2025 * 100.0

    def __repr__(self) -> str:
        status = "SELECTED" if self.selected else "candidate"
        return (
            f"Node({self.fac_id} | fips={self.county_fips} | "
            f"{self.demand_ton_2025:,.1f} kton-2025 | {status})"
        )


# ---------------------------------------------------------------------------
# Link
# ---------------------------------------------------------------------------

@dataclass
class Link:
    """
    A directed freight corridor connecting two regional hub nodes.

    Physical grounding
    ------------------
    Links encode the operational relationship between two hubs: how long
    it takes a truck to travel between them, and how much freight actually
    flows along that corridor.  The 5.5-hour travel-time constraint from
    §2.3 is enforced at NetworkManager level, but stored here for
    transparency and sanity checks.

    Attributes
    ----------
    origin : Node
        The upstream hub (departure end of the link).
    dest : Node
        The downstream hub (arrival end of the link).
    travel_time_h : float
        Door-to-door truck travel time in hours (from HERE / Google Maps
        API or a highway-network shortest-path model).  Must satisfy
        travel_time_h ≤ 5.5 for the link to be admissible in the regional
        hub network.
    distance_km : float
        Great-circle or road-network distance in kilometres.  Kept
        alongside travel_time_h because the flow assignment objective
        (Task 8) minimizes total miles, not total time.
    flow_ton_2025 : float
        Assigned freight flow (thousand short tons, 2025) on this link
        after Task 8 flow assignment.  Zero until assignment is run.
    flow_ton_2030 : float
        Same for 2030.
    highway_corridor : Optional[str]
        Primary interstate corridor for this link (e.g. ``"I-95"``,
        ``"I-78"``).  Used in Task 7 map annotations and Task 9 synthesis.
    """

    origin: Node
    dest: Node
    travel_time_h: float
    distance_km: float
    flow_ton_2025: float = 0.0
    flow_ton_2030: float = 0.0
    highway_corridor: Optional[str] = None

    @property
    def is_admissible(self) -> bool:
        """True when travel time satisfies the ≤ 5.5 h regional hub constraint (§2.3)."""
        return self.travel_time_h <= 5.5

    def __repr__(self) -> str:
        return (
            f"Link({self.origin.fac_id} → {self.dest.fac_id} | "
            f"{self.travel_time_h:.2f}h | {self.distance_km:.1f}km | "
            f"{self.flow_ton_2025:,.1f} kton-2025)"
        )


# ---------------------------------------------------------------------------
# NetworkManager
# ---------------------------------------------------------------------------

class NetworkManager:
    """
    Container and operator for the full regional hub network.

    Physical grounding
    ------------------
    The NetworkManager mirrors the megaregion freight network as a whole:
    a set of candidate/selected hub nodes connected by truck-travel links.
    It owns the set-cover hub selection logic (Task 5), the travel-time
    feasibility checks (§2.3), and the graph-level queries (shortest path,
    coverage) needed for Tasks 5–7.

    Internally, nodes and links are stored in Python lists for readability.
    Before any heavy computation (distance matrix, shortest path, set-cover
    solver), the NetworkManager converts them to numpy arrays / scipy sparse
    structures at the data-layer boundary defined in the Coder skill.

    Attributes
    ----------
    nodes : list[Node]
        All candidate regional hub nodes loaded from Task 4 CoStar screening
        and Task 2 interface node CSVs.
    links : list[Link]
        All directed hub-to-hub links with travel time ≤ 5.5 h.
    _node_index : dict[str, int]
        Internal mapping from fac_id → list position, used to O(1)-look up
        nodes when constructing the adjacency matrix.
    """

    def __init__(self) -> None:
        self.nodes: list[Node] = []
        self.links: list[Link] = []
        self._node_index: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Register a candidate hub node.

        Raises
        ------
        ValueError
            If a node with the same fac_id is already registered (prevents
            silent duplicates from CoStar data re-loads).
        """
        if node.fac_id in self._node_index:
            raise ValueError(
                f"Node '{node.fac_id}' already registered in the network."
            )
        self._node_index[node.fac_id] = len(self.nodes)
        self.nodes.append(node)

    def add_link(self, link: Link, enforce_constraint: bool = True) -> None:
        """Register a directed hub-to-hub link.

        Parameters
        ----------
        link : Link
            The link to add.  Both ``link.origin`` and ``link.dest`` must
            already be registered via :meth:`add_node`.
        enforce_constraint : bool
            When True (default), raises ValueError if the link's travel
            time exceeds the 5.5-hour regional hub constraint (§2.3).
            Pass False only during exploratory analysis to retain all
            candidate links before pruning.

        Raises
        ------
        ValueError
            If either endpoint is not registered, or if the travel time
            constraint is violated (when enforce_constraint=True).
        """
        for endpoint in (link.origin, link.dest):
            if endpoint.fac_id not in self._node_index:
                raise ValueError(
                    f"Node '{endpoint.fac_id}' not in network. "
                    "Call add_node() first."
                )
        if enforce_constraint and not link.is_admissible:
            raise ValueError(
                f"Link {link.origin.fac_id} → {link.dest.fac_id} "
                f"has travel_time_h={link.travel_time_h:.2f} > 5.5h constraint."
            )
        self.links.append(link)

    def get_node(self, fac_id: str) -> Node:
        """Return the node with the given facility ID.

        Raises
        ------
        KeyError
            If fac_id is not registered.
        """
        idx = self._node_index[fac_id]
        return self.nodes[idx]

    # ------------------------------------------------------------------
    # Numpy boundary — enter compute layer
    # ------------------------------------------------------------------

    def coords_array(self) -> np.ndarray:
        """Return (N, 2) float64 array of [lon, lat] for all nodes.

        Use this to compute the pairwise distance / travel-time matrix
        with scipy.spatial or a road-network API before building links.

        Example
        -------
        >>> coords = network.coords_array()
        >>> from scipy.spatial.distance import cdist
        >>> gc_dist = cdist(coords, coords, metric="euclidean")
        """
        return np.array([n.coords for n in self.nodes], dtype=np.float64)

    def demand_vector(self, year: int = 2025) -> np.ndarray:
        """Return (N,) float64 array of node demand for the given year.

        Parameters
        ----------
        year : int
            Forecast year.  Supported: 2025, 2030.

        Raises
        ------
        ValueError
            If year is not 2025 or 2030.
        """
        if year == 2025:
            return np.array([n.demand_ton_2025 for n in self.nodes], dtype=np.float64)
        elif year == 2030:
            return np.array([n.demand_ton_2030 for n in self.nodes], dtype=np.float64)
        else:
            raise ValueError(f"Unsupported year {year}. Use 2025 or 2030.")

    def adjacency_matrix(self) -> np.ndarray:
        """Return (N, N) float64 travel-time matrix for existing links.

        Unconnected pairs are filled with ``np.inf``.  Diagonal is 0.
        This matrix is the primary input to the shortest-path solver
        (scipy.sparse.csgraph.shortest_path or networkx).
        """
        n = len(self.nodes)
        mat = np.full((n, n), np.inf, dtype=np.float64)
        np.fill_diagonal(mat, 0.0)
        for link in self.links:
            i = self._node_index[link.origin.fac_id]
            j = self._node_index[link.dest.fac_id]
            mat[i, j] = link.travel_time_h
        return mat

    # ------------------------------------------------------------------
    # Hub selection helpers
    # ------------------------------------------------------------------

    def selected_nodes(self) -> list[Node]:
        """Return all nodes where node.selected is True."""
        return [n for n in self.nodes if n.selected]

    def coverage_check(self, max_travel_h: float = 5.5) -> bool:
        """Check whether every node can reach at least one selected hub
        within max_travel_h using the current link set.

        This is the coverage feasibility test for the set-cover result.
        Uses a BFS/Dijkstra over the adjacency matrix.

        Parameters
        ----------
        max_travel_h : float
            Maximum admissible travel time to a hub.  Defaults to the
            5.5 h regional hub constraint (§2.3).

        Returns
        -------
        bool
            True if every node is within max_travel_h of at least one
            selected hub.  False otherwise — indicates the current hub
            selection leaves uncovered demand.
        """
        from scipy.sparse.csgraph import shortest_path
        from scipy.sparse import csr_matrix

        if not self.selected_nodes():
            return False

        adj = self.adjacency_matrix()
        # Replace inf with 0 for sparse representation — scipy handles this
        sparse_adj = csr_matrix(np.where(np.isinf(adj), 0, adj))
        dist_matrix = shortest_path(sparse_adj, directed=True, unweighted=False)

        selected_idx = [
            self._node_index[n.fac_id] for n in self.selected_nodes()
        ]
        # For each node, find minimum distance to any selected hub
        for i in range(len(self.nodes)):
            min_dist = min(dist_matrix[i, j] for j in selected_idx)
            if min_dist > max_travel_h:
                return False
        return True

    def shortest_path(
        self, origin_id: str, dest_id: str
    ) -> tuple[float, list[str]]:
        """Return the shortest travel-time path between two nodes.

        Parameters
        ----------
        origin_id : str
            fac_id of the origin node.
        dest_id : str
            fac_id of the destination node.

        Returns
        -------
        total_time_h : float
            Minimum travel time in hours.  ``np.inf`` if unreachable.
        path_ids : list[str]
            Ordered list of fac_ids along the shortest path.
            Empty list if unreachable.
        """
        import networkx as nx

        G = nx.DiGraph()
        for link in self.links:
            G.add_edge(
                link.origin.fac_id,
                link.dest.fac_id,
                weight=link.travel_time_h,
            )
        try:
            path_ids = nx.shortest_path(
                G, source=origin_id, target=dest_id, weight="weight"
            )
            total_time_h = nx.shortest_path_length(
                G, source=origin_id, target=dest_id, weight="weight"
            )
            return total_time_h, path_ids
        except nx.NetworkXNoPath:
            return np.inf, []

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> None:
        """Print a human-readable network snapshot for sanity checking."""
        n_selected = len(self.selected_nodes())
        admissible = sum(1 for lk in self.links if lk.is_admissible)
        print(
            f"NetworkManager summary\n"
            f"  Nodes         : {len(self.nodes):>6}  ({n_selected} selected as hubs)\n"
            f"  Links         : {len(self.links):>6}  ({admissible} admissible ≤ 5.5h)\n"
            f"  2025 demand   : {self.demand_vector(2025).sum():>10,.1f} kton\n"
            f"  2030 demand   : {self.demand_vector(2030).sum():>10,.1f} kton\n"
        )

    def __repr__(self) -> str:
        return (
            f"NetworkManager("
            f"{len(self.nodes)} nodes, "
            f"{len(self.links)} links, "
            f"{len(self.selected_nodes())} selected hubs)"
        )
```

---

## Design notes

### Why these attributes and not others?

| Attribute | Why it belongs here |
|---|---|
| `Node.county_fips` | Direct join key back to `raw.parquet` for demand attribution |
| `Node.area_sqft` | Gateway-hub threshold (≥ 20,000 ft²) and regional-hub tiebreaker (§2.5) |
| `Node.demand_ton_2025/2030` | Throughput sizing for both forecast years (§2.3) |
| `Node.near_interstate`, `Node.near_rail` | Primary infrastructure-proximity screening criteria (§2.3) |
| `Node.interface_class` | Distinguishes Task 2 interface nodes (global/continental/national) from internal regional hubs — needed for Task 7 multi-tier integration |
| `Link.travel_time_h` | The 5.5 h admissibility gate lives here (§2.3) |
| `Link.distance_km` | Flow assignment objective (Task 8) minimizes total miles — needs road distance, not time |
| `Link.highway_corridor` | Task 7 map annotation and Task 9 synthesis narrative |
| `NetworkManager.adjacency_matrix()` | Returns numpy array — clean entry to the compute layer for scipy shortest-path and set-cover formulations |

### Data-layer boundary pattern (Coder skill §2)

```python
# pandas → numpy  (loading boundary)
df = pd.read_csv("Data/Task2/task2_global_interface_nodes_final.csv")
# ... build Node objects ...
coords = network.coords_array()          # enter numpy compute layer

# numpy → pandas  (output boundary)
result_df = pd.DataFrame({
    "fac_id":    [n.fac_id for n in network.selected_nodes()],
    "lon":       [n.lon    for n in network.selected_nodes()],
    "lat":       [n.lat    for n in network.selected_nodes()],
    "demand_ton_2025": [n.demand_ton_2025 for n in network.selected_nodes()],
})
result_df.to_csv("Data/Task5/selected_regional_hubs.csv", index=False)
```

### Serialization pattern (Coder skill §4)

```python
from pathlib import Path
import joblib

CACHE_DIR = Path("Data/Task5")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Save the whole manager (nodes + links + selection state)
joblib.dump(network, CACHE_DIR / "network_manager.pkl")

# Save just the adjacency matrix for fast re-load in solver cells
np.save(CACHE_DIR / "adjacency_matrix.npy", network.adjacency_matrix())
```

### Sanity checks to run after populating the network

```python
# After loading all candidate nodes
assert len(network.nodes) > 0, "No nodes loaded — check CoStar / Task2 CSV paths"
assert all(n.demand_ton_2025 >= 0 for n in network.nodes), \
    "Negative demand on one or more nodes — check O-D join"

# After building links
inadmissible = [lk for lk in network.links if not lk.is_admissible]
assert len(inadmissible) == 0, \
    f"{len(inadmissible)} links exceed 5.5h constraint — prune before set-cover"

# After set-cover selection
assert 0 < len(network.selected_nodes()) <= len(network.nodes), \
    "Hub selection returned empty or full set — check solver feasibility"
covered = network.coverage_check(max_travel_h=5.5)
assert covered, "Set-cover result leaves uncovered demand — relax k or re-run"

network.summary()
```

---

## Milestone gate (pending)

Once the network is populated and sanity checks pass, present:

```
Subtask complete: Task 5 — Node / Link / NetworkManager class definitions
Outputs saved:   [no files yet — skeleton only; populate in next cells]
Sanity checks:   [to be run after data loading in subsequent cells]

Proceed with commit? (y/n)
```
