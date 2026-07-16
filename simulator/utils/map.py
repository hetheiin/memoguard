from __future__ import annotations

from typing import Any, Mapping

from simulator.utils.validation import required_list


def has_node(map_configuration: Mapping[str, Any], node_id: str) -> bool:
    return any(node.get("id") == node_id for node in required_list(map_configuration, "nodes"))


def get_node(map_configuration: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    for node in required_list(map_configuration, "nodes"):
        if node.get("id") == node_id:
            return node
    raise ValueError(f"Unknown node: {node_id}")


def get_edge_between(
    map_configuration: Mapping[str, Any],
    left: str,
    right: str,
) -> Mapping[str, Any]:
    for edge in required_list(map_configuration, "edges"):
        nodes = edge.get("nodes")
        if isinstance(nodes, list) and set(nodes) == {left, right}:
            return edge
    raise ValueError(f"No edge between {left} and {right}")
