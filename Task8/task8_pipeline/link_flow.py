"""Task 8.4 — Hub-to-Hub Link Flow Loading.

Assigns inter-region freight flows to each of the 133 hub-to-hub links using
direct-link assignment where available, falling back to a nearest-neighbor
heuristic (88.7% of hub-pairs lack a direct link).
"""
from collections import defaultdict

import numpy as np
import pandas as pd

from .config import Task8Config


class LinkFlowLoader:
    """Loads flow onto the 133-link hub network (Task 8.4).

    Parameters
    ----------
    cfg : Task8Config
    rfm_total_2025 : float
        Symmetrized RFM total; used only for reference reporting.
    region_hubs : dict[int, list[tuple[str, float]]]
        Mapping region_id → [(candidate_id, hub_share), …].
        Must match the structure returned by HubThroughputCalculator.
    """

    def __init__(
        self,
        cfg: Task8Config,
        rfm_total_2025: float,
        region_hubs: dict[int, list[tuple[str, float]]],
    ) -> None:
        self.cfg = cfg
        self._rfm_total_25 = rfm_total_2025
        self._region_hubs  = region_hubs

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        """Assign flow to links, save CSV, and return the DataFrame."""
        rfm        = self._load_rfm()
        links, edge_idx, hub_neighbors, hub_lat, hub_lon = self._load_network()
        link_flow_25, link_flow_30 = self._assign_flows(
            rfm, edge_idx, hub_neighbors, hub_lat, hub_lon
        )
        hub_link_flows = self._build_output(links, link_flow_25, link_flow_30)
        self._validate(hub_link_flows, rfm)
        self._save(hub_link_flows)
        return hub_link_flows

    # ── Private helpers ─────────────────────────────────────────────────────

    def _load_rfm(self) -> pd.DataFrame:
        rfm = pd.read_parquet(self.cfg.REGION_FLOW_MAT)
        rfm["origin_region"] = rfm["origin_region"].astype(int)
        rfm["dest_region"]   = rfm["dest_region"].astype(int)
        return rfm

    def _load_network(
        self,
    ) -> tuple[
        pd.DataFrame,
        dict[frozenset, int],
        dict[str, list[str]],
        dict[str, float],
        dict[str, float],
    ]:
        links = pd.read_csv(self.cfg.HUB_NETWORK_LINKS)
        print(f"  [8.4] Hub network: {len(links)} links")

        edge_idx: dict[frozenset, int] = {}
        hub_neighbors: dict[str, list[str]] = defaultdict(list)
        for i, row in links.iterrows():
            key = frozenset((row["hub_a_candidate_id"], row["hub_b_candidate_id"]))
            edge_idx[key] = i
            hub_neighbors[row["hub_a_candidate_id"]].append(row["hub_b_candidate_id"])
            hub_neighbors[row["hub_b_candidate_id"]].append(row["hub_a_candidate_id"])

        pos = pd.read_csv(
            self.cfg.HUB_REGION_ASSIGN,
            usecols=["candidate_id", "latitude", "longitude"],
        )
        hub_lat: dict[str, float] = pos.set_index("candidate_id")["latitude"].to_dict()
        hub_lon: dict[str, float] = pos.set_index("candidate_id")["longitude"].to_dict()
        return links, edge_idx, hub_neighbors, hub_lat, hub_lon

    @staticmethod
    def _latlon_dist_sq(
        h1: str,
        h2: str,
        hub_lat: dict[str, float],
        hub_lon: dict[str, float],
    ) -> float:
        dlat = hub_lat[h1] - hub_lat[h2]
        dlon = hub_lon[h1] - hub_lon[h2]
        return dlat * dlat + dlon * dlon

    def _assign_flows(
        self,
        rfm: pd.DataFrame,
        edge_idx: dict[frozenset, int],
        hub_neighbors: dict[str, list[str]],
        hub_lat: dict[str, float],
        hub_lon: dict[str, float],
    ) -> tuple[dict[frozenset, float], dict[frozenset, float]]:
        link_flow_25: dict[frozenset, float] = defaultdict(float)
        link_flow_30: dict[frozenset, float] = defaultdict(float)
        direct_count = 0
        nn_count     = 0

        inter_rfm = rfm[rfm["origin_region"] != rfm["dest_region"]]
        for row in inter_rfm.itertuples(index=False):
            r_o, r_d = row.origin_region, row.dest_region
            t25, t30 = row.tons_2025, row.tons_2030
            for h_o, s_o in self._region_hubs[r_o]:
                for h_d, s_d in self._region_hubs[r_d]:
                    f25 = t25 * s_o * s_d
                    f30 = t30 * s_o * s_d
                    key = frozenset((h_o, h_d))
                    if key in edge_idx:
                        link_flow_25[key] += f25
                        link_flow_30[key] += f30
                        direct_count += 1
                    else:
                        neighbors = hub_neighbors.get(h_o, [])
                        if not neighbors:
                            continue
                        best_nn = min(
                            neighbors,
                            key=lambda h: self._latlon_dist_sq(h, h_d, hub_lat, hub_lon),
                        )
                        nn_key = frozenset((h_o, best_nn))
                        link_flow_25[nn_key] += f25
                        link_flow_30[nn_key] += f30
                        nn_count += 1

        total = direct_count + nn_count
        print(
            f"  [8.4] Assignments: {total:,} total | "
            f"direct={direct_count:,} ({100*direct_count/total:.1f}%) | "
            f"nearest-neighbor={nn_count:,} ({100*nn_count/total:.1f}%)"
        )
        return link_flow_25, link_flow_30

    def _build_output(
        self,
        links: pd.DataFrame,
        link_flow_25: dict[frozenset, float],
        link_flow_30: dict[frozenset, float],
    ) -> pd.DataFrame:
        rows = []
        for _, link in links.iterrows():
            h_a, h_b = link["hub_a_candidate_id"], link["hub_b_candidate_id"]
            key = frozenset((h_a, h_b))
            rows.append({
                "hub_a_candidate_id":           h_a,
                "hub_b_candidate_id":           h_b,
                "hub_a_name":                   link["hub_a_name"],
                "hub_b_name":                   link["hub_b_name"],
                "distance_miles":               link["distance_miles"],
                "flow_ktons_2025":              link_flow_25.get(key, 0.0),
                "flow_ktons_2030":              link_flow_30.get(key, 0.0),
                "flow_intensity_original_ktons": link["flow_intensity"],
            })
        df = pd.DataFrame(rows).sort_values("flow_ktons_2025", ascending=False)
        return df

    def _validate(
        self, hub_link_flows: pd.DataFrame, rfm: pd.DataFrame
    ) -> None:
        inter_total = rfm.loc[
            rfm["origin_region"] != rfm["dest_region"], "tons_2025"
        ].sum()
        link_total = hub_link_flows["flow_ktons_2025"].sum()
        dev_pct = abs(link_total - inter_total) / inter_total * 100

        assert dev_pct < 0.001, (
            f"Link flow total deviates {dev_pct:.4f}% from inter-region RFM total"
        )
        assert len(hub_link_flows) == self.cfg.EXPECTED_LINKS, (
            f"Expected {self.cfg.EXPECTED_LINKS} links, got {len(hub_link_flows)}"
        )
        assert (hub_link_flows["flow_ktons_2025"] >= 0).all(), "Negative flow"
        zero_flow = (hub_link_flows["flow_ktons_2025"] == 0).sum()
        print(
            f"  [8.4] ✓ link total={link_total:,.1f} ktons ≈ inter-region RFM total | "
            f"zero-flow links: {zero_flow}"
        )

    def _save(self, hub_link_flows: pd.DataFrame) -> None:
        out = self.cfg.HUB_LINK_FLOWS
        hub_link_flows.to_csv(out, index=False)
        print(f"  [8.4] Saved → {out}  ({out.stat().st_size / 1024:.1f} KB)")
