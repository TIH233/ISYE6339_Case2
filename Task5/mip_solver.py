"""
Task 5.3 — Regional Hub Selection MIP
======================================
Capacity-aware set-cover MIP implemented with gurobipy.

Formulation (from Doc/Task.md § Task 5 — Formulation)
------------------------------------------------------
Sets
    H : pre-screened hub candidates  (indexed by h_idx ∈ {0 … |H|-1})
    R : 50 Task 3 regions            (indexed by r_idx ∈ {0 … 49})
    Z : feasible (h,r) pairs — Euclidean distance ≤ 150 miles

Variables
    A[h,r] ∈ {0,1}   hub h is assigned to serve region r
    O[h]   ∈ {0,1}   hub h is opened

Objective
    minimize  Σ_{(h,r)∈Z}  c_hat[h,r] · A[h,r]

Constraints
    1. Coverage      : Σ_h A[h,r] ≥ 1             ∀r ∈ R
    2. Concentration : Σ_r A[h,r] ≤ p_h            ∀h ∈ H     (p_h = 2)
    3. Link          : O[h] ≤ Σ_r A[h,r]           ∀h ∈ H
    4. Capacity      : Σ_h A[h,r]·s_h ≥ RHS_r      ∀r ∈ R

Constraint 5 (road gate) is enforced as a pre-filter on H (Task 5.1).

Classes
-------
MIPParameters   Immutable solver and model configuration.
MIPResult       Compact summary of the Gurobi solve outcome.
RegionalHubMIP  Builds, solves, and extracts the hub-selection MIP.

Usage
-----
>>> from mip_solver import RegionalHubMIP, MIPParameters
>>> params = MIPParameters(time_limit=600, mip_gap=0.01)
>>> solver = RegionalHubMIP(H_arr, Z, c_hat, cap_rhs, s_h, params)
>>> solver.build()
>>> result = solver.solve()
>>> hubs_df, assign_df = solver.extract_solution(H_df, R_ids)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

try:
    import gurobipy as gp
    from gurobipy import GRB
except ImportError as exc:
    raise ImportError(
        "gurobipy is required for Task 5.3. "
        "Install via: conda install -c gurobi gurobi  "
        "or: pip install gurobipy"
    ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Domain objects
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MIPParameters:
    """
    Solver configuration for RegionalHubMIP.

    Attributes
    ----------
    time_limit : float
        Gurobi TimeLimit in seconds (default 600).
    mip_gap : float
        Relative MIP optimality gap at which the solver stops (default 0.01 = 1%).
    output_flag : int
        1 = print Gurobi log to console; 0 = silent.
    concentration_cap : int
        Maximum number of regions a single hub may serve (p_h, default 2).
    threads : int
        Number of solver threads; 0 = all available cores.
    """
    time_limit:        float = 600.0
    mip_gap:           float = 0.01
    output_flag:       int   = 1
    concentration_cap: int   = 2
    threads:           int   = 0


@dataclass
class MIPResult:
    """
    Summary of a completed Gurobi solve.

    Attributes
    ----------
    status : int
        Gurobi status code (GRB.OPTIMAL = 2, GRB.TIME_LIMIT = 9, …).
    status_name : str
        Human-readable label for status.
    objective : float
        Primal objective value (∑ c_hat · A).
    mip_gap : float
        Relative gap between primal and dual bound at termination.
    solve_time : float
        Wall-clock seconds consumed by optimize().
    n_hubs_open : int
        Number of hubs with O[h] = 1.
    n_assignments : int
        Number of (h, r) pairs with A[h,r] = 1.
    open_h_idx : list[int]
        h_idx values for open hubs.
    assigned_pairs : list[tuple[int, int]]
        (h_idx, r_idx) pairs for active assignments.
    """
    status:          int
    status_name:     str
    objective:       float
    mip_gap:         float
    solve_time:      float
    n_hubs_open:     int
    n_assignments:   int
    open_h_idx:      list[int]               = field(default_factory=list)
    assigned_pairs:  list[tuple[int, int]]   = field(default_factory=list)

    def is_feasible(self) -> bool:
        """True if a primal integer solution was found."""
        return self.n_hubs_open > 0


# ─────────────────────────────────────────────────────────────────────────────
# MIP solver class
# ─────────────────────────────────────────────────────────────────────────────

class RegionalHubMIP:
    """
    Capacity-aware set-cover MIP for regional hub selection (Task 5.3).

    Parameters
    ----------
    H_arr : np.ndarray, shape (|H|,)
        Integer hub indices, typically ``np.arange(len(H))``.
    Z : np.ndarray, shape (|Z|, 2), dtype int32
        Feasibility pairs — each row is ``[h_idx, r_idx]``.
    c_hat : np.ndarray, shape (|Z|,), dtype float64
        Objective cost coefficients aligned row-for-row with Z.
    cap_rhs : np.ndarray, shape (|R|,), dtype float64
        Capacity constraint RHS per region (sqft), aligned to region_metrics
        row order (r_idx == region_id since region IDs are 0–49).
    s_h : np.ndarray, shape (|H|,), dtype float64
        Usable floor area of each hub (sqft).
    params : MIPParameters, optional
        Solver and model configuration.  Defaults applied if omitted.
    """

    def __init__(
        self,
        H_arr:    np.ndarray,
        Z:        np.ndarray,
        c_hat:    np.ndarray,
        cap_rhs:  np.ndarray,
        s_h:      np.ndarray,
        params:   Optional[MIPParameters] = None,
    ) -> None:
        self.H_arr   = np.asarray(H_arr,   dtype=np.int64)
        self.Z       = np.asarray(Z,        dtype=np.int32)
        self.c_hat   = np.asarray(c_hat,    dtype=np.float64)
        self.cap_rhs = np.asarray(cap_rhs,  dtype=np.float64)
        self.s_h     = np.asarray(s_h,      dtype=np.float64)
        self.params  = params or MIPParameters()

        self._n_H = int(len(H_arr))
        self._n_R = int(len(cap_rhs))
        self._n_Z = int(len(Z))

        # Internal Gurobi objects (populated by build())
        self._model:  Optional[gp.Model]      = None
        self._A:      Optional[gp.tupledict]  = None   # z → Var
        self._O:      Optional[gp.tupledict]  = None   # h → Var
        self._z_by_r: Optional[list[list[int]]] = None
        self._z_by_h: Optional[list[list[int]]] = None

        # Solve result (populated by solve())
        self.result: Optional[MIPResult] = None

    # ── Model construction ────────────────────────────────────────────────────

    def build(self) -> None:
        """
        Assemble the Gurobi model: variables, objective, and constraints 1–4.

        Must be called before ``solve()``.
        """
        p = self.params
        m = gp.Model("RegionalHubMIP")

        # ── Solver parameters ─────────────────────────────────────────────────
        m.setParam("TimeLimit",  p.time_limit)
        m.setParam("MIPGap",     p.mip_gap)
        m.setParam("OutputFlag", p.output_flag)
        if p.threads > 0:
            m.setParam("Threads", p.threads)

        # ── Decision variables ────────────────────────────────────────────────
        # A[z] = A_{h,r} for each row z in Z
        A = m.addVars(self._n_Z, vtype=GRB.BINARY, name="A")
        # O[h] = O_h for each hub h ∈ H
        O = m.addVars(self._n_H, vtype=GRB.BINARY, name="O")

        # ── Objective: minimize Σ_z  c_hat[z] · A[z] ─────────────────────────
        m.setObjective(
            gp.quicksum(float(self.c_hat[z]) * A[z] for z in range(self._n_Z)),
            GRB.MINIMIZE,
        )

        # ── Index lookups (built once; reused by all four constraint groups) ──
        # z_by_r[r] : list of Z-row indices whose r_idx == r
        z_by_r: list[list[int]] = [[] for _ in range(self._n_R)]
        # z_by_h[h] : list of Z-row indices whose h_idx == h
        z_by_h: list[list[int]] = [[] for _ in range(self._n_H)]

        for z, (h, r) in enumerate(self.Z):
            z_by_r[r].append(z)
            z_by_h[h].append(z)

        # ── Constraint 1 — Coverage ───────────────────────────────────────────
        # Σ_{h:(h,r)∈Z} A[h,r] ≥ 1    ∀r
        for r in range(self._n_R):
            if z_by_r[r]:
                m.addConstr(
                    gp.quicksum(A[z] for z in z_by_r[r]) >= 1,
                    name=f"coverage_r{r}",
                )

        # ── Constraint 2 — Concentration cap ─────────────────────────────────
        # Σ_{r:(h,r)∈Z} A[h,r] ≤ p_h    ∀h
        for h in range(self._n_H):
            if z_by_h[h]:
                m.addConstr(
                    gp.quicksum(A[z] for z in z_by_h[h]) <= p.concentration_cap,
                    name=f"conc_h{h}",
                )

        # ── Constraint 3 — Activation link ───────────────────────────────────
        # O[h] ≤ Σ_{r:(h,r)∈Z} A[h,r]    ∀h
        for h in range(self._n_H):
            if z_by_h[h]:
                m.addConstr(
                    O[h] <= gp.quicksum(A[z] for z in z_by_h[h]),
                    name=f"link_h{h}",
                )

        # ── Constraint 4 — Capacity coverage ─────────────────────────────────
        # Σ_{h:(h,r)∈Z} A[h,r]·s_h ≥ RHS_r    ∀r
        for r in range(self._n_R):
            if z_by_r[r]:
                m.addConstr(
                    gp.quicksum(
                        float(self.s_h[self.Z[z, 0]]) * A[z] for z in z_by_r[r]
                    ) >= float(self.cap_rhs[r]),
                    name=f"capacity_r{r}",
                )

        m.update()

        # Store references
        self._model  = m
        self._A      = A
        self._O      = O
        self._z_by_r = z_by_r
        self._z_by_h = z_by_h

        print(
            f"Model built — "
            f"{m.NumVars:,} variables  "
            f"{m.NumConstrs:,} constraints  "
            f"{m.NumNZs:,} non-zeros"
        )

    # ── Solve ─────────────────────────────────────────────────────────────────

    def solve(self) -> MIPResult:
        """
        Run Gurobi's branch-and-cut and store the result.

        Returns
        -------
        MIPResult
            Summary object; also stored as ``self.result``.
        """
        if self._model is None:
            raise RuntimeError("Call build() before solve().")

        t0 = time.perf_counter()
        self._model.optimize()
        elapsed = time.perf_counter() - t0

        m = self._model
        A = self._A
        O = self._O

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
            self.result = MIPResult(
                status=m.Status,
                status_name=status_name,
                objective=float("inf"),
                mip_gap=float("inf"),
                solve_time=elapsed,
                n_hubs_open=0,
                n_assignments=0,
            )
            return self.result

        # Extract active assignments from A variables
        assigned = [
            (int(self.Z[z, 0]), int(self.Z[z, 1]))
            for z in range(self._n_Z)
            if A[z].X > 0.5
        ]
        # Derive open hubs from assignments (O[h] ≤ Σ A[h,r] is one-sided;
        # O is 0 in optimal since it has no objective cost — use A instead)
        open_h = sorted({h for h, r in assigned})

        self.result = MIPResult(
            status=m.Status,
            status_name=status_name,
            objective=m.ObjVal,
            mip_gap=m.MIPGap,
            solve_time=elapsed,
            n_hubs_open=len(open_h),
            n_assignments=len(assigned),
            open_h_idx=open_h,
            assigned_pairs=assigned,
        )
        return self.result

    # ── Solution extraction ───────────────────────────────────────────────────

    def extract_solution(
        self,
        H: pd.DataFrame,
        R_ids: np.ndarray,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Build output DataFrames from the stored solve result.

        Parameters
        ----------
        H : pd.DataFrame
            Hub candidate table (``H_candidates.parquet``).
            Required columns: ``h_idx``, ``candidate_id``, ``facility_name``,
            ``city``, ``source_state``, ``region_id``, ``latitude``,
            ``longitude``, ``usable_available_space_sf``,
            ``d_road_m``, ``d_road_miles``.
        R_ids : np.ndarray, shape (|R|,)
            Region IDs in row order (0–49); from
            ``region_metrics.region_id.values``.

        Returns
        -------
        selected_hubs_df : pd.DataFrame
            One row per open hub with characterisation columns and
            ``regions_served`` (list of region_id values) and
            ``n_regions_served``.
        assignments_df : pd.DataFrame
            One row per active (hub, region) assignment, joined with hub
            metadata and the cost coefficient ``c_hat``.
        """
        if self.result is None:
            raise RuntimeError("Call solve() before extract_solution().")
        if not self.result.is_feasible():
            raise RuntimeError(
                f"No feasible solution found (status={self.result.status_name}). "
                "Cannot extract."
            )

        res  = self.result
        Z    = self.Z
        c    = self.c_hat

        # ── assignments table ─────────────────────────────────────────────────
        assign_rows = []
        for h_idx, r_idx in res.assigned_pairs:
            # Retrieve cost coefficient for this (h, r) pair
            z_pos = np.where((Z[:, 0] == h_idx) & (Z[:, 1] == r_idx))[0]
            c_val = float(c[z_pos[0]]) if len(z_pos) else float("nan")
            assign_rows.append({
                "h_idx":     h_idx,
                "r_idx":     r_idx,
                "region_id": int(R_ids[r_idx]),
                "c_hat":     c_val,
            })
        assignments_df = pd.DataFrame(assign_rows)

        # Join hub metadata onto assignments
        meta_cols = [
            "h_idx", "candidate_id", "facility_name", "city", "source_state",
            "latitude", "longitude", "usable_available_space_sf",
            "d_road_m", "d_road_miles",
        ]
        assignments_df = assignments_df.merge(
            H[meta_cols], on="h_idx", how="left"
        )

        # ── regions served per hub ────────────────────────────────────────────
        regions_per_hub = (
            assignments_df.groupby("h_idx")["region_id"]
            .apply(list)
            .reset_index()
            .rename(columns={"region_id": "regions_served"})
        )

        # ── selected hubs table ───────────────────────────────────────────────
        selected_hubs_df = (
            H[H["h_idx"].isin(res.open_h_idx)]
            .copy()
            .merge(regions_per_hub, on="h_idx", how="left")
        )
        selected_hubs_df["n_regions_served"] = (
            selected_hubs_df["regions_served"].apply(
                lambda x: len(x) if isinstance(x, list) else 0
            )
        )

        keep_cols = [
            "h_idx", "candidate_id", "facility_name", "city", "source_state",
            "region_id", "latitude", "longitude",
            "usable_available_space_sf", "d_road_m", "d_road_miles",
            "regions_served", "n_regions_served",
        ]
        selected_hubs_df = selected_hubs_df[keep_cols].reset_index(drop=True)

        return selected_hubs_df, assignments_df

    # ── Convenience repr ──────────────────────────────────────────────────────

    def __repr__(self) -> str:
        solved = self.result is not None
        status = self.result.status_name if solved else "not solved"
        return (
            f"RegionalHubMIP("
            f"|H|={self._n_H}, |Z|={self._n_Z}, |R|={self._n_R}, "
            f"status={status})"
        )
