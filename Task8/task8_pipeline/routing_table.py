"""Task 8.1 — County Routing Lookup Table builder.

Builds a flat table mapping every NE county to its assigned gateway(s) and
regional hub(s) with capacity-share weights.
"""
import numpy as np
import pandas as pd

from .config import Task8Config


class RoutingTableBuilder:
    """Builds ``county_routing_lookup.parquet`` (Task 8.1).

    The output has one row per (county, gateway, hub) combination.
    ``combined_share`` sums to 1.0 within each FIPS.
    """

    def __init__(self, cfg: Task8Config) -> None:
        self.cfg = cfg

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        """Build routing table, save to parquet, and return the DataFrame."""
        county_area  = self._load_county_area()
        gw_shares    = self._compute_gateway_shares()
        hub_shares   = self._compute_hub_shares()
        lookup       = self._assemble(county_area, gw_shares, hub_shares)
        self._validate(lookup)
        self._save(lookup)
        return lookup

    # ── Private helpers ─────────────────────────────────────────────────────

    def _load_county_area(self) -> pd.DataFrame:
        df = pd.read_csv(
            self.cfg.AREA_ASSIGN,
            dtype={"fips": "int64", "area_id": "str", "region_id": "int64"},
        )
        county_area = df[["fips", "area_id", "region_id"]].copy()
        print(
            f"  [8.1] county_area: {len(county_area)} rows | "
            f"areas: {county_area['area_id'].nunique()} | "
            f"regions: {county_area['region_id'].nunique()}"
        )
        return county_area

    def _compute_gateway_shares(self) -> pd.DataFrame:
        raw = pd.read_csv(
            self.cfg.GW_AREA_ASSIGN,
            usecols=["candidate_id", "area_id", "usable_available_space_sf"],
            dtype={"candidate_id": "str", "area_id": "str", "usable_available_space_sf": "int64"},
        )
        total = raw.groupby("area_id")["usable_available_space_sf"].sum().rename("gw_sqft_total")
        shares = raw.join(total, on="area_id")
        shares["gw_share"] = shares["usable_available_space_sf"] / shares["gw_sqft_total"]
        shares = shares[["candidate_id", "area_id", "gw_share"]].rename(
            columns={"candidate_id": "gateway_candidate_id"}
        )
        # Validate per-area sums
        area_sum = shares.groupby("area_id")["gw_share"].sum()
        bad = area_sum[~np.isclose(area_sum, 1.0, atol=1e-9)]
        assert len(bad) == 0, f"gw_share does not sum to 1.0 in areas: {bad.index.tolist()}"
        print(
            f"  [8.1] gw_shares: {len(shares)} rows | "
            f"unique gateways: {shares['gateway_candidate_id'].nunique()} ✓"
        )
        return shares

    def _compute_hub_shares(self) -> pd.DataFrame:
        raw = pd.read_csv(
            self.cfg.HUB_REGION_ASSIGN,
            usecols=["candidate_id", "region_id", "usable_available_space_sf"],
            dtype={"candidate_id": "str", "region_id": "int64", "usable_available_space_sf": "int64"},
        )
        total = raw.groupby("region_id")["usable_available_space_sf"].sum().rename("hub_sqft_total")
        shares = raw.join(total, on="region_id")
        shares["hub_share"] = shares["usable_available_space_sf"] / shares["hub_sqft_total"]
        shares = shares[["candidate_id", "region_id", "hub_share"]].rename(
            columns={"candidate_id": "hub_candidate_id"}
        )
        # Validate per-region sums
        region_sum = shares.groupby("region_id")["hub_share"].sum()
        bad = region_sum[~np.isclose(region_sum, 1.0, atol=1e-9)]
        assert len(bad) == 0, f"hub_share does not sum to 1.0 in regions: {bad.index.tolist()}"
        multi_hub = shares.groupby("region_id").size()
        multi = multi_hub[multi_hub > 1]
        print(
            f"  [8.1] hub_shares: {len(shares)} rows | "
            f"multi-hub regions: {multi.to_dict()} ✓"
        )
        return shares

    def _assemble(
        self,
        county_area: pd.DataFrame,
        gw_shares: pd.DataFrame,
        hub_shares: pd.DataFrame,
    ) -> pd.DataFrame:
        county_gw = county_area.merge(gw_shares, on="area_id", how="left")
        no_gw = county_gw["gateway_candidate_id"].isna().sum()
        if no_gw:
            print(f"  WARNING: {no_gw} (county × area) rows have no gateway assignment")

        routing = county_gw.merge(hub_shares, on="region_id", how="left")
        no_hub = routing["hub_candidate_id"].isna().sum()
        if no_hub:
            print(f"  WARNING: {no_hub} rows have no hub assignment")

        routing["combined_share"] = routing["gw_share"] * routing["hub_share"]
        lookup = routing[
            ["fips", "area_id", "region_id",
             "gateway_candidate_id", "hub_candidate_id",
             "gw_share", "hub_share", "combined_share"]
        ].copy()
        print(
            f"  [8.1] lookup: {len(lookup):,} rows | "
            f"county × gateway × hub combos"
        )
        return lookup

    def _validate(self, lookup: pd.DataFrame) -> None:
        fips_sum = lookup.groupby("fips")["combined_share"].sum()
        bad = fips_sum[~np.isclose(fips_sum, 1.0, atol=1e-9)]
        if len(bad):
            raise AssertionError(
                f"combined_share does not sum to 1.0 for {len(bad)} counties: {bad}"
            )
        print(f"  [8.1] ✓ combined_share sums to 1.0 for all {len(fips_sum)} counties")

    def _save(self, lookup: pd.DataFrame) -> None:
        out = self.cfg.COUNTY_ROUTING_LOOKUP
        lookup.to_parquet(out, index=False)
        print(f"  [8.1] Saved → {out}  ({out.stat().st_size / 1024:.1f} KB)")
