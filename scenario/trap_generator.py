from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Mapping

from scenario.utils import (
    optional_bool,
    optional_int,
    optional_number,
    required_mapping,
    required_sequence,
)


TRAP_REMOVE_ALT_VIEWPOINT = "remove_alt_viewpoint"
TRAP_BLOCK_EDGES = "block_edges"
TRAP_REDUCE_BATTERY = "reduce_battery"
TRAP_TYPES = (
    TRAP_REMOVE_ALT_VIEWPOINT,
    TRAP_BLOCK_EDGES,
    TRAP_REDUCE_BATTERY,
)


class TrapGenerator:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def generate(self, scenario: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            trap_type: self.apply(scenario, config, trap_type)
            for trap_type in TRAP_TYPES
            if self._enabled(config, trap_type)
        }

    def apply(
        self,
        scenario: Mapping[str, Any],
        config: Mapping[str, Any],
        trap_type: str,
    ) -> dict[str, Any]:
        if trap_type not in TRAP_TYPES:
            raise ValueError(f"Unknown trap type: {trap_type}")
        if not self._enabled(config, trap_type):
            raise ValueError(f"Trap type is disabled: {trap_type}")

        trapped = deepcopy(dict(scenario))
        if trap_type == TRAP_REMOVE_ALT_VIEWPOINT:
            self._remove_alt_viewpoint(trapped)
        elif trap_type == TRAP_BLOCK_EDGES:
            self._block_edges(trapped, required_mapping(config, TRAP_BLOCK_EDGES))
        elif trap_type == TRAP_REDUCE_BATTERY:
            self._reduce_battery(trapped, required_mapping(config, TRAP_REDUCE_BATTERY))

        self._mark_trap(trapped, trap_type)
        return trapped

    @staticmethod
    def _enabled(config: Mapping[str, Any], trap_type: str) -> bool:
        enabled = required_mapping(config, "enabled")
        return optional_bool(enabled, trap_type, False)

    @staticmethod
    def _remove_alt_viewpoint(scenario: dict[str, Any]) -> None:
        map_configuration = required_mapping(scenario, "map_configuration")
        for node in required_sequence(map_configuration, "nodes"):
            if isinstance(node, dict):
                node["has_alt_viewpoint"] = False

        metadata = required_mapping(scenario, "metadata")
        if isinstance(metadata, dict):
            metadata["alt_viewpoints"] = []

    def _block_edges(
        self,
        scenario: dict[str, Any],
        config: Mapping[str, Any],
    ) -> None:
        count = optional_int(config, "count", 1)
        if count < 1:
            raise ValueError("block_edges.count must be at least 1")

        candidate_edges = [
            tuple(str(node) for node in edge)
            for edge in required_sequence(config, "candidate_edges")
            if isinstance(edge, list) and len(edge) == 2
        ]
        if len(candidate_edges) < count:
            raise ValueError("block_edges.candidate_edges does not contain enough edges")

        map_configuration = required_mapping(scenario, "map_configuration")
        edges = required_sequence(map_configuration, "edges")
        candidates = [
            edge
            for edge in edges
            if isinstance(edge, dict)
            and self._edge_key(edge) in {edge_key(candidate) for candidate in candidate_edges}
            and str(edge.get("obstacle", "none")) != "blocked"
        ]
        if len(candidates) < count:
            raise ValueError("Not enough non-blocked candidate edges in scenario")

        for edge in self._rng.sample(candidates, count):
            edge["obstacle"] = "blocked"

    @staticmethod
    def _edge_key(edge: Mapping[str, Any]) -> tuple[str, str]:
        nodes = edge.get("nodes")
        if not isinstance(nodes, list) or len(nodes) != 2:
            raise ValueError("Each edge must have exactly two nodes")
        return edge_key((str(nodes[0]), str(nodes[1])))

    @staticmethod
    def _reduce_battery(
        scenario: dict[str, Any],
        config: Mapping[str, Any],
    ) -> None:
        amount = optional_number(config, "amount", 0.0)
        minimum_battery = optional_number(config, "minimum_battery", 0.0)
        if amount < 0:
            raise ValueError("reduce_battery.amount cannot be negative")
        if minimum_battery < 0:
            raise ValueError("reduce_battery.minimum_battery cannot be negative")

        initial_state = required_mapping(scenario, "agent_initial_state")
        if not isinstance(initial_state, dict):
            raise ValueError("agent_initial_state must be an object")
        current_battery = float(initial_state.get("battery", 0.0))
        initial_state["battery"] = max(minimum_battery, current_battery - amount)

    @staticmethod
    def _mark_trap(scenario: dict[str, Any], trap_type: str) -> None:
        original_id = str(scenario.get("id", "scenario"))
        scenario["id"] = f"{original_id}_{trap_type}"
        metadata = scenario.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        metadata["trap"] = {
            "type": trap_type,
            "source_id": original_id,
        }


def edge_key(edge: tuple[str, str]) -> tuple[str, str]:
    return tuple(sorted(edge))
