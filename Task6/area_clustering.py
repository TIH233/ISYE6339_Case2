"""
area_clustering.py — Simulated Annealing area clustering for Task 6 Phase 1

Areas are geographic groupings for gateway hub siting only.  They do NOT require
balanced demand across areas — Phase 2's Set-Cover MIP scales hub count to each
area's own freight demand independently.

Objective: compact + spread (travel-time) only.  The population-balance term
(C_balance) present in the Task 3 region-clustering module has been removed
because cross-area equity is not a design requirement at this tier.

Structure
─────────
AreaStats           — mutable cache for per-area statistics
build_region_graph  — construct NetworkX subgraph for counties within one region
initialize_area_partition — maximin seed selection + BFS growing
compute_J_area      — two-component objective (compact + spread)
compute_delta_J_area — incremental ΔJ for a single county move
is_feasible_area    — hard constraint checker (adjacency + non-empty + contiguity)
run_sa_area         — SA loop for one region
run_all_regions     — outer loop: iterate 50 regions, serialize cache
"""

from __future__ import annotations

import csv
import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

class AreaStats:
    """
    Mutable cache of per-area summary statistics used by move evaluation.
    
    For each area a in region r:
      count   — number of counties
      pop     — total population
      sum_x   — sum of centroid_x (EPSG:9311 meters)
      sum_y   — sum of centroid_y
      sse     — sum of squared distances to area centroid
    
    Population is retained for initialization diagnostics, but the SA objective
    has no balance term.  ΔC_compact and ΔC_spread are recomputed on the two
    affected areas for accuracy; areas are small enough that this is cheap.
    """
    
    def __init__(
        self, 
        assignment: np.ndarray,
        cx: np.ndarray,
        cy: np.ndarray,
        pop: np.ndarray,
        k: int
    ) -> None:
        """
        Parameters
        ----------
        assignment : (N,) int array — area_id for each county (local index)
        cx, cy     : (N,) float arrays — projected centroid coords (EPSG:9311)
        pop        : (N,) float array — county populations
        k          : number of areas in this region
        """
        self.k = k
        self.count = np.zeros(k, dtype=np.int32)
        self.pop = np.zeros(k, dtype=np.float64)
        self.sx = np.zeros(k, dtype=np.float64)
        self.sy = np.zeros(k, dtype=np.float64)
        self.sse = np.zeros(k, dtype=np.float64)
        
        # Initial population
        for i in range(len(assignment)):
            a = assignment[i]
            self._add(a, cx[i], cy[i], pop[i])
    
    def _add(self, a: int, x: float, y: float, p: float) -> None:
        self.count[a] += 1
        self.pop[a] += p
        self.sx[a] += x
        self.sy[a] += y
    
    def _remove(self, a: int, x: float, y: float, p: float) -> None:
        self.count[a] -= 1
        self.pop[a] -= p
        self.sx[a] -= x
        self.sy[a] -= y
    
    def area_centroid(self, a: int) -> Tuple[float, float]:
        n = self.count[a]
        if n == 0:
            return (0.0, 0.0)
        return (self.sx[a] / n, self.sy[a] / n)
    
    def area_sse(self, a: int, cx_arr: np.ndarray, cy_arr: np.ndarray, 
                  assignment: np.ndarray) -> float:
        """O(|a|) full SSE recompute for area a."""
        mask = assignment == a
        if not np.any(mask):
            return 0.0
        mx, my = self.area_centroid(a)
        return float(np.sum((cx_arr[mask] - mx)**2 + (cy_arr[mask] - my)**2))
    
    def apply_move(self, i: int, from_a: int, to_a: int,
                   x: float, y: float, p: float) -> None:
        """Apply county i move from_a → to_a and update cached stats."""
        self._remove(from_a, x, y, p)
        self._add(to_a, x, y, p)


# ─────────────────────────────────────────────────────────────────────────────
# Graph Construction
# ─────────────────────────────────────────────────────────────────────────────

def build_region_graph(fips_list: List[str], edges_df: pd.DataFrame) -> nx.Graph:
    """
    Build NetworkX subgraph for counties within one region.
    
    Parameters
    ----------
    fips_list : list of FIPS strings in the region
    edges_df  : full NE county edge list with columns [fips_a, fips_b, ...]
    
    Returns
    -------
    G : undirected graph with FIPS strings as nodes
    """
    fips_set = set(fips_list)
    sub_edges = edges_df[
        edges_df['fips_a'].isin(fips_set) & 
        edges_df['fips_b'].isin(fips_set)
    ]
    
    G = nx.Graph()
    for _, row in sub_edges.iterrows():
        G.add_edge(row['fips_a'], row['fips_b'])
    
    # Ensure all counties are nodes (even islands)
    for f in fips_list:
        if f not in G:
            G.add_node(f)
    
    return G


# ─────────────────────────────────────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────────────────────────────────────

def _maximin_seeds(
    cx: np.ndarray,
    cy: np.ndarray,
    k: int,
    seed: int = 42
) -> np.ndarray:
    """
    Phase 1 — Maximin seed selection.
    
    Iteratively choose k counties by maximum geographic spread:
    - First seed: random
    - Each subsequent seed: farthest from all previously chosen seeds
    
    Returns
    -------
    seed_indices : (k,) int array of county indices
    """
    np.random.seed(seed)
    n = len(cx)
    
    if k == 1:
        return np.array([np.random.randint(n)])
    
    coords = np.column_stack([cx, cy])
    seed_idx = [np.random.randint(n)]
    
    for _ in range(k - 1):
        # Compute min distance to any existing seed
        min_dists = np.full(n, np.inf)
        for sidx in seed_idx:
            dists = np.linalg.norm(coords - coords[sidx], axis=1)
            min_dists = np.minimum(min_dists, dists)
        
        # Exclude already-selected counties
        for sidx in seed_idx:
            min_dists[sidx] = -np.inf
        
        # Pick county with max min-distance
        next_seed = np.argmax(min_dists)
        seed_idx.append(next_seed)
    
    return np.array(seed_idx)


def initialize_area_partition(
    fips: np.ndarray,
    cx: np.ndarray,
    cy: np.ndarray,
    pop: np.ndarray,
    G: nx.Graph,
    k: int,
    p_target: float,
    alpha_dist: float = 0.5,
    alpha_balance: float = 0.5,
    seed: int = 42
) -> Dict[str, int]:
    """
    Two-phase initialization: maximin seeds + BFS growing.
    
    Phase 1 — Maximin seed selection (see _maximin_seeds).
    Phase 2 — Frontier BFS that scores candidate counties by:
    
        score(i, a) = alpha_dist * dist(i, centroid_a) 
                    + alpha_balance * max(0, (pop_a + pop_i - p_target) / p_target)
    
    Parameters
    ----------
    fips     : (N,) string array of county FIPS codes (local to region)
    cx, cy   : (N,) projected centroid arrays (meters, EPSG:9311)
    pop      : (N,) population weights
    G        : adjacency graph (nodes = FIPS strings)
    k        : target number of areas
    p_target : target population per area
    alpha_dist, alpha_balance : scoring weights
    seed     : random seed
    
    Returns
    -------
    assignment : dict {fips_str: area_id}
    """
    fips_to_idx = {f: i for i, f in enumerate(fips)}
    
    # Phase 1 — seeds
    seed_idx = _maximin_seeds(cx, cy, k, seed=seed)
    
    assignment: Dict[str, int] = {}
    area_cx = cx[seed_idx].copy()
    area_cy = cy[seed_idx].copy()
    area_count = np.ones(k, dtype=np.int32)
    area_pop = pop[seed_idx].copy()
    
    for a, sidx in enumerate(seed_idx):
        assignment[fips[sidx]] = a
    
    # Build frontier heap
    import heapq
    heap: List[Tuple[float, str, int]] = []
    
    for a, sidx in enumerate(seed_idx):
        sf = fips[sidx]
        for nb in G.neighbors(sf):
            if nb not in assignment:
                i = fips_to_idx[nb]
                d = math.hypot(cx[i] - area_cx[a], cy[i] - area_cy[a])
                overshoot = max(0.0, (area_pop[a] + pop[i] - p_target) / p_target)
                score = alpha_dist * d + alpha_balance * overshoot
                heapq.heappush(heap, (score, nb, a))
    
    assigned_set = set(assignment.keys())
    
    while heap and len(assigned_set) < len(fips):
        score, cf, a = heapq.heappop(heap)
        if cf in assigned_set:
            continue
        assignment[cf] = a
        assigned_set.add(cf)
        
        i = fips_to_idx[cf]
        # Update running centroid (unweighted mean)
        n = area_count[a]
        area_cx[a] = (area_cx[a] * n + cx[i]) / (n + 1)
        area_cy[a] = (area_cy[a] * n + cy[i]) / (n + 1)
        area_count[a] += 1
        area_pop[a] += pop[i]
        
        for nb in G.neighbors(cf):
            if nb not in assigned_set:
                j = fips_to_idx[nb]
                d = math.hypot(cx[j] - area_cx[a], cy[j] - area_cy[a])
                overshoot = max(0.0, (area_pop[a] + pop[j] - p_target) / p_target)
                score = alpha_dist * d + alpha_balance * overshoot
                heapq.heappush(heap, (score, nb, a))
    
    # Handle islands (counties with no neighbors in region)
    unassigned = set(fips) - assigned_set
    if unassigned:
        coords = np.column_stack([cx, cy])
        assigned_idx = [fips_to_idx[f] for f in assigned_set]
        assigned_coords = coords[assigned_idx]
        
        for cf in unassigned:
            i = fips_to_idx[cf]
            dists = np.linalg.norm(assigned_coords - coords[i], axis=1)
            nearest_local_idx = np.argmin(dists)
            nearest_fips = list(assigned_set)[nearest_local_idx]
            assignment[cf] = assignment[nearest_fips]
    
    return assignment


# ─────────────────────────────────────────────────────────────────────────────
# Objective Function
# ─────────────────────────────────────────────────────────────────────────────

def compute_J_area(
    stats: AreaStats,
    assignment: np.ndarray,
    cx: np.ndarray,
    cy: np.ndarray,
    D_r: float,
    exempt_from_spread: bool,
    w_compact: float = 1.0,
    w_spread: float = 2.0
) -> float:
    """
    Two-component normalized objective for area clustering.

    J = w_compact * C_compact + w_spread * C_spread

    C_compact = (1/(N*D²)) Σ_a Σ_{i∈a} ||(x_i, y_i) - μ_a||²
    C_spread  = (1/k) Σ_a max(0, (d_max_a - 80mi)/80mi)²  [non-exempt only]

    C_balance has been intentionally removed.  Areas are geographic groupings for
    gateway hub siting; Phase 2 scales hub count per area to its own freight demand
    independently, so cross-area population equity is not a design requirement.

    Parameters
    ----------
    stats : AreaStats instance with current assignment
    assignment : (N,) int array of area assignments
    cx, cy : (N,) centroid coordinates
    D_r : bounding-box diagonal of region (meters)
    exempt_from_spread : if True, C_spread = 0 (large-span regions)
    w_compact, w_spread : component weights

    Returns
    -------
    J : scalar objective value
    """
    k = stats.k
    N = len(assignment)

    # C_compact — geographic SSE
    total_sse = 0.0
    for a in range(k):
        if stats.count[a] == 0:
            continue
        total_sse += stats.area_sse(a, cx, cy, assignment)

    if D_r > 0 and N > 0:
        C_compact = total_sse / (N * D_r**2)
    else:
        C_compact = 0.0

    # C_spread — distance penalty (non-exempt only)
    if exempt_from_spread:
        C_spread = 0.0
    else:
        spread_sq = 0.0
        for a in range(k):
            mask = assignment == a
            if not np.any(mask):
                continue
            coords_a = np.column_stack([cx[mask], cy[mask]])
            if len(coords_a) < 2:
                continue
            from scipy.spatial.distance import pdist
            dists = pdist(coords_a, metric='euclidean')
            if len(dists) > 0:
                d_max_m = dists.max()
                d_max_mi = d_max_m / 1609.34
                excess = max(0.0, d_max_mi - 80.0)
                spread_sq += (excess / 80.0)**2
        C_spread = spread_sq / k if k > 0 else 0.0

    J = w_compact * C_compact + w_spread * C_spread
    return J


def compute_delta_J_area(
    i: int,
    from_a: int,
    to_a: int,
    stats: AreaStats,
    assignment: np.ndarray,
    cx: np.ndarray,
    cy: np.ndarray,
    D_r: float,
    exempt_from_spread: bool,
    w_compact: float = 1.0,
    w_spread: float = 2.0
) -> float:
    """
    Incremental ΔJ for moving county i from from_a to to_a.

    C_spread is recomputed for the two affected areas (O(|area|) but areas are small).
    C_balance is not computed — removed from objective (see module docstring).

    Returns
    -------
    ΔJ : change in objective (positive = worse, negative = better)
    """
    k = stats.k
    N = len(assignment)

    # ── ΔC_compact ──────────────────────────────────────────────────────────
    # From area — direct recompute for accuracy
    n_from = stats.count[from_a]
    if n_from == 1:
        delta_sse_from = 0.0  # area becomes empty (blocked upstream by non-empty check)
    else:
        sse_from_old = stats.area_sse(from_a, cx, cy, assignment)
        temp_assignment = assignment.copy()
        temp_assignment[i] = to_a
        mask = temp_assignment == from_a
        if np.any(mask):
            mx_new = cx[mask].mean()
            my_new = cy[mask].mean()
            sse_from_new = float(np.sum((cx[mask] - mx_new)**2 + (cy[mask] - my_new)**2))
        else:
            sse_from_new = 0.0
        delta_sse_from = sse_from_new - sse_from_old

    # To area
    n_to = stats.count[to_a]
    if n_to == 0:
        delta_sse_to = 0.0
    else:
        sse_to_old = stats.area_sse(to_a, cx, cy, assignment)
        temp_assignment = assignment.copy()
        temp_assignment[i] = to_a
        mask = temp_assignment == to_a
        mx_new = cx[mask].mean()
        my_new = cy[mask].mean()
        sse_to_new = float(np.sum((cx[mask] - mx_new)**2 + (cy[mask] - my_new)**2))
        delta_sse_to = sse_to_new - sse_to_old

    delta_sse = delta_sse_from + delta_sse_to
    if D_r > 0 and N > 0:
        delta_C_compact = delta_sse / (N * D_r**2)
    else:
        delta_C_compact = 0.0

    # ── ΔC_spread (recompute for affected areas) ────────────────────────────
    if exempt_from_spread:
        delta_C_spread = 0.0
    else:
        def area_spread_penalty(area_id: int, temp_assignment: np.ndarray) -> float:
            mask = temp_assignment == area_id
            if not np.any(mask) or mask.sum() < 2:
                return 0.0
            coords_a = np.column_stack([cx[mask], cy[mask]])
            from scipy.spatial.distance import pdist
            dists = pdist(coords_a, metric='euclidean')
            if len(dists) == 0:
                return 0.0
            d_max_m = dists.max()
            d_max_mi = d_max_m / 1609.34
            excess = max(0.0, d_max_mi - 80.0)
            return (excess / 80.0)**2

        old_spread_from = area_spread_penalty(from_a, assignment)
        old_spread_to = area_spread_penalty(to_a, assignment)

        temp_assignment = assignment.copy()
        temp_assignment[i] = to_a
        new_spread_from = area_spread_penalty(from_a, temp_assignment)
        new_spread_to = area_spread_penalty(to_a, temp_assignment)

        delta_C_spread = ((new_spread_from - old_spread_from +
                           new_spread_to - old_spread_to) / k) if k > 0 else 0.0

    delta_J = w_compact * delta_C_compact + w_spread * delta_C_spread
    return delta_J


# ─────────────────────────────────────────────────────────────────────────────
# Feasibility Checks
# ─────────────────────────────────────────────────────────────────────────────

def is_feasible_area(
    i: int,
    from_a: int,
    to_a: int,
    assignment: np.ndarray,
    fips: np.ndarray,
    G: nx.Graph,
    stats: AreaStats
) -> bool:
    """
    Check hard constraints for moving county i from from_a to to_a.

    1. Adjacency  : i must border at least one county in to_a
    2. Non-empty  : from_a must not be emptied
    3. Contiguity : from_a must remain connected after removal

    The population-floor constraint (constraint 4 in the original formulation)
    has been removed.  Areas are gateway-hub groupings; no minimum population
    per area is required — Phase 2 handles hub viability independently.

    Returns
    -------
    bool : True if move is feasible
    """
    cf = fips[i]

    # 1. Adjacency
    neighbors_in_to = [nb for nb in G.neighbors(cf)
                       if nb in fips and assignment[np.where(fips == nb)[0][0]] == to_a]
    if not neighbors_in_to:
        return False

    # 2. Non-empty donor
    if stats.count[from_a] <= 1:
        return False

    # 3. Contiguity
    from_a_fips = fips[assignment == from_a]
    from_a_fips_after = [f for f in from_a_fips if f != cf]
    if len(from_a_fips_after) == 0:
        return False

    subgraph = G.subgraph(from_a_fips_after)
    if not nx.is_connected(subgraph):
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Simulated Annealing
# ─────────────────────────────────────────────────────────────────────────────

def run_sa_area(
    region_id: int,
    fips: np.ndarray,
    cx: np.ndarray,
    cy: np.ndarray,
    pop: np.ndarray,
    G: nx.Graph,
    k: int,
    p_target: float,
    D_r: float,
    exempt_from_spread: bool,
    alpha: float = 0.998,
    n_proposals: int = 5000,
    patience: int = 2000,
    n_restarts: int = 2,
    seed: int = 42,
    verbose: bool = True
) -> Tuple[np.ndarray, float, List[Dict]]:
    """
    Run SA area clustering for one region.

    Objective: compact + spread only (no balance term).
    Feasibility: adjacency + non-empty + contiguity only (no population floor).

    Parameters
    ----------
    region_id : int region identifier
    fips, cx, cy, pop : (N,) arrays for counties in this region
        pop is used only for BFS initialization scoring, not for SA feasibility
    G : NetworkX graph for this region
    k : number of areas to create
    p_target : population target per area (BFS initialization only)
    D_r : bounding-box diagonal (meters)
    exempt_from_spread : if True, skip spread penalty
    alpha : cooling rate
    n_proposals : number of move proposals
    patience : early stop if no improvement
    n_restarts : number of SA restarts
    seed : random seed
    verbose : print progress

    Returns
    -------
    best_assignment : (N,) int array
    best_J : scalar objective
    log : list of dicts with SA trajectory
    """
    random.seed(seed)
    np.random.seed(seed)

    # Handle trivial cases
    if k == 1:
        return np.zeros(len(fips), dtype=int), 0.0, []

    if len(fips) <= k:
        return np.arange(len(fips), dtype=int), 0.0, []

    # Build border set (counties with neighbors in different areas)
    def get_border_counties(assignment: np.ndarray) -> List[int]:
        border = []
        for i, cf in enumerate(fips):
            my_area = assignment[i]
            for nb in G.neighbors(cf):
                if nb in fips:
                    nb_idx = np.where(fips == nb)[0][0]
                    if assignment[nb_idx] != my_area:
                        border.append(i)
                        break
        return border

    # Temperature calibration — sample |ΔJ| from random feasible moves
    def sample_T0(n_samples: int = 200) -> float:
        init_assignment = initialize_area_partition(
            fips, cx, cy, pop, G, k, p_target, seed=seed
        )
        init_arr = np.array([init_assignment.get(f, 0) for f in fips])
        init_stats = AreaStats(init_arr, cx, cy, pop, k)

        deltas = []
        border = get_border_counties(init_arr)

        for _ in range(n_samples):
            if not border:
                break
            i = random.choice(border)
            cf = fips[i]
            from_a = init_arr[i]

            candidate_areas = set()
            for nb in G.neighbors(cf):
                if nb in fips:
                    nb_idx = np.where(fips == nb)[0][0]
                    candidate_areas.add(init_arr[nb_idx])
            candidate_areas.discard(from_a)

            if not candidate_areas:
                continue

            to_a = random.choice(list(candidate_areas))

            if is_feasible_area(i, from_a, to_a, init_arr, fips, G, init_stats):
                dJ = compute_delta_J_area(
                    i, from_a, to_a, init_stats, init_arr, cx, cy,
                    D_r, exempt_from_spread
                )
                deltas.append(abs(dJ))

        if len(deltas) < 10:
            return 1e-3
        return float(np.percentile(deltas, 75))

    T0 = sample_T0()

    global_best_assignment = None
    global_best_J = np.inf
    global_log: List[Dict] = []

    for restart in range(n_restarts):
        if verbose:
            print(f"  Restart {restart+1}/{n_restarts}...")

        init_assignment = initialize_area_partition(
            fips, cx, cy, pop, G, k, p_target,
            seed=seed + restart * 1000
        )
        assignment = np.array([init_assignment.get(f, 0) for f in fips])
        stats = AreaStats(assignment, cx, cy, pop, k)

        J = compute_J_area(stats, assignment, cx, cy, D_r, exempt_from_spread)

        best_assignment = assignment.copy()
        best_J = J

        T = T0
        accepted = 0
        no_improve = 0

        for step in range(n_proposals):
            border = get_border_counties(assignment)
            if not border:
                break

            i = random.choice(border)
            cf = fips[i]
            from_a = assignment[i]

            candidate_areas = set()
            for nb in G.neighbors(cf):
                if nb in fips:
                    nb_idx = np.where(fips == nb)[0][0]
                    candidate_areas.add(assignment[nb_idx])
            candidate_areas.discard(from_a)

            if not candidate_areas:
                continue

            to_a = random.choice(list(candidate_areas))

            if not is_feasible_area(i, from_a, to_a, assignment, fips, G, stats):
                continue

            dJ = compute_delta_J_area(
                i, from_a, to_a, stats, assignment, cx, cy,
                D_r, exempt_from_spread
            )

            if dJ < 0 or random.random() < math.exp(-dJ / T):
                assignment[i] = to_a
                stats.apply_move(i, from_a, to_a, cx[i], cy[i], pop[i])
                J += dJ
                accepted += 1

                if J < best_J:
                    best_J = J
                    best_assignment = assignment.copy()
                    no_improve = 0
                else:
                    no_improve += 1
            else:
                no_improve += 1

            T *= alpha

            if no_improve >= patience:
                if verbose:
                    print(f"    Early stop at step {step} (patience)")
                break

            if T < 1e-6:
                break

        if verbose:
            print(f"    Final J = {best_J:.6f} (accepted {accepted}/{n_proposals})")

        if best_J < global_best_J:
            global_best_J = best_J
            global_best_assignment = best_assignment.copy()

    return global_best_assignment, global_best_J, global_log


def run_all_regions(
    gdf: pd.DataFrame,
    edges_df: pd.DataFrame,
    region_info: pd.DataFrame,
    exempt_region_ids: set,
    cache_dir: Path,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Run SA area clustering for all 50 regions and save results.

    Parameters
    ----------
    gdf        : DataFrame with columns [fips, centroid_x, centroid_y, pop2020, region_id]
    edges_df   : DataFrame with edge list [fips_a, fips_b, ...]
    region_info: DataFrame with [region_id, region_type, n_counties, total_pop,
                 min_areas_effective].  p_min is no longer used.
    exempt_region_ids : set of region_ids exempt from spread penalty
    cache_dir  : Path to save checkpoints
    verbose    : print progress

    Returns
    -------
    area_assignment_df : DataFrame with columns [fips, region_id, area_id]
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    records = []

    for rid in sorted(region_info['region_id'].unique()):
        row = region_info[region_info.region_id == rid].iloc[0]
        k_r = int(row['min_areas_effective'])
        p_target = float(row['total_pop']) / k_r   # BFS init only, not a hard constraint
        n_counties = int(row['n_counties'])
        rtype = row['region_type']

        if verbose:
            print(f"Region {rid:2d} ({rtype}, n={n_counties:2d}, k={k_r})...", end=" ")

        # Extract region data
        gdf_r = gdf[gdf.region_id == rid].copy()
        fips_r = gdf_r['fips'].to_numpy()
        cx_r = gdf_r['centroid_x'].to_numpy()
        cy_r = gdf_r['centroid_y'].to_numpy()
        pop_r = gdf_r['pop2020'].to_numpy()

        # Build graph
        G_r = build_region_graph(list(fips_r), edges_df)

        # Bounding box diagonal
        x_min, x_max = cx_r.min(), cx_r.max()
        y_min, y_max = cy_r.min(), cy_r.max()
        D_r = math.hypot(x_max - x_min, y_max - y_min)

        exempt = rid in exempt_region_ids

        t0 = time.time()
        assignment, J, _ = run_sa_area(
            rid, fips_r, cx_r, cy_r, pop_r, G_r, k_r, p_target, D_r, exempt,
            n_proposals=max(5000, 800 * n_counties),
            verbose=False
        )
        elapsed = time.time() - t0

        for i, f in enumerate(fips_r):
            area_label = f"{rid}_{assignment[i]}"
            records.append({'fips': f, 'region_id': rid, 'area_id': area_label})

        if verbose:
            n_areas = len(set(assignment))
            print(f"{n_areas} areas, J={J:.4f}, {elapsed:.1f}s")

    return pd.DataFrame(records)
