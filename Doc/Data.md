# Project Data Sources

## `raw.parquet` — Full NE county-to-county O-D flow matrix (all modes, 2025 & 2030)

> **path** · `Data/Task1/raw.parquet` · **format** · parquet · **shape** · 33,404,629 rows × 7 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| origin_county_fips | int64 | 100% | 5-digit FIPS code of the origin county (stored as raw int; use `.str.zfill(5)` after casting to string before joins) |
| dest_county_fips | int64 | 100% | 5-digit FIPS code of the destination county (same zfill note as above) |
| mode | int64 | 100% | FAF experimental county-level mode code — see full table below |
| sctgG5 | object | 100% | FAF 5-group commodity code — see full table below |
| trade_type | int64 | 100% | FAF trade type: `1` = Domestic, `2` = Import, `3` = Export |
| tons_2025 | float64 | 100% | Forecasted freight flow in thousand short tons for 2025 (multiply by 1 000 for short tons) |
| tons_2030 | float64 | 100% | Forecasted freight flow in thousand short tons for 2030 |

**Mode codes** (FAF experimental county-county re-coding; differs from the FAF Regional Database):

| `mode` value | Label | FAF Regional Database modes aggregated |
| --- | --- | --- |
| 2 | Rail | FAF mode 2 — Rail |
| 3 | Water | FAF mode 3 — Water |
| 5 | Multiple modes and mail | FAF mode 5 — Multiple modes and mail |
| 6 | Pipeline | FAF mode 6 — Pipeline |
| 11 | Truck and Air | FAF modes 1 (Truck) and 4 (Air) combined; truck disaggregation factors also applied to air flows |

> Note: FAF modes 1 (Truck) and 4 (Air) do not appear separately in this file — they are merged into mode `11`. Mode 7 (Other/Unknown) is excluded from the experimental product.

**`sctgG5` commodity codes** (5-group aggregation of the 42 FAF SCTG categories; Handout §Data Sources b):

| `sctgG5` value | Commodity group label | FAF SCTG codes covered |
| --- | --- | --- |
| `sctg0109` | Agricultural products | SCTG 1–9 |
| `sctg1014` | Gravel and mining products | SCTG 10–14 |
| `sctg1519` | Coal and other energy products | SCTG 15–19 |
| `sctg2033` | Chemical, wood and metals | SCTG 20–33 |
| `sctg3499` | Manufactured goods, mixed freight, waste and unknown | SCTG 34–99 |

> Project commodity filter: `sctg1014` (gravel/mining) and `sctg1519` (coal/energy) are excluded from truck-compatible freight analysis as non-palletizable bulk commodities.

**Context**: Produced in Task 1 by applying FAF disaggregation factors to the FAF Regional Database and filtering to NE megaregion flows (`internal` NE→NE, `inbound` ext→NE, `outbound` NE→ext); `outside_outside` county pairs were excluded. Source methodology: BTS Experimental County-to-County Estimates (Handout §Data Sources b). This is the primary freight demand dataset for all downstream tasks.

---

## `breakdown_by_flow_type.csv` — NE freight tonnage subtotals by flow direction

> **path** · `Data/Task1/breakdown_by_flow_type.csv` · **format** · csv · **shape** · 3 rows × 5 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| flow_type | object | 100% | Flow direction: `Internal` (NE→NE), `Inbound` (ext→NE), or `Outbound` (NE→ext) |
| tons_2025 | float64 | 100% | Total tonnage (thousand short tons) for that flow type in 2025 |
| tons_2030 | float64 | 100% | Total tonnage for that flow type in 2030 |
| label | object | 100% | Human-readable label (same as flow_type) |
| growth_pct | float64 | 100% | Percentage tonnage growth from 2025 to 2030 |

**Context**: Pareto summary aggregated from `raw.parquet`. Characterizes total megaregion freight demand by direction; used in Task 1 reporting.

---

## `breakdown_by_mode.csv` — NE freight tonnage by transport mode

> **path** · `Data/Task1/breakdown_by_mode.csv` · **format** · csv · **shape** · 5 rows × 5 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| mode | int64 | 100% | FAF mode code (2=Truck, 3=Water, 5=Multi-mode/Mail, 11=Truck+Air; Rail & Pipeline also present) |
| tons_2025 | float64 | 100% | Total tonnage (thousand short tons) for that mode in 2025 |
| tons_2030 | float64 | 100% | Total tonnage for that mode in 2030 |
| label | object | 100% | Human-readable mode label (e.g. `Truck`, `Rail`, `Pipeline`, `Truck+Air`) |
| growth_pct | float64 | 100% | Percentage tonnage growth from 2025 to 2030 |

**Context**: Mode-split summary across all NE flows. Truck dominates (~2.38M thousand tons in 2025). Informs which modes need dedicated interface node treatment in Task 2.

---

## `breakdown_by_trade_type.csv` — NE freight tonnage by trade type

> **path** · `Data/Task1/breakdown_by_trade_type.csv` · **format** · csv · **shape** · 3 rows × 5 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| trade_type | int64 | 100% | FAF trade type code (1=Internal/domestic, 2=Import, 3=Export) |
| tons_2025 | float64 | 100% | Total tonnage (thousand short tons) for that trade type in 2025 |
| tons_2030 | float64 | 100% | Total tonnage for that trade type in 2030 |
| label | object | 100% | Human-readable label (e.g. `Internal (domestic)`, `Import`, `Export`) |
| growth_pct | float64 | 100% | Percentage tonnage growth from 2025 to 2030 |

**Context**: Trade-type split of NE freight. Domestic flows dominate (~2.89M thousand tons in 2025); Import/Export (~0.2–0.4M each) inform gateway node sizing in Task 2.

---

## `ne_state_summary.csv` — Per-state outbound/inbound tonnage for NE states

> **path** · `Data/Task1/ne_state_summary.csv` · **format** · csv · **shape** · 14 rows × 6 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| state_fips | int64 | 100% | 2-digit state FIPS code |
| outbound_2025 | float64 | 100% | Total outbound tonnage (thousand short tons) originating from this state in 2025 |
| outbound_2030 | float64 | 100% | Total outbound tonnage in 2030 |
| inbound_2025 | float64 | 100% | Total inbound tonnage destined for this state in 2025 |
| inbound_2030 | float64 | 100% | Total inbound tonnage in 2030 |
| state_name | object | 100% | Full state name (e.g. Pennsylvania, New York, Virginia) |

**Context**: Aggregates Task 1 flows to state level for the 14 NE megaregion states. Useful for comparing freight volumes across states and identifying high-demand states for node placement in later tasks.

---

## `top50_origin_counties.csv` — Top 50 NE counties by outbound freight tonnage

> **path** · `Data/Task1/top50_origin_counties.csv` · **format** · csv · **shape** · 50 rows × 6 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| origin_county_fips | int64 | 100% | 5-digit FIPS code of the origin county |
| tons_2025 | float64 | 100% | Total outbound tonnage (thousand short tons) in 2025 |
| tons_2030 | float64 | 100% | Total outbound tonnage in 2030 |
| state_fips | int64 | 100% | 2-digit FIPS of the state containing this county |
| state_name | object | 100% | Full state name |
| rank | int64 | 100% | Rank by outbound tons_2025 (1 = highest volume) |

**Context**: Pareto list of highest freight-generating origins in the NE megaregion (dominated by PA, NY, NJ counties). Used to prioritize county-level infrastructure focus in later tasks.

---

## `top50_dest_counties.csv` — Top 50 NE counties by inbound freight tonnage

> **path** · `Data/Task1/top50_dest_counties.csv` · **format** · csv · **shape** · 50 rows × 6 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| dest_county_fips | int64 | 100% | 5-digit FIPS code of the destination county |
| tons_2025 | float64 | 100% | Total inbound tonnage (thousand short tons) in 2025 |
| tons_2030 | float64 | 100% | Total inbound tonnage in 2030 |
| state_fips | int64 | 100% | 2-digit FIPS of the state containing this county |
| state_name | object | 100% | Full state name |
| rank | int64 | 100% | Rank by inbound tons_2025 (1 = highest volume) |

**Context**: Pareto list of highest freight-attracting destinations (dominated by NJ, NY, PA counties). Used alongside `top50_origin_counties.csv` to identify candidate node locations in later tasks.

---

## `task2_global_interface_nodes_final.csv` — Global-tier interface nodes (seaports + cargo airports)

> **path** · `Data/Task2/task2_global_interface_nodes_final.csv` · **format** · csv · **shape** · 9 rows × 6 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| node_name | object | 100% | Facility name (e.g. `Hampton Roads, VA`, `WASHINGTON DULLES INTL`) |
| state_name | object | 100% | State where the node is located |
| node_type | object | 100% | Facility type: `seaport` or `cargo_airport` |
| interface_class | object | 100% | Always `global` — marks this as the global interface tier |
| tons_2025 | float64 | 100% | Allocated freight volume (thousand short tons) in 2025 |
| tons_2030 | float64 | 100% | Allocated freight volume in 2030 |

**Context**: Task 2 output listing 9 global-tier interface nodes handling maritime and air freight crossing the NE megaregion boundary. Tonnage allocated from `global_maritime` (mode=3) and `global_air` (mode=5,11) flow buckets.

---

## `task2_continental_interface_nodes_final.csv` — Continental-tier interface nodes (US–Canada border crossings)

> **path** · `Data/Task2/task2_continental_interface_nodes_final.csv` · **format** · csv · **shape** · 8 rows × 6 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| node_name | object | 100% | Border crossing name (e.g. `Buffalo Niagara Falls`, `Champlain Rouses Point`) |
| state_name | object | 100% | US state where the crossing is located |
| node_type | object | 100% | Always `border_crossing` |
| interface_class | object | 100% | Always `continental` — marks this as the continental interface tier |
| tons_2025 | int64 | 100% | Allocated freight volume (thousand short tons) in 2025 |
| tons_2030 | int64 | 100% | Allocated freight volume in 2030 (same as 2025 — no disaggregated forecast available) |

**Context**: Task 2 output for 8 US–Canada border crossings in NY, VT, NH, and ME. Handles the `continental_border` flow bucket. Tonnage integers reflect allocation from aggregate border totals without per-crossing disaggregation.

---

## `task2_national_interface_nodes_final.csv` — National-tier interface nodes (external domestic nodes)

> **path** · `Data/Task2/task2_national_interface_nodes_final.csv` · **format** · csv · **shape** · 12 rows × 6 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| node_name | object | 100% | County-level node identifier (e.g. `LUCAS, OH`, `HARRIS, TX`, `COOK, IL`) |
| state_name | object | 100% | State abbreviation |
| node_type | object | 100% | Always `external_domestic_hub` (retained schema label for the external domestic node tier) |
| interface_class | object | 100% | Always `national` — marks this as the national interface tier |
| tons_2025 | float64 | 100% | Allocated freight volume (thousand short tons) in 2025 |
| tons_2030 | float64 | 100% | Allocated freight volume in 2030 |

**Context**: Task 2 output listing 12 major external US counties acting as domestic interchange points for `national_domestic` flows. Represents primary freight origins/destinations connecting the NE megaregion to the rest of the US.

---

## `Data/Task3/` layout — Task 3 directory organization

Task 3 data is now organized by role instead of a flat folder:

- `Data/Task3/raw/` — authoritative shapefile bundles and downloaded source layers
- `Data/Task3/derived/` — retained derived datasets reused across notebooks
- `Data/Task3/cache/` — regenerable geospatial intermediates, SA checkpoints, and logs
- `Data/Task3/figures/` — publication or diagnostic figures
- `Data/Task3/outputs/` — final tabular exports for downstream use

---

## `cb_2023_us_county_500k.shp` — US county cartographic boundary shapefile

> **path** · `Data/Task3/raw/census_counties/cb_2023_us_county_500k.shp` · **format** · shapefile · **shape** · 3,235 features × 12 attrs + geometry

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| STATEFP | char(2) | 100% | 2-digit state FIPS code |
| COUNTYFP | char(3) | 100% | 3-digit county FIPS code within the state |
| COUNTYNS | char(8) | 100% | GNIS county identifier |
| GEOIDFQ | char(14) | 100% | Fully qualified geographic identifier |
| GEOID | char(5) | 100% | 5-digit county FIPS used to join Task 3 throughput data |
| NAME | char(100) | 100% | County or county-equivalent short name |
| NAMELSAD | char(100) | 100% | Full county legal/statistical area description |
| STUSPS | char(2) | 100% | State postal abbreviation |
| STATE_NAME | char(100) | 100% | Full state name |
| LSAD | char(2) | 100% | Legal/statistical area descriptor code |
| ALAND | numeric | 100% | Land area |
| AWATER | numeric | 100% | Water area |

**Context**: Generalized Census county boundaries used in Task 3.1 to map freight demand. The workflow filtered this national file to the 14-state NE megaregion, joined `GEOID` to `county_throughput.parquet`, dissolved state outlines for overlay, and used county centroids to place Task 2 national node annotations.

---

## `North_American_Roads.shp` — NTAD North American roads network

> **path** · `Data/Task3/raw/roads/North_American_Roads.shp` · **format** · shapefile · **shape** · 720,055 features × 16 attrs + geometry

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| ID | int | 100% | NTAD road segment identifier |
| DIR | int | 100% | Directional code |
| LENGTH | float | 100% | Segment length |
| LINKID | char(16) | 100% | Link identifier |
| COUNTRY | int | 100% | Country code (`1`=Canada, `2`=US, `3`=Mexico in notebook checks) |
| JURISCODE | char(5) | 100% | Jurisdiction code |
| JURISNAME | char(30) | 100% | Jurisdiction name |
| ROADNUM | char(20) | 100% | Route number |
| ROADNAME | char(80) | 100% | Route name |
| ADMIN | char(15) | 100% | Administrative class/name field |
| SURFACE | char(20) | 100% | Surface type |
| LANES | int | 100% | Lane count |
| SPEEDLIM | int | 100% | Speed limit |
| CLASS | int | 100% | Road class (`1` = Interstate per notebook checks) |
| NHS | float | 100% | National Highway System indicator/weight field |
| BORDER | int | 100% | Border-related flag |

**Context**: Task 3.1 used this BTS NTAD source to isolate US interstate segments (`COUNTRY == 2`, `CLASS == 1`), clip them to the NE bounding box, and overlay them on the freight demand map. The derived `ne_interstates.parquet` cache was intentionally deleted after cleanup, so this shapefile remains the authoritative road source for regenerating the overlay.

---

## `tl_2023_us_rails.shp` — TIGER/Line national rail network

> **path** · `Data/Task3/raw/rails/tl_2023_us_rails.shp` · **format** · shapefile · **shape** · 119,857 features × 3 attrs + geometry

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| LINEARID | char(22) | 100% | Census/TIGER linear feature identifier |
| FULLNAME | char(100) | partial | Railroad line name where available |
| MTFCC | char(5) | 100% | Census feature class code for rail features |

**Context**: Task 3.1 downloaded this Census TIGER rail dataset separately because the NTAD file is road-only. The workflow clipped the national rail network to the NE bounding box for map overlay; the derived `ne_railroads.parquet` intermediate was later deleted, so this shapefile is the retained source for rebuilding the railroad layer.

---

## `county_throughput.parquet` — County-level freight demand weights for clustering

> **path** · `Data/Task3/derived/county_throughput.parquet` · **format** · parquet · **shape** · 3,144 rows × 4 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| fips | object | 100% | 5-digit county FIPS code |
| tons_in | float64 | 100% | Total 2025 inbound freight tonnage to the county (thousand short tons) |
| tons_out | float64 | 100% | Total 2025 outbound freight tonnage from the county (thousand short tons) |
| throughput | float64 | 100% | Bidirectional county demand weight: `tons_in + tons_out` |

**Context**: Core retained Task 3.1 output built from the commodity-filtered Task 1 O-D table. It covers 3,144 counties with positive freight interaction tied to the NE megaregion and serves as the clustering weight table for Task 3.2 onward as well as the joined demand surface behind the heatmap and composite map.

---

## `ne_counties_prepared.gpkg` — Prepared NE county subset for clustering

> **path** · `Data/Task3/derived/ne_counties_prepared.gpkg` · **format** · geopackage · **shape** · 434 rows × 9 cols + geometry

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| fips | object | 100% | 5-digit county or county-equivalent FIPS code |
| NAME | object | 100% | County or county-equivalent name |
| STUSPS | object | 100% | State postal abbreviation |
| tons_in | float64 | 100% | Total inbound 2025 freight tonnage (thousand short tons) |
| tons_out | float64 | 100% | Total outbound 2025 freight tonnage (thousand short tons) |
| throughput | float64 | 100% | Bidirectional demand weight used by clustering |
| centroid_x | float64 | 100% | County centroid x-coordinate in EPSG:9311 meters |
| centroid_y | float64 | 100% | County centroid y-coordinate in EPSG:9311 meters |
| geometry | geometry | 100% | NE county polygon projected to EPSG:9311 |

**Context**: Retained Task 3.2 preparation layer created by filtering the national county shapefile to the 14-state study area, joining `county_throughput.parquet`, projecting to the equal-area clustering CRS, and caching centroid coordinates for optimization reuse.

---

## `fig_demand_heatmap.png` — NE county freight demand choropleth

> **path** · `Data/Task3/figures/fig_demand_heatmap.png` · **format** · png · **shape** · 3355 × 2736 px

**Context**: Publication-quality choropleth of county-level 2025 freight throughput over the NE megaregion. Built by joining `county_throughput.parquet` to `cb_2023_us_county_500k.shp`, filtering to 434 NE counties, and applying a log-scale color ramp with county borders and state outlines for readability.

---

## `fig_composite_map.png` — Composite demand, corridor, and interface-node map

> **path** · `Data/Task3/figures/fig_composite_map.png` · **format** · png · **shape** · 3564 × 3569 px

**Context**: Final Task 3.1 map combining the county throughput choropleth with interstate overlays from `North_American_Roads.shp`, railroad overlays from `tl_2023_us_rails.shp`, and Task 2 interface nodes from `task2_global_interface_nodes_final.csv`, `task2_continental_interface_nodes_final.csv`, and `task2_national_interface_nodes_final.csv`. This is the visual synthesis used to guide later region clustering and corridor-aligned node design.

---

## `fig_sa_convergence.png` — Simulated annealing convergence diagnostic

> **path** · `Data/Task3/figures/fig_sa_convergence.png` · **format** · png

**Context**: Task 3.2 diagnostic figure showing objective value and temperature by proposal index for each restart. Used to verify cooling behavior and whether additional restarts or proposals are needed.

---

## `fig_demand_balance.png` — Regional demand balance summary figure

> **path** · `Data/Task3/figures/fig_demand_balance.png` · **format** · png

**Context**: Task 3.2 summary figure showing sorted regional throughput bars and a demand histogram against the target `W*`. Used to assess coefficient of variation and nRMSE at a glance.

---

## `fig_region_map.png` — Final 50-region clustering map

> **path** · `Data/Task3/figures/fig_region_map.png` · **format** · png

**Context**: Final Task 3.2 choropleth of the 50 freight regions with county boundaries, dissolved region boundaries, labels, and interstate overlay.

---

## `sa_log.csv` — Simulated annealing iteration log

> **path** · `Data/Task3/cache/sa_log.csv` · **format** · csv

**Context**: Regenerable Task 3.2 cache recording restart id, proposal count, objective, and temperature during the SA run. This file supports the convergence plot and restart diagnostics.

---

## `region_assignment.csv` — Final county-to-region assignment

> **path** · `Data/Task3/outputs/region_assignment.csv` · **format** · csv · **shape** · 434 rows × 5 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| fips | object | 100% | 5-digit county or county-equivalent FIPS code |
| county_name | object | 100% | County name from the prepared NE subset |
| state | object | 100% | State postal abbreviation |
| region_id | int64 | 100% | Final Task 3.2 region label in `[0, 49]` |
| throughput_ktons | float64 | 100% | County demand weight used in optimization |

**Context**: Final Task 3.2 output used to join the 50-region solution back to maps or downstream analyses.

---

## `region_metrics.csv` — Final per-region clustering summary

> **path** · `Data/Task3/outputs/region_metrics.csv` · **format** · csv · **shape** · 50 rows × 8 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| region_id | int64 | 100% | Region label in `[0, 49]` |
| n_counties | int64 | 100% | Number of county-equivalent units in the region |
| total_throughput_ktons | float64 | 100% | Regional demand total |
| demand_vs_target_pct | float64 | 100% | Percent deviation from target throughput `W*` |
| centroid_x_m | float64 | 100% | Region centroid x-coordinate in EPSG:9311 meters |
| centroid_y_m | float64 | 100% | Region centroid y-coordinate in EPSG:9311 meters |
| sse_m2 | float64 | 100% | Within-region compactness SSE in square meters |
| is_connected | bool | 100% | Whether the final region remains graph-connected |

**Context**: Final Task 3.2 export summarizing balance, compactness, and contiguity at the region level.

---

## `Data/Task4/` layout — Task 4 directory organization

Task 4 data is organized by role:

- `Data/Task4/ALL/` — raw CoStar exports per state (one CSV per state; 14 files)
- `Data/Task4/Available/` — available-only subset per state (existing buildings with listed space)
- `Data/Task4/processed/` — screened & tagged candidate outputs consumed by downstream tasks
- `Data/Task4/figures/` — candidate facility maps (static PNG)
- `Data/Task4/cache/` — font/render caches (regenerable)

---

## `preprocessed_capacity_location.csv` — Full lean candidate pool (all 2,064 facilities)

> **path** · `Data/Task4/processed/preprocessed_capacity_location.csv` · **format** · csv · **shape** · 2,064 rows × 19 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| candidate_id | object | 100% | Stable identifier `T4-{STATE}-{row:05d}` assigned during loading |
| source_state | object | 100% | 2-letter state abbreviation of the CoStar export file |
| facility_name | object | 100% | Resolved display name: `property_name` if present, else `address, city, state` |
| city | object | 100% | City from CoStar export |
| county_fips | object | ~100% | 5-digit county FIPS assigned by spatial join to `ne_counties_prepared.gpkg` |
| county_name | object | ~100% | County name from the county layer |
| region_id | int64 | ~100% | Task 3.2 region label `[0, 49]` from `region_assignment.csv` via county FIPS |
| latitude | float64 | 100% | WGS-84 latitude from CoStar |
| longitude | float64 | 100% | WGS-84 longitude from CoStar |
| secondary_type | object | 100% | CoStar secondary property type: `Warehouse` or `Distribution` |
| building_class | object | 100% | CoStar building class: `A`, `B`, or `C` |
| building_status | object | 100% | CoStar building status: `Existing`, `Under Construction`, or `Final Planning` |
| year_built | float64 | partial | Year the building was constructed |
| usable_available_space_sf | float64 | 100% | **s_h for Task 5 MIP** = RBA (rentable building area, total building capacity in sqft) |
| number_loading_docks | float64 | partial | Number of loading docks reported by CoStar |
| availability_class | object | 100% | Derived status tag: `direct_existing_facility`, `pipeline_under_construction`, `proxy_final_planning`, or `needs_status_review` |
| is_directly_usable_by_status | bool | 100% | `True` if `building_status == Existing` |
| meets_min_rba_200k | bool | 100% | `True` if `usable_available_space_sf ≥ 200,000 sqft` |
| is_primary_regional_hub_candidate | bool | 100% | `True` if existing + logistics type + rba ≥ 200k + valid coordinates |

**Context**: Lean 19-column dataset covering all 2,064 CoStar facilities across 14 NE states, tagged with Task 4 availability and screening flags, and spatially joined to Task 3 county and region identifiers. Serves as the broader fallback pool for Task 5.1 sparse-region supplementation.

---

## `primary_regional_hub_candidates.csv` — Pre-screened primary hub candidate pool

> **path** · `Data/Task4/processed/primary_regional_hub_candidates.csv` · **format** · csv · **shape** · 1,862 rows × 19 cols

Same 19-column schema as `preprocessed_capacity_location.csv`. This is the subset where `is_primary_regional_hub_candidate == True`.

**Screening criteria applied** (all four must hold):

1. `building_status == Existing` — directly usable today
2. `secondary_type ∈ {Warehouse, Distribution, Truck Terminal, Manufacturing}` — logistics-compatible type
3. `usable_available_space_sf (= RBA) ≥ 200,000 sqft` — minimum regional hub scale
4. `latitude ∈ [35, 48]`, `longitude ∈ [−84, −66]` — valid NE megaregion coordinates

**Key statistics:**

- 1,862 candidates across all 50 Task 3 regions (min 4 per region)
- `usable_available_space_sf` range: 200,000 – 500,000 sqft; median Q̄ ≈ 304,224 sqft
- PA, NJ, NY, MA, MD, VA are the highest-density states

**Downstream use**: Primary input to Task 5.1 H-construction. Task 5 reads `candidate_id`, `facility_name`, `city`, `source_state`, `region_id`, `county_fips`, `latitude`, `longitude`, and `usable_available_space_sf` (= s_h) directly from this file.

---

## `region_candidate_stats.csv` — Per-region primary candidate coverage summary

> **path** · `Data/Task4/processed/region_candidate_stats.csv` · **format** · csv · **shape** · 50 rows × 5 cols

| Column | Type | Meaning |
| ------ | ---- | ------- |
| region_id | int64 | Task 3.2 region label `[0, 49]` |
| all_candidates | float64 | Total CoStar facilities (any status) matched to this region |
| direct_existing_by_status | float64 | Facilities with `building_status == Existing` |
| primary_regional_hub_candidates | float64 | Facilities passing the full Task 4 primary screen |
| total_usable_available_sf | float64 | Sum of `usable_available_space_sf` across all candidates in region |

**Context**: Diagnostic coverage table used to identify sparse regions requiring fallback treatment in Task 5.1.

---

## `state_candidate_stats.csv` — Per-state candidate summary

> **path** · `Data/Task4/processed/state_candidate_stats.csv` · **format** · csv · **shape** · 14 rows × 9 cols

Columns: `source_state`, `all_candidates`, `direct_existing_by_status`, `pipeline_or_proxy_by_status`, `listed_available_space`, `primary_regional_hub_candidates`, `total_usable_available_sf`, `median_rba_sf`, `median_loading_docks`.

**Context**: State-level rollup for reporting; not consumed by Task 5.

---

## `Data/Task5/` layout — Task 5 directory organization

Task 5 data is organized by role:

- `Data/Task5/cache/` — all intermediate arrays and filtered datasets (regenerable from Task 5.1 onward)
- `Data/Task5/` (root) — final CSV/parquet exports produced after MIP solution (Tasks 5.3–5.6)

---

## `H_candidates.parquet` — Filtered regional hub candidate set (Task 5.1 output)

> **path** · `Data/Task5/cache/H_candidates.parquet` · **format** · parquet · **shape** · 1,675 rows × 22 cols

Same 19-column schema as `primary_regional_hub_candidates.csv`, plus three columns added by Task 5.1:

| Column | Type | Meaning |
| ------ | ---- | ------- |
| x_m | float64 | Hub easting in EPSG:9311 metres |
| y_m | float64 | Hub northing in EPSG:9311 metres |
| d_road_m | float64 | Euclidean distance from hub to nearest US interstate segment (metres) |
| d_road_miles | float64 | Same distance in miles |
| h_idx | int64 | Row index in this file; used as the hub integer key in Z_pairs and c_hat arrays |

**Construction**: 1,862 primary candidates → β-gate removes 187 with d_road > β (β = 12,831 m, 7.97 mi, 90th percentile). No sparse-region fallback was triggered; all 50 regions had ≥ 4 in-region candidates.

**Key statistics**: sqft range 200,000–500,000; median = 306,250; d_road range 44–12,820 m.

**Downstream use**: Primary input to Task 5.2 (coefficient computation) and Task 5.3 (MIP variables).

---

## `Z_pairs.npy` — Feasibility set Z (hub–region index pairs)

> **path** · `Data/Task5/cache/Z_pairs.npy` · **format** · numpy int32 · **shape** · (25,667, 2)

Each row is an `(h_idx, r_idx)` pair where `h_idx` indexes into `H_candidates.parquet` and `r_idx` is the positional index in `region_metrics.csv` sorted by `region_id` (i.e. `r_idx == region_id` since region IDs are 0–49).

**Construction rule**: pair included iff Euclidean distance ≤ 241,402 m (150 miles) in EPSG:9311.

**Coverage**: all 50 regions have ≥ 13 Z-hubs (min region 43 = 13, median = 475, max = 944).

**Downstream use**: defines the variable set for Task 5.3 MIP (`A[h,r]` and `O[h]` variables).

---

## `dist_hr.npy` — Hub-to-region centroid distance matrix

> **path** · `Data/Task5/cache/dist_hr.npy` · **format** · numpy float64 · **shape** · (1,675, 50)

Entry `[h, r]` is the Euclidean distance in EPSG:9311 metres from hub `h` (row index in `H_candidates.parquet`) to region `r` centroid (`region_metrics.csv` row `r`, sorted by `region_id`).

**Downstream use**: Z construction (Task 5.1, already done) and can be reused for any hub-to-region spatial query in Tasks 5.2–5.6.

---

## `beta_m.npy` — Road accessibility threshold β

> **path** · `Data/Task5/cache/beta_m.npy` · **format** · numpy float64 · **shape** · (1,)

Scalar β = 12,831 m (7.97 miles) = 90th percentile of `d_road_m` across all 1,862 primary candidates before gate. Hubs with `d_road_m > β` were removed from H.

---

## `H_region_summary.csv` — Per-region H candidate summary

> **path** · `Data/Task5/cache/H_region_summary.csv` · **format** · csv · **shape** · 49 rows × 5 cols

| Column | Type | Meaning |
| ------ | ---- | ------- |
| region_id | int64 | Task 3.2 region label `[0, 49]` |
| n_candidates | int64 | Number of H candidates in this region (post β-gate) |
| min_sqft | float64 | Minimum `usable_available_space_sf` in region |
| max_sqft | float64 | Maximum `usable_available_space_sf` in region |
| median_d_road_miles | float64 | Median road distance for candidates in this region |

**Note**: 49 rows because one region (region 43, ME) has 0 in-region candidates but is covered by external Z-hubs.

---

## `c_hat.npy` — Objective cost coefficients ĉ_hr (Task 5.2 output)

> **path** · `Data/Task5/cache/c_hat.npy` · **format** · numpy float64 · **shape** · (25,667,)

Entry `z` corresponds to row `z` of `Z_pairs.npy`. For the pair `(h, r) = Z[z]`:

$$\hat{c}_{hr} = \left( \sum_{c \in C_r} w_{cr} \cdot d_{hcr} \right) \cdot \left( \frac{\bar{Q}}{s_h} \right)^{0.5}$$

where $w_{cr}$ = county throughput (ktons), $d_{hcr}$ = Euclidean distance hub→county centroid (EPSG:9311 m), $\bar{Q}$ = 306,250 sqft.

**Distribution**: min ≈ 75.6 M, mean ≈ 8.69 B, max ≈ 44.9 B (units: ktons·m·sqft^0.5 / sqft^0.5 = ktons·m).

**Downstream use**: objective coefficients for Task 5.3 MIP — `minimize Σ_{(h,r)∈Z} A[h,r] · c_hat[z]`.

---

## `cap_rhs.npy` — Capacity constraint RHS values (Task 5.2 output)

> **path** · `Data/Task5/cache/cap_rhs.npy` · **format** · numpy float64 · **shape** · (50,)

Entry `r` is `RHS_r = Q̄ · (T_r / T̄)` in sqft, aligned to `region_metrics.csv` row order (sorted by `region_id`).

**Distribution**: min = 160,135 sqft, mean = 306,250 sqft (= Q̄), max = 813,530 sqft.

**Feasibility note**: max(RHS_r) = 813,530 > max(s_h) = 500,000 sqft, so the highest-demand region requires ≥ 2 assigned hubs to satisfy Constraint 4. This is valid since the concentration cap allows p_h = 2.

**Downstream use**: RHS of Constraint 4 in Task 5.3 MIP — `Σ_{h:(h,r)∈Z} A[h,r] · s_h ≥ cap_rhs[r]`.

---

## `Q_bar.npy` / `T_bar.npy` — MIP scalar parameters (Task 5.2 output)

> **paths** · `Data/Task5/cache/Q_bar.npy`, `Data/Task5/cache/T_bar.npy` · **format** · numpy float64 · **shape** · (1,)

| File | Value | Meaning |
| ---- | ----- | ------- |
| `Q_bar.npy` | 306,250 sqft | Median `usable_available_space_sf` across H (1,675 candidates) |
| `T_bar.npy` | 58,038.55 ktons | Mean `total_throughput_ktons` across all 50 regions |

---

## `selected_hubs.csv` — MIP-selected regional hubs (Task 5.6 final export)

> **path** · `Data/Task5/selected_hubs.csv` · **format** · csv · **shape** · 51 rows × 13 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| h_idx | int64 | 100% | Row index in `H_candidates.parquet`; hub integer key used in Z_pairs and c_hat arrays |
| candidate_id | object | 100% | Stable CoStar identifier from Task 4 (e.g. `T4-CT-00017`) |
| facility_name | object | 100% | Resolved display name from CoStar |
| city | object | 100% | City of the facility |
| source_state | object | 100% | 2-letter state abbreviation |
| region_id | int64 | 100% | Hub's home Task 3.2 region label `[0, 49]` from Task 4 assignment |
| latitude | float64 | 100% | WGS-84 latitude |
| longitude | float64 | 100% | WGS-84 longitude |
| usable_available_space_sf | int64 | 100% | Usable floor area = s_h (sqft) |
| d_road_m | float64 | 100% | Distance to nearest US interstate segment (metres) |
| d_road_miles | float64 | 100% | Same distance in miles |
| regions_served | object | 100% | Semicolon-separated list of region_ids this hub is assigned to serve (e.g. `0` or `24;24`) |
| n_regions_served | int64 | 100% | Count of regions served (1 or 2) |

**Key statistics**: 51 selected hubs; all serve exactly 1 region in this OPTIMAL solution (region 24 uses 2 separate hubs for capacity reasons). Hub states span CT, DE, MA, MD, ME, NH, NJ, NY, PA, RI, VA.

**Downstream use**: Task 6 gateway node screening; Task 7 multi-tier integration.

---

## `hub_region_assignments.csv` — Hub–region pair table (Task 5.6 final export)

> **path** · `Data/Task5/hub_region_assignments.csv` · **format** · csv · **shape** · 51 rows × 11 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| h_idx | int64 | 100% | Hub integer key (row index in `H_candidates.parquet`) |
| candidate_id | object | 100% | Stable CoStar identifier |
| facility_name | object | 100% | Facility display name |
| city | object | 100% | Facility city |
| source_state | object | 100% | 2-letter state abbreviation |
| region_id | int64 | 100% | Task 3.2 region served by this assignment (the MIP A[h,r] = 1 region) |
| usable_available_space_sf | int64 | 100% | Hub floor area s_h (sqft) contributed to this region's capacity |
| d_road_miles | float64 | 100% | Hub road accessibility distance (miles) |
| c_hat | float64 | 100% | MIP objective cost coefficient ĉ_hr for this (h, r) pair (ktons·m) |
| latitude | float64 | 100% | WGS-84 latitude |
| longitude | float64 | 100% | WGS-84 longitude |

**Note**: 51 rows = 50 regions × 1 hub/region + 1 extra assignment for region 24 (2 hubs required to meet capacity RHS_24 = 813,530 sqft > max single hub 500,000 sqft).

---

## `task5_hub_network_links.csv` — Regional hub network links (Task 5.5 output)

> **path** · `Data/Task5/task5_hub_network_links.csv` · **format** · csv · **shape** · 140 rows × 11 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| hub_a_h_idx | int64 | 100% | h_idx of the first hub endpoint |
| hub_b_h_idx | int64 | 100% | h_idx of the second hub endpoint |
| hub_a_candidate_id | object | 100% | candidate_id of hub A |
| hub_b_candidate_id | object | 100% | candidate_id of hub B |
| hub_a_name | object | 100% | facility_name of hub A |
| hub_b_name | object | 100% | facility_name of hub B |
| hub_a_state | object | 100% | source_state of hub A |
| hub_b_state | object | 100% | source_state of hub B |
| distance_miles | float64 | 100% | Euclidean straight-line distance between hubs (miles, EPSG:9311) |
| drive_time_h | float64 | 100% | Estimated driving time = distance / 64 mph |
| shared_region | bool | 100% | `True` if both hubs are co-assigned to the same region (p_h = 2 case) |

**Construction**: Delaunay triangulation on 51 hub EPSG:9311 coordinates → unique undirected edges → supplemented with 1 shared-region pair (region 24) → pruned at 350 miles. Final 140 links; max distance = 350 mi (drive time ≤ 5.47 h at 64 mph).

**Downstream use**: Task 7 network topology; Task 8 flow assignment routing.

---

## `region_hub_summary.csv` — Per-region hub coverage summary (Task 5.6 final export)

> **path** · `Data/Task5/region_hub_summary.csv` · **format** · csv · **shape** · 50 rows × 10 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| region_id | int64 | 100% | Task 3.2 region label `[0, 49]` |
| n_counties | int64 | 100% | Number of county-equivalent units in the region |
| T_r_ktons | float64 | 100% | Total 2025 bidirectional throughput of the region (ktons) |
| n_hubs_assigned | int64 | 100% | Number of MIP-selected hubs assigned to this region (1 or 2) |
| assigned_hubs | object | 100% | Semicolon-separated h_idx list of assigned hubs |
| assigned_sqft | int64 | 100% | Total usable sqft across assigned hubs (sum of s_h for assigned hubs) |
| rhs_sqft | int64 | 100% | Capacity constraint RHS = Q̄ · (T_r / T̄) rounded to nearest integer |
| capacity_slack_sqft | int64 | 100% | `assigned_sqft − rhs_sqft` (always ≥ 0 in a feasible solution) |
| dw_dist_to_hub_miles | float64 | 100% | Demand-weighted average distance from region counties to nearest assigned hub (miles) |
| out_of_region_hub | bool | 100% | `True` if any assigned hub's home `region_id` (from Task 4) differs from this region |

**Key statistics**: All 50 capacity slacks ≥ 0 (Constraint 4 satisfied). Region 24 has `n_hubs_assigned = 2`; all others = 1.

**Downstream use**: Task 6 and Task 7 for understanding regional coverage quality and identifying areas needing gateway node supplementation.

---

## `fig_regional_hub_locations.png` — Regional hub location map (Task 5.6 output)

> **path** · `Data/Task5/figures/fig_regional_hub_locations.png` · **format** · png · **size** · ~636 KB

**Context**: NE county choropleth colored by Task 3.2 region (tab20 colormap), with 51 selected hub markers (★) colored by their primary served region and sized proportional to `usable_available_space_sf`. State outlines overlaid in black.

---

## `fig_regional_hub_network.png` — Regional hub network map (Task 5.6 output)

> **path** · `Data/Task5/figures/fig_regional_hub_network.png` · **format** · png · **size** · ~860 KB

**Context**: Grey county basemap with NE US interstate overlay (light blue), 51 gold hub stars, and 140 network links. Link thickness is proportional to inverse distance (thicker = shorter); red links indicate shared-region co-assignments (p_h = 2 case).
