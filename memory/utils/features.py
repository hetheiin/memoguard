from __future__ import annotations

from typing import Any, Mapping


def build_retrieval_features(
    step: Mapping[str, Any],
    map_configuration: Mapping[str, Any],
    simulator_config: Mapping[str, Any],
) -> dict[str, Any]:
    from_node = str(step["from_node"])
    to_node = step.get("to_node")
    localization_confidence = float(
        step.get(
            "localization_confidence_before",
            step.get("localization_confidence_after", 0.0),
        )
    )
    return {
        "node": from_node,
        "visibility": node_visibility(map_configuration, from_node),
        "obstacle": edge_obstacle(map_configuration, from_node, to_node),
        "edge_cost": edge_cost(map_configuration, from_node, to_node),
        "localization_confidence_level": localization_confidence_level(
            simulator_config,
            localization_confidence,
        ),
        "battery_range": battery_range(float(step["battery_before"])),
    }


def node_visibility(map_configuration: Mapping[str, Any], node_id: str) -> str:
    for node in required_list(map_configuration, "nodes"):
        if isinstance(node, Mapping) and node.get("id") == node_id:
            return str(node.get("visibility", "high"))
    raise ValueError(f"Unknown node in map_configuration: {node_id}")


def edge_obstacle(
    map_configuration: Mapping[str, Any],
    from_node: str,
    to_node: Any,
) -> str:
    if to_node is None or str(to_node) == from_node:
        return "none"

    for edge in required_list(map_configuration, "edges"):
        if not isinstance(edge, Mapping):
            continue
        nodes = edge.get("nodes")
        if isinstance(nodes, list) and set(nodes) == {from_node, str(to_node)}:
            return str(edge.get("obstacle", "none"))
    return "none"


def edge_cost(
    map_configuration: Mapping[str, Any],
    from_node: str,
    to_node: Any,
) -> float | None:
    if to_node is None or str(to_node) == from_node:
        return None

    for edge in required_list(map_configuration, "edges"):
        if not isinstance(edge, Mapping):
            continue
        nodes = edge.get("nodes")
        if isinstance(nodes, list) and set(nodes) == {from_node, str(to_node)}:
            value = edge.get("battery_cost")
            if isinstance(value, (int, float)):
                return float(value)
            return None
    return None


def localization_confidence_level(
    simulator_config: Mapping[str, Any],
    localization_confidence: float,
) -> str:
    localization_config = required_mapping(simulator_config, "localization_confidence")
    ranges = required_mapping(localization_config, "ranges")

    for level, bounds in ranges.items():
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("localization_confidence.ranges values must be [min, max]")
        lower = float(bounds[0])
        upper = float(bounds[1])
        if lower <= localization_confidence <= upper:
            return str(level)

    raise ValueError(
        f"localization_confidence is out of configured ranges: {localization_confidence}"
    )


def battery_range(value: float) -> str:
    lower = int(value // 5) * 5
    upper = lower + 5
    return [lower, upper]


def required_mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def required_list(source: Mapping[str, Any], key: str) -> list[Any]:
    value = source.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value
