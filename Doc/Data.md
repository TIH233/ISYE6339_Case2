# Project Data Sources

All primary data files used in Casework 2.1. Refer to this file when loading data, applying filters, or direct file schemas acquisition. See `Task.md` for how each source is consumed per task.

---

## `raw.parquet` — Full NE county-to-county O-D flow matrix (all modes, 2025 & 2030)

> **path** · `Data/Task1/raw.parquet` · **format** · parquet · **shape** · 33,404,629 rows × 7 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| origin_county_fips | int64 | 100% | 5-digit FIPS code of the origin county |
| dest_county_fips | int64 | 100% | 5-digit FIPS code of the destination county |
| mode | int64 | 100% | FAF transport mode code (2=Truck, 3=Water, 5=Multi-mode/Mail, 11=Truck+Air) |
| sctgG5 | object | 100% | SCTG commodity group code at ~2-digit level (e.g. `sctg2033`, `sctg0109`) |
| trade_type | int64 | 100% | FAF trade type (1=Domestic, 2=Import, 3=Export) |
| tons_2025 | float64 | 100% | Forecasted freight flow in thousand short tons for 2025 |
| tons_2030 | float64 | 100% | Forecasted freight flow in thousand short tons for 2030 |

**Context**: Produced in Task 1 by filtering the FAF experimental county-county parquet to NE megaregion flows (internal + inbound + outbound); `outside_outside` pairs were excluded. This is the primary freight demand dataset for all downstream tasks.

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

**Context**: Aggregates Task 1 flows to state level for the 14 NE megaregion states. Useful for comparing freight volumes across states and identifying high-demand states for hub placement in later tasks.

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

**Context**: Pareto list of highest freight-attracting destinations (dominated by NJ, NY, PA counties). Used alongside `top50_origin_counties.csv` to identify candidate hub locations in later tasks.

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

## `task2_national_interface_nodes_final.csv` — National-tier interface nodes (external domestic hubs)

> **path** · `Data/Task2/task2_national_interface_nodes_final.csv` · **format** · csv · **shape** · 12 rows × 6 cols

| Column | Type | Non-null | Meaning |
| ------ | ---- | -------- | ------- |
| node_name | object | 100% | County-level hub identifier (e.g. `LUCAS, OH`, `HARRIS, TX`, `COOK, IL`) |
| state_name | object | 100% | State abbreviation |
| node_type | object | 100% | Always `external_domestic_hub` |
| interface_class | object | 100% | Always `national` — marks this as the national interface tier |
| tons_2025 | float64 | 100% | Allocated freight volume (thousand short tons) in 2025 |
| tons_2030 | float64 | 100% | Allocated freight volume in 2030 |

**Context**: Task 2 output listing 12 major external US counties acting as domestic interchange points for `national_domestic` flows. Represents primary freight origins/destinations connecting the NE megaregion to the rest of the US.
