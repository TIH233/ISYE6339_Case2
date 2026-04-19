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

### Task 4 — Regional Node Candidates `[not started]`

Screen CoStar data; distinguish directly usable facilities from proxy locations.

---

### Task 5 — Regional Node Network `[not started]`

Apply set-cover or equivalent optimization/heuristic to select nodes; define network links using travel time and freight interaction.

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
