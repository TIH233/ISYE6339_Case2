"""Task 8.8 — Figure generation.

Produces 5 publication-quality figures saved to Data/Task8/figures/:
  1. Hub Throughput Map
  2. Hub-to-Hub Link Flow Map
  3. Gateway Throughput Map
  4. Top-15 Corridors Bar Chart
  5. Top-20 Regional Hub Throughput Bar Chart
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import numpy as np
import pandas as pd
import geopandas as gpd

from .config import Task8Config


class FigureGenerator:
    """Generates all 5 Task 8 figures (Task 8.8).

    Parameters
    ----------
    cfg : Task8Config
    hub_tp : pd.DataFrame
        Augmented hub throughput (from FlowAnalyzer — carries growth/interface cols).
    gateway_tp : pd.DataFrame
        312-row gateway throughput.
    hub_links : pd.DataFrame
        133-row link flow table (carries growth/flow_per_mile cols).
    """

    def __init__(
        self,
        cfg: Task8Config,
        hub_tp: pd.DataFrame,
        gateway_tp: pd.DataFrame,
        hub_links: pd.DataFrame,
    ) -> None:
        self.cfg        = cfg
        self._hub_tp    = hub_tp
        self._gw_tp     = gateway_tp
        self._hub_links = hub_links

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self) -> None:
        """Generate and save all 5 figures."""
        ne_gdf, hub_geo, gw_geo = self._load_geo()
        ne_bounds = ne_gdf.total_bounds

        self._fig1_hub_throughput_map(ne_gdf, ne_bounds, hub_geo)
        self._fig2_link_flow_map(ne_gdf, ne_bounds, hub_geo)
        self._fig3_gateway_throughput_map(ne_gdf, ne_bounds, hub_geo, gw_geo)
        self._fig4_corridors_bar()
        self._fig5_hub_bar()

        figs = sorted(self.cfg.FIG_DIR.glob("fig_*.png"))
        print(f"\n  [8.8] {len(figs)} figures saved to {self.cfg.FIG_DIR}")
        for f in figs:
            print(f"    ✓ {f.name}  ({f.stat().st_size // 1024} KB)")

    # ── Private helpers ─────────────────────────────────────────────────────

    def _load_geo(
        self,
    ) -> tuple[gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame]:
        ne_gdf = gpd.read_file(self.cfg.NE_COUNTIES_GPKG).to_crs("EPSG:4326")

        sh  = pd.read_csv(self.cfg.SELECTED_HUBS,
                          usecols=["candidate_id", "facility_name",
                                   "latitude", "longitude"])
        gws = pd.read_csv(self.cfg.GATEWAY_SEL,
                          usecols=["candidate_id", "facility_name",
                                   "latitude", "longitude"])

        hub_geo = sh.merge(
            self._hub_tp[[
                "candidate_id", "throughput_ktons_2025", "throughput_ktons_2030",
                "interface_throughput_ktons_2025", "interface_share",
                "growth_abs_ktons", "region_id",
            ]],
            on="candidate_id",
        )
        gw_geo = gws.merge(
            self._gw_tp[[
                "candidate_id", "throughput_ktons_2025",
                "throughput_ktons_2030", "region_id",
            ]],
            on="candidate_id",
        )
        print(
            f"  [8.8] hub_geo: {len(hub_geo)} | gw_geo: {len(gw_geo)} | "
            f"NE counties: {len(ne_gdf)}"
        )
        return ne_gdf, hub_geo, gw_geo

    # ── Figure 1 ────────────────────────────────────────────────────────────

    def _fig1_hub_throughput_map(
        self,
        ne_gdf: gpd.GeoDataFrame,
        ne_bounds: np.ndarray,
        hub_geo: pd.DataFrame,
    ) -> None:
        fig, ax = plt.subplots(figsize=(14, 10))
        ne_gdf.plot(ax=ax, color="#f0f0f0", edgecolor="#cccccc", linewidth=0.4)

        sizes  = (hub_geo["throughput_ktons_2025"] / hub_geo["throughput_ktons_2025"].max()) * 600 + 30
        colors = hub_geo["interface_share"].values
        sc = ax.scatter(
            hub_geo["longitude"], hub_geo["latitude"],
            s=sizes, c=colors, cmap=plt.cm.YlOrRd,
            vmin=0, vmax=max(colors.max(), 1e-6),
            edgecolors="k", linewidths=0.5, zorder=5, alpha=0.85,
        )
        top10_ids = (
            self._hub_tp.nlargest(10, "throughput_ktons_2025")["candidate_id"].tolist()
        )
        for _, row in hub_geo[hub_geo["candidate_id"].isin(top10_ids)].iterrows():
            ax.annotate(
                row["facility_name"].split(",")[0][:22],
                xy=(row["longitude"], row["latitude"]),
                xytext=(5, 5), textcoords="offset points",
                fontsize=6.5, color="#222222",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.7, ec="none"),
                zorder=6,
            )

        cbar = plt.colorbar(sc, ax=ax, fraction=0.025, pad=0.02)
        cbar.set_label("Interface-flow share", fontsize=9)
        for val, lbl in [(100_000, "100k"), (250_000, "250k"), (400_000, "400k")]:
            s = (val / hub_geo["throughput_ktons_2025"].max()) * 600 + 30
            ax.scatter([], [], s=s, c="grey", alpha=0.6, edgecolors="k",
                       linewidths=0.5, label=f"{lbl} ktons")
        ax.legend(title="Throughput (2025)", loc="lower right", fontsize=8, title_fontsize=9)
        ax.set_xlim(ne_bounds[0] - 0.5, ne_bounds[2] + 0.5)
        ax.set_ylim(ne_bounds[1] - 0.5, ne_bounds[3] + 0.5)
        ax.set_title(
            "Task 8 — Regional Hub Throughput (2025)\n"
            "Size ∝ throughput, Color = interface-flow share",
            fontsize=12, pad=8,
        )
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        ax.tick_params(labelsize=8)
        out = self.cfg.FIG_DIR / "fig_hub_throughput_map.png"
        plt.tight_layout(); plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()

    # ── Figure 2 ────────────────────────────────────────────────────────────

    def _fig2_link_flow_map(
        self,
        ne_gdf: gpd.GeoDataFrame,
        ne_bounds: np.ndarray,
        hub_geo: pd.DataFrame,
    ) -> None:
        coord_map = hub_geo.set_index("candidate_id")[["longitude", "latitude"]].to_dict("index")
        max_flow  = self._hub_links["flow_ktons_2025"].max()
        top15 = set(
            zip(
                self._hub_links.nlargest(15, "flow_ktons_2025")["hub_a_candidate_id"],
                self._hub_links.nlargest(15, "flow_ktons_2025")["hub_b_candidate_id"],
            )
        )

        fig, ax = plt.subplots(figsize=(14, 10))
        ne_gdf.plot(ax=ax, color="#f0f0f0", edgecolor="#cccccc", linewidth=0.4)

        for _, row in self._hub_links.iterrows():
            ca = coord_map.get(row["hub_a_candidate_id"])
            cb = coord_map.get(row["hub_b_candidate_id"])
            if ca is None or cb is None:
                continue
            lw    = (row["flow_ktons_2025"] / max_flow) * 5 + 0.3
            pair  = (row["hub_a_candidate_id"], row["hub_b_candidate_id"])
            is_top = pair in top15 or (pair[1], pair[0]) in top15
            color  = "#d73027" if is_top else "#4575b4"
            alpha  = 0.85 if is_top else 0.45
            ax.plot(
                [ca["longitude"], cb["longitude"]],
                [ca["latitude"],  cb["latitude"]],
                color=color, linewidth=lw, alpha=alpha, zorder=3 if is_top else 2,
            )

        ax.scatter(hub_geo["longitude"], hub_geo["latitude"],
                   s=40, c="#333333", edgecolors="white", linewidths=0.5, zorder=5)
        ax.add_line(mlines.Line2D([], [], color="#d73027", linewidth=3, label="Top-15 corridor"))
        ax.add_line(mlines.Line2D([], [], color="#4575b4", linewidth=1.5, label="Other link"))
        ax.scatter([], [], s=40, c="#333333", label="Regional hub",
                   edgecolors="white", linewidths=0.5)
        ax.legend(loc="lower right", fontsize=9)
        ax.set_xlim(ne_bounds[0] - 0.5, ne_bounds[2] + 0.5)
        ax.set_ylim(ne_bounds[1] - 0.5, ne_bounds[3] + 0.5)
        ax.set_title(
            "Task 8 — Hub-to-Hub Link Flow Loading (2025)\n"
            "Linewidth ∝ flow; red = top-15 corridors  [88.7% nearest-neighbor approx.]",
            fontsize=12, pad=8,
        )
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        ax.tick_params(labelsize=8)
        out = self.cfg.FIG_DIR / "fig_hub_link_flow_map.png"
        plt.tight_layout(); plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()

    # ── Figure 3 ────────────────────────────────────────────────────────────

    def _fig3_gateway_throughput_map(
        self,
        ne_gdf: gpd.GeoDataFrame,
        ne_bounds: np.ndarray,
        hub_geo: pd.DataFrame,
        gw_geo: pd.DataFrame,
    ) -> None:
        fig, ax = plt.subplots(figsize=(14, 10))
        ne_gdf.plot(ax=ax, color="#f0f0f0", edgecolor="#cccccc", linewidth=0.4)

        max_gw   = gw_geo["throughput_ktons_2025"].max()
        gw_sizes = (gw_geo["throughput_ktons_2025"] / max_gw) * 120 + 5
        ax.scatter(gw_geo["longitude"], gw_geo["latitude"],
                   s=gw_sizes, c="#2166ac", alpha=0.55,
                   edgecolors="none", zorder=4, label="Gateway hub")
        ax.scatter(hub_geo["longitude"], hub_geo["latitude"],
                   s=120, c="#d73027", marker="*",
                   edgecolors="white", linewidths=0.5, zorder=6, label="Regional hub")

        for val, lbl in [(5_000, "5k"), (15_000, "15k"), (30_000, "30k")]:
            s = (val / max_gw) * 120 + 5
            ax.scatter([], [], s=s, c="#2166ac", alpha=0.6,
                       edgecolors="none", label=f"GW {lbl} ktons")
        ax.legend(loc="lower right", fontsize=8, title="Legend", title_fontsize=9)
        ax.set_xlim(ne_bounds[0] - 0.5, ne_bounds[2] + 0.5)
        ax.set_ylim(ne_bounds[1] - 0.5, ne_bounds[3] + 0.5)
        ax.set_title(
            "Task 8 — Gateway Hub Throughput (2025, NE-internal flows only)\n"
            "Size ∝ throughput; stars = regional hubs",
            fontsize=12, pad=8,
        )
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        ax.tick_params(labelsize=8)
        out = self.cfg.FIG_DIR / "fig_gateway_throughput_map.png"
        plt.tight_layout(); plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()

    # ── Figure 4 ────────────────────────────────────────────────────────────

    def _fig4_corridors_bar(self) -> None:
        top15 = self._hub_links.nlargest(15, "flow_ktons_2025").copy()
        top15["label"] = (
            top15["hub_a_name"].str[:20] + " ↔\n" + top15["hub_b_name"].str[:20]
        )
        top15 = top15.sort_values("flow_ktons_2025", ascending=True)
        x     = np.arange(len(top15))
        bh    = 0.35

        fig, ax = plt.subplots(figsize=(12, 8))
        ax.barh(x - bh/2, top15["flow_ktons_2025"] / 1e3, bh,
                label="2025", color="#4575b4", alpha=0.85)
        ax.barh(x + bh/2, top15["flow_ktons_2030"] / 1e3, bh,
                label="2030", color="#d73027", alpha=0.85)
        ax.set_yticks(x)
        ax.set_yticklabels(top15["label"].tolist(), fontsize=7.5)
        ax.set_xlabel("Flow (thousand ktons)", fontsize=10)
        ax.set_title(
            "Task 8 — Top 15 Hub-to-Hub Corridors (2025 vs 2030)\n"
            "[88.7% of hub-pairs use nearest-neighbor routing — load indicators only]",
            fontsize=11, pad=8,
        )
        ax.legend(fontsize=10)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}k"))
        ax.grid(axis="x", linestyle="--", alpha=0.4)
        out = self.cfg.FIG_DIR / "fig_top_corridors_bar.png"
        plt.tight_layout(); plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()

    # ── Figure 5 ────────────────────────────────────────────────────────────

    def _fig5_hub_bar(self) -> None:
        top20 = self._hub_tp.nlargest(20, "throughput_ktons_2025").copy()
        top20["short_name"] = (
            top20["facility_name"].str[:28] + "\n(" + top20["source_state"] + ")"
        )
        top20 = top20.sort_values("throughput_ktons_2025", ascending=True)
        x     = np.arange(len(top20))
        bh    = 0.35

        fig, ax = plt.subplots(figsize=(12, 10))
        ax.barh(x - bh/2, top20["throughput_ktons_2025"] / 1e3, bh,
                label="2025 (NE-internal)", color="#4575b4", alpha=0.85)
        ax.barh(x + bh/2, top20["throughput_ktons_2030"] / 1e3, bh,
                label="2030 (NE-internal)", color="#d73027", alpha=0.85)
        ax.set_yticks(x)
        ax.set_yticklabels(top20["short_name"].tolist(), fontsize=7.5)
        ax.set_xlabel("Throughput (thousand ktons)", fontsize=10)
        ax.set_title(
            "Task 8 — Top 20 Regional Hubs by Throughput (2025 vs 2030)\n"
            "NE-internal flows only; interface-node flows reported separately",
            fontsize=11, pad=8,
        )
        ax.legend(fontsize=10)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}k"))
        ax.grid(axis="x", linestyle="--", alpha=0.4)
        out = self.cfg.FIG_DIR / "fig_hub_throughput_bar.png"
        plt.tight_layout(); plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()
