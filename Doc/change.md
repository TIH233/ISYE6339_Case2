# Change Instructions

This file is the work queue for correcting demand metrics that currently use
bidirectional endpoint throughput. Each item must carry one of these tags:

- `[fixed]` — implemented and verified in code/data/docs
- `[not fixed]` — identified but not yet implemented

## Demand Definition Change

### [fixed] Replace all-flow bidirectional throughput for hub-facing demand

**Problem**

Task 3 currently computes county throughput as:

```text
throughput_i = sum_j T_ij + sum_j T_ji
```

This counts every retained 2025 O-D row at both endpoints when both counties are
inside the NE megaregion. It also counts same-county and same-final-region flow
twice. That is acceptable for a general demand heatmap, but it is not reliable
for later regional hub location and capacity decisions because a regional hub is
intended to serve inter-node / external-to-region freight, not freight that
stays inside the same final region.

**New principle**

For hub-facing regional demand, do not use internal-within-region flow. Recompute
the demand from `Data/Task1/raw.parquet` after the Task 3 region assignment is
known.

For each retained O-D row with 2025 tonnage `T`:

```text
origin_region = region_assignment[origin_county_fips] if origin is a Task 3 NE county
dest_region   = region_assignment[dest_county_fips]   if dest is a Task 3 NE county
```

Credit demand to a region only when the paired county is outside that same
region:

```text
if origin_region == r and dest_region != r:
    region_external_out_r += T

if dest_region == r and origin_region != r:
    region_external_in_r += T

region_external_throughput_r = region_external_in_r + region_external_out_r
```

Rows where both endpoints are inside the same final Task 3 region must contribute
`0` to hub-facing regional demand. This includes same-county flow and
county-to-county flow within the same region.

Rows where exactly one endpoint is in an NE Task 3 region and the other endpoint
is outside the NE megaregion contribute once to the NE region endpoint. Do not
distinguish FAF `trade_type`; domestic, import, and export rows are all included.

Rows where both endpoints are in NE but in different Task 3 regions contribute
once to each endpoint region. These are inter-region movements and are relevant
to regional hub / inter-node demand.

## Task 3 Changes

### [fixed] Update `Task3/map_create.ipynb` demand construction

**Where**

- `Task3/map_create.ipynb`, section `3.1.1`
- `Task3/map_create.ipynb`, section `3.1.2`
- Current retained output: `Data/Task3/derived/county_throughput.parquet`

**Current behavior**

The notebook loads `Data/Task1/raw.parquet`, removes `sctg1014` and `sctg1519`,
then groups by `origin_county_fips` and `dest_county_fips` over all retained
rows. This produces a county-level all-flow endpoint throughput table.

**Fix**

Keep the commodity filter:

```text
exclude sctg1014 and sctg1519
```

Do not filter or split by `trade_type`.

Split demand outputs into two separate concepts:

1. `county_activity_throughput.parquet`
   - Purpose: heatmap / exploratory demand surface only.
   - Formula may remain the current all-flow bidirectional endpoint formula.
   - Must be clearly documented as an activity metric, not a hub demand metric.

2. `county_external_throughput.parquet`
   - Purpose: clustering and later hub-facing demand.
   - Initial Task 3.1 version can include only NE-to-non-NE boundary flows,
     because final region assignments do not exist yet at this stage.
   - Formula:

```text
county_external_out_i = sum T_ij where i is NE and j is non-NE
county_external_in_i  = sum T_ji where i is NE and j is non-NE
county_external_throughput_i = county_external_in_i + county_external_out_i
```

**Notes**

This county external metric is region-independent and can be used before the SA
partition is solved. The final hub sizing metric still needs the
post-assignment outside-region recomputation described below.

### [fixed] Update Task 3.2 clustering demand weight input

**Where**

- `Task3/task3_2_clustering.ipynb`, section `3.2.1`
- `Task3/task3_2_clustering.ipynb`, seed initialization and SA setup
- `Task3/clustering.py`, functions using `throughput`

**Current behavior**

Task 3.2 joins `county_throughput.parquet` to the 434 NE county polygons and
passes `throughput` into the clustering module as the county demand weight.

**Fix**

Replace the clustering demand weight with the corrected county-level external
demand:

```text
county_external_throughput_ktons
```

The SA algorithm can still receive this as the `throughput` array if only the
input column name changes. If the code is updated more explicitly, rename the
variable to `demand_weight` to avoid implying all-flow throughput.

Review all uses of `throughput` in `Task3/clustering.py`:

- K-means sample weights
- demand-aware region growing
- `RegionStats.w`
- `compute_J` demand-balance term
- `compute_delta_J` demand-balance term
- SA logging and quality summaries

The logic does not need to know `trade_type`. It only needs the corrected county
demand weights.

### [fixed] Add post-assignment outside-region demand recomputation

**Where**

- New helper script or notebook section after final `best_arr` is available
- Suggested script: `Task3/recompute_region_external_demand.py`
- Outputs should be under `Data/Task3/outputs/`

**Fix**

After `region_assignment.csv` is written, reload `Data/Task1/raw.parquet` and
`Data/Task3/outputs/region_assignment.csv`, then compute regional hub-facing
demand using final region IDs.

Required output:

```text
Data/Task3/outputs/region_external_metrics.csv
```

Required columns:

```text
region_id
n_counties
external_in_ktons
external_out_ktons
external_throughput_ktons
ne_non_ne_in_ktons
ne_non_ne_out_ktons
inter_region_in_ktons
inter_region_out_ktons
same_region_excluded_ktons
```

Definitions:

- `external_in_ktons`: tonnage entering the region from any county outside that
  final region.
- `external_out_ktons`: tonnage leaving the region to any county outside that
  final region.
- `external_throughput_ktons`: `external_in_ktons + external_out_ktons`.
- `ne_non_ne_*`: subset where the other endpoint is outside the NE megaregion.
- `inter_region_*`: subset where the other endpoint is inside NE but assigned to
  a different final Task 3 region.
- `same_region_excluded_ktons`: raw tonnage removed because both endpoints are in
  the same final region.

Do not split or filter by `trade_type`; all FAF trade codes `1`, `2`, and `3`
are included after the commodity filter.

### [fixed] Update `region_metrics.csv` or add a replacement metric

**Where**

- `Task3/task3_2_clustering.ipynb`, final export block
- Current output: `Data/Task3/outputs/region_metrics.csv`

**Current behavior**

`region_metrics.csv.total_throughput_ktons` is the sum of county all-flow
bidirectional endpoint weights.

**Fix**

Do not use the old `total_throughput_ktons` column for hub location selection.
Either:

1. Replace it with `external_throughput_ktons`, or
2. Keep it only as `activity_throughput_ktons` and add
   `external_throughput_ktons`.

Preferred safer schema:

```text
activity_throughput_ktons
external_throughput_ktons
demand_vs_target_pct
```

If the clustering objective is changed to use external demand, then
`demand_vs_target_pct` must be based on `external_throughput_ktons`, not the old
activity metric.

### [fixed] Update Task 3 docs

**Where**

- `Doc/Task.md`, Task 3.1 and Task 3.2 sections
- `Doc/Data.md`, Task 3 data entries
- `Task3/Cluster.md`, demand-weight definition

**Fix**

Replace wording that describes `county_throughput.parquet` as the clustering
weight unless that file has been rebuilt with the corrected definition.

Document the distinction:

- `activity_throughput`: all retained endpoint activity, useful for maps.
- `external_throughput`: hub-facing demand, excludes same-final-region flow.

Any downstream task that uses Task 3 regional demand must explicitly reference
`external_throughput_ktons`.

## Downstream Changes To Check After Task 3 Is Fixed

### [not fixed] Task 4 candidate summaries

Check whether any Task 4 summaries or plots assume old `region_metrics.csv`
throughput. Candidate screening mostly joins facilities to `region_id`, so the
main risk is documentation and region coverage interpretation.

### [not fixed] Task 5 hub location model coefficients

Task 5 capacity RHS and demand-weighted distance coefficients must be rebuilt
from corrected external region demand.

Specific values to replace:

- `T_r_ktons`
- `T_bar.npy`
- `RHS_r.npy`
- any coefficient that weights counties or regions by old `throughput`

Use `external_throughput_ktons` for region-level capacity. For county-level
distance weighting, use corrected county external demand where possible.

### [not fixed] Task 5 final reports and figures

Any final tables or figures that report regional throughput, selected hub
coverage, or capacity adequacy must be regenerated after Task 3 and Task 5
metrics are rebuilt.

## Verification Checklist

### [not fixed] Demand accounting tests

Add a reproducible audit that confirms:

```text
same_region_excluded_ktons > 0
same-county rows contribute 0 to external_throughput_ktons
NE-to-non-NE rows contribute once to the NE endpoint region
NE inter-region rows contribute once to each endpoint region
trade_type values 1, 2, and 3 are all retained
```

### [not fixed] Output consistency tests

After recomputation:

```text
sum(region_external_metrics.external_throughput_ktons)
    == sum(county external endpoint demand over 434 NE counties)

region_metrics.external_throughput_ktons
    == region_external_metrics.external_throughput_ktons
```

If `activity_throughput_ktons` is retained, verify it is never used for Task 5
capacity RHS or hub selection demand.
