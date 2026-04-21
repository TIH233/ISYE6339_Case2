"""Task 8.6 — Interface Node Flow Routing.

For each of the 29 Task 2 interface nodes, finds the nearest regional hub by
minimum Euclidean distance in EPSG:9311 and saves the routing table.

Also appends ``interface_throughput_ktons_2025/2030`` columns to
``hub_throughput.csv``, overwriting the file written by Task 8.3.
"""
import numpy as np
import pandas as pd
from pyproj import Transformer

from .config import Task8Config


class InterfaceNodeRouter:
    """Routes interface nodes to nearest hubs and augments hub_throughput.csv (Task 8.6).

    Parameters
    ----------
    cfg : Task8Config
    hub_tp : pd.DataFrame
        The 50-row hub throughput DataFrame returned by HubThroughputCalculator.
        This method appends interface columns and resaves it.
    """

    def __init__(self, cfg: Task8Config, hub_tp: pd.DataFrame) -> None:
        self.cfg    = cfg
        self._hub_tp = hub_tp.copy()

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Route interface nodes, save CSVs, return (iface_routing, hub_tp_updated)."""
        iface   = self._load_interface_nodes()
        hubs_df = self._load_hubs()
        iface   = self._assign_nearest_hub(iface, hubs_df)
        routing = self._build_routing_table(iface)
        hub_tp_updated = self._update_hub_throughput(routing)
        self._validate(routing, hub_tp_updated)
        self._save(routing, hub_tp_updated)
        return routing, hub_tp_updated

    # ── Private helpers ─────────────────────────────────────────────────────

    def _load_interface_nodes(self) -> pd.DataFrame:
        nodes_df = pd.read_csv(self.cfg.NODES_CSV)
        iface = (
            nodes_df[nodes_df["tier"] == 3][
                ["node_id", "facility_name", "interface_class",
                 "latitude", "longitude", "tons_2025_ktons", "tons_2030_ktons"]
            ]
            .copy()
            .reset_index(drop=True)
        )
        print(
            f"  [8.6] Interface nodes: {len(iface)} rows | "
            f"classes: {iface['interface_class'].value_counts().to_dict()}"
        )
        # Abort guard: continental tons must be < 1 M ktons
        cont = iface[iface["interface_class"] == "continental"]
        if cont["tons_2025_ktons"].max() > 1_000_000:
            raise RuntimeError(
                "ABORT: continental node tons > 1M ktons — raw Task 2 file likely loaded. "
                "Reload from Data/Task7/nodes.csv."
            )
        print(
            f"  [8.6] ✓ Continental range: "
            f"[{cont['tons_2025_ktons'].min():.1f}, {cont['tons_2025_ktons'].max():.1f}] ktons"
        )
        return iface

    def _load_hubs(self) -> pd.DataFrame:
        df = pd.read_csv(
            self.cfg.SELECTED_HUBS,
            usecols=["candidate_id", "facility_name", "latitude", "longitude"],
        )
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:9311", always_xy=True)
        x, y = transformer.transform(df["longitude"].to_numpy(), df["latitude"].to_numpy())
        df = df.assign(x_9311=x, y_9311=y)
        return df

    def _assign_nearest_hub(
        self, iface: pd.DataFrame, hubs_df: pd.DataFrame
    ) -> pd.DataFrame:
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:9311", always_xy=True)
        iface_x, iface_y = transformer.transform(
            iface["longitude"].to_numpy(), iface["latitude"].to_numpy()
        )
        iface = iface.assign(x_9311=iface_x, y_9311=iface_y)

        hub_xy   = np.column_stack([hubs_df["x_9311"], hubs_df["y_9311"]])
        iface_xy = np.column_stack([iface["x_9311"], iface["y_9311"]])

        # (29, 1, 2) - (1, 50, 2) → (29, 50) distances
        diff     = iface_xy[:, np.newaxis, :] - hub_xy[np.newaxis, :, :]
        dist_m   = np.sqrt((diff ** 2).sum(axis=2))
        nearest_idx = dist_m.argmin(axis=1)

        iface = iface.assign(
            nearest_hub_candidate_id=hubs_df["candidate_id"].iloc[nearest_idx].values,
            nearest_hub_name=hubs_df["facility_name"].iloc[nearest_idx].values,
            distance_miles=dist_m[np.arange(len(iface)), nearest_idx] / 1609.34,
        )
        return iface

    def _build_routing_table(self, iface: pd.DataFrame) -> pd.DataFrame:
        routing = (
            iface[[
                "node_id", "facility_name", "interface_class",
                "nearest_hub_candidate_id", "nearest_hub_name",
                "distance_miles", "tons_2025_ktons", "tons_2030_ktons",
            ]]
            .rename(columns={"node_id": "node_name"})
            .reset_index(drop=True)
        )
        return routing

    def _update_hub_throughput(self, routing: pd.DataFrame) -> pd.DataFrame:
        iface_by_hub = (
            routing.groupby("nearest_hub_candidate_id")
            .agg(
                interface_throughput_ktons_2025=("tons_2025_ktons", "sum"),
                interface_throughput_ktons_2030=("tons_2030_ktons", "sum"),
            )
            .reset_index()
            .rename(columns={"nearest_hub_candidate_id": "candidate_id"})
        )
        updated = self._hub_tp.merge(iface_by_hub, on="candidate_id", how="left")
        updated["interface_throughput_ktons_2025"] = (
            updated["interface_throughput_ktons_2025"].fillna(0.0)
        )
        updated["interface_throughput_ktons_2030"] = (
            updated["interface_throughput_ktons_2030"].fillna(0.0)
        )
        return updated

    def _validate(
        self, routing: pd.DataFrame, hub_tp_updated: pd.DataFrame
    ) -> None:
        assert len(routing) == self.cfg.EXPECTED_INTERFACE, (
            f"Expected {self.cfg.EXPECTED_INTERFACE} interface nodes, got {len(routing)}"
        )
        cont_mask = routing["interface_class"] == "continental"
        cont_max = routing.loc[cont_mask, "tons_2025_ktons"].max()
        cont_min = routing.loc[cont_mask, "tons_2025_ktons"].min()
        assert cont_max <= 30_163, f"Continental max {cont_max:.1f} > 30,162 ktons"
        assert cont_min >= 2_738,  f"Continental min {cont_min:.1f} < 2,739 ktons"

        n_nonnull = (hub_tp_updated["interface_throughput_ktons_2025"] >= 0).sum()
        assert n_nonnull == self.cfg.EXPECTED_HUBS, (
            f"Expected {self.cfg.EXPECTED_HUBS} non-null interface entries, got {n_nonnull}"
        )
        total_iface = routing["tons_2025_ktons"].sum()
        hub_sum     = hub_tp_updated["interface_throughput_ktons_2025"].sum()
        assert abs(hub_sum - total_iface) < 1.0, (
            f"Hub interface sum {hub_sum:.1f} ≠ total interface volume {total_iface:.1f}"
        )
        print(
            f"  [8.6] ✓ All {self.cfg.EXPECTED_INTERFACE} interface nodes assigned | "
            f"hub interface sum = {hub_sum:,.1f} ktons ✓"
        )

    def _save(
        self, routing: pd.DataFrame, hub_tp_updated: pd.DataFrame
    ) -> None:
        out_r = self.cfg.INTERFACE_HUB_ROUTING
        routing.to_csv(out_r, index=False)
        print(f"  [8.6] Saved → {out_r}  ({out_r.stat().st_size / 1024:.1f} KB)")

        out_h = self.cfg.HUB_THROUGHPUT
        hub_tp_updated.to_csv(out_h, index=False)
        print(
            f"  [8.6] Updated → {out_h}  "
            f"(added interface_throughput_ktons_2025/2030 columns)"
        )
