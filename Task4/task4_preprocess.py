"""Task 4 CoStar candidate facility preprocessing.

This module loads state-level CoStar exports, adds Task 4 availability tags,
assigns candidates to Task 3 counties/regions when the county layer exists,
and writes the reduced capacity/location dataset used for regional hub screening.
"""

from __future__ import annotations

from pathlib import Path
import os
import re

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ALL_DIR = PROJECT_ROOT / "Data" / "Task4" / "ALL"
DERIVED_DIR = PROJECT_ROOT / "Data" / "Task4" / "processed"
AVAILABLE_DIR = PROJECT_ROOT / "Data" / "Task4" / "Available"
FIGURE_DIR = PROJECT_ROOT / "Data" / "Task4" / "figures"
COUNTY_LAYER_PATH = PROJECT_ROOT / "Data" / "Task3" / "derived" / "ne_counties_prepared.gpkg"
REGION_ASSIGNMENT_PATH = PROJECT_ROOT / "Data" / "Task3" / "outputs" / "region_assignment.csv"

MIN_REGIONAL_AVAILABLE_SF = 20_000


RENAME_MAP = {
    "Property Address": "property_address",
    "Property Name": "property_name",
    "Building Class": "building_class",
    "Building Status": "building_status",
    "RBA": "rba_sf",
    "Total Available Space (SF)": "total_available_space_sf",
    "Rent/SF/Yr": "rent_sf_yr",
    "Secondary Type": "secondary_type",
    "City": "city",
    "Percent Leased": "percent_leased",
    "Year Built": "year_built",
    "Year Renovated": "year_renovated",
    "Typical Floor Size": "typical_floor_size_sf",
    "Parking Ratio": "parking_ratio",
    "Ceiling Ht": "ceiling_height_raw",
    "Column Spacing": "column_spacing",
    "Number Of Loading Docks": "number_loading_docks",
    "Power": "power",
    "Rail Lines": "rail_lines",
    "Sewer": "sewer",
    "Building Operating Expenses": "building_operating_expenses",
    "Capacity - Available kW": "capacity_available_kw",
    "Direct Available Space": "direct_available_space_sf",
    "Direct Vacant Space": "direct_vacant_space_sf",
    "Drive Ins": "drive_ins",
    "Sprinklers": "sprinklers",
    "Water": "water",
    "Number Of Parking Spaces": "parking_spaces",
    "Latitude": "latitude",
    "Longitude": "longitude",
}


CAPACITY_LOCATION_COLUMNS = [
    "candidate_id",
    "source_state",
    "source_file",
    "source_row",
    "facility_name",
    "property_name",
    "property_address",
    "city",
    "county_fips",
    "county_name",
    "region_id",
    "latitude",
    "longitude",
    "secondary_type",
    "building_class",
    "building_status",
    "availability_class",
    "is_directly_usable_by_status",
    "has_listed_available_space",
    "is_primary_regional_hub_candidate",
    "rba_sf",
    "usable_available_space_sf",
    "total_available_space_sf",
    "direct_available_space_sf",
    "direct_vacant_space_sf",
    "meets_min_available_space_20k",
    "percent_leased",
    "typical_floor_size_sf",
    "ceiling_height_raw",
    "column_spacing",
    "number_loading_docks",
    "drive_ins",
    "rail_lines",
    "capacity_available_kw",
    "power",
    "sprinklers",
    "water",
    "sewer",
    "parking_ratio",
    "parking_spaces",
    "year_built",
    "year_renovated",
]


def _ensure_dirs() -> None:
    for path in (DERIVED_DIR, AVAILABLE_DIR, FIGURE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _clean_string(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def _clean_numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = (
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.extract(r"([-+]?\d*\.?\d+)", expand=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def load_all_costar_exports(raw_dir: Path = RAW_ALL_DIR) -> pd.DataFrame:
    """Load all state-level CoStar CSVs from the ALL folder."""
    files = sorted(raw_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {raw_dir}")

    frames: list[pd.DataFrame] = []
    for path in files:
        df = pd.read_csv(path)
        df["source_state"] = path.stem.upper()
        df["source_file"] = path.name
        df["source_row"] = np.arange(1, len(df) + 1)
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns=RENAME_MAP)
    out["candidate_id"] = [
        f"T4-{state}-{row:05d}"
        for state, row in zip(out["source_state"], out["source_row"], strict=False)
    ]
    return out


def add_availability_tags(df: pd.DataFrame) -> pd.DataFrame:
    """Add Task 4 availability tags without modifying raw export columns."""
    out = df.copy()

    text_cols = [
        "property_name",
        "property_address",
        "building_class",
        "building_status",
        "secondary_type",
        "city",
        "ceiling_height_raw",
        "column_spacing",
        "power",
        "rail_lines",
        "sewer",
        "drive_ins",
        "sprinklers",
        "water",
    ]
    for col in text_cols:
        if col in out.columns:
            out[col] = _clean_string(out[col])

    numeric_cols = [
        "rba_sf",
        "total_available_space_sf",
        "percent_leased",
        "year_built",
        "year_renovated",
        "typical_floor_size_sf",
        "parking_ratio",
        "number_loading_docks",
        "capacity_available_kw",
        "direct_available_space_sf",
        "direct_vacant_space_sf",
        "parking_spaces",
        "latitude",
        "longitude",
    ]
    for col in numeric_cols:
        if col in out.columns:
            out[col] = _clean_numeric(out[col])

    status = out["building_status"].fillna("").str.casefold()
    out["building_status_normalized"] = status
    out["is_directly_usable_by_status"] = status.eq("existing")
    out["is_pipeline_or_proxy_by_status"] = status.isin(
        ["under construction", "final planning"]
    )

    out["availability_class"] = np.select(
        [
            status.eq("existing"),
            status.eq("under construction"),
            status.eq("final planning"),
        ],
        [
            "direct_existing_facility",
            "pipeline_under_construction",
            "proxy_final_planning",
        ],
        default="needs_status_review",
    )

    available_space_cols = [
        "total_available_space_sf",
        "direct_available_space_sf",
        "direct_vacant_space_sf",
    ]
    out["usable_available_space_sf"] = out[available_space_cols].max(axis=1, skipna=True)
    out["usable_available_space_sf"] = out["usable_available_space_sf"].fillna(0)
    out["has_listed_available_space"] = out["usable_available_space_sf"].gt(0)
    out["meets_min_available_space_20k"] = out["usable_available_space_sf"].ge(
        MIN_REGIONAL_AVAILABLE_SF
    )

    secondary = out["secondary_type"].fillna("").str.casefold()
    out["is_logistics_related_type"] = secondary.isin(
        ["warehouse", "distribution", "truck terminal", "manufacturing"]
    )
    out["has_valid_coordinates"] = (
        out["latitude"].between(35, 48) & out["longitude"].between(-84, -66)
    )

    out["facility_name"] = out["property_name"].fillna("")
    missing_name = out["facility_name"].eq("")
    out.loc[missing_name, "facility_name"] = (
        out.loc[missing_name, "property_address"].fillna("")
        + ", "
        + out.loc[missing_name, "city"].fillna("")
        + ", "
        + out.loc[missing_name, "source_state"].fillna("")
    )
    out["facility_name"] = out["facility_name"].str.strip(", ")

    out["is_primary_regional_hub_candidate"] = (
        out["is_directly_usable_by_status"]
        & out["is_logistics_related_type"]
        & out["meets_min_available_space_20k"]
        & out["has_valid_coordinates"]
    )
    return out


def assign_county_and_region(df: pd.DataFrame) -> pd.DataFrame:
    """Spatially assign candidates to prepared Task 3 counties and region ids."""
    if not COUNTY_LAYER_PATH.exists():
        return df

    import geopandas as gpd

    counties = gpd.read_file(COUNTY_LAYER_PATH)[["fips", "NAME", "STUSPS", "geometry"]]
    points = gpd.GeoDataFrame(
        df.copy(),
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    ).to_crs(counties.crs)

    try:
        joined = gpd.sjoin(points, counties, how="left", predicate="within")
    except TypeError:
        joined = gpd.sjoin(points, counties, how="left", op="within")

    joined = joined.drop(columns=["geometry", "index_right"], errors="ignore")
    joined = joined.rename(
        columns={
            "fips": "county_fips",
            "NAME": "county_name",
            "STUSPS": "county_state",
        }
    )

    if REGION_ASSIGNMENT_PATH.exists():
        regions = pd.read_csv(REGION_ASSIGNMENT_PATH, dtype={"fips": "string"})
        regions = regions.rename(
            columns={
                "fips": "county_fips",
                "county_name": "region_county_name",
                "state": "region_state",
                "throughput_ktons": "county_throughput_ktons",
            }
        )
        joined["county_fips"] = joined["county_fips"].astype("string")
        joined = joined.merge(
            regions[
                [
                    "county_fips",
                    "region_id",
                    "county_throughput_ktons",
                    "region_state",
                ]
            ],
            on="county_fips",
            how="left",
        )

    return pd.DataFrame(joined)


def build_summary_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build state, status, secondary-type, and region coverage summaries."""
    summaries: dict[str, pd.DataFrame] = {}

    summaries["state_candidate_stats"] = (
        df.groupby("source_state", dropna=False)
        .agg(
            all_candidates=("candidate_id", "count"),
            direct_existing_by_status=("is_directly_usable_by_status", "sum"),
            pipeline_or_proxy_by_status=("is_pipeline_or_proxy_by_status", "sum"),
            listed_available_space=("has_listed_available_space", "sum"),
            primary_regional_hub_candidates=("is_primary_regional_hub_candidate", "sum"),
            total_usable_available_sf=("usable_available_space_sf", "sum"),
            median_rba_sf=("rba_sf", "median"),
            median_loading_docks=("number_loading_docks", "median"),
        )
        .reset_index()
        .sort_values("primary_regional_hub_candidates", ascending=False)
    )

    summaries["status_summary"] = (
        df.groupby("availability_class", dropna=False)
        .agg(
            candidates=("candidate_id", "count"),
            primary_regional_hub_candidates=("is_primary_regional_hub_candidate", "sum"),
            total_usable_available_sf=("usable_available_space_sf", "sum"),
            median_usable_available_sf=("usable_available_space_sf", "median"),
        )
        .reset_index()
        .sort_values("candidates", ascending=False)
    )

    summaries["secondary_type_summary"] = (
        df.groupby("secondary_type", dropna=False)
        .agg(
            candidates=("candidate_id", "count"),
            primary_regional_hub_candidates=("is_primary_regional_hub_candidate", "sum"),
            median_rba_sf=("rba_sf", "median"),
            total_usable_available_sf=("usable_available_space_sf", "sum"),
        )
        .reset_index()
        .sort_values("candidates", ascending=False)
    )

    if "region_id" in df.columns:
        region_summary = (
            df.dropna(subset=["region_id"])
            .groupby("region_id", dropna=False)
            .agg(
                all_candidates=("candidate_id", "count"),
                direct_existing_by_status=("is_directly_usable_by_status", "sum"),
                primary_regional_hub_candidates=(
                    "is_primary_regional_hub_candidate",
                    "sum",
                ),
                total_usable_available_sf=("usable_available_space_sf", "sum"),
            )
            .reset_index()
        )

        if REGION_ASSIGNMENT_PATH.exists():
            all_regions = (
                pd.read_csv(REGION_ASSIGNMENT_PATH)[["region_id"]]
                .drop_duplicates()
                .sort_values("region_id")
            )
            region_summary = all_regions.merge(region_summary, on="region_id", how="left")

        count_cols = [
            "all_candidates",
            "direct_existing_by_status",
            "primary_regional_hub_candidates",
            "total_usable_available_sf",
        ]
        for col in count_cols:
            if col in region_summary.columns:
                region_summary[col] = region_summary[col].fillna(0)

        summaries["region_candidate_stats"] = region_summary.sort_values(
            "region_id", na_position="last"
        )

    return summaries


def write_plotly_map(df: pd.DataFrame) -> Path | None:
    """Write an interactive candidate map if plotly is installed."""
    try:
        import plotly.express as px
    except ImportError:
        return None

    plot_df = df[df["has_valid_coordinates"]].copy()
    if plot_df.empty:
        return None

    plot_df["plot_size"] = np.clip(
        np.sqrt(plot_df["usable_available_space_sf"].fillna(0) + 1),
        4,
        40,
    )
    fig = px.scatter_geo(
        plot_df,
        lat="latitude",
        lon="longitude",
        color="availability_class",
        size="plot_size",
        scope="usa",
        hover_name="facility_name",
        hover_data={
            "source_state": True,
            "city": True,
            "secondary_type": True,
            "building_status": True,
            "usable_available_space_sf": ":,.0f",
            "rba_sf": ":,.0f",
            "number_loading_docks": True,
            "region_id": True if "region_id" in plot_df.columns else False,
            "plot_size": False,
            "latitude": False,
            "longitude": False,
        },
        title="Task 4 Candidate Freight Facilities",
    )
    fig.update_geos(
        projection_type="albers usa",
        lataxis_range=[36, 48],
        lonaxis_range=[-84, -66],
        showcountries=False,
        showland=True,
        landcolor="rgb(245, 245, 240)",
        showsubunits=True,
        subunitcolor="rgb(190, 190, 190)",
    )
    fig.update_layout(
        legend_title_text="Availability tag",
        margin={"r": 20, "t": 55, "l": 20, "b": 20},
    )

    out_path = FIGURE_DIR / "all_candidate_facilities_map.html"
    fig.write_html(out_path, include_plotlyjs=True, full_html=True)
    return out_path


def write_static_png_map(df: pd.DataFrame) -> Path | None:
    """Write a static PNG map of all candidate facilities."""
    cache_dir = PROJECT_ROOT / "Data" / "Task4" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))

    try:
        import geopandas as gpd
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    plot_df = df[df["has_valid_coordinates"]].copy()
    if plot_df.empty:
        return None

    points = gpd.GeoDataFrame(
        plot_df,
        geometry=gpd.points_from_xy(plot_df["longitude"], plot_df["latitude"]),
        crs="EPSG:4326",
    )

    fig, ax = plt.subplots(figsize=(12, 9))

    if COUNTY_LAYER_PATH.exists():
        counties = gpd.read_file(COUNTY_LAYER_PATH).to_crs("EPSG:4326")
        counties.boundary.plot(ax=ax, linewidth=0.25, color="#b8b8b8")

    colors = {
        "direct_existing_facility": "#1f77b4",
        "pipeline_under_construction": "#ff7f0e",
        "proxy_final_planning": "#2ca02c",
        "needs_status_review": "#d62728",
    }

    for availability_class, group in points.groupby("availability_class", dropna=False):
        size = np.clip(
            np.sqrt(group["usable_available_space_sf"].fillna(0) + 1) / 8,
            8,
            65,
        )
        group.plot(
            ax=ax,
            markersize=size,
            color=colors.get(str(availability_class), "#7f7f7f"),
            alpha=0.78,
            edgecolor="white",
            linewidth=0.25,
            label=str(availability_class),
        )

    ax.set_title("Task 4 Candidate Freight Facilities", fontsize=15, pad=12)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_xlim(-84, -66)
    ax.set_ylim(36, 48)
    ax.legend(title="Availability tag", loc="lower left", frameon=True)
    ax.grid(color="#e2e2e2", linewidth=0.4)
    fig.tight_layout()

    out_path = FIGURE_DIR / "all_candidate_facilities_map.png"
    fig.savefig(out_path, dpi=220)
    plt.close(fig)
    return out_path


def write_outputs(df: pd.DataFrame) -> dict[str, Path]:
    _ensure_dirs()
    outputs: dict[str, Path] = {}

    tagged_path = DERIVED_DIR / "all_candidates_tagged.csv"
    df.to_csv(tagged_path, index=False)
    outputs["all_candidates_tagged"] = tagged_path

    reduced_cols = [col for col in CAPACITY_LOCATION_COLUMNS if col in df.columns]
    reduced = df[reduced_cols].copy()
    reduced_path = DERIVED_DIR / "preprocessed_capacity_location.csv"
    reduced.to_csv(reduced_path, index=False)
    outputs["preprocessed_capacity_location"] = reduced_path

    primary = reduced[df["is_primary_regional_hub_candidate"]].copy()
    primary_path = DERIVED_DIR / "primary_regional_hub_candidates.csv"
    primary.to_csv(primary_path, index=False)
    outputs["primary_regional_hub_candidates"] = primary_path

    for state, state_df in df[df["is_directly_usable_by_status"]].groupby("source_state"):
        state_path = AVAILABLE_DIR / f"{state}.csv"
        state_df.to_csv(state_path, index=False)

    summaries = build_summary_tables(df)
    for name, summary in summaries.items():
        path = DERIVED_DIR / f"{name}.csv"
        summary.to_csv(path, index=False)
        outputs[name] = path

    map_path = write_plotly_map(df)
    if map_path is not None:
        outputs["all_candidate_facilities_map"] = map_path

    png_map_path = write_static_png_map(df)
    if png_map_path is not None:
        outputs["all_candidate_facilities_map_png"] = png_map_path

    return outputs


def run_pipeline() -> tuple[pd.DataFrame, dict[str, Path]]:
    """Execute the full Task 4 preprocessing pipeline."""
    raw = load_all_costar_exports()
    tagged = add_availability_tags(raw)
    tagged = assign_county_and_region(tagged)
    outputs = write_outputs(tagged)
    return tagged, outputs


def print_run_summary(df: pd.DataFrame, outputs: dict[str, Path]) -> None:
    status_counts = df["availability_class"].value_counts(dropna=False)
    primary_count = int(df["is_primary_regional_hub_candidate"].sum())
    direct_count = int(df["is_directly_usable_by_status"].sum())
    region_count = int(df["region_id"].nunique()) if "region_id" in df.columns else 0
    unmatched_count = int(df["region_id"].isna().sum()) if "region_id" in df.columns else 0

    print("Task 4 preprocessing complete")
    print("-" * 80)
    print(f"{'Rows':45s}: {len(df):,}")
    print(f"{'Direct existing facilities by status':45s}: {direct_count:,}")
    print(f"{'Primary regional hub candidates':45s}: {primary_count:,}")
    print(f"{'Regions with at least one matched candidate':45s}: {region_count:,}")
    print(f"{'Rows not matched to a Task 3 region':45s}: {unmatched_count:,}")
    print()
    print("Availability classes")
    print("-" * 80)
    for label, count in status_counts.items():
        print(f"{str(label):45s}: {int(count):,}")
    print()
    print("Outputs:")
    print("-" * 80)
    for name, path in outputs.items():
        rel = path.relative_to(PROJECT_ROOT)
        print(f"{name:45s}: {rel}")


if __name__ == "__main__":
    candidates, output_paths = run_pipeline()
    print_run_summary(candidates, output_paths)
