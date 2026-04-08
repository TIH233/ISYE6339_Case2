# Task 3 — Region Clustering Notebook: Setup and Section 1

## Overview

Task 3 clusters the NE megaregion counties into roughly 50 demand-balanced, geographically contiguous regions following the methodology in §2.2 of the reference paper. The first step is to build a county-level demand table from the Task 1 flow matrix, then attach spatial geometry (centroids) so the clustering step has both a freight-weight and a geographic anchor.

---

## Notebook Plan

The notebook (`Task3/casework2_task3.ipynb`) will be organized into the following sections:

| Section | Title | Purpose |
|---------|-------|---------|
| 0 | Setup & Paths | Imports, path definitions, constants |
| 1 | Load Freight Data & Compute County Demand | Read `raw.parquet`; apply commodity/mode filters; compute per-county inbound + outbound + internal demand |
| 2 | Attach County Geometry | Join demand table to TIGER/Line shapefile; compute centroids |
| 3 | K-Means Clustering | Demand-weighted k-means on lat/lon; target k=50 |
| 4 | Contiguity Post-processing | Merge non-contiguous fragments into neighbors |
| 5 | Quality Assessment | Within-cluster demand CV, region-crossing distance, compactness ratio |
| 6 | Export & Visualization | Save cluster assignments; choropleth map |

This response covers **Sections 0 and 1** in full, ready to paste into the notebook.

---

## Section 0 — Setup & Paths

```python
# ── Section 0: Setup & Paths ──────────────────────────────────────────────────
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from pathlib import Path

# ── Project root (notebook lives in Task3/, one level below project root) ──
ROOT = Path.cwd().parent           # adjust if you run from a different location
DATA_T1 = ROOT / "Data" / "Task1"
DATA_T3 = ROOT / "Data" / "Task3"
DATA_T3.mkdir(parents=True, exist_ok=True)

# ── Constants ────────────────────────────────────────────────────────────────
YEAR      = "2025"          # primary planning year
K_TARGET  = 50              # target number of regions (paper: ~50)
RANDOM_STATE = 42

# Non-palletizable commodity groups to exclude (§2.1 of paper)
# These are the SCTG group codes for coal and gravel/stone
EXCLUDE_SCTG = {"sctg1516", "sctg2428"}   # coal=15-16, gravel/crushed stone=24-28
                                            # adjust exact codes if your encoding differs

# Truck-compatible mode codes to retain (focus: truck primary, but include all
# truck-compatible modes for total demand estimation per §2.1)
TRUCK_MODES = {2, 5, 11}    # 2=Truck, 5=Multi-mode/Mail, 11=Truck+Air

print("ROOT  :", ROOT)
print("DATA  :", DATA_T1)
print("OUTPUT:", DATA_T3)
```

**Notes on path setup:**
- `ROOT` is set to `Path.cwd().parent` because the notebook will live in `Task3/`. If you open the notebook from a different working directory, change `ROOT` accordingly (e.g., hard-code it as `Path("/Users/.../ISYE6339_Case2")`).
- `DATA_T3` is created now so all subsequent saves in the section work without manual folder creation.
- `EXCLUDE_SCTG` uses the `sctgG5` group-code string format used in `raw.parquet` (e.g., `"sctg1516"`, `"sctg2428"`). Verify exact strings against the parquet after loading — the commodity filter is the most likely source of mismatch.

---

## Section 1 — Load Freight Data & Compute County-Level Demand

### Cell 1-A: Load raw.parquet and apply filters

```python
# ── Section 1-A: Load raw.parquet ────────────────────────────────────────────
RAW_PATH = DATA_T1 / "raw.parquet"

print(f"Loading {RAW_PATH} ...")
raw = pd.read_parquet(RAW_PATH)
print(f"  Shape (raw)          : {raw.shape}")
print(f"  Columns              : {list(raw.columns)}")
print(f"  Unique modes         : {sorted(raw['mode'].unique())}")
print(f"  Unique sctgG5 groups : {sorted(raw['sctgG5'].unique())}")
print(f"  Unique trade_types   : {sorted(raw['trade_type'].unique())}")
```

This cell just loads and inspects — no filtering yet. Run it first to confirm the exact `sctgG5` strings for coal and gravel so you can set `EXCLUDE_SCTG` correctly in Section 0 if needed.

### Cell 1-B: Apply commodity and mode filters

```python
# ── Section 1-B: Commodity & Mode Filters ─────────────────────────────────────
n_before = len(raw)

# 1. Drop non-palletizable commodity groups (coal, gravel/crushed stone)
mask_sctg = ~raw["sctgG5"].isin(EXCLUDE_SCTG)

# 2. Retain only truck-compatible modes
mask_mode = raw["mode"].isin(TRUCK_MODES)

flows = raw[mask_sctg & mask_mode].copy()
n_after = len(flows)

print(f"Records before filter : {n_before:,}")
print(f"Records after filter  : {n_after:,}  ({100*n_after/n_before:.1f}% retained)")
print(f"\nMode split after filter:")
print(flows["mode"].value_counts().rename({2: "Truck", 5: "Multi/Mail", 11: "Truck+Air"}))
print(f"\nTop 10 commodity groups by tonnage (2025):")
print(
    flows.groupby("sctgG5")["tons_2025"]
    .sum()
    .sort_values(ascending=False)
    .head(10)
    .apply(lambda x: f"{x:,.1f} ktons")
)
```

**Why this filter matters:** The paper (§2.1) explicitly removes coal and gravel because those commodities require bulk handling equipment incompatible with a pallet-based hyperconnected hub network. Retaining them would artificially inflate demand in mining/quarry counties and distort cluster boundaries.

### Cell 1-C: Compute per-county demand metrics

The paper uses the **larger of inbound or outbound** flow as the county's peak-demand proxy (§2.1). We compute four metrics per county:

- `tons_inbound` — sum of all flows where this county is the destination
- `tons_outbound` — sum of all flows where this county is the origin
- `tons_internal` — flows where this county is both origin and destination (within-county)
- `tons_total` — inbound + outbound + internal (gross throughput)
- `tons_demand` — max(inbound, outbound); used as the clustering weight

```python
# ── Section 1-C: Per-County Demand Aggregation ────────────────────────────────
YEAR_COL = f"tons_{YEAR}"   # "tons_2025"

# --- Inbound demand: flows arriving AT this county ---
inbound = (
    flows
    .groupby("dest_county_fips")[YEAR_COL]
    .sum()
    .rename("tons_inbound")
)

# --- Outbound demand: flows departing FROM this county ---
outbound = (
    flows
    .groupby("origin_county_fips")[YEAR_COL]
    .sum()
    .rename("tons_outbound")
)

# --- Internal demand: origin == destination ---
internal_mask = flows["origin_county_fips"] == flows["dest_county_fips"]
internal = (
    flows[internal_mask]
    .groupby("origin_county_fips")[YEAR_COL]
    .sum()
    .rename("tons_internal")
)

# --- Assemble county demand table ---
# Build the union of all NE counties that appear in any role
all_fips = pd.Index(
    pd.concat([
        flows["origin_county_fips"],
        flows["dest_county_fips"]
    ]).unique(),
    name="county_fips"
)

county_demand = (
    pd.DataFrame(index=all_fips)
    .join(inbound,  how="left")
    .join(outbound, how="left")
    .join(internal, how="left")
    .fillna(0.0)
    .reset_index()
)

# Gross throughput and peak-demand weight
county_demand["tons_total"]  = (
    county_demand["tons_inbound"] +
    county_demand["tons_outbound"] +
    county_demand["tons_internal"]
)
county_demand["tons_demand"] = county_demand[["tons_inbound", "tons_outbound"]].max(axis=1)

# Pad FIPS to 5-digit string for joins downstream
county_demand["county_fips"] = county_demand["county_fips"].astype(str).str.zfill(5)

print(f"Counties in demand table : {len(county_demand):,}")
print(f"\nDemand summary ({YEAR}, thousand short tons):")
print(county_demand[["tons_inbound","tons_outbound","tons_internal","tons_total","tons_demand"]]
      .describe()
      .applymap(lambda x: f"{x:,.1f}"))
```

### Cell 1-D: Sanity checks

```python
# ── Section 1-D: Sanity Checks ────────────────────────────────────────────────

# 1. Total megaregion tonnage should be in the right ballpark
#    From Task 1 breakdown_by_flow_type.csv:
#      Internal ~1.1M, Inbound ~0.6M, Outbound ~0.7M (approximate ktons)
total_inbound  = county_demand["tons_inbound"].sum()
total_outbound = county_demand["tons_outbound"].sum()
total_internal = county_demand["tons_internal"].sum() / 2   # each internal pair counted once

print("Megaregion totals (truck-compatible modes, excl. coal/gravel):")
print(f"  Sum of county inbound  : {total_inbound:>12,.1f} ktons")
print(f"  Sum of county outbound : {total_outbound:>12,.1f} ktons")
print(f"  Sum of county internal : {total_internal:>12,.1f} ktons (halved for double-count)")

# 2. Top 10 counties by demand weight — should align with Task 1 top-50 lists
print("\nTop 10 counties by tons_demand:")
print(
    county_demand.nlargest(10, "tons_demand")[
        ["county_fips", "tons_inbound", "tons_outbound", "tons_demand"]
    ].to_string(index=False)
)

# 3. Zero-demand counties (should be few or none after filter)
n_zero = (county_demand["tons_demand"] == 0).sum()
print(f"\nCounties with zero demand weight : {n_zero}")
if n_zero > 0:
    print("  These will get equal weight in clustering — consider dropping or imputing.")
```

### Cell 1-E: Save county demand table

```python
# ── Section 1-E: Save County Demand Table ─────────────────────────────────────
out_path = DATA_T3 / "county_demand.csv"
county_demand.to_csv(out_path, index=False)
print(f"Saved: {out_path}")
print(f"Shape: {county_demand.shape}")
print(county_demand.dtypes)
```

---

## What Section 1 Produces

After running all Section 1 cells, you will have:

| Output | Location | Description |
|--------|----------|-------------|
| `county_demand` (DataFrame) | in-memory | One row per NE county; columns: `county_fips`, `tons_inbound`, `tons_outbound`, `tons_internal`, `tons_total`, `tons_demand` |
| `Data/Task3/county_demand.csv` | disk | Same table, persisted for downstream cells |

`tons_demand` is the clustering weight: the larger of inbound or outbound tonnage, consistent with §2.1 of the paper's approach of sizing infrastructure to the dominant directional flow.

---

## What Comes Next (Section 2 Preview)

The next section will:

1. Download or load the TIGER/Line county shapefile (Census Bureau, 2023 vintage is standard) — `geopandas.read_file()` from a local path or the Census URL
2. Join `county_demand` to the shapefile on `GEOID` (= 5-digit FIPS)
3. Reproject to EPSG:5070 (Albers Equal Area, suitable for CONUS distance and area calculations)
4. Extract `centroid_lon` and `centroid_lat` columns — the spatial coordinates that will feed directly into k-means
5. Produce a choropleth of `tons_demand` across NE counties as a visual check before clustering

The county shapefile path to prepare for Section 2:

```
# Expected location (add to Section 0 after you place the file):
COUNTY_SHP = ROOT / "Data" / "GIS" / "tl_2023_us_county" / "tl_2023_us_county.shp"
```

You can download it from: https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip

---

## Key Implementation Notes

- **Double-counting of internal flows:** An internal flow (origin == destination) is a within-county trip and should not be double-counted when summing gross throughput. Section 1-C halves it in the sanity check, but `tons_internal` in the saved table is the raw sum (one record per pair direction) — be consistent downstream.
- **Commodity code verification:** Run Cell 1-A first and print `sorted(raw['sctgG5'].unique())` before assuming `EXCLUDE_SCTG` is correct. The exact string encoding (e.g., `"sctg1516"` vs `"SCTG15"`) must match.
- **Mode 3 (Water) is excluded:** This is intentional. Maritime flows are handled by the global interface nodes identified in Task 2 and should not drive county-level truck clustering.
- **Demand weight for k-means:** Using `max(inbound, outbound)` rather than `inbound + outbound` avoids double-counting transit counties (high inbound AND outbound) as artificially high-demand.
