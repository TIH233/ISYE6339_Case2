"""Central configuration for Task 8: paths, constants, validation targets."""
from pathlib import Path


class Task8Config:
    """All file paths and scalar constants used by the Task 8 pipeline.

    Attributes are class-level so callers can reference them without
    instantiating (``Task8Config.ROOT``), but the class can also be
    instantiated for injection-style testing.
    """

    # ── Project root ────────────────────────────────────────────────────────
    ROOT: Path = Path(__file__).resolve().parents[2]  # …/ISYE6339_Case2
    DATA: Path = ROOT / "Data"
    OUT_DIR: Path = DATA / "Task8"
    FIG_DIR: Path = OUT_DIR / "figures"

    # ── Input paths ─────────────────────────────────────────────────────────
    AREA_ASSIGN: Path       = DATA / "Task6/area_assignment.csv"
    GW_AREA_ASSIGN: Path    = DATA / "Task6/gateway_area_assignments.csv"
    HUB_REGION_ASSIGN: Path = DATA / "Task5/hub_region_assignments.csv"
    SELECTED_HUBS: Path     = DATA / "Task5/selected_hubs.csv"
    RAW_PARQUET: Path       = DATA / "Task1/raw.parquet"
    REGION_FLOW_MAT: Path   = DATA / "Task5/cache/region_flow_matrix.parquet"
    HUB_NETWORK_LINKS: Path = DATA / "Task5/task5_hub_network_links_flow_weighted.csv"
    NODES_CSV: Path         = DATA / "Task7/nodes.csv"
    NE_COUNTIES_GPKG: Path  = DATA / "Task3/derived/ne_counties_prepared.gpkg"
    GATEWAY_SEL: Path       = DATA / "Task6/gateway_selected.csv"

    # ── Output paths ─────────────────────────────────────────────────────────
    COUNTY_ROUTING_LOOKUP: Path = OUT_DIR / "county_routing_lookup.parquet"
    AREA_FLOW_MATRIX: Path      = OUT_DIR / "area_flow_matrix.parquet"
    HUB_THROUGHPUT: Path        = OUT_DIR / "hub_throughput.csv"
    HUB_LINK_FLOWS: Path        = OUT_DIR / "hub_link_flows.csv"
    GATEWAY_THROUGHPUT: Path    = OUT_DIR / "gateway_throughput.csv"
    INTERFACE_HUB_ROUTING: Path = OUT_DIR / "interface_hub_routing.csv"

    # ── Commodity filter ─────────────────────────────────────────────────────
    EXCLUDE_COMMODITIES: frozenset = frozenset({"sctg1014", "sctg1519"})

    # ── Expected row counts (for assertions) ────────────────────────────────
    EXPECTED_HUBS: int      = 50
    EXPECTED_GATEWAYS: int  = 312
    EXPECTED_LINKS: int     = 133
    EXPECTED_INTERFACE: int = 29

    # ── Validation targets ───────────────────────────────────────────────────
    # region_flow_matrix total (ktons, symmetrized — every ton counted twice)
    RFM_EXPECTED_TOTAL: float = 2_454_583.0
    # Maximum allowed deviation for area-flow validation (percent)
    AREA_FLOW_TOLERANCE_PCT: float = 0.5
    # NJ/NY metro corridor region IDs for concentration analysis
    NJNY_REGIONS: frozenset = frozenset({3, 18, 34, 36})
    NJNY_REGIONS_EXTENDED: frozenset = frozenset({0, 3, 18, 34, 36})

    def __init__(self) -> None:
        self.OUT_DIR.mkdir(parents=True, exist_ok=True)
        self.FIG_DIR.mkdir(parents=True, exist_ok=True)
