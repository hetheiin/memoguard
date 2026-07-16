from __future__ import annotations

import math
from typing import Any, Mapping

from simulator.utils import expected_inspection_cost, expected_movement_cost, shortest_path
from simulator.utils.validation import required_list, required_number, required_str


class Planner:
    def __init__(self, simulator_config: Mapping[str, Any]) -> None:
        self._config = simulator_config

    def plan(
        self,
        map_configuration: Mapping[str, Any],
        current_node: str,
        goal_node: str,
        localization_confidence: float | None = None,
        inspection_cost: float | None = None,
    ) -> dict[str, Any]:
        nodes = self._node_index(map_configuration)
        graph = self._build_graph(map_configuration, nodes, localization_confidence)

        if current_node not in nodes:
            raise ValueError(f"Unknown current node: {current_node}")
        if goal_node not in nodes:
            raise ValueError(f"Unknown goal node: {goal_node}")

        plan = shortest_path(graph, current_node, goal_node)
        return self._include_goal_cost(
            plan,
            nodes[goal_node],
            localization_confidence,
            inspection_cost,
        )

    def _build_graph(
        self,
        map_configuration: Mapping[str, Any],
        nodes: Mapping[str, Mapping[str, Any]],
        localization_confidence: float | None,
    ) -> dict[str, list[dict[str, Any]]]:
        graph = {node_id: [] for node_id in nodes}

        for edge in required_list(map_configuration, "edges"):
            if not isinstance(edge, Mapping):
                raise ValueError("Each edge must be an object")

            edge_nodes = required_list(edge, "nodes")
            if len(edge_nodes) != 2:
                raise ValueError("Each edge must connect exactly two nodes")

            left, right = edge_nodes
            if left not in nodes or right not in nodes:
                raise ValueError(f"Edge references unknown node: {edge_nodes}")

            obstacle = required_str(edge, "obstacle")
            base_cost = required_number(edge, "battery_cost")

            self._add_edge(
                graph,
                source=left,
                target=right,
                source_node=nodes[left],
                obstacle=obstacle,
                base_cost=base_cost,
                localization_confidence=localization_confidence,
            )
            self._add_edge(
                graph,
                source=right,
                target=left,
                source_node=nodes[right],
                obstacle=obstacle,
                base_cost=base_cost,
                localization_confidence=localization_confidence,
            )

        return graph

    def _add_edge(
        self,
        graph: dict[str, list[dict[str, Any]]],
        source: str,
        target: str,
        source_node: Mapping[str, Any],
        obstacle: str,
        base_cost: float,
        localization_confidence: float | None,
    ) -> None:
        expected_cost = expected_movement_cost(
            self._config,
            base_cost,
            visibility=required_str(source_node, "visibility"),
            obstacle=obstacle,
            localization_confidence=localization_confidence,
        )
        if math.isinf(expected_cost):
            return

        graph[source].append(
            {
                "node": target,
                "expected_cost": expected_cost,
                "base_cost": base_cost,
                "obstacle": obstacle,
            }
        )

    @staticmethod
    def _node_index(map_configuration: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        nodes = {}
        for node in required_list(map_configuration, "nodes"):
            if not isinstance(node, Mapping):
                raise ValueError("Each node must be an object")
            node_id = required_str(node, "id")
            nodes[node_id] = node
        return nodes

    def _include_goal_cost(
        self,
        plan: dict[str, Any],
        goal_node: Mapping[str, Any],
        localization_confidence: float | None,
        inspection_cost: float | None,
    ) -> dict[str, Any]:
        needs_inspection = bool(goal_node.get("has_alt_viewpoint", False)) or bool(
            goal_node.get("has_target", False)
        )
        if not plan["reachable"] or not needs_inspection or inspection_cost is None:
            return plan

        expected_cost = expected_inspection_cost(
            self._config,
            base_cost=inspection_cost,
            visibility=required_str(goal_node, "visibility"),
            localization_confidence=localization_confidence,
        )
        if math.isinf(expected_cost):
            return {
                "path": [],
                "expected_cost": math.inf,
                "steps": math.inf,
                "reachable": False,
            }

        plan = dict(plan)
        plan["expected_cost"] += expected_cost
        plan["steps"] += 1
        plan["goal_action"] = "inspect_target"
        plan["goal_action_expected_cost"] = expected_cost
        return plan
