from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Mapping, Sequence

from scenario.utils import (
    choice,
    load_map,
    optional_mapping,
    required_mapping,
    required_sequence,
    required_str,
    weighted_choice,
)


class ScenarioGenerator:
    def __init__(self, maps_dir: Path, rng: random.Random | None = None) -> None:
        self._maps_dir = maps_dir
        self._rng = rng or random.Random()

    def generate(self, config: Mapping[str, Any], index: int) -> dict[str, Any]:
        scenario_type = required_str(config, "scenario_type")
        map_id = required_str(config, "map_id")
        sampling_config = required_mapping(config, "sampling_config")
        map_template = load_map(map_id, self._maps_dir)

        target_node = choice(
            self._rng,
            required_sequence(sampling_config, "target_node_candidates"),
            "target_node_candidates",
        )
        alt_viewpoint = choice(
            self._rng,
            required_sequence(sampling_config, "alt_viewpoint_candidates"),
            "alt_viewpoint_candidates",
        )
        inspect_target_cost = float(
            choice(
                self._rng,
                required_sequence(sampling_config, "inspect_target_costs"),
                "inspect_target_costs",
            )
        )

        edges = self._sample_edges(map_template, sampling_config)

        return {
            "id": f"{scenario_type}_{index}",
            "instruction": (
                f"Inspect the target in {target_node} and return to the base or a safe waypoint."
            ),
            "agent_initial_state": {
                "start_node": "Base",
                "battery": float(
                    choice(
                        self._rng,
                        required_sequence(sampling_config, "battery_choices"),
                        "battery_choices",
                    )
                ),
                "localization_confidence": float(
                    choice(
                        self._rng,
                        required_sequence(sampling_config, "localization_confidence_choices"),
                        "localization_confidence_choices",
                    )
                ),
            },
            "metadata": {
                "target_node": target_node,
                "safe_waypoint_adjacent_nodes": self._safe_waypoint_adjacent_nodes(edges),
                "alt_viewpoints": [alt_viewpoint],
                "inspect_target_cost": inspect_target_cost,
            },
            "map_id": map_template.get("id", map_id),
            "map_class": map_template.get("class"),
            "map_configuration": {
                "nodes": self._sample_nodes(
                    map_template,
                    sampling_config,
                    target_node,
                    alt_viewpoint,
                ),
                "edges": edges,
            },
        }

    def _sample_nodes(
        self,
        map_template: Mapping[str, Any],
        sampling_config: Mapping[str, Any],
        target_node: str,
        alt_viewpoint: str,
    ) -> list[dict[str, Any]]:
        visibility_config = required_mapping(sampling_config, "visibility_config")
        fixed_visibility = optional_mapping(visibility_config, "fixed")
        visibility_probs = required_mapping(visibility_config, "probs")

        sampled_nodes = []
        for node in required_sequence(map_template, "nodes"):
            if not isinstance(node, Mapping):
                raise ValueError("Each map node must be an object")

            node_id = required_str(node, "id")
            if node_id in fixed_visibility:
                visibility = fixed_visibility[node_id]
            else:
                visibility = weighted_choice(
                    self._rng,
                    visibility_probs,
                    "visibility_config.probs",
                )

            sampled_nodes.append(
                {
                    "id": node_id,
                    "visibility": visibility,
                    "has_alt_viewpoint": node_id == alt_viewpoint,
                    "has_target": node_id == target_node,
                }
            )

        return sampled_nodes

    def _sample_edges(
        self,
        map_template: Mapping[str, Any],
        sampling_config: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        obstacle_config = required_mapping(sampling_config, "obstacle_config")
        obstacle_probs = required_mapping(obstacle_config, "probs")
        edge_cost_config = required_mapping(sampling_config, "edge_battery_cost_config")
        level_probs = required_mapping(edge_cost_config, "level_probs")
        levels = required_mapping(edge_cost_config, "levels")

        sampled_edges = []
        for edge in required_sequence(map_template, "edges"):
            if not isinstance(edge, Mapping):
                raise ValueError("Each map edge must be an object")

            level = weighted_choice(
                self._rng,
                level_probs,
                "edge_battery_cost_config.level_probs",
            )
            sampled_edges.append(
                {
                    "nodes": list(required_sequence(edge, "nodes")),
                    "battery_cost": float(
                        choice(
                            self._rng,
                            required_sequence(levels, level),
                            f"edge_battery_cost_config.levels.{level}",
                        )
                    ),
                    "obstacle": weighted_choice(
                        self._rng,
                        obstacle_probs,
                        "obstacle_config.probs",
                    ),
                }
            )

        return sampled_edges

    @staticmethod
    def _safe_waypoint_adjacent_nodes(edges: Sequence[Mapping[str, Any]]) -> list[str]:
        adjacent_nodes = []
        for edge in edges:
            nodes = edge.get("nodes", [])
            if len(nodes) != 2 or "Safe_WP" not in nodes:
                continue
            adjacent_nodes.append(nodes[0] if nodes[1] == "Safe_WP" else nodes[1])
        return adjacent_nodes
