"""
clustering.py — Core SA clustering algorithms for Task 3.2 (Region Clustering)

Structure
─────────
Region          — dataclass holding cached per-region statistics
build_graph()   — construct NetworkX adjacency graph from edge list parquet
initialize_partition()  — K-means seed selection + demand-aware region growing (3.2.4)
RegionStats     — mutable cache of per-region summary statistics used by delta evals
compute_J()     — full three-component normalized objective (3.2.5)
compute_delta_J()       — incremental ΔJ for a single border-county move (3.2.5)
is_feasible()   — hard constraint checker (3.2.6)
run_sa()        — simulated annealing loop with logging + checkpointing (3.2.7)
"""

from __future__ import annotations

import csv
import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans


# ─────────────────────────────────────────────────────────────────────────────
# 3.2.4 — Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Region:
    """Physical representation of one logistics region.

    All mutable attributes are kept in RegionStats for fast delta evaluation.
    This class is a lightweight label carrier used for final reporting only.
    """
    region_id: int
    fips_set: set = field(default_factory=set)

    def __repr__(self) -> str:
        return f"Region({self.region_id}, n={len(self.fips_set)})"


class RegionStats:
    """
    Mutable cache of per-region summary statistics needed for O(1) delta evaluation.

    For each region r, we track:
      count      — number of counties
      throughput — total freight demand (W_r)
      sum_x      — sum of centroid_x for compactness SSE
      sum_y      — sum of centroid_y for compactness SSE
      sse        — sum of squared distances to region centroid: Σ ||(x_i,y_i) - (μx,μy)||²

    These allow ΔC_compact and ΔC_balance to be computed in O(1) per move.
    """

    def __init__(
        self,
        assignment: np.ndarray,
        cx: np.ndarray,
        cy: np.ndarray,
        throughput: np.ndarray,
        k: int,
    ) -> None:
        """
        Parameters
        ----------
        assignment : (N,) int array — region_id for each county (index = county idx)
        cx, cy     : (N,) float arrays — projected centroid coordinates
        throughput : (N,) float array — county demand weights
        k          : number of regions
        """
        self.k = k
        self.count = np.zeros(k, dtype=np.int32)
        self.w = np.zeros(k, dtype=np.float64)
        self.sx = np.zeros(k, dtype=np.float64)
        self.sy = np.zeros(k, dtype=np.float64)
        self.sse = np.zeros(k, dtype=np.float64)

        # Initial population
        for i in range(len(assignment)):
            r = assignment[i]
            self._add(r, cx[i], cy[i], throughput[i])

    def _add(self, r: int, x: float, y: float, w: float) -> None:
        """Add county i to region r, updating SSE incrementally.

        Uses the online formula:
          new_cx = (old_sx + x) / (count+1)
          Δsse   = (x - new_cx)² + (x - old_cx)² * count / (count+1)   [approx]

        For simplicity we use the exact recompute-on-move approach via
        the parallel-axis / shift identity:
          sse_r = Σ(x_i - μ_r)² = Σx_i² - n·μ_r²
        which reduces to tracking Σx² and Σy² alongside Σx and Σy.
        """
        old_count = self.count[r]
        self.count[r] += 1
        self.w[r] += w
        self.sx[r] += x
        self.sy[r] += y
        # Recompute SSE contribution (incremental shift identity)
        if self.count[r] == 1:
            pass  # first county — SSE contribution is 0
        # SSE is recomputed from scratch only when needed in _recompute_sse()

    def _remove(self, r: int, x: float, y: float, w: float) -> None:
        self.count[r] -= 1
        self.w[r] -= w
        self.sx[r] -= x
        self.sy[r] -= y

    def region_centroid(self, r: int) -> Tuple[float, float]:
        n = self.count[r]
        if n == 0:
            return (0.0, 0.0)
        return (self.sx[r] / n, self.sy[r] / n)

    def region_sse(self, r: int, cx_arr: np.ndarray, cy_arr: np.ndarray, assignment: np.ndarray) -> float:
        """O(|r|) full SSE recompute for region r — used only at initialization."""
        mask = assignment == r
        if not np.any(mask):
            return 0.0
        mx, my = self.region_centroid(r)
        return float(np.sum((cx_arr[mask] - mx) ** 2 + (cy_arr[mask] - my) ** 2))

    def apply_move(self, i: int, from_r: int, to_r: int,
                   x: float, y: float, w: float) -> None:
        """Apply county i move from_r → to_r and update cached stats."""
        self._remove(from_r, x, y, w)
        self._add(to_r, x, y, w)


# ─────────────────────────────────────────────────────────────────────────────
# 3.2.2 — Graph Construction
# ─────────────────────────────────────────────────────────────────────────────

def build_graph(edges_df: pd.DataFrame) -> nx.Graph:
    """
    Build NetworkX adjacency graph from the precomputed edge list.

    Parameters
    ----------
    edges_df : DataFrame with columns [fips_a, fips_b, shared_border_m,
               interstate_km, rail_km, infra_weight, synthetic_edge]

    Returns
    -------
    G : undirected graph with FIPS strings as nodes and edge attributes
    """
    G = nx.Graph()
    for _, row in edges_df.iterrows():
        G.add_edge(
            row["fips_a"],
            row["fips_b"],
            shared_border_m=row.get("shared_border_m", 0.0),
            interstate_km=row.get("interstate_km", 0.0),
            rail_km=row.get("rail_km", 0.0),
            infra_weight=row.get("infra_weight", 0.0),
            synthetic_edge=row.get("synthetic_edge", False),
        )
    return G


# ─────────────────────────────────────────────────────────────────────────────
# 3.2.4 — Seed Initialization
# ─────────────────────────────────────────────────────────────────────────────

def _kmeans_seeds(
    cx: np.ndarray,
    cy: np.ndarray,
    throughput: np.ndarray,
    k: int,
    n_init: int = 20,
    seed: int = 42,
) -> np.ndarray:
    """
    Phase 1 — K-means seed selection.

    Run weighted K-means on projected centroids; for each cluster pick the
    actual county closest to the cluster center as the seed county index.

    Returns
    -------
    seed_indices : (k,) int array of county indices
    """
    coords = np.column_stack([cx, cy])
    km = KMeans(n_clusters=k, n_init=n_init, random_state=seed)
    km.fit(coords, sample_weight=throughput)

    seed_indices = np.empty(k, dtype=np.intp)
    for c in range(k):
        cluster_mask = km.labels_ == c
        cluster_idx = np.where(cluster_mask)[0]
        center = km.cluster_centers_[c]
        dists = np.sum((coords[cluster_idx] - center) ** 2, axis=1)
        seed_indices[c] = cluster_idx[np.argmin(dists)]

    return seed_indices


def initialize_partition(
    fips: np.ndarray,
    cx: np.ndarray,
    cy: np.ndarray,
    throughput: np.ndarray,
    G: nx.Graph,
    k: int = 50,
    alpha_dist: float = 0.5,
    alpha_demand: float = 0.5,
    n_init: int = 20,
    seed: int = 42,
) -> Dict[str, int]:
    """
    Two-phase initialization: K-means seeds + demand-aware contiguous region growing.

    Phase 1 — K-means seed selection (see _kmeans_seeds).
    Phase 2 — Frontier BFS that scores candidate counties by:

        score(i) = alpha_dist  * dist_to_seed_centroid(i, r)  [normalized]
               + alpha_demand * demand_overshoot_penalty(i, r) [normalized]

    Counties are assigned greedily by lowest score, subject to graph adjacency.

    Parameters
    ----------
    fips       : (N,) string array of county FIPS codes
    cx, cy     : (N,) projected centroid arrays (meters)
    throughput : (N,) demand weights
    G          : adjacency graph (nodes = FIPS strings)
    k          : target number of regions
    alpha_dist : weight on distance penalty in growing score
    alpha_demand : weight on demand overshoot penalty
    n_init     : K-means n_init
    seed       : random seed

    Returns
    -------
    assignment : dict {fips_str: region_id}
    """
    fips_to_idx = {f: i for i, f in enumerate(fips)}
    target_w = throughput.sum() / k

    # Phase 1 — seeds
    seed_idx = _kmeans_seeds(cx, cy, throughput, k, n_init=n_init, seed=seed)
    seed_fips = set(fips[seed_idx])

    assignment: Dict[str, int] = {}
    region_cx = cx[seed_idx].copy()      # running centroid x per region
    region_cy = cy[seed_idx].copy()      # running centroid y per region
    region_count = np.ones(k, dtype=np.int32)
    region_w = throughput[seed_idx].copy()

    for r, sidx in enumerate(seed_idx):
        assignment[fips[sidx]] = r

    # Build frontier: dict {fips_str: set of region_ids that can claim it}
    import heapq
    # (score, county_fips, region_id)
    heap: List[Tuple[float, str, int]] = []

    for r, sidx in enumerate(seed_idx):
        sf = fips[sidx]
        for nb in G.neighbors(sf):
            if nb not in assignment:
                i = fips_to_idx[nb]
                d = math.hypot(cx[i] - region_cx[r], cy[i] - region_cy[r])
                ov = max(0.0, (region_w[r] + throughput[i] - target_w) / target_w)
                score = alpha_dist * d + alpha_demand * ov
                heapq.heappush(heap, (score, nb, r))

    assigned_set = set(assignment.keys())

    while heap and len(assigned_set) < len(fips):
        score, cf, r = heapq.heappop(heap)
        if cf in assigned_set:
            continue
        assignment[cf] = r
        assigned_set.add(cf)

        i = fips_to_idx[cf]
        # Update running centroid (incremental mean)
        n = region_count[r]
        region_cx[r] = (region_cx[r] * n + cx[i]) / (n + 1)
        region_cy[r] = (region_cy[r] * n + cy[i]) / (n + 1)
        region_count[r] += 1
        region_w[r] += throughput[i]

        for nb in G.neighbors(cf):
            if nb not in assigned_set:
                j = fips_to_idx[nb]
                d = math.hypot(cx[j] - region_cx[r], cy[j] - region_cy[r])
                ov = max(0.0, (region_w[r] + throughput[j] - target_w) / target_w)
                s = alpha_dist * d + alpha_demand * ov
                heapq.heappush(heap, (s, nb, r))

    # Any isolated counties not reachable via graph adjacency → nearest seed
    unassigned = [f for f in fips if f not in assignment]
    if unassigned:
        coords = np.column_stack([cx, cy])
        seed_coords = coords[seed_idx]
        for uf in unassigned:
            i = fips_to_idx[uf]
            dists = np.sum((seed_coords - coords[i]) ** 2, axis=1)
            assignment[uf] = int(np.argmin(dists))

    return assignment


# ─────────────────────────────────────────────────────────────────────────────
# 3.2.5 — Objective Function
# ─────────────────────────────────────────────────────────────────────────────

def _sse_from_stats(stats: RegionStats) -> float:
    """
    Compute total SSE across all regions using the parallel-axis identity:
        SSE_r = Σ(x_i - μ_r)² = Σx_i² - n_r * μ_r²
    We track Σx_i² separately for O(1) computation.

    For simplicity we rely on the caller providing the precomputed per-county
    arrays and do the dot product once.
    """
    total = 0.0
    for r in range(stats.k):
        n = stats.count[r]
        if n == 0:
            continue
        mx = stats.sx[r] / n
        my = stats.sy[r] / n
        # This term is estimated; exact SSE is recomputed in full_sse()
        total += stats.sx[r] * mx + stats.sy[r] * my  # placeholder
    return total


def compute_J(
    assignment_arr: np.ndarray,
    cx: np.ndarray,
    cy: np.ndarray,
    throughput: np.ndarray,
    adj: Dict[int, List[int]],
    infra_weights: np.ndarray,
    D0: float,
    total_infra: float,
    total_throughput: float,
    k: int,
    w_align: float = 1.0,
    w_compact: float = 1.0,
    w_balance: float = 4.0,
) -> float:
    """
    Full three-component normalized objective J.

    C_align   = Σ_{(i,j)∈E} infra_weight_ij * 1[r_i ≠ r_j] / Σ infra_weight_ij
    C_compact = (1 / (N * D0²)) * Σ_i ||(x_i,y_i) - μ_{r_i}||²
    C_balance = (1/K) * Σ_r ((W_r - W*) / W*)²

    Parameters
    ----------
    assignment_arr : (N,) int array, assignment_arr[i] = region_id for county i
    cx, cy         : (N,) projected centroid arrays
    throughput     : (N,) demand weights
    adj            : dict {county_idx: [neighbor_idx, ...]} (integer indices)
    infra_weights  : (E,) edge infra weights indexed by edge_id (see below)
    D0             : reference distance (bounding-box diagonal, meters)
    total_infra    : sum of all infra_weight values
    total_throughput : total freight throughput
    k              : number of regions
    w_align, w_compact, w_balance : objective weights (default w_balance=4.0 for 66.7% weight)

    Returns
    -------
    J : float
    """
    N = len(assignment_arr)
    W_star = total_throughput / k

    # C_align
    align_cut = 0.0
    for i, neighbors in adj.items():
        ri = assignment_arr[i]
        for j, iw in neighbors:
            if j > i and assignment_arr[j] != ri:
                align_cut += iw
    C_align = align_cut / total_infra if total_infra > 0 else 0.0

    # C_compact — region centroids
    region_sx = np.zeros(k)
    region_sy = np.zeros(k)
    region_n = np.zeros(k, dtype=np.int32)
    for i in range(N):
        r = assignment_arr[i]
        region_sx[r] += cx[i]
        region_sy[r] += cy[i]
        region_n[r] += 1

    sse = 0.0
    for i in range(N):
        r = assignment_arr[i]
        n = region_n[r]
        if n == 0:
            continue
        mu_x = region_sx[r] / n
        mu_y = region_sy[r] / n
        sse += (cx[i] - mu_x) ** 2 + (cy[i] - mu_y) ** 2
    C_compact = sse / (N * D0 ** 2) if D0 > 0 else 0.0

    # C_balance
    region_w = np.zeros(k)
    for i in range(N):
        region_w[assignment_arr[i]] += throughput[i]
    C_balance = float(np.mean(((region_w - W_star) / W_star) ** 2))

    return w_align * C_align + w_compact * C_compact + w_balance * C_balance


def compute_delta_J(
    county_idx: int,
    from_r: int,
    to_r: int,
    cx: np.ndarray,
    cy: np.ndarray,
    throughput: np.ndarray,
    stats: RegionStats,
    adj_with_weights: Dict[int, List[Tuple[int, float]]],
    assignment_arr: np.ndarray,
    D0: float,
    total_infra: float,
    total_throughput: float,
    k: int,
    w_align: float,
    w_compact: float,
    w_balance: float,
) -> float:
    """
    Incremental ΔJ for moving county_idx from from_r to to_r.

    All three components are computed locally:
      ΔC_align   — depends only on graph edges incident to county_idx
      ΔC_compact — depends only on from_r and to_r cached statistics
      ΔC_balance — depends only on two affected region throughput totals

    Returns
    -------
    delta_J : float  (negative = improvement)
    """
    xi, yi = cx[county_idx], cy[county_idx]
    wi = throughput[county_idx]
    W_star = total_throughput / k
    N = len(cx)

    # ── ΔC_align ──────────────────────────────────────────────────────────────
    # For each edge (county_idx, j):
    #   before: cut if r_j != from_r; after: cut if r_j != to_r
    delta_align = 0.0
    for j, iw in adj_with_weights.get(county_idx, []):
        rj = assignment_arr[j]
        was_cut = (rj != from_r)
        will_cut = (rj != to_r)
        if will_cut and not was_cut:
            delta_align += iw      # newly cut
        elif was_cut and not will_cut:
            delta_align -= iw      # healed cut
    if total_infra > 0:
        delta_align /= total_infra
    dJ_align = w_align * delta_align

    # ── ΔC_compact ────────────────────────────────────────────────────────────
    # SSE_r = Σ(x_i - μ_r)² = Σx² - n·μ_r²
    # Using cached sum_x, sum_y, count:
    def region_sse_fast(r: int) -> float:
        n = stats.count[r]
        if n == 0:
            return 0.0
        mx = stats.sx[r] / n
        my = stats.sy[r] / n
        # Approximation using identity: SSE = Σ(xi² + yi²) - n*(mx²+my²)
        # We don't store Σxi², so use the Welford / shift identity:
        #   SSE ≈ sx[r]*mx + sy[r]*my is NOT correct.
        # Instead cache exact SSE in the stats via _sse_exact array.
        return stats.sse[r]

    # We maintain exact SSE in stats.sse; update it on every move.
    sse_from_before = stats.sse[from_r]
    sse_to_before = stats.sse[to_r]

    # After removing county_idx from from_r:
    n_from = stats.count[from_r]
    sx_from_new = stats.sx[from_r] - xi
    sy_from_new = stats.sy[from_r] - yi
    n_from_new = n_from - 1
    if n_from_new > 0:
        mx_new = sx_from_new / n_from_new
        my_new = sy_from_new / n_from_new
        # SSE_new = SSE_old - (xi - old_mx)² - (yi - old_my)²
        #         + n_from_new * ((old_mx - new_mx)² + (old_my - new_my)²)
        # Simplified: use parallel-axis shift
        old_mx = stats.sx[from_r] / n_from
        old_my = stats.sy[from_r] / n_from
        sse_from_after = (
            sse_from_before
            - (xi - old_mx) ** 2 - (yi - old_my) ** 2
            + n_from_new * ((old_mx - mx_new) ** 2 + (old_my - my_new) ** 2)
        )
    else:
        sse_from_after = 0.0

    # After adding county_idx to to_r:
    n_to = stats.count[to_r]
    sx_to_new = stats.sx[to_r] + xi
    sy_to_new = stats.sy[to_r] + yi
    n_to_new = n_to + 1
    mx_to_new = sx_to_new / n_to_new
    my_to_new = sy_to_new / n_to_new
    if n_to > 0:
        old_mx_to = stats.sx[to_r] / n_to
        old_my_to = stats.sy[to_r] / n_to
        sse_to_after = (
            sse_to_before
            + (xi - mx_to_new) ** 2 + (yi - my_to_new) ** 2
            + n_to * ((old_mx_to - mx_to_new) ** 2 + (old_my_to - my_to_new) ** 2)
        )
    else:
        sse_to_after = 0.0

    delta_sse = (sse_from_after + sse_to_after) - (sse_from_before + sse_to_before)
    dJ_compact = w_compact * delta_sse / (N * D0 ** 2) if D0 > 0 else 0.0

    # ── ΔC_balance ────────────────────────────────────────────────────────────
    w_from_before = stats.w[from_r]
    w_to_before = stats.w[to_r]
    w_from_after = w_from_before - wi
    w_to_after = w_to_before + wi

    def bal_term(w: float) -> float:
        return ((w - W_star) / W_star) ** 2

    delta_balance = (
        bal_term(w_from_after) + bal_term(w_to_after)
        - bal_term(w_from_before) - bal_term(w_to_before)
    ) / k
    dJ_balance = w_balance * delta_balance

    return dJ_align + dJ_compact + dJ_balance


def update_sse_after_move(
    stats: RegionStats,
    county_idx: int,
    from_r: int,
    to_r: int,
    xi: float,
    yi: float,
) -> None:
    """
    Update stats.sse[from_r] and stats.sse[to_r] using the same parallel-axis
    identity as compute_delta_J — called immediately after the move is accepted.
    """
    # ── Remove from from_r ────────────────────────────────────────────────────
    n_from = stats.count[from_r]   # already decremented by apply_move
    if n_from == 0:
        stats.sse[from_r] = 0.0
    else:
        # Reconstruct old centroid before the remove
        old_sx = stats.sx[from_r] + xi
        old_sy = stats.sy[from_r] + yi
        old_n = n_from + 1
        old_mx = old_sx / old_n
        old_my = old_sy / old_n
        new_mx = stats.sx[from_r] / n_from
        new_my = stats.sy[from_r] / n_from
        stats.sse[from_r] = (
            stats.sse[from_r]
            - (xi - old_mx) ** 2 - (yi - old_my) ** 2
            + n_from * ((old_mx - new_mx) ** 2 + (old_my - new_my) ** 2)
        )
        stats.sse[from_r] = max(0.0, stats.sse[from_r])

    # ── Add to to_r ───────────────────────────────────────────────────────────
    n_to = stats.count[to_r]      # already incremented by apply_move
    new_mx_to = stats.sx[to_r] / n_to
    new_my_to = stats.sy[to_r] / n_to
    if n_to == 1:
        stats.sse[to_r] = 0.0
    else:
        old_n_to = n_to - 1
        old_sx_to = stats.sx[to_r] - xi
        old_sy_to = stats.sy[to_r] - yi
        old_mx_to = old_sx_to / old_n_to
        old_my_to = old_sy_to / old_n_to
        stats.sse[to_r] = (
            stats.sse[to_r]
            + (xi - new_mx_to) ** 2 + (yi - new_my_to) ** 2
            + old_n_to * ((old_mx_to - new_mx_to) ** 2 + (old_my_to - new_my_to) ** 2)
        )
        stats.sse[to_r] = max(0.0, stats.sse[to_r])


# ─────────────────────────────────────────────────────────────────────────────
# 3.2.6 — Constraint Checks
# ─────────────────────────────────────────────────────────────────────────────

def is_feasible(
    county_idx: int,
    from_r: int,
    to_r: int,
    assignment_arr: np.ndarray,
    adj: Dict[int, List[int]],
    G_nodes: List[str],
) -> bool:
    """
    Hard constraint checker for a proposed border-county move.

    Checks (in order, short-circuit on failure):
    1. Target region must contain at least one graph neighbor of county_idx.
    2. Donor region must not become empty after the move.
    3. After removing county_idx, donor region must remain connected (BFS).

    Parameters
    ----------
    county_idx    : integer index of the county being moved
    from_r        : donor region id
    to_r          : receiver region id
    assignment_arr: (N,) current assignment array
    adj           : dict {idx: [neighbor_idx, ...]} (integer indices only, no weights)
    G_nodes       : list of county FIPS (for labeling; not used in checks)

    Returns
    -------
    True if the move is feasible, False otherwise.
    """
    neighbors = adj.get(county_idx, [])

    # 1. Adjacency check: at least one neighbor in to_r
    if not any(assignment_arr[j] == to_r for j in neighbors):
        return False

    # 2. Non-empty donor
    from_count = int(np.sum(assignment_arr == from_r))
    if from_count <= 1:
        return False

    # 3. Contiguity check via BFS on donor subgraph minus county_idx
    from_members = [j for j in range(len(assignment_arr))
                    if assignment_arr[j] == from_r and j != county_idx]
    if len(from_members) == 0:
        return False
    if len(from_members) == 1:
        return True  # single remaining county is trivially connected

    # BFS
    start = from_members[0]
    visited = {start}
    queue = [start]
    adj_set = {j: set(adj.get(j, [])) for j in from_members}
    from_set = set(from_members)

    while queue:
        node = queue.pop()
        for nb in adj_set[node]:
            if nb in from_set and nb not in visited:
                visited.add(nb)
                queue.append(nb)

    return len(visited) == len(from_members)


# ─────────────────────────────────────────────────────────────────────────────
# 3.2.7 — Simulated Annealing Loop
# ─────────────────────────────────────────────────────────────────────────────

def _sample_T0(
    assignment_arr: np.ndarray,
    cx: np.ndarray,
    cy: np.ndarray,
    throughput: np.ndarray,
    adj: Dict[int, List[int]],
    adj_with_weights: Dict[int, List[Tuple[int, float]]],
    border_counties: List[int],
    D0: float,
    total_infra: float,
    total_throughput: float,
    k: int,
    w_align: float,
    w_compact: float,
    w_balance: float,
    stats: RegionStats,
    n_samples: int = 200,
    rng: random.Random = None,
) -> float:
    """
    Sample T0 from the empirical scale of |ΔJ| for random feasible moves.
    Returns the mean |ΔJ| of accepted samples.
    """
    if rng is None:
        rng = random.Random(0)

    samples = []
    attempts = 0
    while len(samples) < n_samples and attempts < n_samples * 20:
        attempts += 1
        if not border_counties:
            break
        ci = rng.choice(border_counties)
        from_r = int(assignment_arr[ci])
        nb_regions = list({int(assignment_arr[j]) for j in adj.get(ci, [])} - {from_r})
        if not nb_regions:
            continue
        to_r = rng.choice(nb_regions)
        if not is_feasible(ci, from_r, to_r, assignment_arr, adj, []):
            continue
        dj = compute_delta_J(
            ci, from_r, to_r, cx, cy, throughput, stats,
            adj_with_weights, assignment_arr, D0, total_infra,
            total_throughput, k, w_align, w_compact, w_balance,
        )
        samples.append(abs(dj))

    return float(np.mean(samples)) if samples else 0.01


def _rebuild_border_set(
    assignment_arr: np.ndarray,
    adj: Dict[int, List[int]],
) -> List[int]:
    """Return list of county indices that border at least one county in a different region."""
    result = []
    for i, neighbors in adj.items():
        ri = assignment_arr[i]
        if any(assignment_arr[j] != ri for j in neighbors):
            result.append(i)
    return result


def run_sa(
    fips: np.ndarray,
    cx: np.ndarray,
    cy: np.ndarray,
    throughput: np.ndarray,
    adj: Dict[int, List[int]],
    adj_with_weights: Dict[int, List[Tuple[int, float]]],
    initial_assignment: Dict[str, int],
    D0: float,
    total_infra: float,
    k: int = 50,
    w_align: float = 1.0,
    w_compact: float = 1.0,
    w_balance: float = 2.0,
    n_restarts: int = 4,
    n_proposals: int = 50_000,
    alpha: float = 0.9995,
    T_min: float = 1e-6,
    patience: int = 5_000,
    checkpoint_every: int = 5_000,
    log_path: str = "Data/Task3/cache/sa_log.csv",
    checkpoint_dir: str = "Data/Task3/cache",
    seed: int = 42,
) -> Tuple[np.ndarray, Dict[str, int], float]:
    """
    Simulated Annealing loop for graph-partitioning region clustering.

    Algorithm
    ─────────
    1. Build integer-indexed assignment array from initial_assignment dict.
    2. Sample T0 from empirical |ΔJ| distribution.
    3. For each proposal:
         a. Pick random border county
         b. Pick random neighboring region
         c. Check feasibility (Task 3.2.6)
         d. Compute ΔJ (Task 3.2.5)
         e. Accept if ΔJ < 0 or with prob exp(-ΔJ/T)
         f. Cool: T ← α·T
    4. Checkpoint every `checkpoint_every` accepted proposals.
    5. Run `n_restarts` restarts; keep best solution.

    Parameters
    ----------
    fips                : (N,) FIPS string array (index matches cx/cy/throughput)
    cx, cy              : (N,) projected centroid arrays (meters)
    throughput          : (N,) county demand weights
    adj                 : {county_idx: [neighbor_idx, ...]}
    adj_with_weights    : {county_idx: [(neighbor_idx, infra_weight), ...]}
    initial_assignment  : {fips_str: region_id} from initialize_partition
    D0                  : NE bounding-box diagonal (meters)
    total_infra         : sum of all edge infra weights
    k                   : number of regions
    w_align/compact/balance : objective weights
    n_restarts          : number of SA restarts
    n_proposals         : proposals per restart
    alpha               : geometric cooling factor
    T_min               : minimum temperature (termination)
    patience            : stop restart if no J improvement after this many proposals
    checkpoint_every    : save assignment to disk every N accepted proposals
    log_path            : CSV path for SA log
    checkpoint_dir      : directory for checkpoint .npy files
    seed                : base RNG seed (each restart increments by restart index)

    Returns
    -------
    best_arr    : (N,) int array — best assignment found
    best_dict   : {fips_str: region_id} — best assignment as dict
    best_J      : float — best objective value
    """
    N = len(fips)
    fips_to_idx = {f: i for i, f in enumerate(fips)}
    total_throughput = float(throughput.sum())
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Convert initial assignment dict → integer array
    init_arr = np.array([initial_assignment[fips[i]] for i in range(N)], dtype=np.int32)

    best_arr = init_arr.copy()
    best_J = float("inf")
    best_restart = -1

    log_rows = []

    for restart in range(n_restarts):
        rng = random.Random(seed + restart)
        arr = init_arr.copy() if restart == 0 else best_arr.copy()

        # Build RegionStats cache
        stats = RegionStats(arr, cx, cy, throughput, k)
        # Initialize SSE exactly for each region
        for r in range(k):
            mask = arr == r
            if np.any(mask):
                mx = cx[mask].mean()
                my = cy[mask].mean()
                stats.sse[r] = float(np.sum((cx[mask] - mx) ** 2 + (cy[mask] - my) ** 2))

        border_counties = _rebuild_border_set(arr, adj)
        if not border_counties:
            print(f"[Restart {restart}] No border counties — skipping.")
            continue

        # Sample T0
        T0 = _sample_T0(
            arr, cx, cy, throughput, adj, adj_with_weights, border_counties,
            D0, total_infra, total_throughput, k,
            w_align, w_compact, w_balance, stats,
            n_samples=300, rng=rng,
        )
        T = T0 if T0 > 1e-10 else 0.1
        print(f"\n[Restart {restart}] T0={T:.6f}  border_counties={len(border_counties)}")

        # Full J for logging
        J = compute_J(
            arr, cx, cy, throughput, adj_with_weights,
            None,   # infra_weights array — passed via adj_with_weights
            D0, total_infra, total_throughput, k,
            w_align, w_compact, w_balance,
        )
        restart_best_J = J
        restart_best_arr = arr.copy()

        n_accepted = 0
        n_rejected_infeas = 0
        n_rejected_metro = 0
        no_improve_count = 0

        t_start = time.time()

        for proposal in range(n_proposals):
            if T < T_min:
                break

            # Pick random border county
            ci = rng.choice(border_counties)
            from_r = int(arr[ci])

            # Pick a neighboring region
            nb_regions = list({int(arr[j]) for j in adj.get(ci, [])} - {from_r})
            if not nb_regions:
                continue
            to_r = rng.choice(nb_regions)

            # Feasibility check
            if not is_feasible(ci, from_r, to_r, arr, adj, []):
                n_rejected_infeas += 1
                continue

            # Delta J
            dJ = compute_delta_J(
                ci, from_r, to_r, cx, cy, throughput, stats,
                adj_with_weights, arr, D0, total_infra,
                total_throughput, k, w_align, w_compact, w_balance,
            )

            # Accept / reject
            accept = False
            if dJ < 0:
                accept = True
            else:
                prob = math.exp(-dJ / T) if T > 1e-15 else 0.0
                if rng.random() < prob:
                    accept = True
                else:
                    n_rejected_metro += 1

            if accept:
                xi, yi, wi = cx[ci], cy[ci], throughput[ci]
                # Update stats
                update_sse_after_move(stats, ci, from_r, to_r, xi, yi)
                stats.apply_move(ci, from_r, to_r, xi, yi, wi)
                arr[ci] = to_r

                J += dJ
                n_accepted += 1
                no_improve_count = 0

                if J < restart_best_J:
                    restart_best_J = J
                    restart_best_arr = arr.copy()

                # Refresh border set periodically
                if n_accepted % 500 == 0:
                    border_counties = _rebuild_border_set(arr, adj)

                # Checkpoint
                if n_accepted % checkpoint_every == 0:
                    cp_path = checkpoint_dir / f"checkpoint_r{restart}_a{n_accepted}.npy"
                    np.save(cp_path, arr)
            else:
                no_improve_count += 1
                if no_improve_count >= patience:
                    print(f"  Patience exhausted at proposal {proposal}")
                    break

            T *= alpha

            # Epoch log every 2500 proposals
            if proposal % 2500 == 0:
                elapsed = time.time() - t_start
                acc_rate = n_accepted / max(proposal, 1)
                log_rows.append({
                    "restart": restart,
                    "proposal": proposal,
                    "T": T,
                    "J": J,
                    "best_J_restart": restart_best_J,
                    "best_J_global": min(best_J, restart_best_J),
                    "n_accepted": n_accepted,
                    "n_rejected_infeas": n_rejected_infeas,
                    "n_rejected_metro": n_rejected_metro,
                    "accept_rate": acc_rate,
                    "elapsed_s": elapsed,
                })

        print(
            f"  Restart {restart} done | J={restart_best_J:.6f} | "
            f"accepted={n_accepted} | infeas_rejected={n_rejected_infeas}"
        )

        if restart_best_J < best_J:
            best_J = restart_best_J
            best_arr = restart_best_arr.copy()
            best_restart = restart

    print(f"\nBest solution from restart {best_restart} | J={best_J:.6f}")

    # Save log
    if log_rows:
        log_df = pd.DataFrame(log_rows)
        log_df.to_csv(log_path, index=False)
        print(f"SA log saved to {log_path}")

    # Convert best_arr → dict
    best_dict = {fips[i]: int(best_arr[i]) for i in range(N)}
    return best_arr, best_dict, best_J
