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

Task 3.1 built the demand-mapping inputs for clustering by loading `Data/Task1/raw.parquet`, removing non-palletizable bulk commodities (`sctg1014`, `sctg1519`), standardizing county FIPS, aggregating 2025 inbound and outbound tonnage into county-level bidirectional throughput, and joining that demand surface to generalized Census county boundaries for the 14-state NE megaregion. The workflow then overlaid clipped NTAD interstate segments, Census rail segments, and Task 2 interface nodes to produce a publication-quality heatmap and composite infrastructure map; temporary intermediates (`freight_clean.parquet`, `ne_interstates.parquet`, `ne_railroads.parquet`) were deleted after validation. **Retained outputs:** `Data/Task3/derived/county_throughput.parquet`, `Data/Task3/figures/fig_demand_heatmap.png`, `Data/Task3/figures/fig_composite_map.png`.

#### Task 3.2 — Region Clustering (Simulated Annealing) `[complete]`

Partition the 434 NE county-equivalent units into `k = 50` demand-balanced, spatially contiguous, compact regions aligned to major interstate/rail corridors using a Simulated Annealing (SA) graph-partitioning heuristic. Use `throughput` from `Data/Task3/derived/county_throughput.parquet` as the county demand weight (2025 bidirectional throughput in thousand short tons). Algorithm design is documented in `Task3/Cluster.md`, but the implementation below is the executable specification.

**Implementation reference:**

#### Task 3.2.1 — NE County Preparation `[complete]`

Loaded the national county shapefile from `Data/Task3/raw/census_counties/`, filtered to the 14-state study area, joined the national `Data/Task3/derived/county_throughput.parquet` table, projected the polygons to `EPSG:9311`, computed centroid coordinates, and cached the prepared 434-unit layer.

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
**Outputs:** `Data/Task3/outputs/region_assignment.csv`, `Data/Task3/outputs/region_metrics.csv`
**Downstream use:** these outputs feed later node-screening and regional network design tasks.

---

### Task 4 — Regional Node Candidates `[complete]`

Screen CoStar data; distinguish directly usable facilities from proxy locations.

---

### Task 5 — Regional Node Network `[in process]`

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
| w_cr | Flow-based weight of county c in region r = county 2025 bidirectional throughput (ktons) | Task 3 `ne_counties_prepared.gpkg` joined to `county_throughput.parquet` |
| d_hcr | Euclidean distance (EPSG:9311 meters) from hub h to centroid of county c in region r | Computed from hub lat/lon projected to EPSG:9311 |
| d_h^road | Euclidean distance (EPSG:9311 meters) from hub h to the nearest US interstate segment | Computed from `North_American_Roads.shp` (CLASS=1, COUNTRY=2) |
| β | Road accessibility threshold: hubs with d_h^road > β are excluded from H | Set at the 90th percentile of the candidate-to-interstate distance distribution |
| Q̄ | Median usable sqft across all candidates in H; target capacity assignment for an average-demand region | Computed from H |
| T_r | Total 2025 bidirectional throughput of region r (ktons) | Task 3 `region_metrics.csv` |
| T̄ | Mean regional throughput across all 50 regions (ktons) | Computed from region_metrics |

##### Objective cost term

The per-assignment cost discounts larger facilities to encode a capacity preference with no free parameter:

ĉ_hr = (∑_{c ∈ C_r} w_cr · d_hcr) · (Q̄ / s_h)^0.5

The square-root exponent keeps geography primary while giving larger facilities a moderate discount. A facility at the median size gets no adjustment; the largest facility (~527k sqft) receives approximately a 44% cost reduction relative to the smallest post-screened facility (~100k sqft).

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
- Constraint 4 uses sqft on both sides (no tons conversion). With Q̄ ≈ 164k sqft and the pre-screened candidate pool capped at 527k sqft, all 50 regions can be satisfied by a single large facility; the constraint primarily redirects the optimizer away from under-sized facilities toward larger ones within the same Z neighborhood.
- Constraint 5 is implemented as a pre-filter on H rather than a MIP constraint, reducing model size.
- The road-access soft penalty term (w^road · ∑ O_h · d_h^road) is dropped; β-gating as a hard pre-filter is sufficient and avoids calibrating an additional weight.

Solver: Gurobi (via `gurobipy`), with a 10-minute time limit and a 1% MIP gap.

---

#### Data inputs required from Task 4

Task 5 does not re-run Task 4 preprocessing. The following files are consumed as-is:

| File | Usage in Task 5 |
| ---- | --------------- |
| `Data/Task4/processed/primary_regional_hub_candidates.csv` | Base candidate pool (458 rows): lat/lon, `usable_available_space_sf`, `region_id`, `candidate_id`, `facility_name` |
| `Data/Task4/processed/preprocessed_capacity_location.csv` | Supplementary source for fallback candidates (50k–100k sqft) in sparse regions |

The H construction step in Task 5.1 applies the size floor and sparse-region fallback logic to these files.

---

#### Task 5.1 — Candidate Set H and Z Construction `[complete]`

Build the filtered hub candidate set H and the feasibility set Z.

##### H construction (adaptive floor)

- Base filter: keep candidates with `usable_available_space_sf ≥ 100,000` sqft from `primary_regional_hub_candidates.csv`.
- Sparse-region fallback: for any region r where fewer than 2 candidates pass the base filter AND the region has no Z-neighbors with ≥2 candidates within 75 miles, include candidates from `preprocessed_capacity_location.csv` with `usable_available_space_sf ≥ 50,000` sqft from within that region.
- Region 43 (ME, 0 candidates at any floor) and Region 19 (rural PA/WV, 0 candidates): these regions have confirmed Z coverage from ≥160 external candidates within 150 miles; no fallback candidates are added.
- Report final |H| and per-region candidate count after floor application.

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

Key outputs: filtered H dataframe with d_h^road, Z index pairs, β value.

---

#### Task 5.2 — Objective Coefficients and Capacity Parameters `[planning]`

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
- Report the distribution of RHS_r and confirm that max(RHS_r) ≤ max(s_h) (feasibility sanity check for constraint 4 under m_r = 1).

Key outputs: coefficient dict `c_hat[h,r]`, RHS array `cap_rhs[r]`, scalar Q̄, T̄.

---

#### Task 5.3 — MIP Build and Gurobi Solution `[planning]`

Build and solve the MIP using `gurobipy`.

##### Model construction

- Binary variables: A[h,r] for (h,r) ∈ Z; O[h] for h ∈ H.
- Objective: minimize ∑_{(h,r)∈Z} c_hat[h,r] · A[h,r].
- Constraints 1–4 as specified in the formulation; constraint 5 enforced by H pre-filter (no β variables in model).
- Solver parameters: TimeLimit=600s, MIPGap=0.01, OutputFlag=1.

##### Solution extraction

- Extract selected hubs: {h : O[h].X > 0.5}.
- Extract assignments: {(h,r) : A[h,r].X > 0.5}.
- Record objective value, MIP gap, solve time.

Key outputs: `task5_selected_hubs.csv` (hub metadata + region assignments), `task5_hub_region_assignments.csv` (full (h,r) pair list).

---

#### Task 5.4 — Solution Analysis and Regional Hub Characterization `[planning]`

Characterize the selected hub set and assess solution quality.

Per-hub report: for each selected hub h — candidate_id, facility_name, city, state, region(s) served, s_h (sqft), d_h^road (miles), ĉ_hr for each assigned region.

Per-region report: for each region r — assigned hub(s), total assigned sqft vs. RHS_r (capacity slack), demand-weighted distance to assigned hub(s), flag if served by out-of-region hub.

##### Aggregate statistics

- Total open hubs, hubs serving 1 vs. 2 regions, regions served by out-of-region hubs.
- Distribution of assigned sqft by region relative to RHS_r.
- Cross-check: do regions 19, 43 (zero in-region candidates) have valid external hub assignments?

Key outputs: summary tables and diagnostic flags; no new data files beyond Task 5.3 outputs.

---

#### Task 5.5 — Network Link Definition `[planning]`

Define the principal links of the regional hub network using Delaunay triangulation and a 5.5-hour driving supplement.

##### Method

- Apply Delaunay triangulation on selected hub locations (EPSG:9311 coordinates) to generate the planar neighbor graph. This produces the minimal set of geometrically natural hub-to-hub links.
- Supplement with any hub pairs not connected by Delaunay but sharing a region assignment (i.e., two hubs both assigned to the same region r via p_h = 2).
- Prune links with Euclidean distance > 350 miles (≈ 5.5h at highway speeds); these represent unrealistically long direct connections for a regional tier.
- Annotate each link with: straight-line distance (miles), estimated driving time (distance / 60 mph), and whether the two hubs share a region assignment.

Key outputs: `task5_hub_network_links.csv` (hub_a, hub_b, distance_miles, shared_region flag).

---

#### Task 5.6 — Figures and Exports `[planning]`

Produce the final map, network diagram, and tabular outputs for Task 5 reporting.

##### Figures

- `fig_regional_hub_locations.png`: regional hub markers on NE basemap, colored by region assignment, sized by s_h (sqft), with region polygon boundaries overlaid.
- `fig_regional_hub_network.png`: selected hubs with network links overlaid on NE interstate layer; link thickness proportional to inverse distance.

##### Tabular exports (all under `Data/Task5/`)

- `selected_hubs.csv`: full hub list with all characterization fields.
- `hub_region_assignments.csv`: (hub_id, region_id) pair table.
- `hub_network_links.csv`: network link list from Task 5.5.
- `region_hub_summary.csv`: per-region coverage summary (assigned hubs, sqft, distance metrics).

---

### Task 6 — Gateway Node Design `[not started]`

Cluster counties into freight areas within each region; screen CoStar for gateway candidates; select nodes avoiding redundancy.

---

### Task 7 — Multi-Tier Integration `[not started]`

Combine regional nodes, gateway nodes, regions, and areas into a single hierarchical network; produce maps and diagrams.

---

### Task 8 — Flow Assignment `[not started]`

Assign 2025 and 2030 flows through the network; identify critical nodes and highest-throughput corridors.

---

### Task 9 — Synthesis `[not started]`

Summarize principal challenges, insights, and limitations.
