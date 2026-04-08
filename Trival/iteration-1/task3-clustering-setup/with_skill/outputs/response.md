# Task 3 — Region Clustering: Notebook Setup and Section 1 (Demand Loading)

## Context Confirmed (Step 0)

Before writing a single cell, the retriever output was confirmed:

**Task objective (from Task.md):**
Task 3 — Region Clustering `[not started]`
Demand-balanced, geographically contiguous and compact clusters aligned to interstate corridors; justify parameters and assess quality.

**Target:** ~50 regions (paper §2.2 — K-means on county centroids, balance freight demand; quality metric ~148 miles / ~2.5h average region-crossing distance).

**Primary input confirmed (from Data.md):**
- `Data/Task1/raw.parquet` — 33,404,629 rows × 7 cols
  - `origin_county_fips` (int64), `dest_county_fips` (int64), `mode` (int64), `sctgG5` (object), `trade_type` (int64), `tons_2025` (float64), `tons_2030` (float64)
  - Tonnage units: **thousand short tons**
  - Commodity filter to apply: exclude SCTG coal and gravel (non-palletizable)

**Task 3 outputs to produce:**
- `Data/Task3/county_demand.csv` — per-county demand table (FIPS, lon, lat, tons_2025, tons_2030)
- `Data/Task3/region_assignments.csv` — county → region_id mapping
- `Data/Task3/region_centroids.csv` — per-region centroid and total demand
- `Data/Task3/distance_matrix.npy` — pairwise county centroid distance matrix (cache)
- `Data/Task3/regions.pkl` — list of Region objects (cache)

---

## Notebook Location

`Task3/task3_notebook.ipynb`

Create the `Task3/` directory alongside the existing `Task2/` folder.

---

## Notebook Plan (all sections)

| Section | Title | What it does |
|---------|-------|--------------|
| 3.1 | Imports & paths | Standard library setup, path constants |
| 3.2 | Load freight flows & compute county demand | Load raw.parquet, apply commodity filter, aggregate per-county demand, geocode county centroids |
| 3.3 | Distance matrix | Compute pairwise Haversine distances; cache to .npy |
| 3.4 | K-means clustering | Run sklearn K-means (k=50) on demand-weighted county coordinates; iterate k |
| 3.5 | Contiguity enforcement | Post-process to merge isolated counties into adjacent clusters |
| 3.6 | Quality assessment | Compute average region-crossing distance; compare to ~148 mi / 2.5h paper benchmark |
| 3.7 | Output serialization | Save region_assignments.csv, region_centroids.csv, regions.pkl |

This response covers **Section 3.1 and 3.2** in full, with all cells ready to paste.

---

## Section 3.1 — Imports and Path Constants

### Cell 1 — Markdown

```markdown
## 3.1 — Imports and Path Constants

This notebook implements **Task 3: Region Clustering** for the NE megaregion freight network.

**Objective:** Partition NE counties into ~50 demand-balanced, geographically contiguous regions
using K-means on county centroids with a freight-tonnage weighting objective, following §2.2
of the reference paper.

**Input:** `Data/Task1/raw.parquet` — county-to-county O-D matrix (all modes, 2025 & 2030)

**Outputs:**
- `Data/Task3/county_demand.csv` — per-county aggregated demand
- `Data/Task3/region_assignments.csv` — county → region_id mapping
- `Data/Task3/region_centroids.csv` — demand-weighted cluster centroids
- `Data/Task3/distance_matrix.npy` — pairwise Haversine distance cache
- `Data/Task3/regions.pkl` — serialized Region objects
```

### Cell 2 — Code

```python
# ── Imports ──────────────────────────────────────────────────────────────────
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

# ── Path constants ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path("/Users/tianyihu/Documents/Dev/Python/Projects/ISYE6339_Case2")

RAW_PARQUET   = PROJECT_ROOT / "Data" / "Task1" / "raw.parquet"
TASK3_DIR     = PROJECT_ROOT / "Data" / "Task3"
TASK3_DIR.mkdir(parents=True, exist_ok=True)

# Cache paths
DEMAND_CSV      = TASK3_DIR / "county_demand.csv"
DIST_NPY        = TASK3_DIR / "distance_matrix.npy"
ASSIGN_CSV      = TASK3_DIR / "region_assignments.csv"
CENTROIDS_CSV   = TASK3_DIR / "region_centroids.csv"
REGIONS_PKL     = TASK3_DIR / "regions.pkl"

# ── Key parameters ────────────────────────────────────────────────────────────
N_REGIONS_TARGET = 50        # target cluster count (§2.2)
TRUCK_MODE       = 2         # FAF mode code for truck
# SCTG groups to exclude (non-palletizable: coal, gravel)
SCTG_EXCLUDE     = {"sctg1500", "sctg2400"}   # coal=15xx, gravel/stone=24xx prefixes

print(f"Task3 output dir: {TASK3_DIR}")
print(f"raw.parquet:      {RAW_PARQUET.exists()}")
```

### Cell 3 — Sanity check

```python
# Verify the input file is present before proceeding
assert RAW_PARQUET.exists(), f"raw.parquet not found at {RAW_PARQUET}"
print("✓ Input file confirmed.")
```

---

## Section 3.2 — Load Freight Flows and Compute County-Level Demand

### Cell 4 — Markdown

```markdown
## 3.2 — Load Freight Flows and Compute County-Level Demand

The per-county demand $d_i$ is the sum of all truck-mode flows for which county $i$
appears as **origin or destination**, after excluding non-palletizable SCTG groups
(coal, gravel):

$$d_i = \sum_{j} \bigl(f_{ij} + f_{ji}\bigr) \cdot \mathbf{1}[\text{mode}=\text{truck}]
         \cdot \mathbf{1}[\text{sctg} \notin \text{excluded}]$$

where $f_{ij}$ is the 2025 truck tonnage on the O→D pair $(i, j)$.

This produces a **symmetric demand signal** — a county with high both outbound and inbound
freight registers high total demand, which appropriately anchors it as a cluster seed.

County centroids (lon, lat) are sourced from the US Census TIGER county centroid file,
joined on 5-digit FIPS.
```

### Cell 5 — Code: load and filter raw.parquet

```python
# ── Load raw O-D matrix ───────────────────────────────────────────────────────
# The file is large (~33M rows); read only the columns we need.
COLS_NEEDED = ["origin_county_fips", "dest_county_fips", "mode", "sctgG5",
               "tons_2025", "tons_2030"]

print("Loading raw.parquet (this may take ~30s on first load)...")
df_raw = pd.read_parquet(RAW_PARQUET, columns=COLS_NEEDED)
print(f"  Loaded: {len(df_raw):,} rows × {df_raw.shape[1]} cols")

# ── Apply commodity filter: keep only truck-compatible (non-coal, non-gravel) ─
mask_mode  = df_raw["mode"] == TRUCK_MODE
# Exclude rows whose sctgG5 starts with any excluded prefix
mask_sctg  = ~df_raw["sctgG5"].str[:8].isin(SCTG_EXCLUDE)
mask_valid = mask_mode & mask_sctg

df_truck = df_raw.loc[mask_valid].copy()
del df_raw   # free ~33M row frame immediately

print(f"  After truck + commodity filter: {len(df_truck):,} rows "
      f"({len(df_truck)/mask_valid.shape[0]*100:.1f}% retained)")
```

### Cell 6 — Sanity check on filter

```python
# Confirm no excluded SCTG codes remain; confirm mode is exclusively truck
assert df_truck["mode"].unique().tolist() == [TRUCK_MODE], \
    "Non-truck modes present after filter"
assert not df_truck["sctgG5"].str[:8].isin(SCTG_EXCLUDE).any(), \
    "Excluded SCTG groups still present after filter"
assert (df_truck["tons_2025"] >= 0).all(), \
    "Negative tons_2025 values found — data integrity issue"

print(f"✓ Mode filter OK: all rows are mode={TRUCK_MODE} (Truck)")
print(f"✓ Commodity filter OK: no coal/gravel SCTG groups present")
print(f"✓ tons_2025 all non-negative")
print(f"  SCTG groups remaining: {df_truck['sctgG5'].nunique()} unique codes")
```

### Cell 7 — Code: aggregate per-county demand

```python
# ── Aggregate demand per county ───────────────────────────────────────────────
# A county's demand = sum of tons where it appears as origin + sum where it appears as dest.
# This symmetrizes the signal: high-traffic counties appear large regardless of direction.

origin_demand = (
    df_truck.groupby("origin_county_fips")[["tons_2025", "tons_2030"]]
    .sum()
    .rename(columns={"tons_2025": "origin_tons_2025", "tons_2030": "origin_tons_2030"})
)

dest_demand = (
    df_truck.groupby("dest_county_fips")[["tons_2025", "tons_2030"]]
    .sum()
    .rename(columns={"tons_2025": "dest_tons_2025", "tons_2030": "dest_tons_2030"})
)

del df_truck   # free filtered frame

# Outer join so counties that only appear as origins or only as destinations are retained
county_demand = (
    origin_demand
    .join(dest_demand, how="outer")
    .fillna(0.0)
)
county_demand["tons_2025"] = county_demand["origin_tons_2025"] + county_demand["dest_tons_2025"]
county_demand["tons_2030"] = county_demand["origin_tons_2030"] + county_demand["dest_tons_2030"]
county_demand = county_demand[["tons_2025", "tons_2030"]].reset_index()
county_demand.rename(columns={"origin_county_fips": "county_fips"}, inplace=True)

# Ensure FIPS is a zero-padded 5-char string for reliable joins
county_demand["county_fips"] = county_demand["county_fips"].astype(str).str.zfill(5)

print(f"County-level demand aggregated: {len(county_demand):,} unique counties")
print(county_demand[["tons_2025", "tons_2030"]].describe().round(1))
```

### Cell 8 — Code: join county centroids (Census TIGER)

```python
# ── Fetch county centroids from Census TIGER via pygris ───────────────────────
# pygris wraps the Census TIGER API and returns a GeoDataFrame with geometry.
# We extract the internal point (INTPTLAT / INTPTLON) as centroid proxy.
#
# If pygris is unavailable, fall back to the Census FTP file:
#   https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt

try:
    import pygris
    gdf_counties = pygris.counties(year=2020, cb=True)
    gdf_counties = gdf_counties[["GEOID", "INTPTLAT", "INTPTLON"]].copy()
    gdf_counties.rename(columns={
        "GEOID": "county_fips",
        "INTPTLAT": "lat",
        "INTPTLON": "lon"
    }, inplace=True)
    gdf_counties["lat"] = gdf_counties["lat"].astype(float)
    gdf_counties["lon"] = gdf_counties["lon"].astype(float)
    centroid_source = "pygris (Census TIGER 2020)"

except ImportError:
    # Fallback: read Census population-weighted centroid file
    CEN_URL = (
        "https://www2.census.gov/geo/docs/reference/cenpop2020/county/"
        "CenPop2020_Mean_CO.txt"
    )
    gdf_counties = pd.read_csv(CEN_URL, encoding="latin-1", dtype={"COUNTYFP": str, "STATEFP": str})
    gdf_counties["county_fips"] = gdf_counties["STATEFP"].str.zfill(2) + gdf_counties["COUNTYFP"].str.zfill(3)
    gdf_counties = gdf_counties.rename(columns={"LATITUDE": "lat", "LONGITUDE": "lon"})
    gdf_counties = gdf_counties[["county_fips", "lat", "lon"]]
    centroid_source = "Census CenPop2020 (population-weighted centroids)"

print(f"Centroid source: {centroid_source}")
print(f"Counties with centroid data: {len(gdf_counties):,}")
```

### Cell 9 — Code: merge and finalize county_demand table

```python
# ── Merge demand with centroids ───────────────────────────────────────────────
county_df = county_demand.merge(gdf_counties, on="county_fips", how="inner")

n_dropped = len(county_demand) - len(county_df)
if n_dropped > 0:
    print(f"  Warning: {n_dropped} counties dropped (no centroid match) — "
          f"likely non-contiguous territories (e.g. PR, VI). Review if > 5.")

# Drop any rows with null coordinates or zero demand
county_df = county_df.dropna(subset=["lat", "lon"])
county_df = county_df[county_df["tons_2025"] > 0].reset_index(drop=True)

print(f"Final county_demand table: {len(county_df):,} counties with non-zero truck demand")
print(county_df.head(3))
```

### Cell 10 — Code: serialize county_demand.csv + enter compute layer

```python
# ── Serialize snapshot (pandas → CSV) ─────────────────────────────────────────
county_df.to_csv(DEMAND_CSV, index=False)
print(f"Saved: {DEMAND_CSV}")

# ── Enter compute layer (pandas → numpy) ──────────────────────────────────────
# From here, all geometry and demand operations use numpy arrays.
fips_arr    = county_df["county_fips"].to_numpy()          # shape (N,)  — string IDs
coords_arr  = county_df[["lat", "lon"]].to_numpy()         # shape (N, 2) — degrees
demand_arr  = county_df["tons_2025"].to_numpy()            # shape (N,)  — kton
demand_2030 = county_df["tons_2030"].to_numpy()            # shape (N,)  — kton

N = len(fips_arr)
print(f"Compute layer initialized: {N} counties")
print(f"  coords_arr shape : {coords_arr.shape}")
print(f"  demand_arr shape : {demand_arr.shape}")
print(f"  total demand 2025: {demand_arr.sum():,.1f} thousand short tons")
print(f"  total demand 2030: {demand_2030.sum():,.1f} thousand short tons")
```

### Cell 11 — Sanity checks for Section 3.2

```python
# ── Section 3.2 sanity checks ─────────────────────────────────────────────────
# 1. County count is reasonable for the NE megaregion
#    NE has ~14 states × ~50–100 counties each; expect 400–900 counties with truck demand
assert 300 <= N <= 1000, \
    f"Unexpected county count {N} — check FIPS filter or centroid join"

# 2. All demand values are positive (filter already dropped zeros, but verify arrays)
assert (demand_arr > 0).all(), \
    "Zero or negative demand in compute array — check aggregation step"

# 3. Coordinates are within continental US bounding box
assert coords_arr[:, 0].min() >= 24.0,  "Latitude below 24° N — unexpected territory"
assert coords_arr[:, 0].max() <= 50.0,  "Latitude above 50° N — unexpected territory"
assert coords_arr[:, 1].min() >= -85.0, "Longitude west of -85° — outside NE megaregion"
assert coords_arr[:, 1].max() <= -65.0, "Longitude east of -65° — outside NE megaregion"

# 4. Total demand should be in a plausible range
#    From breakdown_by_flow_type.csv: internal + inbound + outbound truck is ~2.38M kton
#    Per-county aggregation double-counts (origin + dest), so expect ~4–5M kton total
total_2025 = demand_arr.sum()
assert 1_000 < total_2025 < 10_000_000, \
    f"Total demand {total_2025:,.0f} kton is outside plausible range"

print(f"✓ County count: {N} (within 300–1000 range)")
print(f"✓ All demand values positive")
print(f"✓ All coordinates within NE megaregion bounding box")
print(f"✓ Total 2025 demand: {total_2025:,.1f} thousand short tons")
print(f"  Demand range: [{demand_arr.min():,.1f}, {demand_arr.max():,.1f}] kton/county")
print(f"  Median county demand: {np.median(demand_arr):,.1f} kton")
```

---

## Milestone Gate — Section 3.2 Complete

Once the sanity checks above print all ✓ lines, present this to the user:

```
Subtask complete: 3.2 — Load freight flows and compute county-level demand
Outputs saved:
  - Data/Task3/county_demand.csv  (county_fips, tons_2025, tons_2030, lat, lon)
Compute-layer arrays initialized:
  - fips_arr    shape (N,)   — county FIPS strings
  - coords_arr  shape (N, 2) — (lat, lon) in degrees
  - demand_arr  shape (N,)   — 2025 truck tonnage, thousand short tons
Sanity checks passed:
  - N counties confirmed in 300–1000 range
  - All demand > 0
  - All coordinates within NE bounding box
  - Total demand plausible

Proceed with commit? (y/n)
```

If yes, run:
```bash
./git_tools.sh sync "Task 3 — 3.2 county demand load and compute layer init"
```

---

## What Comes Next (Preview)

**Section 3.3** will use `coords_arr` to compute a pairwise Haversine distance matrix
(shape N×N) and save it to `Data/Task3/distance_matrix.npy`. Because this is O(N²) and
N ≈ 600, it runs in ~1s with numpy broadcasting — no scipy cdist needed. The cache
pattern from SKILL.md Step 4 will be applied so subsequent runs skip the computation.

**Section 3.4** will pass `coords_arr` (optionally demand-weighted via repeat/tile tricks)
into `sklearn.cluster.KMeans(n_clusters=50)`, then iterate k ∈ {40, 45, 50, 55, 60} to
find the k that minimizes intra-cluster demand variance while keeping average cluster size
above a floor.

**Section 3.5** will use `libpysal.weights.Queen` to build a county adjacency graph and
enforce contiguity via a union-find merge of isolated counties into their nearest neighbor.
