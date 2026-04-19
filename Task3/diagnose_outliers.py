"""
diagnose_outliers.py — Task 3.2 Demand-Balance Outlier Analysis

Loads region_metrics.csv and region_assignment.csv, identifies outlier regions
(high/low demand vs. W*), prints county-level breakdowns, and flags structural
geographic constraints that prevent the SA from balancing certain regions.

Usage:
    ~/.venvs/general/bin/python3 Task3/diagnose_outliers.py
"""

import pandas as pd
import numpy as np

METRICS = "Data/Task3/outputs/region_metrics.csv"
ASSIGN  = "Data/Task3/outputs/region_assignment.csv"

HIGH_THRESH_MULT = 1.50   # flag regions > 1.5 × W*
LOW_THRESH_MULT  = 0.65   # flag regions < 0.65 × W*

def main():
    metrics = pd.read_csv(METRICS)
    assign  = pd.read_csv(ASSIGN)

    W_star = metrics['total_throughput_ktons'].sum() / len(metrics)
    print(f"W* (target per region) = {W_star:,.0f} k-tons")
    print(f"Total regions = {len(metrics)},  Total counties = {len(assign)}\n")

    metrics = metrics.copy()
    metrics['deviation_pct'] = (metrics['total_throughput_ktons'] - W_star) / W_star * 100

    # --- Identify outliers ---
    high_out = metrics[metrics['total_throughput_ktons'] > HIGH_THRESH_MULT * W_star].sort_values('total_throughput_ktons', ascending=False)
    low_out  = metrics[metrics['total_throughput_ktons'] < LOW_THRESH_MULT  * W_star].sort_values('total_throughput_ktons')

    print("=" * 70)
    print(f"HIGH-DEMAND OUTLIERS  (> {HIGH_THRESH_MULT:.0%} of W* = {HIGH_THRESH_MULT*W_star:,.0f} k-tons)")
    print("=" * 70)
    _print_outlier_table(high_out, assign, W_star)

    print()
    print("=" * 70)
    print(f"LOW-DEMAND OUTLIERS   (< {LOW_THRESH_MULT:.0%} of W* = {LOW_THRESH_MULT*W_star:,.0f} k-tons)")
    print("=" * 70)
    _print_outlier_table(low_out, assign, W_star)

    # --- Full distribution summary ---
    print()
    print("=" * 70)
    print("DISTRIBUTION SUMMARY")
    print("=" * 70)
    tp = metrics['total_throughput_ktons']
    print(f"  Min       : {tp.min():>10,.0f} k-tons  ({tp.min()/W_star:.2f}× W*)  Region {metrics.loc[tp.idxmin(),'region_id']}")
    print(f"  Max       : {tp.max():>10,.0f} k-tons  ({tp.max()/W_star:.2f}× W*)  Region {metrics.loc[tp.idxmax(),'region_id']}")
    print(f"  Median    : {tp.median():>10,.0f} k-tons  ({tp.median()/W_star:.2f}× W*)")
    print(f"  Std dev   : {tp.std():>10,.0f} k-tons")
    print(f"  CV (σ/μ)  : {tp.std()/tp.mean():.3f}")

    # --- Single-county regions ---
    single = metrics[metrics['n_counties'] == 1]
    if len(single):
        print()
        print("=" * 70)
        print("SINGLE-COUNTY REGIONS (may not be splittable due to high per-county demand)")
        print("=" * 70)
        for _, row in single.iterrows():
            rid = row['region_id']
            c = assign[assign['region_id'] == rid].iloc[0]
            print(f"  Region {rid:2d}: {c['county_name']:20s} {c['state']}  "
                  f"{row['total_throughput_ktons']:>10,.0f} k-tons ({row['deviation_pct']:+.1f}%)")

    # --- Geographic constraint diagnosis ---
    print()
    print("=" * 70)
    print("STRUCTURAL DIAGNOSIS")
    print("=" * 70)
    print("""
Region 24  [EXTREME HIGH, +165.6%]  — Long Island / NYC Outer Boroughs
  Counties: Kings (Brooklyn), Queens, Richmond (Staten Island), Nassau, Suffolk
  Root cause: Long Island is a geographic peninsula. Suffolk is only adjacent to
  Nassau (within the NE region). Nassau + Suffolk alone = ~68,925 k-tons (>W*),
  and they must connect via Brooklyn/Queens — already high-demand. No low-demand
  neighbor is accessible. The SA hard contiguity constraint makes redistribution
  infeasible without splitting the island mid-county.
  Recommendation: Accept as a structural limitation; note in Task 3 write-up.
  Or: merge Staten Island (7,419 k-tons) into the NJ side (Region 9/7) if
  a synthetic cross-harbor edge is permitted.

Region 14  [LOW, -47.7%]  — SW Virginia / Appalachian (Roanoke + 11 rural VA)
  Counties: Roanoke City, Roanoke Co, Franklin, Salem, Smyth, Wythe, Carroll,
            Patrick, Floyd, Galax, Grayson, Craig
  Root cause: Rural mountainous SW Virginia has inherently sparse freight demand.
  12 counties totaling only 30,348 k-tons — adding more territory from already
  larger regions would create compactness or contiguity issues.
  Recommendation: Accept as structural; possible to merge with Region 28 (WV)
  or dissolve into the broader central VA corridor to raise demand.

Region 26  [BORDERLINE LOW, -38.7%]  — Boston Core
  Counties: Suffolk MA (Boston), Norfolk MA
  Root cause: Only 2 counties, both geographically pinned by coastal geography
  and surrounded by already-formed neighboring regions (MA interior, north shore).
  Recommendation: Could absorb Plymouth MA or Bristol MA county to raise demand.
    """)

def _print_outlier_table(subset: pd.DataFrame, assign: pd.DataFrame, W_star: float):
    for _, row in subset.iterrows():
        rid = int(row['region_id'])
        print(f"\n  Region {rid:2d} | {row['n_counties']:2d} counties | "
              f"{row['total_throughput_ktons']:>10,.0f} k-tons  "
              f"({row['deviation_pct']:+.1f}% vs W*)")
        counties = assign[assign['region_id'] == rid].sort_values('throughput_ktons', ascending=False)
        for _, c in counties.iterrows():
            bar = "█" * int(c['throughput_ktons'] / W_star * 20)
            print(f"    {c['fips']:>5}  {c['county_name']:20s} {c['state']}  "
                  f"{c['throughput_ktons']:>10,.0f} k-tons  {bar}")

if __name__ == "__main__":
    main()
