"""Task 8.5 — Gateway-Level Throughput calculator.

Computes NE-internal inbound / outbound / total throughput for each of the
312 gateway hubs using the area_flow_matrix and gateway capacity shares.
"""
from collections import defaultdict

import numpy as np
import pandas as pd

from .config import Task8Config


class GatewayThroughputCalculator:
    """Computes ``gateway_throughput.csv`` (Task 8.5).

    Scope: NE-internal flows only (~1,227,291 ktons directed). Interface-node
    (external) traffic is credited to regional hubs in Task 8.6, not here.
    """

    def __init__(self, cfg: Task8Config) -> None:
        self.cfg = cfg

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        """Compute gateway throughput, save CSV, and return the DataFrame."""
        area_flow, area_flow_total = self._load_area_flow()
        area_gws, gw_meta          = self._load_gateway_data()
        gw_tp                      = self._accumulate(area_flow, area_gws, gw_meta)
        self._validate(gw_tp, area_flow_total)
        self._save(gw_tp)
        return gw_tp

    # ── Private helpers ─────────────────────────────────────────────────────

    def _load_area_flow(self) -> tuple[pd.DataFrame, float]:
        af = pd.read_parquet(self.cfg.AREA_FLOW_MATRIX)
        total = af["tons_2025"].sum()
        print(
            f"  [8.5] area_flow_matrix: {len(af):,} rows | "
            f"total_2025 = {total:,.1f} ktons (directed)"
        )
        return af, total

    def _load_gateway_data(
        self,
    ) -> tuple[dict[str, list[tuple[str, float]]], pd.DataFrame]:
        gaa = pd.read_csv(
            self.cfg.GW_AREA_ASSIGN,
            usecols=["candidate_id", "area_id", "usable_available_space_sf",
                     "facility_name", "source_state"],
        )
        gaa = gaa.rename(columns={"candidate_id": "gateway_id"})
        sqft_total = gaa.groupby("area_id")["usable_available_space_sf"].transform("sum")
        gaa["gw_share"] = gaa["usable_available_space_sf"] / sqft_total

        share_sum = gaa.groupby("area_id")["gw_share"].sum()
        assert (share_sum - 1.0).abs().max() < 1e-9, \
            "Gateway shares don't sum to 1.0 in some area"

        area_gws: dict[str, list[tuple[str, float]]] = (
            gaa.groupby("area_id")
            .apply(
                lambda g: list(zip(g["gateway_id"], g["gw_share"])),
                include_groups=False,
            )
            .to_dict()
        )

        gw_meta = (
            gaa[["gateway_id", "facility_name", "source_state", "area_id"]]
            .drop_duplicates("gateway_id")
            .set_index("gateway_id")
        )
        # Attach region_id
        area_region = (
            pd.read_csv(
                self.cfg.AREA_ASSIGN,
                usecols=["area_id", "region_id"],
            )
            .drop_duplicates("area_id")
        )
        area_to_region = area_region.set_index("area_id")["region_id"].to_dict()
        gw_meta["region_id"] = gw_meta["area_id"].map(area_to_region)

        print(
            f"  [8.5] gaa: {len(gaa)} rows | "
            f"gateways: {gaa['gateway_id'].nunique()} | "
            f"areas: {gaa['area_id'].nunique()} ✓"
        )
        return area_gws, gw_meta

    def _accumulate(
        self,
        area_flow: pd.DataFrame,
        area_gws: dict[str, list[tuple[str, float]]],
        gw_meta: pd.DataFrame,
    ) -> pd.DataFrame:
        gw_inbound_25:  dict[str, float] = defaultdict(float)
        gw_outbound_25: dict[str, float] = defaultdict(float)
        gw_inbound_30:  dict[str, float] = defaultdict(float)
        gw_outbound_30: dict[str, float] = defaultdict(float)

        for row in area_flow.itertuples(index=False):
            o_area, d_area = row.origin_area_id, row.dest_area_id
            t25, t30       = row.tons_2025, row.tons_2030
            for g_o, s_o in area_gws[o_area]:
                gw_outbound_25[g_o] += t25 * s_o
                gw_outbound_30[g_o] += t30 * s_o
            for g_d, s_d in area_gws[d_area]:
                gw_inbound_25[g_d] += t25 * s_d
                gw_inbound_30[g_d] += t30 * s_d

        records = []
        for gid in gw_meta.index:
            ib25 = gw_inbound_25[gid]
            ob25 = gw_outbound_25[gid]
            records.append({
                "candidate_id":          gid,
                "facility_name":         gw_meta.loc[gid, "facility_name"],
                "source_state":          gw_meta.loc[gid, "source_state"],
                "area_id":               gw_meta.loc[gid, "area_id"],
                "region_id":             gw_meta.loc[gid, "region_id"],
                "inbound_ktons_2025":    ib25,
                "outbound_ktons_2025":   ob25,
                "throughput_ktons_2025": ib25 + ob25,
                "throughput_ktons_2030": gw_inbound_30[gid] + gw_outbound_30[gid],
            })
        df = pd.DataFrame(records).sort_values("throughput_ktons_2025", ascending=False)
        print(f"  [8.5] Accumulation complete. {len(df)} gateway rows built.")
        return df

    def _validate(self, gw_tp: pd.DataFrame, area_flow_total: float) -> None:
        assert len(gw_tp) == self.cfg.EXPECTED_GATEWAYS, (
            f"Expected {self.cfg.EXPECTED_GATEWAYS} gateways, got {len(gw_tp)}"
        )
        assert (gw_tp["throughput_ktons_2025"] >= 0).all(), "Negative gateway throughput"

        half = gw_tp["throughput_ktons_2025"].sum() * 0.5
        dev_pct = abs(half - area_flow_total) / area_flow_total * 100
        assert dev_pct < 0.001, (
            f"Gateway throughput total deviates {dev_pct:.4f}% from area_flow total"
        )
        print(
            f"  [8.5] ✓ sum(gw_throughput)×0.5 = {half:,.1f} ktons ≈ "
            f"directed area_flow total ✓"
        )

    def _save(self, gw_tp: pd.DataFrame) -> None:
        out = self.cfg.GATEWAY_THROUGHPUT
        gw_tp.to_csv(out, index=False)
        print(f"  [8.5] Saved → {out}  ({out.stat().st_size / 1024:.1f} KB)")
