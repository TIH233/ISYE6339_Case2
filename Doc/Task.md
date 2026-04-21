# Casework Tasks


### Task 1 — County-to-County Freight Flow Matrix `[complete]`

Build the NE megaregion O-D matrix and produce Pareto summaries by mode, trade type, and commodity for 2025 and 2030.

**Methodology implemented:**
- Loaded FAF experimental county-county parquet (`northeast_c2c_all_modes.parquet`) containing all-mode O-D flows for all US county pairs
- Standardized FIPS codes to 5-digit strings; joined with `county_fips_lookup_clean.xlsx` to tag each county as Northeast or non-Northeast
- Classified every flow record into `internal` (NE→NE), `inbound` (external→NE), `outbound` (NE→external), or `outside_outside`; retained only the first three
- Produced per-flow-type tonnage subtotals (2025 & 2030) and Pareto breakdowns by mode, trade type, and commodity group
- Identified top-50 origin and destination counties by truck tonnage
- Intermediate results saved to `Data/Task1/`

**Key outputs:** `raw.parquet`, `breakdown_by_flow_type.csv`, `breakdown_by_mode.csv`, `breakdown_by_trade_type.csv`, `ne_state_summary.csv`, `top50_origin_counties.csv`, `top50_dest_counties.csv`

---

### Task 2 — Global, Continental, and National Interface Nodes `[complete]`

Identify major seaports, cargo airports, border crossings, and external demand-dense nodes; estimate throughput volumes; produce interface maps.

**Implementation reference:**

#### Task 2.1 — External Flow Isolation `[complete]`

Loaded the FAF county-county flow parquet and county FIPS lookup, standardized all FIPS fields, tagged origin/destination counties as inside or outside the 14-state NE megaregion, and retained only `inbound` and `outbound` records for Task 2. A compact external-flow table was saved for reuse.

**Key reference:** external flows exclude `internal` and `outside_outside` records.
**Working cache:** `task2_flows_compact.parquet`

#### Task 2.2 — Assignment Bucketing `[complete]`

Assigned every external flow record to one mutually exclusive interface bucket using priority-ordered rules:

- `global_maritime` for water flows (`mode == 3`)
- `continental_border` for Canada-border-state flows (NY, VT, NH, ME) after maritime exclusion
- `global_air` for air-related flows (`mode` 5 or 11) after the above
- `national_domestic` for all remaining external domestic flows

This bucket logic is the bridge between raw external flows and node-level allocation.

#### Task 2.3 — Global Interface Nodes `[complete]`

Built the global tier from two components:

- Maritime: shortlisted major NE coastal seaports from the NTAD commercial seaport dataset and allocated `global_maritime` tonnage across the selected ports
- Air: shortlisted seven major NE cargo airports and allocated `global_air` tonnage using air-truck facility area shares (`EST_AREA`) as the throughput proxy

**Key finding:** Hampton Roads and Philadelphia anchor the maritime side; JFK, PHL, and EWR dominate the air side.

#### Task 2.4 — Continental Interface Nodes `[complete]`

Used the BTS border-crossing dataset, filtered to the US-Canada border and freight-relevant truck/rail measures, restricted the geography to NY, VT, NH, and ME, aggregated crossings to a node-level `throughput_proxy`, ranked crossings, and allocated the `continental_border` tonnage bucket proportionally across the top eight nodes.

**Key finding:** Buffalo Niagara Falls and Champlain–Rouses Point are the dominant continental gateways.

#### Task 2.5 — National Interface Nodes `[complete]`

Aggregated the compact external-flow table twice:

- inbound external origins sending freight into the NE
- outbound external destinations receiving freight from the NE

These were combined into a bilateral county interaction table, ranked by `tons_2025`, and reduced to the top 12 external counties. Tonnage was allocated proportionally using county bilateral throughput as the proxy.

**Key finding:** the national tier concentrates in Ohio, Texas, and major Midwest / mid-Atlantic logistics corridors.

#### Task 2.6 — Mapping and Final Outputs `[complete]`

Produced separate global, continental, and national interface maps on an NE basemap and exported the final node tables for downstream tasks.

**Key outputs:** `Data/Task2/task2_global_interface_nodes_final.csv`, `Data/Task2/task2_continental_interface_nodes_final.csv`, `Data/Task2/task2_national_interface_nodes_final.csv`
**Downstream use:** Task 3.1 uses these node tables for the composite demand-and-corridor map.

---

### Task 3 — Region Clustering `[complete]`

Demand-balanced, geographically contiguous and compact clusters aligned to interstate corridors; justify parameters and assess quality.

#### Task 3.1 — Demand Map Construction `[complete]`

Task 3.1 built the demand-mapping inputs for clustering by loading `Data/Task1/raw.parquet`, removing non-palletizable bulk commodities (`sctg1014`, `sctg1519`), standardizing county FIPS, and computing two separate county-level demand metrics:

- **Activity throughput** (`county_activity_throughput.parquet`): bidirectional all-flow endpoint sum used for heatmap / visualization only. Do not use for hub sizing.
- **External throughput** (`county_external_throughput.parquet`): flows where one endpoint is NE and the other is non-NE. Hub-facing demand proxy used as clustering demand weight. A post-assignment correction (`Task3/recompute_region_external_demand.py`) further excludes same-final-region flows.

The workflow joined the activity throughput to Census county boundaries for the 14-state NE megaregion, overlaid clipped NTAD interstate segments, Census rail segments, and Task 2 interface nodes, and produced a publication-quality heatmap and composite infrastructure map. Temporary intermediates (`freight_clean.parquet`, `ne_interstates.parquet`, `ne_railroads.parquet`) were deleted after validation. **Retained outputs:** `Data/Task3/derived/county_activity_throughput.parquet`, `Data/Task3/derived/county_external_throughput.parquet`, `Data/Task3/figures/fig_demand_heatmap.png`, `Data/Task3/figures/fig_composite_map.png`.

#### Task 3.2 — Region Clustering (Simulated Annealing) `[complete]`

Partition the 434 NE county-equivalent units into `k = 50` demand-balanced, spatially contiguous, compact regions aligned to major interstate/rail corridors using a Simulated Annealing (SA) graph-partitioning heuristic. Use `external_throughput` from `Data/Task3/derived/county_external_throughput.parquet` as the county demand weight (`demand_weight`, NE-to-non-NE boundary flows in thousand short tons). Algorithm design is documented in `Task3/Cluster.md`, but the implementation below is the executable specification.

**Implementation reference:**

#### Task 3.2.1 — NE County Preparation `[complete]`

Loaded the national county shapefile from `Data/Task3/raw/census_counties/`, filtered to the 14-state study area, joined the activity throughput from `Data/Task3/derived/county_activity_throughput.parquet` (visualization reference column), then joined external throughput from `Data/Task3/derived/county_external_throughput.parquet` as `demand_weight` (the SA clustering weight), projected the polygons to `EPSG:9311`, computed centroid coordinates, and cached the prepared 434-unit layer.

**Key reference:** the valid clustering study area is **434** county-equivalent units, not a historical county count from another source.
**Output:** `Data/Task3/derived/ne_counties_prepared.gpkg`

#### Task 3.2.2 — Adjacency and Corridor Weights `[complete]`

Built the county graph using **positive shared border length** as the adjacency rule, excluded point-only contacts, patched the known island cases with documented synthetic links, and cached the base edge list. Then overlaid `Data/Task3/raw/roads/North_American_Roads.shp` and `Data/Task3/raw/rails/tl_2023_us_rails.shp` to compute `interstate_km`, `rail_km`, and normalized `infra_weight` per county-to-county edge.

**Key reference:** `touches()` alone is not sufficient for this task; rook-style shared-border adjacency is the production rule.
**Outputs:** `Data/Task3/cache/ne_county_edges.parquet`, `Data/Task3/cache/ne_county_edges_infra.parquet`

#### Task 3.2.3 — Initialization `[complete]`

Generated the warm start in two phases:

- weighted K-means on county centroids to choose 50 dispersed seed counties
- contiguous region growing over the county graph with distance and demand-overshoot penalties

This produced a valid initial partition that was materially better than a pure BFS or nearest-centroid start.

**Cached outputs:** `Data/Task3/cache/init_assignment.npy`, `Data/Task3/cache/init_assignment_fips.parquet`

#### Task 3.2.4 — Objective and Constraints `[complete]`

Implemented a normalized three-part objective:

- alignment penalty from corridor-weighted cut edges
- compactness penalty from within-region centroid SSE
- demand-balance penalty from deviation from target throughput `W*`

Implemented local `ΔJ` updates and hard move filters:

- adjacent-region moves only
- donor region cannot become empty
- donor region must remain connected after removal
- optional geometry screening treated only as a proxy, not as the paper's 5.5-hour rule

**Coding reference:** all expensive geometry work is cached before optimization; the move loop runs on arrays, adjacency lists, and cached region statistics only.

#### Task 3.2.5 — Simulated Annealing Search `[complete]`

Ran the SA search with cached arrays and graph structures, empirical temperature scaling, multiple restarts, resumable checkpoints, and proposal logging. The implementation is in `Task3/clustering.py`, and the executed workflow is in `Task3/task3_2_clustering.ipynb`.

**Key cache/log outputs:** `Data/Task3/cache/sa_best_assignment.npy`, `Data/Task3/cache/sa_best_fips.parquet`, `Data/Task3/cache/sa_log.csv`

#### Task 3.2.6 — Quality Assessment `[complete]`

Evaluated the final solution on:

- demand balance
- compactness
- corridor alignment
- contiguity across all 50 regions

The final saved solution achieved:

- `Best J = 0.490952`
- `Initial J = 1.620501`
- `J improvement = 69.7%`
- `CV = 0.291`
- `nRMSE = 0.291`
- `Alignment cut fraction = 0.3199`
- all 50 regions contiguous

#### Task 3.2.7 — Figures and Exports `[complete]`

Saved the clustering diagnostics, final map, and tabular outputs for downstream tasks.

**Figures:** `Data/Task3/figures/fig_sa_convergence.png`, `Data/Task3/figures/fig_demand_balance.png`, `Data/Task3/figures/fig_region_map.png`
**Outputs:** `Data/Task3/outputs/region_assignment.csv` (with `external_throughput_ktons` and `activity_throughput_ktons` per county), `Data/Task3/outputs/region_metrics.csv` (with both `activity_throughput_ktons` and `external_throughput_ktons` per region)
**Post-assignment correction:** run `Task3/recompute_region_external_demand.py` to produce `Data/Task3/outputs/region_external_metrics.csv` with fully corrected hub-facing demand that excludes same-final-region flows.
**Downstream use:** `external_throughput_ktons` in `region_metrics.csv` feeds hub location and capacity decisions in Tasks 5+. Use `activity_throughput_ktons` for visualization only.

---

### Task 4 — Regional Node Candidates `[complete]`

Screen CoStar data; distinguish directly usable facilities from proxy locations.

---

### Task 5 — Regional Node Network `[complete]`

Select regional hubs from the CoStar candidate pool using a capacity-aware set-cover MIP, then define the regional hub network topology using geographic and freight-interaction criteria.

---

#### Formulation

##### Sets and indices

| Symbol | Definition |
| ------ | ---------- |
| H | Set of pre-screened regional hub candidates (indexed by h) |
| R | Set of 50 Task 3 regions (indexed by r) |
| C_r | Set of county-equivalent units in region r |
| Z | Set of feasible hub–region pairs: (h,r) ∈ Z iff Euclidean distance from hub h to region r centroid ≤ 150 miles |

##### Parameters

| Symbol | Definition | Source |
| ------ | ---------- | ------ |
| s_h | Usable available floor area of hub h (sqft) | Task 4 `primary_regional_hub_candidates.csv` |
| w_cr | Flow-based weight of county c in region r = county 2025 external throughput (ktons; NE-to-non-NE boundary flows) | Task 3 `county_external_throughput.parquet` joined via `region_assignment.csv` |
| d_hcr | Euclidean distance (EPSG:9311 meters) from hub h to centroid of county c in region r | Computed from hub lat/lon projected to EPSG:9311 |
| d_h^road | Euclidean distance (EPSG:9311 meters) from hub h to the nearest US interstate segment | Computed from `North_American_Roads.shp` (CLASS=1, COUNTRY=2) |
| β | Road accessibility threshold: hubs with d_h^road > β are excluded from H | Set at the 90th percentile of the candidate-to-interstate distance distribution |
| Q̄ | Median usable sqft across all candidates in H; target capacity assignment for an average-demand region | Computed from H |
| T_r | Total 2025 external throughput of region r (ktons; `external_throughput_ktons`) | Task 3 `region_metrics.csv` |
| T̄ | Mean regional external throughput across all 50 regions (ktons) | Computed from region_metrics |

##### Objective cost term

The per-assignment cost discounts larger facilities to encode a capacity preference with no free parameter:

ĉ_hr = (∑_{c ∈ C_r} w_cr · d_hcr) · (Q̄ / s_h)^0.5

The square-root exponent keeps geography primary while giving larger facilities a moderate discount. A facility at the median size gets no adjustment; the largest facility (500k sqft) receives approximately a 37% cost reduction relative to the smallest post-screened facility (200k sqft).

##### Variables

| Variable | Domain | Meaning |
| -------- | ------ | ------- |
| O_h | {0,1} | 1 if hub h is opened |
| A_hr | {0,1} | 1 if hub h is assigned to serve region r |

##### MIP formulation

Minimize:

    ∑_{(h,r)∈Z} A_hr · ĉ_hr

Subject to:

1. ∑_{h:(h,r)∈Z} A_hr ≥ 1                          ∀r ∈ R       [coverage: every region gets ≥1 hub]
2. ∑_{r:(h,r)∈Z} A_hr ≤ 2                          ∀h ∈ H       [concentration cap: each hub serves ≤2 regions]
3. O_h ≤ ∑_{r:(h,r)∈Z} A_hr                         ∀h ∈ H       [hub opens only if assigned to ≥1 region]
4. ∑_{h:(h,r)∈Z} A_hr · s_h ≥ Q̄ · (T_r / T̄)      ∀r ∈ R       [capacity coverage: assigned sqft ≥ demand-scaled target]
5. A_hr = 0  ∀h ∈ H with d_h^road > β                             [road gate: remote hubs excluded]
6. A_hr, O_h ∈ {0,1}

Notes on constraint design:

- Constraint 1 with p_h = 2 (constraint 2) yields approximately 25–50 open hubs; no explicit hub-count bound needed.
- Constraint 4 uses sqft on both sides (no tons conversion). With Q̄ = 306,250 sqft and the pre-screened candidate pool capped at 500k sqft, the highest-demand regions can require two assigned hubs; the constraint redirects the optimizer away from under-sized facilities toward larger feasible facilities within the same Z neighborhood.
- Constraint 5 is implemented as a pre-filter on H rather than a MIP constraint, reducing model size.
- The road-access soft penalty term (w^road · ∑ O_h · d_h^road) is dropped; β-gating as a hard pre-filter is sufficient and avoids calibrating an additional weight.

Solver: Gurobi (via `gurobipy`), with a 10-minute time limit and a 1% MIP gap.

---

#### Data inputs required from Task 4

Task 5 does not re-run Task 4 preprocessing. The following files are consumed as-is:

| File | Usage in Task 5 |
| ---- | --------------- |
| `Data/Task4/processed/primary_regional_hub_candidates.csv` | Base candidate pool (1,862 rows): lat/lon, `usable_available_space_sf`, `region_id`, `candidate_id`, `facility_name` |
| `Data/Task4/processed/preprocessed_capacity_location.csv` | Supplementary source for fallback candidates (50k–100k sqft) in sparse regions |

The H construction step in Task 5.1 applies the size floor and sparse-region fallback logic to these files.

---

#### Task 5.1 — Candidate Set H and Z Construction `[complete]`

Build the filtered hub candidate set H and the feasibility set Z.

##### H construction (adaptive floor)

- Base filter: keep candidates with `usable_available_space_sf ≥ 200,000` sqft from `primary_regional_hub_candidates.csv` (already enforced by Task 4).
- Sparse-region fallback: for any region r where fewer than 2 candidates pass the base filter AND the region has no Z-neighbors with ≥2 candidates within 75 miles, include candidates from `preprocessed_capacity_location.csv` with `usable_available_space_sf ≥ 50,000` sqft from within that region.
- No sparse-region fallback was triggered in the current run.
- After the road-access β gate, region 25 has 0 in-region H candidates but remains covered by 708 feasible external Z-hubs within 150 miles.
- Report final |H| and per-region candidate count after floor and road-access filtering.

##### Road accessibility pre-filter (β gate)

- Load `North_American_Roads.shp`, filter to US interstates (COUNTRY=2, CLASS=1), project to EPSG:9311.
- For each candidate in H, compute d_h^road as the minimum Euclidean distance (EPSG:9311 meters) to any interstate segment using a spatial index (STRtree).
- Compute the distribution of d_h^road across H; set β = 90th percentile value.
- Remove candidates with d_h^road > β from H; report how many are excluded.
- Save candidate-level d_h^road values for reporting.

##### Z construction

- Project all candidates in H to EPSG:9311 using lat/lon.
- Load region centroids from `region_metrics.csv` (centroid_x_m, centroid_y_m in EPSG:9311).
- Compute Euclidean distance from each h to each r centroid; flag pairs with distance ≤ 241,402 m (150 miles).
- Build Z as a list of (h, r) index pairs.
- Verify that every region r ∈ R has at least one (h, r) ∈ Z; report coverage gaps if any.

Key outputs: filtered H dataframe with d_h^road (`H_candidates.parquet`, 1,675 rows), Z index pairs (`Z_pairs.npy`, 26,133 pairs), β value (`beta_m.npy`, 12,831 m).

---

#### Task 5.2 — Objective Coefficients and Capacity Parameters `[complete]`

Pre-compute all MIP coefficients outside the solver loop.

##### County centroid distances (d_hcr matrix)

- Load `ne_counties_prepared.gpkg`; extract centroid_x, centroid_y (EPSG:9311) and throughput per county.
- For each (h, r) ∈ Z: compute d_hcr for all counties c ∈ C_r as Euclidean distance from hub h to county centroid c. Store as a nested dict or sparse array indexed by (h, r).
- Load `region_assignment.csv` to map county FIPS to region_id.

##### Objective cost coefficients (ĉ_hr)

- For each (h, r) ∈ Z: ĉ_hr = (∑_{c ∈ C_r} throughput_c · d_hcr) · (Q̄ / s_h)^0.5
- Q̄ = median s_h across final H.

##### Capacity constraint RHS

- T̄ = mean T_r across 50 regions.
- For each r: RHS_r = Q̄ · (T_r / T̄).
- Report the distribution of RHS_r and confirm that any region with max(RHS_r) > max(s_h) has enough feasible hubs for multi-hub capacity coverage.

Key outputs: coefficient dict `c_hat[h,r]`, RHS array `cap_rhs[r]`, scalar Q̄, T̄.

---

#### Task 5.3 — MIP Build and Gurobi Solution `[complete]`

Build and solve the MIP using `gurobipy`.

##### Model construction

- Binary variables: A[h,r] for (h,r) ∈ Z; O[h] for h ∈ H.
- Objective: minimize ∑_{(h,r)∈Z} c_hat[h,r] · A[h,r].
- Constraints 1–4 as specified in the formulation; constraint 5 enforced by H pre-filter (no β variables in model).
- Solver parameters: TimeLimit=600s, MIPGap=0.01, OutputFlag=1.

##### Solution extraction

- Extract selected hubs from active assignments: {h : ∃r with A[h,r].X > 0.5}. The implementation does not rely on `O[h].X` because the activation constraint is one-sided and `O_h` has no objective cost.
- Extract assignments: {(h,r) : A[h,r].X > 0.5}.
- Record objective value, MIP gap, solve time.

Key outputs: `task5_selected_hubs.csv` (hub metadata + region assignments), `task5_hub_region_assignments.csv` (full (h,r) pair list).

---

#### Task 5.4 — Solution Analysis and Regional Hub Characterization `[complete]`

Characterize the selected hub set and assess solution quality.

Per-hub report: for each selected hub h — candidate_id, facility_name, city, state, region(s) served, s_h (sqft), d_h^road (miles), ĉ_hr for each assigned region.

Per-region report: for each region r — assigned hub(s), total assigned sqft vs. RHS_r (capacity slack), demand-weighted distance to assigned hub(s), flag if served by out-of-region hub.

##### Aggregate statistics

- Total open hubs, hubs serving 1 vs. 2 regions, regions served by out-of-region hubs.
- Distribution of assigned sqft by region relative to RHS_r.
- Cross-check: does region 25 (0 in-region H candidates after β-gating) have valid external hub coverage?

**Implementation reference:**

MIP solution: OPTIMAL, 0.4352% gap, 0.14 s solve time. Selected **50 hubs** covering all 50 regions with **52 hub-region assignments**. Regions 0 and 7 each receive 2 assigned hubs to satisfy capacity; all other regions receive 1 assigned hub.

**Key findings:**

- Total open hubs: 50; 48 serve 1 region and 2 serve 2 regions (`h_idx=697` serves regions 34 and 45; `h_idx=1631` serves regions 4 and 41)
- Out-of-region hubs: checked per region (hub's home region_id vs. served region_id)
- Capacity slack: all regions satisfied; min slack determined from assigned sqft − RHS_r
- Demand-weighted distance to assigned hub: varies by region geography
- Region 25 has no in-region H candidate after β-gating but receives valid external hub coverage through Z

Key outputs: `hub_report` and `region_report` DataFrames (feeds into `region_hub_summary.csv` in 5.6).

---

#### Task 5.5 — Network Link Definition (Flow-Weighted Hybrid Strategy) `[complete]`

Define the principal links of the regional hub network using a **hybrid flow-weighted strategy** combining Delaunay triangulation, region-to-region freight interaction intensity, and operational distance constraints (Handout Task 5c requirement: "travel time, infrastructure continuity, and expected freight interaction").

##### Method Overview

**Three-stage hybrid approach**:

1. **Spatial Foundation**: Delaunay triangulation + shared-region links → 137 baseline links (pruned at 350 mi)

2. **Flow Measurement**: Compute region-to-region freight interaction from county-level flows (`raw.parquet`):
   - Filter truck-compatible freight (exclude SCTG coal/gravel) → 27.3M records
   - Aggregate to 50×50 region-pair matrix → 2,500 flows (26–115,507 k-tons)
   - Flow intensity metric: $\text{flow}(h_a, h_b) = \sum_{r_i \in \text{regions}(h_a), r_j \in \text{regions}(h_b)} (\text{tons}_{r_i \to r_j} + \text{tons}_{r_j \to r_i})$

3. **Hybrid Refinement**:
   - **Prune** if flow < 10th pct (< 1,001 k-tons) AND distance > 70th pct (> 93 mi) → 9 removed
   - **Supplement** if flow ≥ 75th pct (≥ 8,787 k-tons) AND distance ≤ 350 mi → 5 added
   - **Final network**: 133 links (min flow: 516 k-tons, mean: 7,532 k-tons, max: 51,469 k-tons)

##### Key Results

| Metric | Delaunay (137) | Flow-Weighted (133) | Improvement |
|--------|----------------|---------------------|-------------|
| Mean flow intensity | 6,912 k-tons | 7,532 k-tons | +9% |
| Min flow intensity | 92 k-tons | 516 k-tons | +461% (outlier removed) |
| Mean distance | 75.9 mi | 69.2 mi | −8.8% (more local) |

**Example pruned**: Howell, NJ ↔ Chesapeake, VA (261 mi, 92 k-tons) — inefficient outlier  
**Example added**: Buffalo Road ↔ FedEx (65 mi, 15,280 k-tons) — critical missing corridor

Key outputs: `task5_hub_network_links_flow_weighted.csv` (133 final links), `region_flow_matrix.parquet` (cached 2,500 region pairs). Implementation: `Task5/flow_weighted_links.py`.

---

#### Task 5.6 — Figures and Exports `[complete]`

Produce the final map, network diagram, and tabular outputs for Task 5 reporting.

##### Outputs

**Figures** (all under `Data/Task5/figures/`):
- `fig_regional_hub_locations_flow.png`: Hub markers on NE basemap, colored by region, sized by sqft
- `fig_regional_hub_network_flow.png`: **Flow-weighted network** (link thickness ∝ flow_intensity, 0.5–6.0 linewidth range)

**Tabular exports** (all under `Data/Task5/`):
- `selected_hubs.csv`: 50 hubs with full characterization
- `hub_region_assignments.csv`: 52 hub-region assignments
- `task5_hub_network_links_flow_weighted.csv`: **133 flow-weighted links** (final network for Tasks 6+)
- `region_hub_summary.csv`: Per-region coverage summary
- `cache/region_flow_matrix.parquet`: 2,500 region-pair flows (reusable cache)

**Implementation**: Flow-weighted pipeline in `Task5/task5_mip.ipynb` (cells 5.1–5.6).

---

### Task 6 — Gateway Node Design `[complete]`

Cluster counties into freight areas within each region; screen CoStar for gateway candidates; select nodes avoiding redundancy. Implemented in two phases: **Phase 1** `[complete]` — population-typed Simulated Annealing (SA) area clustering using a standalone Task 6 module patterned after Task 3; **Phase 2** `[not started]` — Set-Cover MIP gateway hub selection per area.

---

#### EDA-Confirmed Parameters (do not re-derive without re-running EDA)

The following values were confirmed by a pre-implementation EDA (deleted after analysis):

| Statistic | Value |
| --------- | ----- |
| NE counties in study | 434 |
| Regions | 50 |
| Mean counties/region | 8.7 (std 7.3, min 1, max 33) |
| Regions with n_counties < 4 | 15 (see list below) |
| Regions with n_counties < 3 | 11 |
| Regions with n_counties < 2 | 3 (regions 0, 7, 12) |
| Mean region span (max pairwise county-centroid) | 82 mi (std 66, max 327) |
| Large-span regions (> 150 mi) | 9 (see list below) |
| Gateway candidates ≥ 20k sqft (full pool) | 2,064 (all from `preprocessed_capacity_location.csv`) |
| Regions with < 10 gateway candidates | 2 (regions 40 and 26) |
| Population data source | Census 2020 DEC PL `P1_001N`; 9 NE counties missing → fallback to ACS 5-year |

**Regions with n_counties < 4 (need min-area cap):**

|region_id|n_counties|states|can form ≥|
|---------|----------|------|----------|
|0|1|PA|1 area max|
|7|1|NY|1 area max|
|12|1|NJ|1 area max|
|3|2|NJ, NY|2 areas max|
|17|2|MD|2 areas max|
|18|2|NJ|2 areas max|
|30|2|PA|2 areas max|
|34|2|NY, NJ|2 areas max|
|36|2|NJ|2 areas max|
|40|2|VA|2 areas max|
|42|2|PA|2 areas max|
|6|3|PA|3 areas max|
|11|3|PA|3 areas max|
|24|3|NJ|3 areas max|
|35|3|NY|3 areas max|

**Regions qualifying for travel-time exemption (span > 150 mi; areas may exceed the 80-mile cross-area guideline):**

|region_id|span (mi)|n_counties|states|gw_candidates|
|---------|---------|----------|------|-------------|
|15|327|33|ME, NH, VT|94|
|32|205|21|PA, WV, MD|32|
|19|191|19|MA, NY, VT|73|
|33|191|8|NY, VT|26|
|9|165|17|VA|49|
|4|160|24|WV, VA|15|
|21|159|13|NY, PA|23|
|46|158|18|VA, WV|13|
|41|155|20|VA, WV|34|

**Regions 4 and 16 (Type C, WV/VA Appalachian)** have < 2 gateway candidates per estimated area — accepted implementation risk; document in Phase 2.

---

#### Task 6.1 — Population Data Acquisition `[complete]`

Fetch Census 2020 county-level total population (`P1_001N`) for all 434 NE counties.

- Primary source: Census 2020 DEC PL API — `https://api.census.gov/data/2020/dec/pl?get=P1_001N&for=county:*&in=state:{sf}` for each of the 14 state FIPS codes: `09 10 11 23 24 25 33 34 36 42 44 50 51 54`.
- 9 counties are missing from the DEC PL response (DC county-equivalent and WV edge cases). For these, fetch from ACS 5-year estimates `https://api.census.gov/data/2022/acs/acs5?get=B01003_001E&for=county:*&in=state:{sf}` as fallback.
- Join on 5-digit FIPS (`str.zfill(5)`); assert 0 missing after fallback.
- Output: `Data/Task6/ne_county_population.csv` — 434 rows × 2 cols (`fips`, `pop2020`).

---

#### Task 6.2 — Region Type Classification `[complete]`

Classify each of the 50 regions into one of 3 population-based types that determine the fixed minimum area count used by the Phase 1 SA workflow.

##### Type assignment

Compute per-region summary from `ne_county_population.csv` joined via `region_assignment.csv`:

- `total_pop` = sum of county populations in the region
- `max_county_pop` = population of the largest county in the region

Composite score: `score_r = 0.6 * rank(total_pop_r) + 0.4 * rank(max_county_pop_r)`

Assign types by tertile of `score_r`:

- **Type A (Urban/Metro)**: top tertile — 17 regions; total_pop range ≈ 1.25M–8.56M; median ≈ 2.42M; targets ≥ 4 areas per region
- **Type B (Suburban)**: middle tertile — 16 regions; total_pop range ≈ 696k–1.76M; median ≈ 950k; targets ≥ 3 areas per region
- **Type C (Rural/Sparse)**: bottom tertile — 17 regions; total_pop range ≈ 429k–873k; median ≈ 678k; targets ≥ 2 areas per region

##### Minimum area cap rule (critical)

The hard floor on number of areas is:

    min_areas_effective[r] = min(min_areas_type[type(r)], n_counties[r])

Rationale: 6 Type A and 3 Type B regions have fewer counties than their type's min area target in the current classification. A region cannot produce more areas than it has counties in the fixed-k area clustering workflow.

Output: `region_type` column appended to `region_metrics` working frame.

---

#### Task 6.3 — SA Objective Setup & Initialization `[complete]`

Define the SA objective and build the initial area assignment for each region.

##### Target area count and population target

For each region `r`:

    k_r        = min_areas_effective[r]          # fixed k from Task 6.2
    pop_target = total_pop[r] / k_r              # BFS initializer reference only

`pop_target` guides the BFS growing phase to produce roughly balanced starting areas.
It is **not** a hard constraint and is **not** a balance objective in the SA — see below.

##### SA objective function (two-component)

$$J_r = w_\text{compact} \cdot C_\text{compact} + w_\text{spread} \cdot C_\text{spread}$$

- **C\_compact** — geographic SSE within areas:

$$C_\text{compact} = \frac{1}{N_r \cdot D_r^2} \sum_{i \in r} \|(x_i, y_i) - \mu_{a_i}\|^2$$

where $D_r$ is the bounding-box diagonal of region $r$'s counties (meters) and $\mu_{a_i}$ is the unweighted centroid of area $a_i$.

- **C\_spread** — soft penalty for areas exceeding the 80-mile cross-area distance guideline (**non-exempt regions only**; exempt set: region_ids 4, 9, 15, 19, 21, 32, 33, 41, 46):

$$C_\text{spread} = \frac{1}{k_r} \sum_{a \notin \text{exempt}} \left(\frac{\max(0,\ d_{\max,a} - 80\ \text{mi})}{80\ \text{mi}}\right)^2$$

where $d_{\max,a}$ = max pairwise Euclidean distance between county centroids in area $a$.

**Weights**: $w_\text{compact} = 1.0$, $w_\text{spread} = 2.0$.

**Why no balance term**: Areas are geographic groupings for gateway hub siting only.
Phase 2's Set-Cover MIP scales hub count to each area's own freight demand independently —
cross-area population equity is not a design requirement at this tier.  A balance term
copied from Task 3 (where demand equity across 50 regions *is* a design goal) would
actively harm area clustering by freezing the SA whenever an area approached the
population target, reducing spread-optimization effectiveness.

##### ΔJ incremental evaluation

$\Delta C_\text{compact}$ is evaluated by direct SSE recompute on the two affected areas (O(|area|); areas are small). $\Delta C_\text{spread}$ evaluates only on the two affected areas.

##### Initialization (per region)

Two-phase init:

1. **Seed selection** — pick $k_r$ counties by maximin geographic spread (iteratively choose the county farthest from all previously chosen seeds). Fallback to uniform random for $k_r = 1$.
2. **BFS growth** — priority-queue BFS scoring candidate counties by:

$$\text{score}(i, a) = \alpha_\text{dist} \cdot d(i, \mu_a) + \alpha_\text{balance} \cdot \max\!\left(0,\ \frac{p_a + p_i - p^*}{p^*}\right)$$

with $\alpha_\text{dist} = \alpha_\text{balance} = 0.5$.  Population is used here for initialization quality only.

3. **Island counties** (no intra-region neighbor): pre-assign to nearest BFS cluster centroid; exclude from SA border set.

---

#### Task 6.4 — SA Area Clustering `[complete]`

Run the SA loop per region using the objective from Task 6.3. The implementation is standalone, but follows the same graph-partitioning architecture used for Task 3.

##### Implementation reference

The area-clustering logic is implemented in `Task6/area_clustering.py`; the executed workflow, cache validation, output assembly, and figure generation are in `Task6/task6_phase1.ipynb`.

| Function | Role |
| --- | --- |
| `build_region_graph(fips_list, edges_df)` | NetworkX subgraph for counties in region |
| `initialize_area_partition(fips, cx, cy, pop, G, k_r)` | Maximin seeds + BFS growth |
| `AreaStats` | Mutable area count/population/centroid cache; affected-area SSE and spread are recomputed directly for accuracy |
| `compute_delta_J_area(...)` | Incremental ΔJ for compact + spread on the two affected areas |
| `is_feasible_area(...)` | Hard constraint checker (see below) |
| `run_sa_area(...)` | SA loop for one region |
| `run_all_regions(...)` | Outer loop over 50 regions; returns the area label table consumed by the notebook |

##### Hard constraints — `is_feasible_area`

For a proposed move of county $i$ from area $a_\text{from}$ to area $a_\text{to}$:

1. **Adjacency**: $\exists$ neighbor $j$ of $i$ in $a_\text{to}$ — county must border the target area.
2. **Non-empty donor**: $|a_\text{from}| > 1$ — donor must not be emptied.
3. **Contiguity**: $a_\text{from} \setminus \{i\}$ remains connected (BFS on county edge subgraph).

The population-floor constraint (originally constraint 4) has been removed. Areas are gateway-hub groupings; Phase 2 handles hub viability independently via the 20k sqft threshold. A floor equal to `p_target` would freeze the SA once any area reached its population target, preventing spread optimisation.

Note: the 80-mile distance constraint is a soft penalty in $C_\text{spread}$, not a hard cut.

##### SA schedule (per region)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `n_proposals` | `max(5_000, 800 × n_counties_r)` | Scales with region size |
| `alpha` | 0.998 | Slower cooling than Task 3 (fewer counties = smaller search space) |
| `T0` | sampled from 200 random feasible \|ΔJ\| | Same method as Task 3 `_sample_T0` |
| `T_min` | 1e-6 | |
| `n_restarts` | 2 | Best of 2 independent restarts with different random seeds |
| `patience` | 2,000 | Early stop if no J improvement |

The notebook first validates `Data/Task6/cache/area_labels.parquet`; if it has 434 counties and the expected per-region area counts, it reuses the cache. Otherwise, it recomputes all region-level SA partitions and writes a fresh cache. The current implementation does not write per-restart checkpoint files.

##### Edge cases

- **Single-county region** (regions 0, 7, 12): area `"{r}_0"`, skip SA.
- **`n_counties <= k_r`**: one county per area (trivial partition), skip SA. With the current county-count cap this occurs as equality, not as an infeasible `k_r > n_counties` case.

##### Output

`Data/Task6/cache/area_labels.parquet` — 434-row table: `fips, region_id, area_id`.

---

#### Task 6.5 — Area Post-Processing `[complete]`

Validate SA outputs and compute final diagnostic metrics. SA enforces contiguity as a hard constraint, so most checks are confirmatory.

##### Contiguity verification (assertion)

For each area, BFS-verify the county subgraph is connected. SA's `is_feasible_area` constraint 3 guarantees this for the final solution, but assert post-hoc to catch any initialization artifacts from island counties.

If any area fails (should be rare), split disconnected components into new areas by incrementing the area-id suffix.

##### Travel-time audit (informational, not corrective)

Compute `max_cross_area_dist_miles[a]` = max pairwise Euclidean distance (EPSG:9311 → miles) for all area pairs.

- Log areas where `max_cross_area_dist_miles > 80` and parent region is **not** in the exempt set.
- With the balance term removed, the SA can freely optimise spread; the current solution has **0 non-exempt distance violations**.
- Exempt regions (4, 9, 15, 19, 21, 32, 33, 41, 46): no flag, no action.

##### Infrastructure check (soft, informational only)

For each area, check whether at least one county has `interstate_km > 0` in `ne_county_edges.parquet`. Log areas with no interstate county. No clustering changes — used as Phase 2 gateway hub siting guidance only.

---

#### Task 6.6 — Area Outputs `[complete]`

Produce the area assignment table and metrics for downstream Phase 2 and Task 7 use.

##### Output files

| File | Shape (approx) | Columns |
| ---- | -------------- | ------- |
| `Data/Task6/area_assignment.csv` | 434 × 7 | `fips, county_name, state, region_id, region_type, area_id, pop2020` |
| `Data/Task6/area_metrics.csv` | one row per area × 10 | `area_id, region_id, region_type, n_counties, total_pop, centroid_x_m, centroid_y_m, external_throughput_ktons, max_cross_area_dist_miles, has_interstate` |
| `Data/Task6/figures/fig_area_map.png` | — | NE map with counties colored by area, region outlines, region_type label per region |

Nominal uncapped type-target total is 150 areas. With the critical county-count cap (`min_areas_effective = min(type target, n_counties)`) applied to the current 50-region partition, the effective planned total is **132 areas** (actual: 132 produced). Objective reformulation (compact + spread, no balance) yielded **0 distance violations** in non-exempt regions vs. 5 under the prior balance-heavy formulation.

##### Area centroid

`centroid_x_m, centroid_y_m` = population-weighted mean of county centroids (from `ne_counties_prepared.gpkg` centroid_x/y columns, EPSG:9311), weighted by `pop2020`.

##### External throughput per area

Sum `external_throughput_ktons` from `region_assignment.csv` across all counties in the area. This feeds Phase 2 hub sizing.

---

#### Task 6 Phase 2 — Gateway Hub Selection `[complete]`

##### Overview and Key Differences from Task 5

Apply a single global Set-Cover MIP for gateway hub selection across all 132 areas (analogous to Task 5's region-level MIP, but at the area tier). All differences from Task 5 are listed here for quick orientation:

| Dimension | Task 5 (regional hubs) | Task 6 Phase 2 (gateway hubs) |
|-----------|------------------------|-------------------------------|
| Units covered | 50 regions | 132 areas |
| Candidate pool | `primary_regional_hub_candidates.csv` ≥ 200k sqft, 1,862 rows | `preprocessed_capacity_location.csv` ≥ 20k sqft, 2,064 rows |
| Coverage radius | 150 miles (241,402 m) | 50 miles (80,467 m) |
| Hub count target | 1 per region (min-coverage) | m_a per area (demand-scaled, see Task 6.7) |
| Concentration cap | ≤ 2 regions per hub | ≤ 2 areas per gateway |
| Separation constraint | none | co-area selected gateways must be ≥ 20 miles apart |
| Road gate | β = 90th pct, hard pre-filter | none (gateway hubs tolerate lower interstate proximity) |
| Capacity proxy | Q̄_hub · (T_r / T̄_r) | Q̄_gw · (T_a / T̄_a) |
| Expected open hubs | ~50 | ~319 total gateway slots across 132 areas |

**EDA-confirmed parameters (do not re-derive):**

| Parameter | Value | Source |
|-----------|-------|--------|
| Q̄_gw | 296,862 sqft | median `usable_available_space_sf` in candidate pool |
| T_mean_area | 3,389 ktons | mean `external_throughput_ktons` across 132 areas (`area_metrics.csv`) |
| Expected total gateway slots (Σ m_a) | 319 | EDA on `area_metrics.csv` |
| Areas with 0 in-area candidates | some | resolved by Z_gw 50-mile radius |
| Areas needing Z_gw radius (in-area < m_a) | 13 | resolved by Z_gw radius |

**Implementation location:** `Task6/task6_phase2.ipynb` (new notebook, mirroring `Task5/task5_mip.ipynb` cell structure).

---

#### Task 6.7 — Candidate Set G and Z_gw Construction `[complete]`

Build the gateway candidate set G and the feasibility set Z_gw.

##### G construction

- Load `Data/Task4/processed/preprocessed_capacity_location.csv` (2,064 rows).
- Apply ≥ 20,000 sqft filter on `usable_available_space_sf` (all 2,064 rows pass; actual pool min is 100k).
- **Exclude regional hubs**: drop any candidate whose `candidate_id` appears in `Data/Task5/selected_hubs.csv`. Gateway hubs must be distinct from the already-selected regional tier. Load `selected_hubs.csv`, extract the `candidate_id` column, and filter G accordingly. Report how many candidates are removed (expected: ~50).
- **No road-accessibility β gate** — unlike Task 5, gateway hubs tolerate lower interstate proximity.
- Project each candidate to EPSG:9311 using lat/lon.
- Report: final |G|, per-state count.

##### m_a (target hub count per area)

Compute once from `Data/Task6/area_metrics.csv`:

    T_mean = area_metrics['external_throughput_ktons'].mean()   # ≈ 3,389 ktons (EDA-confirmed)

    m_a[a] = max(1, min(5, ceil(2.0 × T_a / T_mean)))   for each area a

- Floor = 1 (not 2): low-demand areas legitimately need only 1 gateway.
- Cap = 5: prevents runaway count in a few ultra-high-demand metro areas.
- Expected distribution: {1:32, 2:45, 3:32, 4:14, 5:9}, Σ m_a = 319, mean = 2.42.
- **Do not hard-code T_mean**; compute it at runtime from the file so the formula stays correct if area_metrics changes.

##### Z_gw construction

- Load area centroids `centroid_x_m, centroid_y_m` from `area_metrics.csv` (EPSG:9311).
- For each (g ∈ G, a ∈ A): compute Euclidean distance in EPSG:9311 meters.
- Include (g, a) in Z_gw if distance ≤ 80,467 m (50 miles).
- **Also include all in-area candidates** regardless of centroid distance: join G to `area_assignment.csv` on `county_fips = fips`; any candidate whose county belongs to area a is included in Z_gw for (g, a).
- Verify: every area a has ≥ m_a entries in Z_gw. If any area falls short (expected: 0 after radius + in-area inclusion), report it and expand the radius to 100 miles for that area only.

**Known issue — separation feasibility in sparse areas:** Regions 4 and 16 (Appalachian) have < 2 candidates per estimated area. The MIP will attempt to satisfy m_a=1 (low demand) for these areas; log them explicitly after Z_gw construction. No intervention needed — the MIP handles coverage gaps naturally and the report flags them.

##### Pairwise separation clash set S

Precompute before model build (not inside solver):

    S = {(g, g', a) : (g,a) ∈ Z_gw, (g',a) ∈ Z_gw, g < g', dist(g, g') < 32,187 m (20 miles)}

Store S as a list of (g_idx, g_idx', area_id) triples. Report |S| — this determines the number of separation constraints added to the MIP.

**Key outputs:** `Data/Task6/cache/G_candidates.parquet` (2,064 rows with EPSG:9311 coords and m_a per area), `Data/Task6/cache/Z_gw_pairs.npy` (index pairs), `Data/Task6/cache/separation_clashes.parquet` (S triples), `m_a` series saved in `area_metrics_phase2.csv`.

---

#### Task 6.8 — Objective Coefficients and Capacity Parameters `[complete]`

Pre-compute all MIP coefficients outside the solver loop.

##### County centroid distances (d_gca)

- Load `Data/Task3/derived/ne_counties_prepared.gpkg`; extract `centroid_x`, `centroid_y` (EPSG:9311) and `external_throughput_ktons` per county (use as `w_ca`).
- Load `Data/Task6/area_assignment.csv` to map county fips → area_id.
- For each (g, a) ∈ Z_gw: compute d_gca for all counties c ∈ C_a as Euclidean distance from hub g centroid to county centroid c.
- Store as a dict `d_gca[(g_idx, area_id)] = {county_fips: distance_m}` or equivalent sparse structure.

##### Objective cost coefficients (ĉ_ga)

    Q̄_gw = 296,862 sqft   (EDA-confirmed; still recompute at runtime from G)

    ĉ_ga = (∑_{c ∈ C_a} w_ca · d_gca) · (Q̄_gw / s_g)^0.5

Same formula as Task 5. Larger facilities receive a moderate cost discount; geography remains the primary driver.

##### 6.8 — Capacity constraint RHS

    T̄_a = T_mean   (same value used for m_a)
    RHS_a = Q̄_gw · (T_a / T̄_a)   for each area a

Report distribution of RHS_a and confirm that each area has sufficient total feasible capacity in Z_gw (i.e., sum of s_g for all g in Z_gw for that area ≥ RHS_a). Areas failing this check need the Z_gw radius expanded — expected 0 failures given dense candidate pool.

**Key outputs:** `c_hat` dict, `cap_rhs` array, scalar Q̄_gw, T̄_a.

---

#### Task 6.9 — MIP Build and Gurobi Solution `[complete]`

Build and solve the single global MIP using `gurobipy`.

##### 6.9 — MIP Formulation

**Sets and indices:**

| Symbol | Definition |
|--------|-----------|
| G | Gateway candidates (2,064 rows) |
| A | Areas (132) |
| Z_gw | Feasible (g, a) pairs |
| S | Separation clash triples (g, g', a) with dist(g,g') < 20 mi |

**Variables:** `A_ga` ∈ {0,1} for (g,a) ∈ Z_gw; `O_g` ∈ {0,1} for g ∈ G.

**Objective:** minimize ∑_{(g,a)∈Z_gw} A_ga · ĉ_ga

**Constraints:**

| # | Formula | Meaning |
|---|---------|---------|
| 1 | ∑_{g:(g,a)∈Z_gw} A_ga ≥ m_a ∀a | Every area gets ≥ m_a gateways |
| 2 | ∑_{a:(g,a)∈Z_gw} A_ga ≤ 2 ∀g | Each gateway serves ≤ 2 areas |
| 3 | ∑_{g:(g,a)∈Z_gw} A_ga · s_g ≥ RHS_a ∀a | Capacity coverage per area |
| 4 | A_ga + A_g'a ≤ 1 ∀(g,g',a) ∈ S | No two gateways < 20 mi apart in same area |
| 5 | O_g ≤ ∑_{a:(g,a)∈Z_gw} A_ga ∀g | Open only if assigned |
| 6 | A_ga, O_g ∈ {0,1} | Binary |

**Solver parameters:** `TimeLimit=600`, `MIPGap=0.01`, `OutputFlag=1`.

**Note on constraint 4:** S may be large if the candidate pool is dense. If |S| > 500,000, add constraints lazily via a Gurobi callback on integer solutions rather than upfront. Check |S| after Task 6.7 and adjust accordingly.

##### 6.9 — Solution extraction

- Extract selected gateways: `{g : ∃a with A_ga.X > 0.5}` (same pattern as Task 5 — do not rely on `O_g.X`).
- Extract assignments: `{(g, a) : A_ga.X > 0.5}`.
- Record: objective value, MIP gap, solve time.
- If MIP is infeasible (expected: not, but possible for Appalachian sparse areas), report the infeasible areas and relax constraint 1 for those areas to `≥ min(m_a, |Z_gw_a|)`.

**Key outputs:** raw solution dicts; downstream formatting in Task 6.10.

---

#### Task 6.10 — Solution Analysis and Gateway Characterization `[complete]`

Characterize the selected gateway set and assess solution quality.

##### Per-gateway report

For each selected gateway g: `candidate_id`, `facility_name`, `city`, `state`, `area(s) served`, `s_g` (sqft), `distance to area centroid` (miles), `ĉ_ga` for each assigned area.

##### Per-area report

For each area a: assigned gateway(s), total assigned sqft vs. RHS_a (capacity slack), demand-weighted distance to nearest gateway, flag if served by out-of-area candidate (county_fips not in area a).

##### 6.10 — Aggregate statistics

- Total open gateways, gateways serving 1 vs. 2 areas.
- Distribution of assigned sqft by area relative to RHS_a.
- Areas in regions 4 and 16 (Appalachian): report coverage status and actual m_a achieved. These are documented sparse-area risks — do not treat as a solver error.
- Summary table: total gateways by region_type.

**Key outputs:** `hub_report` and `area_report` DataFrames.

---

#### Task 6.11 — Network Link Definition `[complete]`

Define two link types for the gateway tier network.

##### Area-to-regional-hub links

For each area a: connect area's selected gateway(s) to the regional hub(s) assigned to region r = parent region of area a, from `Data/Task5/selected_hubs.csv` and `Data/Task5/hub_region_assignments.csv`.

- Link attributes: `gateway_candidate_id`, `regional_hub_candidate_id`, `region_id`, `area_id`, `distance_miles`, `external_throughput_ktons` (area demand as link weight).
- Every area must have at least one such link. Verify no orphaned areas.

##### Inter-area links (intra-region)

For each pair of areas (a, a') in the same region r: add a link if they share at least one county border (use `Data/Task3/cache/ne_county_edges.parquet` to check county adjacency; two areas are adjacent if any county in a is adjacent to any county in a').

- Link attributes: `area_a`, `area_b`, `region_id`, `shared_borders` (count of adjacent county pairs), `cross_area_flow_ktons` (sum of county-to-county external throughput across the border).

**Key outputs:** `Data/Task6/gateway_area_to_hub_links.csv`, `Data/Task6/gateway_inter_area_links.csv`.

---

#### Task 6.12 — Figures and Exports `[complete]`

Produce final outputs for Task 6 reporting.

##### Figures

| File | Content |
|------|---------|
| `Data/Task6/figures/fig_gateway_hub_locations.png` | NE basemap; gateway markers colored by region, sized by sqft; regional hub markers overlaid for reference |
| `Data/Task6/figures/fig_gateway_hub_network.png` | Area-to-hub links (colored by region) + inter-area links (gray); link thickness ∝ external_throughput_ktons |

##### Tabular exports

| File | Content |
|------|---------|
| `Data/Task6/gateway_selected.csv` | All selected gateways with full characterization |
| `Data/Task6/gateway_area_assignments.csv` | Full (g, a) pair list with ĉ_ga |
| `Data/Task6/gateway_area_to_hub_links.csv` | Area-to-regional-hub links |
| `Data/Task6/gateway_inter_area_links.csv` | Inter-area adjacency links |
| `Data/Task6/area_metrics_phase2.csv` | `area_metrics.csv` extended with `m_a`, `n_selected_gateways`, `total_assigned_sqft`, `capacity_slack`, `demand_weighted_dist_miles` |

---

### Task 7 — Multi-Tier Integration `[not started]`

Combine regional nodes, gateway nodes, regions, and areas into a single hierarchical network; produce maps and diagrams.

---

### Task 8 — Flow Assignment `[not started]`

Assign 2025 and 2030 flows through the network; identify critical nodes and highest-throughput corridors.

---

### Task 9 — Synthesis `[not started]`

Summarize principal challenges, insights, and limitations.
