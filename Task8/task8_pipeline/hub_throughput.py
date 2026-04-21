"""Task 8.3 — Hub-Level Throughput calculator.

Computes total freight handled at each of the 50 regional hubs from the
pre-aggregated region_flow_matrix. The initial output (without interface-node
columns) is written here; Task 8.6 (InterfaceNodeRouter) appends the
``interface_throughput_ktons`` columns and overwrites the file.
"""
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from .config import Task8Config


class HubThroughputCalculator:
    """Computes ``hub_throughput.csv`` (Task 8.3).

    Returns the DataFrame and intermediate structures consumed by
    downstream steps (LinkFlowLoader and InterfaceNodeRouter).
    """

    def __init__(self, cfg: Task8Config) -> None:
        self.cfg = cfg

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self) -> tuple[pd.DataFrame, float, dict[int, list[tuple[str, float]]]]:
        """Compute hub throughput, save CSV, return (hub_tp, rfm_total_25, region_hubs).

        Returns
        -------
        hub_tp : pd.DataFrame
            50-row throughput table.
        rfm_total_25 : float
            Total ktons in region_flow_matrix (used by downstream validators).
        region_hubs : dict[int, list[tuple[str, float]]]
            Mapping region_id → [(candidate_id, hub_share), …] for 8.4.
        """
        rfm, rfm_total_25 = self._load_region_flow_matrix()
        hub_assign, region_hubs = self._load_hub_assignments()
        hub_tp = self._accumulate(rfm, region_hubs, hub_assign)
        self._validate(hub_tp, rfm_total_25)
        self._save(hub_tp)
        return hub_tp, rfm_total_25, region_hubs

    # ── Private helpers ─────────────────────────────────────────────────────

    def _load_region_flow_matrix(self) -> tuple[pd.DataFrame, float]:
        rfm = pd.read_parquet(self.cfg.REGION_FLOW_MAT)
        # Cast float region IDs to int immediately (stored as float64)
        rfm["origin_region"] = rfm["origin_region"].astype(int)
        rfm["dest_region"]   = rfm["dest_region"].astype(int)
        total = rfm["tons_2025"].sum()
        assert abs(total - self.cfg.RFM_EXPECTED_TOTAL) < 100, (
            f"region_flow_matrix total mismatch: {total:.1f} "
            f"(expected ~{self.cfg.RFM_EXPECTED_TOTAL:,})"
        )
        print(
            f"  [8.3] region_flow_matrix: {len(rfm):,} rows | "
            f"total_2025 = {total:,.1f} ktons ✓"
        )
        return rfm, total

    def _load_hub_assignments(
        self,
    ) -> tuple[pd.DataFrame, dict[int, list[tuple[str, float]]]]:
        df = pd.read_csv(
            self.cfg.HUB_REGION_ASSIGN,
            dtype={"candidate_id": str, "region_id": "int64",
                   "usable_available_space_sf": "int64"},
        )
        sqft_by_region = (
            df.groupby("region_id")["usable_available_space_sf"]
            .sum()
            .rename("sqft_total")
        )
        df = df.join(sqft_by_region, on="region_id")
        df["hub_share"] = df["usable_available_space_sf"] / df["sqft_total"]

        region_hubs: dict[int, list[tuple[str, float]]] = (
            df.groupby("region_id")
            .apply(
                lambda g: list(zip(g["candidate_id"], g["hub_share"])),
                include_groups=False,
            )
            .to_dict()
        )
        multi = {r: v for r, v in region_hubs.items() if len(v) > 1}
        print(
            f"  [8.3] hub_assign: {len(df)} rows | "
            f"multi-hub regions: { {r: [(c, f'{s:.4f}') for c,s in v] for r,v in multi.items()} }"
        )
        return df, region_hubs

    def _accumulate(
        self,
        rfm: pd.DataFrame,
        region_hubs: dict[int, list[tuple[str, float]]],
        hub_assign: pd.DataFrame,
    ) -> pd.DataFrame:
        inbound_25:  dict[str, float] = defaultdict(float)
        outbound_25: dict[str, float] = defaultdict(float)
        internal_25: dict[str, float] = defaultdict(float)
        inbound_30:  dict[str, float] = defaultdict(float)
        outbound_30: dict[str, float] = defaultdict(float)

        for row in rfm.itertuples(index=False):
            r_o, r_d = row.origin_region, row.dest_region
            t25, t30 = row.tons_2025, row.tons_2030
            for h_o, s_o in region_hubs[r_o]:
                for h_d, s_d in region_hubs[r_d]:
                    f25 = t25 * s_o * s_d
                    f30 = t30 * s_o * s_d
                    outbound_25[h_o] += f25
                    inbound_25[h_d]  += f25
                    outbound_30[h_o] += f30
                    inbound_30[h_d]  += f30
                    if h_o == h_d:
                        internal_25[h_o] += f25

        hub_meta = (
            hub_assign[["candidate_id", "facility_name", "source_state", "region_id"]]
            .drop_duplicates("candidate_id")
            .set_index("candidate_id")
        )
        records = []
        for hid in hub_meta.index:
            ob25 = outbound_25[hid]
            ib25 = inbound_25[hid]
            records.append({
                "candidate_id":          hid,
                "facility_name":         hub_meta.loc[hid, "facility_name"],
                "source_state":          hub_meta.loc[hid, "source_state"],
                "region_id":             hub_meta.loc[hid, "region_id"],
                "inbound_ktons_2025":    ib25,
                "outbound_ktons_2025":   ob25,
                "internal_ktons_2025":   internal_25[hid],
                "throughput_ktons_2025": ob25 + ib25,
                "throughput_ktons_2030": outbound_30[hid] + inbound_30[hid],
            })
        hub_tp = pd.DataFrame(records).sort_values("throughput_ktons_2025", ascending=False)
        print(f"  [8.3] Accumulation complete. {len(hub_tp)} hub rows built.")
        return hub_tp

    def _validate(self, hub_tp: pd.DataFrame, rfm_total_25: float) -> None:
        assert len(hub_tp) == self.cfg.EXPECTED_HUBS, (
            f"Expected {self.cfg.EXPECTED_HUBS} hubs, got {len(hub_tp)}"
        )
        assert (hub_tp["throughput_ktons_2025"] >= 0).all(), "Negative throughput"
        assert (hub_tp["inbound_ktons_2025"]    >= 0).all(), "Negative inbound"
        assert (hub_tp["outbound_ktons_2025"]   >= 0).all(), "Negative outbound"

        total_tp = hub_tp["throughput_ktons_2025"].sum()
        half     = total_tp * 0.5
        assert abs(half - rfm_total_25) < 1.0, (
            f"VALIDATION FAILED: sum×0.5={half:.1f} ≠ {rfm_total_25:.1f} ktons"
        )
        ib = hub_tp["inbound_ktons_2025"].sum()
        ob = hub_tp["outbound_ktons_2025"].sum()
        assert abs(ib - ob) < 1.0, f"Inbound/outbound imbalance: {ib:.1f} vs {ob:.1f}"
        print(
            f"  [8.3] ✓ sum(throughput)×0.5 = {half:,.1f} ktons ≈ RFM total | "
            f"inbound≈outbound ✓"
        )

    def _save(self, hub_tp: pd.DataFrame) -> None:
        out = self.cfg.HUB_THROUGHPUT
        hub_tp.to_csv(out, index=False)
        print(f"  [8.3] Saved → {out}  ({out.stat().st_size / 1024:.1f} KB)")
