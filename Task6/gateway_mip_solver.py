"""
Task 6 Phase 2 — Gateway Hub Selection MIP
===========================================
Capacity-aware set-cover MIP with separation constraints for gateway hub
selection.  Mirrors Task 5's mip_solver.py but operates at the area tier.

Key differences from Task 5 (mip_solver.py)
--------------------------------------------
- Units covered  : 132 areas  (not 50 regions)
- Coverage target: m_a ≥ 1 per area  (demand-scaled, not fixed ≥ 1)
- Separation     : co-area gateways must be ≥ 20 mi apart  (new constraint)
- No road-gate   : β pre-filter not applied

Formulation
-----------
Sets
    G   : gateway candidates  (indexed 0 … |G|-1)
    A   : areas               (indexed 0 … |A|-1)
    Z   : feasible (g, a) pairs — centroid dist ≤ 50 mi OR in-area county
    S   : separation clash triples (g, g', a) where dist(g,g') < 20 mi
          and both (g,a) and (g',a) are in Z

Variables
    A_ga ∈ {0,1}   gateway g is assigned to area a
    O_g  ∈ {0,1}   gateway g is opened

Objective
    minimize  ∑_{(g,a)∈Z}  A_ga · ĉ_ga

Constraints
    1. ∑_{g:(g,a)∈Z}  A_ga         ≥ m_a[a]   ∀a ∈ A   (coverage)
    2. ∑_{a:(g,a)∈Z}  A_ga         ≤ 2        ∀g ∈ G   (concentration cap)
    3. O_g                          ≤ ∑_a A_ga  ∀g ∈ G   (activation link)
    4. ∑_{g:(g,a)∈Z}  A_ga · s_g   ≥ RHS_a    ∀a ∈ A   (capacity)
    5. A_ga + A_{g'a}               ≤ 1        ∀(g,g',a) ∈ S (separation)

Classes
-------
GatewayMIPParameters   Immutable solver and model configuration.
GatewayMIPResult       Compact summary of the Gurobi solve outcome.
GatewayMIP             Builds, solves, and extracts the gateway-selection MIP.

Usage
-----
>>> from gateway_mip_solver import GatewayMIP, GatewayMIPParameters
>>> params = GatewayMIPParameters(time_limit=600, mip_gap=0.01)
>>> solver = GatewayMIP(G_arr, Z, c_hat, m_a, cap_rhs, s_g, S, params)
>>> solver.build()
>>> result = solver.solve()
>>> gw_df, assign_df = solver.extract_solution(G_df, area_ids)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import gurobipy as gp
    from gurobipy import GRB
except ImportError as exc:
    raise ImportError(
        "gurobipy is required for Task 6 Phase 2. "
        "Install via: conda install -c gurobi gurobi  "
        "or: pip install gurobipy"
    ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Domain objects
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GatewayMIPParameters:
    """
    Solver configuration for GatewayMIP.

    Attributes
    ----------
    time_limit : float
        Gurobi TimeLimit in seconds (default 600).
    mip_gap : float
        Relative MIP optimality gap at which the solver stops (default 0.01).
    output_flag : int
        1 = print Gurobi log to console; 0 = silent.
    concentration_cap : int
        Maximum number of areas a single gateway may serve (default 2).
    lazy_sep_threshold : int
        If |S| exceeds this, separation constraints are skipped in build() and
        a warning is printed; caller must add them manually via callback.
        Default 500_000.
    threads : int
        Number of solver threads; 0 = all available cores.
    """
    time_limit:           float = 600.0
    mip_gap:              float = 0.01
    output_flag:          int   = 1
    concentration_cap:    int   = 2
    lazy_sep_threshold:   int   = 500_000
    threads:              int   = 0


@dataclass
class GatewayMIPResult:
    """
    Summary of a completed Gurobi solve.

    Attributes
    ----------
    status : int
        Gurobi status code.
    status_name : str
        Human-readable status label.
    objective : float
        Primal objective value (∑ ĉ_ga · A_ga).
    mip_gap : float
        Relative gap at termination.
    solve_time : float
        Wall-clock seconds consumed by optimize().
    n_gateways_open : int
        Number of gateways opened (∃ area assigned).
    n_assignments : int
        Number of active (g, a) assignment pairs.
    open_g_idx : list[int]
        g_idx values of open gateways.
    assigned_pairs : list[tuple[int, int]]
        (g_idx, a_idx) pairs with A_ga = 1.
    """
    status:           int
    status_name:      str
    objective:        float
    mip_gap:          float
    solve_time:       float
    n_gateways_open:  int
    n_assignments:    int
    open_g_idx:       List[int]                  = field(default_factory=list)
    assigned_pairs:   List[Tuple[int, int]]      = field(default_factory=list)

    def is_feasible(self) -> bool:
        """True if a primal integer solution was found."""
        return self.n_gateways_open > 0


# ─────────────────────────────────────────────────────────────────────────────
# MIP solver class
# ─────────────────────────────────────────────────────────────────────────────

class GatewayMIP:
    """
    Capacity-aware set-cover MIP for gateway hub selection (Task 6 Phase 2).

    Parameters
    ----------
    G_arr : np.ndarray, shape (|G|,)
        Integer gateway indices — typically ``np.arange(len(G))``.
    Z : np.ndarray, shape (|Z|, 2), dtype int32
        Feasibility pairs; each row is ``[g_idx, a_idx]``.
    c_hat : np.ndarray, shape (|Z|,), dtype float64
        Objective cost coefficients aligned row-for-row with Z.
    m_a : np.ndarray, shape (|A|,), dtype int32
        Target gateway count per area; entry a_idx → m_a[a_idx].
    cap_rhs : np.ndarray, shape (|A|,), dtype float64
        Capacity constraint RHS per area (sqft), aligned to area_metrics row order.
    s_g : np.ndarray, shape (|G|,), dtype float64
        Usable floor area of each gateway candidate (sqft).
    S : list of (int, int, int)
        Separation clash triples (g_idx, g_prime_idx, a_idx) where
        dist(g, g') < 20 miles and both (g,a) and (g',a) are in Z.
    params : GatewayMIPParameters, optional
        Solver and model configuration.  Defaults applied if omitted.
    """

    def __init__(
        self,
        G_arr:    np.ndarray,
        Z:        np.ndarray,
        c_hat:    np.ndarray,
        m_a:      np.ndarray,
        cap_rhs:  np.ndarray,
        s_g:      np.ndarray,
        S:        List[Tuple[int, int, int]],
        params:   Optional[GatewayMIPParameters] = None,
    ) -> None:
        self.G_arr   = np.asarray(G_arr,   dtype=np.int64)
        self.Z       = np.asarray(Z,        dtype=np.int32)
        self.c_hat   = np.asarray(c_hat,    dtype=np.float64)
        self.m_a     = np.asarray(m_a,      dtype=np.int32)
        self.cap_rhs = np.asarray(cap_rhs,  dtype=np.float64)
        self.s_g     = np.asarray(s_g,      dtype=np.float64)
        self.S       = list(S)
        self.params  = params or GatewayMIPParameters()

        self._n_G = int(len(G_arr))
        self._n_A = int(len(cap_rhs))
        self._n_Z = int(len(Z))

        # Internal Gurobi objects (populated by build())
        self._model:  Optional[gp.Model]         = None
        self._A_var:  Optional[gp.tupledict]     = None   # z → Var
        self._O_var:  Optional[gp.tupledict]     = None   # g → Var
        self._z_by_a: Optional[List[List[int]]]  = None
        self._z_by_g: Optional[List[List[int]]]  = None

        # Solve result (populated by solve())
        self.result: Optional[GatewayMIPResult] = None

    # ── Model construction ────────────────────────────────────────────────────

    def build(self) -> None:
        """
        Assemble the Gurobi model: variables, objective, and all constraints.

        If |S| > params.lazy_sep_threshold, separation constraints are skipped
        with a printed warning.  Must be called before solve().
        """
        p = self.params
        m = gp.Model("GatewayMIP")

        # ── Solver parameters ─────────────────────────────────────────────────
        m.setParam("TimeLimit",  p.time_limit)
        m.setParam("MIPGap",     p.mip_gap)
        m.setParam("OutputFlag", p.output_flag)
        if p.threads > 0:
            m.setParam("Threads", p.threads)

        # ── Decision variables ────────────────────────────────────────────────
        # A_var[z] = A_{g,a} for each row z in Z
        A_var = m.addVars(self._n_Z, vtype=GRB.BINARY, name="A")
        # O_var[g] = O_g for each gateway g ∈ G
        O_var = m.addVars(self._n_G, vtype=GRB.BINARY, name="O")

        # ── Objective: minimize ∑_z  c_hat[z] · A_var[z] ─────────────────────
        m.setObjective(
            gp.quicksum(float(self.c_hat[z]) * A_var[z] for z in range(self._n_Z)),
            GRB.MINIMIZE,
        )

        # ── Index lookups ─────────────────────────────────────────────────────
        # z_by_a[a] : list of Z-row indices with a_idx == a
        z_by_a: List[List[int]] = [[] for _ in range(self._n_A)]
        # z_by_g[g] : list of Z-row indices with g_idx == g
        z_by_g: List[List[int]] = [[] for _ in range(self._n_G)]

        for z, (g, a) in enumerate(self.Z):
            z_by_a[a].append(z)
            z_by_g[g].append(z)

        # ── Constraint 1 — Coverage ───────────────────────────────────────────
        # ∑_{g:(g,a)∈Z} A_ga ≥ m_a[a]    ∀a
        for a in range(self._n_A):
            rows = z_by_a[a]
            if rows:
                m.addConstr(
                    gp.quicksum(A_var[z] for z in rows) >= int(self.m_a[a]),
                    name=f"coverage_a{a}",
                )

        # ── Constraint 2 — Concentration cap ─────────────────────────────────
        # ∑_{a:(g,a)∈Z} A_ga ≤ 2    ∀g
        for g in range(self._n_G):
            rows = z_by_g[g]
            if rows:
                m.addConstr(
                    gp.quicksum(A_var[z] for z in rows) <= p.concentration_cap,
                    name=f"conc_g{g}",
                )

        # ── Constraint 3 — Activation link ───────────────────────────────────
        # O_g ≤ ∑_{a:(g,a)∈Z} A_ga    ∀g
        for g in range(self._n_G):
            rows = z_by_g[g]
            if rows:
                m.addConstr(
                    O_var[g] <= gp.quicksum(A_var[z] for z in rows),
                    name=f"link_g{g}",
                )

        # ── Constraint 4 — Capacity coverage ─────────────────────────────────
        # ∑_{g:(g,a)∈Z} A_ga · s_g ≥ RHS_a    ∀a
        for a in range(self._n_A):
            rows = z_by_a[a]
            if rows:
                m.addConstr(
                    gp.quicksum(
                        float(self.s_g[self.Z[z, 0]]) * A_var[z] for z in rows
                    ) >= float(self.cap_rhs[a]),
                    name=f"capacity_a{a}",
                )

        # ── Constraint 5 — Separation ─────────────────────────────────────────
        # A_ga + A_{g'a} ≤ 1    ∀(g, g', a) ∈ S
        n_S = len(self.S)
        if n_S > p.lazy_sep_threshold:
            print(
                f"WARNING: |S| = {n_S:,} exceeds lazy_sep_threshold "
                f"({p.lazy_sep_threshold:,}). "
                "Separation constraints skipped — add via callback if needed."
            )
        else:
            # Build lookup: (g_idx, a_idx) → z-row index for fast access
            ga_to_z: dict = {}
            for z, (g, a) in enumerate(self.Z):
                ga_to_z[(int(g), int(a))] = z

            for k, (g, g_prime, a) in enumerate(self.S):
                z1 = ga_to_z.get((g, a))
                z2 = ga_to_z.get((g_prime, a))
                if z1 is not None and z2 is not None:
                    m.addConstr(
                        A_var[z1] + A_var[z2] <= 1,
                        name=f"sep_{g}_{g_prime}_a{a}",
                    )

        m.update()

        # Store references
        self._model  = m
        self._A_var  = A_var
        self._O_var  = O_var
        self._z_by_a = z_by_a
        self._z_by_g = z_by_g

        sep_added = n_S if n_S <= p.lazy_sep_threshold else 0
        print(
            f"Model built — "
            f"{m.NumVars:,} variables  "
            f"{m.NumConstrs:,} constraints  "
            f"{m.NumNZs:,} non-zeros  "
            f"({sep_added:,} separation constraints)"
        )

    # ── Solve ─────────────────────────────────────────────────────────────────

    def solve(self) -> GatewayMIPResult:
        """
        Run Gurobi's branch-and-cut and store the result.

        Returns
        -------
        GatewayMIPResult
            Summary object; also stored as self.result.
        """
        if self._model is None:
            raise RuntimeError("Call build() before solve().")

        t0 = time.perf_counter()
        self._model.optimize()
        elapsed = time.perf_counter() - t0

        m     = self._model
        A_var = self._A_var

        status_map = {
            GRB.OPTIMAL:     "OPTIMAL",
            GRB.TIME_LIMIT:  "TIME_LIMIT",
            GRB.INFEASIBLE:  "INFEASIBLE",
            GRB.INF_OR_UNBD: "INF_OR_UNBD",
            GRB.UNBOUNDED:   "UNBOUNDED",
        }
        status_name = status_map.get(m.Status, f"STATUS_{m.Status}")

        # No integer solution available
        if m.Status not in (GRB.OPTIMAL, GRB.TIME_LIMIT) or m.SolCount == 0:
            self.result = GatewayMIPResult(
                status=m.Status,
                status_name=status_name,
                objective=float("inf"),
                mip_gap=float("inf"),
                solve_time=elapsed,
                n_gateways_open=0,
                n_assignments=0,
            )
            return self.result

        # Extract active (g, a) assignments
        assigned = [
            (int(self.Z[z, 0]), int(self.Z[z, 1]))
            for z in range(self._n_Z)
            if A_var[z].X > 0.5
        ]
        # Derive open gateways from assignments
        # (O_var has no objective cost; derive from A_var to be robust)
        open_g = sorted({g for g, a in assigned})

        self.result = GatewayMIPResult(
            status=m.Status,
            status_name=status_name,
            objective=m.ObjVal,
            mip_gap=m.MIPGap,
            solve_time=elapsed,
            n_gateways_open=len(open_g),
            n_assignments=len(assigned),
            open_g_idx=open_g,
            assigned_pairs=assigned,
        )
        return self.result

    # ── Solution extraction ───────────────────────────────────────────────────

    def extract_solution(
        self,
        G: pd.DataFrame,
        area_ids: np.ndarray,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Build output DataFrames from the stored solve result.

        Parameters
        ----------
        G : pd.DataFrame
            Gateway candidate table (``G_candidates.parquet``).
            Required columns: ``g_idx``, ``candidate_id``, ``facility_name``,
            ``city``, ``source_state``, ``latitude``, ``longitude``,
            ``usable_available_space_sf``.
        area_ids : np.ndarray, shape (|A|,)
            Area ID strings in row order (e.g. ["0_0", "1_0", ...]).

        Returns
        -------
        selected_gw_df : pd.DataFrame
            One row per open gateway with characterisation columns and
            ``areas_served`` (list of area_id strings) and
            ``n_areas_served``.
        assignments_df : pd.DataFrame
            One row per active (gateway, area) assignment with gateway
            metadata and cost coefficient ``c_hat``.
        """
        if self.result is None:
            raise RuntimeError("Call solve() before extract_solution().")
        if not self.result.is_feasible():
            raise RuntimeError(
                f"No feasible solution found (status={self.result.status_name})."
            )

        res = self.result
        Z   = self.Z
        c   = self.c_hat

        # ── assignments table ─────────────────────────────────────────────────
        assign_rows = []
        for g_idx, a_idx in res.assigned_pairs:
            z_pos = np.where((Z[:, 0] == g_idx) & (Z[:, 1] == a_idx))[0]
            c_val = float(c[z_pos[0]]) if len(z_pos) else float("nan")
            assign_rows.append({
                "g_idx":   g_idx,
                "a_idx":   a_idx,
                "area_id": str(area_ids[a_idx]),
                "c_hat":   c_val,
            })
        assignments_df = pd.DataFrame(assign_rows)

        # Join gateway metadata onto assignments
        meta_cols = [
            "g_idx", "candidate_id", "facility_name", "city", "source_state",
            "latitude", "longitude", "usable_available_space_sf",
        ]
        assignments_df = assignments_df.merge(G[meta_cols], on="g_idx", how="left")

        # ── areas served per gateway ──────────────────────────────────────────
        areas_per_gw = (
            assignments_df.groupby("g_idx")["area_id"]
            .apply(list)
            .reset_index()
            .rename(columns={"area_id": "areas_served"})
        )

        # ── selected gateways table ───────────────────────────────────────────
        selected_gw_df = (
            G[G["g_idx"].isin(res.open_g_idx)]
            .copy()
            .merge(areas_per_gw, on="g_idx", how="left")
        )
        selected_gw_df["n_areas_served"] = (
            selected_gw_df["areas_served"].apply(
                lambda x: len(x) if isinstance(x, list) else 0
            )
        )

        keep_cols = [
            "g_idx", "candidate_id", "facility_name", "city", "source_state",
            "latitude", "longitude", "usable_available_space_sf",
            "areas_served", "n_areas_served",
        ]
        # Keep only columns that actually exist in selected_gw_df
        keep_cols = [c for c in keep_cols if c in selected_gw_df.columns]
        selected_gw_df = selected_gw_df[keep_cols].reset_index(drop=True)

        return selected_gw_df, assignments_df

    # ── Convenience repr ──────────────────────────────────────────────────────

    def __repr__(self) -> str:
        solved = self.result is not None
        status = self.result.status_name if solved else "not solved"
        return (
            f"GatewayMIP("
            f"|G|={self._n_G}, |Z|={self._n_Z}, |A|={self._n_A}, "
            f"|S|={len(self.S)}, status={status})"
        )
