--- 
- Background: Already has a finished paper of desiging of Hyperconnected Multi-Tier Megaregional Freight Systems in Southwestern US mageregion
- *Target* : Design another network following same methodology, using same data sources in Northestern US, including West Virginia, Virginia, Maryland, Delaware, Washington D.C., Pennsylvania, New York, New Jersey, Connecticut, Massachusetts, New Hampshire, Vermont, Maine, Rhode Island (434 county-equivalent units in the clustering study area)
- Language: Python
---


# Project Landscape

The virtual environment is in `~/.venvs/general/bin/python`

## Folder structure: 

```
ISYE6339_Case2/
├── Paper.pdf                          # Reference paper (SE US megaregion case study)
├── Handout.pdf                        # CW 2.1 & 2.2 project manual
├── Data/
│   ├── Task1/                         # Output data from Task 1 (freight flow matrix)
│   │   ├── raw.parquet                # Full NE county-to-county flows (all modes, 2025 & 2030)
│   │   ├── breakdown_by_flow_type.csv # Inbound / outbound / internal tonnage totals
│   │   ├── breakdown_by_mode.csv      # Tonnage broken down by transport mode
│   │   ├── breakdown_by_trade_type.csv# Tonnage broken down by trade type
│   │   ├── ne_state_summary.csv       # Per-state flow summary for Northeast states
│   │   ├── top50_origin_counties.csv  # Top 50 origin counties by outbound tonnage
│   │   └── top50_dest_counties.csv    # Top 50 destination counties by inbound tonnage
│   ├── Task2/                         # Output data from Task 2 (interface nodes)
│   │   ├── task2_global_interface_nodes_final.csv      # Seaports + cargo airports (global tier)
│   │   ├── task2_continental_interface_nodes_final.csv # US–Canada border crossings (continental tier)
│   │   └── task2_national_interface_nodes_final.csv    # External domestic hubs (national tier)
│   └── Task3/                         # Task 3 spatial data, caches, figures, and outputs
│       ├── raw/
│       │   ├── census_counties/       # Census county shapefile bundle
│       │   ├── roads/                 # NTAD roads shapefile bundle
│       │   └── rails/                 # TIGER rail shapefile bundle
│       ├── derived/
│       │   ├── county_throughput.parquet
│       │   └── ne_counties_prepared.gpkg
│       ├── cache/                     # Regenerable Task 3 intermediates and SA logs/checkpoints
│       ├── figures/                   # Heatmaps, convergence plots, region maps
│       └── outputs/                   # Final CSV exports for Task 3.2
├── Doc/
│   ├── Data.md                        # Data source descriptions and schemas
│   ├── Paper.md                       # Methodology pipeline (§2.1–§2.6)
│   └── Task.md                        # Task descriptions, status, and key outputs
├── Task2/
│   ├── casework 2_task 2.ipynb        # Python notebook implementing Task 2 end-to-end
│   └── task2_report.docx              # Written report for Task 2
└── Task3/
    ├── map_create.ipynb               # Task 3.1 demand map construction notebook
    ├── task3_2_clustering.ipynb       # Task 3.2 clustering notebook
    ├── clustering.py                  # SA clustering implementation
    └── Cluster.md                     # Task 3 clustering design notes
```

# Methodology Pipeline of paper.pdf

Full pipeline details (§2.1–§2.6) are in `Doc/Paper.md`.
Refer to it when designing any implementation stage to understand the original SE case study approach, key parameters, and expected outputs.

---

# Project Data 

Full data source descriptions are in `Doc/Data.md`, and many are already processed and ready to use.
Refer to it when trying to ensure the data schema before loading any dataset in Data folder.

## Data.md overview:


# Casework Tasks

Full task descriptions, implementation details, status markers, and key outputs for all 9 tasks are in `Doc/Task.md`.
Refer to it when starting, resuming, or reviewing any task to understand what has been done and what remains.

## Task.md overview:

Status legend: `[complete]` = implemented and reviewed,  `[not started]` = not yet begun, `[in process]` = is the current task to do

some complicated task may include subtask indexed by subindex (e.g. Task3.1), each subtask will have status `[editing]` , as for working on the code according to plans, `[planning]` as for finished planning in Doc/Task.md, `[complete]` as for completed

Refer to this file when starting, resuming, or reviewing any task. Each entry describes the task objective, what was done (if applicable), intermediate data created, and key outputs.

---

# Key Parameters & Assumptions

- Commodity filter: exclude SCTG coal and gravel (non-palletizable); focus on truck-compatible freight
- Mode focus: truck (primary); other modes used for demand estimation contexts
- Region target: ~50 regions; area target: ~3–5 areas per region
- Regional hub travel constraint: ≤ 5.5h between neighboring hubs
- Area travel constraint: ≤ ~1.2h average cross-area (fits within 11h driving regulation)
- Gateway hub size threshold: ≥ 20,000 ft² available space
