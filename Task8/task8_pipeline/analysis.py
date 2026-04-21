"""Task 8.7 — Analysis: Critical Hubs, Corridors, and Concentration Patterns.

Loads the output CSVs produced by steps 8.3–8.6 and prints structured analysis
tables. Returns augmented DataFrames consumed by FigureGenerator (8.8).
"""
import numpy as np
import pandas as pd

from .config import Task8Config


class FlowAnalyzer:
    """Computes criticality metrics and concentration statistics (Task 8.7).

    Call ``run()`` to load all outputs and print the analysis; the returned
    DataFrames (hub_tp, gateway_tp, hub_links) carry derived columns needed by
    FigureGenerator.
    """

    def __init__(self, cfg: Task8Config) -> None:
        self.cfg = cfg

    # ── Public API ──────────────────────────────────────────────────────────

    def run(
        self,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Load outputs, print analysis, return (hub_tp, gateway_tp, hub_links, iface)."""
        hub_tp, gateway_tp, hub_links, iface, sh, gws = self._load()
        hub_tp    = self._hub_criticality(hub_tp, sh)
        gateway_tp = self._gateway_criticality(gateway_tp)
        hub_links  = self._link_criticality(hub_links)
        hub_tp, hub_links = self._growth_analysis(hub_tp, hub_links)
        self._concentration(hub_tp)
        return hub_tp, gateway_tp, hub_links, iface

    # ── Private helpers ─────────────────────────────────────────────────────

    def _load(
        self,
    ) -> tuple[
        pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame,
        pd.DataFrame, pd.DataFrame,
    ]:
        ht  = pd.read_csv(self.cfg.HUB_THROUGHPUT)
        gt  = pd.read_csv(self.cfg.GATEWAY_THROUGHPUT)
        hl  = pd.read_csv(self.cfg.HUB_LINK_FLOWS)
        ir  = pd.read_csv(self.cfg.INTERFACE_HUB_ROUTING)
        sh  = pd.read_csv(self.cfg.SELECTED_HUBS)
        gws = pd.read_csv(self.cfg.GATEWAY_SEL)
        print(
            f"  [8.7] Loaded: {len(ht)} hubs | {len(gt)} gateways | "
            f"{len(hl)} links | {len(ir)} interface nodes"
        )
        return ht, gt, hl, ir, sh, gws

    def _hub_criticality(
        self, ht: pd.DataFrame, sh: pd.DataFrame
    ) -> pd.DataFrame:
        ht["total_including_interface_2025"] = (
            ht["throughput_ktons_2025"] + ht["interface_throughput_ktons_2025"]
        )
        ht["interface_share"] = np.where(
            ht["total_including_interface_2025"] > 0,
            ht["interface_throughput_ktons_2025"] / ht["total_including_interface_2025"],
            0.0,
        )
        if "n_regions_served" in sh.columns:
            multi_hub_ids = set(sh.loc[sh["n_regions_served"] > 1, "candidate_id"])
            ht["multi_region_hub"] = ht["candidate_id"].isin(multi_hub_ids)
        else:
            ht["multi_region_hub"] = False

        top10 = (
            ht.sort_values("throughput_ktons_2025", ascending=False)
            .reset_index(drop=True)
            .head(10)
        )
        print("\nTop 10 Regional Hubs by Throughput (2025)")
        print("=" * 80)
        for i, row in top10.iterrows():
            iface = f"{row['interface_share']*100:.1f}%"
            multi = " [multi-region]" if row.get("multi_region_hub", False) else ""
            print(
                f"  {i+1:2d}. {row['facility_name'][:45]:<45} "
                f"({row['source_state']}) | {row['throughput_ktons_2025']:>10,.0f} ktons | "
                f"iface={iface}{multi}"
            )
        return ht

    def _gateway_criticality(self, gt: pd.DataFrame) -> pd.DataFrame:
        top20 = (
            gt.sort_values("throughput_ktons_2025", ascending=False)
            .reset_index(drop=True)
            .head(20)
        )
        print("\nTop 20 Gateway Hubs by Throughput (2025)")
        print("=" * 80)
        for i, row in top20.iterrows():
            print(
                f"  {i+1:2d}. {row['facility_name'][:45]:<45} "
                f"({row['source_state']}) | area={row['area_id']} | "
                f"{row['throughput_ktons_2025']:>9,.0f} ktons"
            )
        region_total = (
            gt.groupby("region_id")["throughput_ktons_2025"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        print("\nTop 10 Regions by Total Gateway Throughput (2025)")
        print("=" * 60)
        for _, row in region_total.head(10).iterrows():
            print(
                f"  Region {int(row['region_id'])}: "
                f"{row['throughput_ktons_2025']:>10,.0f} ktons"
            )
        return gt

    def _link_criticality(self, hl: pd.DataFrame) -> pd.DataFrame:
        hl["flow_per_mile_2025"] = hl["flow_ktons_2025"] / hl["distance_miles"]
        top15 = (
            hl.sort_values("flow_ktons_2025", ascending=False)
            .reset_index(drop=True)
            .head(15)
        )
        print("\nTop 15 Hub-to-Hub Corridors by Flow (2025)")
        print("Note: 88.7% of hub-pairs use nearest-neighbor routing")
        print("=" * 90)
        for i, row in top15.iterrows():
            orig_flag = ""
            if pd.notna(row["flow_intensity_original_ktons"]) and row["flow_intensity_original_ktons"] > 0:
                ratio = row["flow_ktons_2025"] / row["flow_intensity_original_ktons"]
                orig_flag = f" | T5-ratio={ratio:.2f}"
            print(
                f"  {i+1:2d}. {row['hub_a_name'][:30]:<30} ↔ "
                f"{row['hub_b_name'][:30]:<30} | "
                f"{row['flow_ktons_2025']:>9,.0f} ktons | "
                f"{row['distance_miles']:.0f} mi{orig_flag}"
            )
        return hl

    def _growth_analysis(
        self, ht: pd.DataFrame, hl: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        ht["growth_abs_ktons"] = ht["throughput_ktons_2030"] - ht["throughput_ktons_2025"]
        ht["growth_pct"]       = ht["growth_abs_ktons"] / ht["throughput_ktons_2025"] * 100
        top10_hub = (
            ht.sort_values("growth_abs_ktons", ascending=False)
            .reset_index(drop=True)
            .head(10)
        )
        print("\nTop 10 Hubs by Absolute Throughput Growth (2025→2030)")
        print("=" * 75)
        for i, row in top10_hub.iterrows():
            print(
                f"  {i+1:2d}. {row['facility_name'][:45]:<45} "
                f"({row['source_state']}) | +{row['growth_abs_ktons']:>8,.0f} ktons "
                f"({row['growth_pct']:+.1f}%)"
            )

        hl["growth_abs_ktons"] = hl["flow_ktons_2030"] - hl["flow_ktons_2025"]
        hl["growth_pct"]       = hl["growth_abs_ktons"] / hl["flow_ktons_2025"] * 100
        return ht, hl

    @staticmethod
    def _gini(x: np.ndarray) -> float:
        x = np.sort(np.asarray(x, dtype=float))
        n = len(x)
        cumx = np.cumsum(x)
        return (n + 1 - 2 * cumx.sum() / cumx[-1]) / n

    def _concentration(self, ht: pd.DataFrame) -> None:
        flows = ht["throughput_ktons_2025"].values
        total = flows.sum()
        gini  = self._gini(flows)
        top5  = ht.nlargest(5,  "throughput_ktons_2025")["throughput_ktons_2025"].sum() / total
        top10 = ht.nlargest(10, "throughput_ktons_2025")["throughput_ktons_2025"].sum() / total

        njny_flow = ht.loc[
            ht["region_id"].isin(self.cfg.NJNY_REGIONS), "throughput_ktons_2025"
        ].sum()
        njny_ext  = ht.loc[
            ht["region_id"].isin(self.cfg.NJNY_REGIONS_EXTENDED), "throughput_ktons_2025"
        ].sum()

        print("\nFreight Concentration Metrics — Regional Hub Network (2025)")
        print("=" * 60)
        print(f"  Total hub throughput (NE-internal): {total:>12,.0f} ktons")
        print(f"  Gini coefficient:                   {gini:.4f}")
        print(f"  Top-5  hub share:                   {top5*100:.1f}%")
        print(f"  Top-10 hub share:                   {top10*100:.1f}%")
        print(
            f"\n  NJ/NY corridor (regions {sorted(self.cfg.NJNY_REGIONS)}): "
            f"{njny_flow/total*100:.1f}% ({njny_flow:,.0f} ktons)"
        )
        print(
            f"  Extended corridor (+region 0): "
            f"{njny_ext/total*100:.1f}% ({njny_ext:,.0f} ktons)"
        )
