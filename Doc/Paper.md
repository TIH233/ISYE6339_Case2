# Methodology Pipeline of paper.pdf

Extracted from §2 of the reference paper: *Pragmatic Hyperconnected Freight Systems Design: A Data-Driven Case Study in the US Southeast Megaregion* (Garbers, Muthukrishnan, Montreuil, Georgia Tech).

Refer to this file when designing any pipeline stage to understand the original approach, parameters, and expected outputs from the SE case study.

---

### §2.1 Inter-County Freight Demand Estimation
- Source: FAF County-County Flows (FAF, 2025)
- Filter: truck mode only; exclude non-palletizable commodities (coal, gravel) — retain 3 of 5 commodity groups
- Compute per-county: annual total, inbound, internal, and outbound flows
- Peak daily demand: multiply largest flow (inbound or outbound) by:
  - Monthly factor from BTS Truck Tonnage Index (FRED, 2025) — highest TTI month
  - Daily factor from IEEE NTDAS truck volume (TMC segments, 2023) — robust max % of volume

### §2.2 Region Clustering
- Algorithm: K-means on county centroids, objective = balance freight demand
- Target: ~50 regions (chosen based on demand distribution balance, region size balance, and inter-region travel time)
- Post-processing: enforce contiguity, compactness, proximity to interstates/infrastructure
- Quality metric: average region-crossing distance (~148 miles / ~2.5h in the paper)

### §2.3 Regional Hub Selection
- Primary criterion: proximity to existing infrastructure (interstates, railroads, ports, freight corridors)
- Connectivity constraint: travel time between neighboring hubs ≤ 5.5 hours
- Output: regional hub clusters (33 in the paper's SE case); each cluster aggregated to a single location
- Hub clusters sized by freight flow throughput

### §2.4 Area Clustering (Lower-Tier Territorial Structure)
- Within each region: group counties into contiguous freight areas using a p-contiguous heuristic
- Demand thresholds: up to 10k / 15k / 20k tons per area (parameterized for demand balance)
- Post-processing: ensure highway intersections and railroad yards fall within area boundaries
- Output: ~186 areas from 755 SE counties (paper); average cross-area distance ~82 miles / ~1.18h

### §2.5 Gateway Hub Identification
- Source: CoStar database — property-level commercial real estate data
- Filter: space use = industrial; secondary type = warehouse, truck terminal, distribution center, or manufacturing; available space ≥ 20,000 ft²
- Fallback: open land plots or in-construction buildings where no qualifying sites exist
- Output: ~4,338 candidate locations in the paper's SE case; density increases near metro areas

### §2.6 Flow Assignment (Multi-Commodity Network Flow)
- Formulation: Minimum Cost Multi-Commodity Network Flow
- Objective: minimize total miles traveled across the hub network
- External regions: non-megaregion areas aggregated into 108 FAF regions
- Flow types: (1) intra-megaregion, (2) inbound from external FAF regions, (3) outbound to external FAF regions
