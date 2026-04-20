"""
recompute_region_external_demand.py — Post-assignment outside-region demand recomputation

After Task 3.2 writes region_assignment.csv, this script reloads
Data/Task1/raw.parquet and credits each region only with flows where the
other endpoint is OUTSIDE that final region.  This removes the double-counting
present in the SA-stage NE-boundary approximation (which kept all intra-NE flows).

Outputs
-------
Data/Task3/outputs/region_external_metrics.csv

Run with
--------
    conda run -n General_env python Task3/recompute_region_external_demand.py

Schema of region_external_metrics.csv
--------------------------------------
region_id                   int    Task 3.2 region label [0, 49]
n_counties                  int    Counties in the region
external_in_ktons           float  Tonnage entering region from any county outside it
external_out_ktons          float  Tonnage leaving region to any county outside it
external_throughput_ktons   float  external_in + external_out (hub-facing demand)
ne_non_ne_in_ktons          float  Subset: other endpoint is non-NE
ne_non_ne_out_ktons         float  Subset: other endpoint is non-NE
inter_region_in_ktons       float  Subset: other endpoint is NE but different region
inter_region_out_ktons      float  Subset: other endpoint is NE but different region
same_region_excluded_ktons  float  Raw tonnage removed (both endpoints same final region)
"""

from pathlib import Path
import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJ_ROOT        = Path(__file__).parent.parent
RAW_PARQUET      = PROJ_ROOT / "Data" / "Task1" / "raw.parquet"
REGION_ASSIGN    = PROJ_ROOT / "Data" / "Task3" / "outputs" / "region_assignment.csv"
OUTPUT_CSV       = PROJ_ROOT / "Data" / "Task3" / "outputs" / "region_external_metrics.csv"

NE_STATE_FIPS    = {'54', '51', '24', '10', '11', '42', '36', '34',
                    '09', '25', '33', '50', '23', '44'}
EXCLUDE_SCTG     = {'sctg1014', 'sctg1519'}


def main() -> None:
    print("Loading region assignment ...")
    assign = pd.read_csv(REGION_ASSIGN)
    assign["fips"] = assign["fips"].astype(str).str.zfill(5)
    fips_to_region = dict(zip(assign["fips"], assign["region_id"].astype(int)))
    n_counties_per_region = assign.groupby("region_id").size()
    print(f"  {len(assign)} counties  |  {assign['region_id'].nunique()} regions")

    print("Loading and filtering raw O-D parquet ...")
    df = pd.read_parquet(RAW_PARQUET)
    df = df[~df["sctgG5"].isin(EXCLUDE_SCTG)].copy()
    df["origin_county_fips"] = df["origin_county_fips"].astype(str).str.zfill(5)
    df["dest_county_fips"]   = df["dest_county_fips"].astype(str).str.zfill(5)
    print(f"  {len(df):,} rows after commodity filter")

    # Tag origin/dest with NE membership and final region
    df["orig_ne"]     = df["origin_county_fips"].str[:2].isin(NE_STATE_FIPS)
    df["dest_ne"]     = df["dest_county_fips"].str[:2].isin(NE_STATE_FIPS)
    df["orig_region"] = df["origin_county_fips"].map(fips_to_region).astype("Int64")
    df["dest_region"] = df["dest_county_fips"].map(fips_to_region).astype("Int64")

    regions = sorted(assign["region_id"].unique())
    rows = []

    print(f"Computing per-region external demand for {len(regions)} regions ...")
    for r in regions:
        orig_in_r = df["orig_region"] == r
        dest_in_r = df["dest_region"] == r

        # External out: origin in r, dest NOT in r (NE other region or non-NE)
        ext_out_mask = orig_in_r & (df["dest_region"] != r)
        ext_out      = df.loc[ext_out_mask, "tons_2025"].sum()

        # External in: dest in r, origin NOT in r
        ext_in_mask  = dest_in_r & (df["orig_region"] != r)
        ext_in       = df.loc[ext_in_mask, "tons_2025"].sum()

        # NE-to-non-NE subset
        ne_non_ne_out = df.loc[orig_in_r & ~df["dest_ne"], "tons_2025"].sum()
        ne_non_ne_in  = df.loc[dest_in_r & ~df["orig_ne"], "tons_2025"].sum()

        # Inter-region subset (NE–NE but different final region)
        inter_out = df.loc[orig_in_r &  df["dest_ne"] & (df["dest_region"] != r), "tons_2025"].sum()
        inter_in  = df.loc[dest_in_r &  df["orig_ne"] & (df["orig_region"] != r), "tons_2025"].sum()

        # Same-region excluded (both endpoints in same final region r)
        same_r = df.loc[orig_in_r & (df["dest_region"] == r), "tons_2025"].sum()

        rows.append({
            "region_id":                 r,
            "n_counties":                int(n_counties_per_region.get(r, 0)),
            "external_in_ktons":         float(ext_in),
            "external_out_ktons":        float(ext_out),
            "external_throughput_ktons": float(ext_in + ext_out),
            "ne_non_ne_in_ktons":        float(ne_non_ne_in),
            "ne_non_ne_out_ktons":       float(ne_non_ne_out),
            "inter_region_in_ktons":     float(inter_in),
            "inter_region_out_ktons":    float(inter_out),
            "same_region_excluded_ktons": float(same_r),
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUTPUT_CSV, index=False)

    print(f"\nSaved: {OUTPUT_CSV}")
    print(result[["region_id", "external_throughput_ktons", "same_region_excluded_ktons"]].describe().round(1).to_string())

    # Validation
    total_ext  = result["external_throughput_ktons"].sum()
    total_same = result["same_region_excluded_ktons"].sum()
    print(f"\nTotal external throughput across all regions: {total_ext:,.0f} k-tons")
    print(f"Total same-region excluded:                   {total_same:,.0f} k-tons")

    assert (result["same_region_excluded_ktons"] > 0).any(), \
        "No same-region flows excluded — check logic or region_assignment.csv"
    assert (result["external_throughput_ktons"] >= 0).all(), \
        "Negative external throughput — check aggregation"
    print("✓ Validation passed")


if __name__ == "__main__":
    main()
