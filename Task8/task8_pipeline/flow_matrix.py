"""Task 8.2 — Area-Pair Flow Matrix builder.

Aggregates county-to-county NE-internal flows from raw.parquet into a
132×132 area-pair directed matrix for 2025 and 2030.
"""
import pandas as pd

from .config import Task8Config


class AreaFlowMatrixBuilder:
    """Builds ``area_flow_matrix.parquet`` (Task 8.2).

    Parameters
    ----------
    cfg : Task8Config
    rfm_total_2025 : float
        Symmetrized region_flow_matrix total (ktons). Used to validate that
        the directed area-flow total ≈ rfm_total / 2.
    """

    def __init__(self, cfg: Task8Config, rfm_total_2025: float) -> None:
        self.cfg = cfg
        self._rfm_total_25 = rfm_total_2025

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        """Build area flow matrix, save to parquet, and return the DataFrame."""
        fips_to_area = self._load_area_map()
        raw          = self._load_raw(fips_to_area)
        area_flow    = self._aggregate(raw)
        self._validate(area_flow)
        self._save(area_flow)
        return area_flow

    # ── Private helpers ─────────────────────────────────────────────────────

    def _load_area_map(self) -> dict[int, str]:
        df = pd.read_csv(
            self.cfg.AREA_ASSIGN,
            usecols=["fips", "area_id"],
            dtype={"fips": "int64", "area_id": "str"},
        )
        mapping = df.set_index("fips")["area_id"].to_dict()
        print(
            f"  [8.2] fips_to_area: {len(mapping)} NE counties | "
            f"areas: {df['area_id'].nunique()}"
        )
        return mapping

    def _load_raw(self, fips_to_area: dict[int, str]) -> pd.DataFrame:
        print("  [8.2] Loading raw.parquet …")
        raw = pd.read_parquet(
            self.cfg.RAW_PARQUET,
            columns=["origin_county_fips", "dest_county_fips",
                     "sctgG5", "tons_2025", "tons_2030"],
        )
        before = len(raw)
        raw = raw[~raw["sctgG5"].isin(self.cfg.EXCLUDE_COMMODITIES)]
        print(
            f"  [8.2] Loaded {before:,} rows → {len(raw):,} after commodity filter"
        )
        raw["origin_area_id"] = raw["origin_county_fips"].map(fips_to_area)
        raw["dest_area_id"]   = raw["dest_county_fips"].map(fips_to_area)

        o_ne = raw["origin_area_id"].notna()
        d_ne = raw["dest_area_id"].notna()
        print(
            f"  [8.2] internal: {(o_ne & d_ne).sum():,} | "
            f"inbound: {(~o_ne & d_ne).sum():,} | "
            f"outbound: {(o_ne & ~d_ne).sum():,}"
        )
        return raw

    def _aggregate(self, raw: pd.DataFrame) -> pd.DataFrame:
        o_ne = raw["origin_area_id"].notna()
        d_ne = raw["dest_area_id"].notna()
        internal = raw.loc[
            o_ne & d_ne,
            ["origin_area_id", "dest_area_id", "tons_2025", "tons_2030"],
        ].copy()

        area_flow = (
            internal
            .groupby(["origin_area_id", "dest_area_id"], as_index=False, sort=False)
            [["tons_2025", "tons_2030"]]
            .sum()
        )
        area_flow = area_flow[
            (area_flow["tons_2025"] > 0) | (area_flow["tons_2030"] > 0)
        ]
        print(
            f"  [8.2] area_flow_matrix: {len(area_flow):,} rows "
            f"(max possible: 132×132 = {132*132:,})"
        )
        return area_flow

    def _validate(self, area_flow: pd.DataFrame) -> None:
        expected = self._rfm_total_25 / 2.0
        total    = area_flow["tons_2025"].sum()
        dev_pct  = abs(total - expected) / expected * 100

        print(
            f"  [8.2] directed internal total = {total:>15,.1f} ktons\n"
            f"         expected (rfm/2)        = {expected:>15,.1f} ktons\n"
            f"         deviation               = {total - expected:>+15,.1f} ktons "
            f"({dev_pct:.4f}%)"
        )
        if dev_pct > self.cfg.AREA_FLOW_TOLERANCE_PCT:
            raise AssertionError(
                f"VALIDATION FAILED: directed internal total {total:.1f} deviates "
                f"{dev_pct:.2f}% from expected rfm/2={expected:.1f}. "
                "Check commodity filter or FIPS join."
            )
        assert (area_flow["tons_2025"] >= 0).all(), "Negative tons_2025 detected"
        assert area_flow["origin_area_id"].nunique() == 132, "Not all 132 areas have outbound flow"
        assert area_flow["dest_area_id"].nunique()   == 132, "Not all 132 areas have inbound flow"
        ratio = area_flow["tons_2030"].sum() / total
        assert ratio > 1.0, f"Expected 2030 > 2025, got ratio={ratio:.4f}"
        print(
            f"  [8.2] ✓ Validation passed | "
            f"2030/2025 ratio = {ratio:.4f} (growth confirmed)"
        )

    def _save(self, area_flow: pd.DataFrame) -> None:
        out = self.cfg.AREA_FLOW_MATRIX
        area_flow.to_parquet(out, index=False)
        print(f"  [8.2] Saved → {out}  ({out.stat().st_size / 1024:.1f} KB)")
