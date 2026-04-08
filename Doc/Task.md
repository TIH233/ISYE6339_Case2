# Casework Tasks

Status legend: `[need verification]` = implemented but not reviewed | `[not started]` = not yet begun

Refer to this file when starting, resuming, or reviewing any task. Each entry describes the task objective, what was done (if applicable), intermediate data created, and key outputs.

---

### Task 1 — County-to-County Freight Flow Matrix `[need verification]`
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

### Task 2 — Global, Continental, and National Interface Nodes `[need verification]`
Identify major seaports, cargo airports, border crossings, and external demand-dense hubs; estimate throughput volumes; produce interface maps.

**Methodology implemented:**
- **External flow isolation:** Used Task 1's classified flow matrix; filtered to `inbound` + `outbound` flows only (i.e., flows crossing the NE megaregion boundary). Built a compact working dataframe `task2_flows_compact.parquet`
- **Assignment bucketing (Step 8A):** Classified each external flow record into one of four assignment buckets:
  - `global_maritime` — water-mode flows (`mode == 3`)
  - `continental_border` — flows with Canada-adjacent state origins/destinations (NY, VT, NH, ME)
  - `global_air` — multi-mode/mail and truck+air flows (`mode` 5 or 11)
  - `national_domestic` — all remaining domestic external flows
- **Global maritime nodes:** Filtered NTAD Commercial Seaport dataset to NE coastal states (PA, MD, DE, VA, NY, NJ, CT, MA, RI, ME, NH); identified Hampton Roads (VA) and Philadelphia (PA) as principal maritime gateways; allocated total `global_maritime` tonnage equally across shortlisted seaports
- **Global air nodes:** Filtered FAA cargo airports dataset to major NE airports (JFK, EWR, PHL, BWI, IAD, BOS, PIT); weighted airport shares by aggregated air-truck facility area (`air_truck` dataset, `EST_AREA` field); allocated total `global_air` tonnage proportionally — JFK, PHL, EWR emerged as dominant
- **Continental nodes:** Filtered BTS border crossing dataset to US–Canada crossings in NY, VT, NH, ME and freight-relevant measures (Trucks, Rail, Containers); summed crossing values as throughput proxy; allocated total `continental_border` tonnage by proxy share — Buffalo Niagara Falls dominated, followed by Champlain–Rouses Point and Alexandria Bay
- **National nodes:** Aggregated `national_domestic` external flows by origin/destination county; identified top external counties by tonnage; shortlisted as national interface hubs (Ohio, Texas, and major Midwest/mid-Atlantic logistics corridors prominent); allocated `national_domestic` tonnage by flow-derived hub shares
- **Visualization:** Produced three separate maps (global, continental, national) using `geopandas` + `matplotlib` on NE state basemap

**Key outputs:** `Data/Task2/task2_global_interface_nodes_final.csv`, `task2_continental_interface_nodes_final.csv`, `task2_national_interface_nodes_final.csv`

**Key findings:** Global tier anchored by Hampton Roads and Philadelphia (maritime) and JFK/PHL/EWR (air). Continental tier dominated by Buffalo Niagara Falls and Champlain–Rouses Point. National tier concentrated in Ohio, Texas, and Midwest logistics corridors.

---

### Task 3 — Region Clustering `[not started]`
Demand-balanced, geographically contiguous and compact clusters aligned to interstate corridors; justify parameters and assess quality.

---

### Task 4 — Regional Hub Candidates `[not started]`
Screen CoStar data; distinguish directly usable facilities from proxy locations.

---

### Task 5 — Regional Hub Network `[not started]`
Apply set-cover or equivalent optimization/heuristic to select hubs; define network links using travel time and freight interaction.

---

### Task 6 — Gateway Hub Design `[not started]`
Cluster counties into freight areas within each region; screen CoStar for gateway candidates; select hubs avoiding redundancy.

---

### Task 7 — Multi-Tier Integration `[not started]`
Combine regional hubs, gateway hubs, regions, and areas into a single hierarchical network; produce maps and diagrams.

---

### Task 8 — Flow Assignment `[not started]`
Assign 2025 and 2030 flows through the network; identify critical hubs and highest-throughput corridors.

---

### Task 9 — Synthesis `[not started]`
Summarize principal challenges, insights, and limitations.
