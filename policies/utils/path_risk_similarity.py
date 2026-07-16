from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


OUTBOUND_RISK_WEIGHT = 0.6
RETURN_RISK_WEIGHT = 0.4
CATEGORICAL_RISK_WEIGHT = 0.7
EDGE_COST_RISK_WEIGHT = 0.3
RECOVERY_NODES = ("Base", "Safe_WP")


@dataclass(frozen=True)
class PathRiskProfile:
    outbound_risk: tuple[int, int, int, int]
    return_risk: tuple[int, int, int, int]
    outbound_edge_cost: float
    return_edge_cost: float

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PathRiskProfile":
        return cls(
            outbound_risk=tuple_ints(payload.get("outbound_risk", []), 4),
            return_risk=tuple_ints(payload.get("return_risk", []), 4),
            outbound_edge_cost=float(payload.get("outbound_edge_cost", 0.0)),
            return_edge_cost=float(payload.get("return_edge_cost", 0.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "outbound_risk": list(self.outbound_risk),
            "return_risk": list(self.return_risk),
            "outbound_edge_cost": self.outbound_edge_cost,
            "return_edge_cost": self.return_edge_cost,
        }


@dataclass(frozen=True)
class PathRiskSimilarityResult:
    score: float
    factor_scores: dict[str, float]
    reference_profile: PathRiskProfile
    comparison_profile: PathRiskProfile

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "factor_scores": self.factor_scores,
            "reference_profile": self.reference_profile.to_dict(),
            "comparison_profile": self.comparison_profile.to_dict(),
        }


class PathRiskComparator:
    def __init__(
        self,
        reference_map: Mapping[str, Any],
        reference_node: str,
        reference_metadata: Mapping[str, Any],
    ) -> None:
        self._reference_graph = GraphView(reference_map)
        self._reference_profile = build_path_risk_profile(
            self._reference_graph,
            reference_node,
            reference_metadata,
        )
        self._comparison_cache: dict[tuple[int, str, str | None, tuple[str, ...]], PathRiskProfile] = {}

    def compare(
        self,
        comparison_map: Mapping[str, Any],
        comparison_node: str,
        comparison_metadata: Mapping[str, Any],
    ) -> PathRiskSimilarityResult:
        comparison_profile = self._comparison_profile(
            comparison_map,
            comparison_node,
            comparison_metadata,
        )
        return compare_path_risk_profiles(self._reference_profile, comparison_profile)

    def compare_profile(
        self,
        comparison_profile: PathRiskProfile,
    ) -> PathRiskSimilarityResult:
        return compare_path_risk_profiles(self._reference_profile, comparison_profile)

    def _comparison_profile(
        self,
        comparison_map: Mapping[str, Any],
        comparison_node: str,
        comparison_metadata: Mapping[str, Any],
    ) -> PathRiskProfile:
        cache_key = profile_cache_key(comparison_map, comparison_node, comparison_metadata)
        if cache_key not in self._comparison_cache:
            self._comparison_cache[cache_key] = build_path_risk_profile(
                GraphView(comparison_map),
                comparison_node,
                comparison_metadata,
            )
        return self._comparison_cache[cache_key]


class GraphView:
    def __init__(self, map_configuration: Mapping[str, Any]) -> None:
        self.nodes = node_index(map_configuration)
        self.edges = edge_index(map_configuration)
        self.adjacency = adjacency_index(self.nodes, self.edges)

    def shortest_path(self, start: str, goal: str | None) -> list[str]:
        if goal is None or start not in self.nodes or goal not in self.nodes:
            return []
        if start == goal:
            return [start]

        queue = deque([(start, [start])])
        visited = {start}
        while queue:
            node, path = queue.popleft()
            for neighbor in self.adjacency.get(node, []):
                if neighbor in visited:
                    continue
                next_path = [*path, neighbor]
                if neighbor == goal:
                    return next_path
                visited.add(neighbor)
                queue.append((neighbor, next_path))
        return []

    def distances_from(self, start: str) -> dict[str, int]:
        if start not in self.nodes:
            return {}
        distances = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in self.adjacency.get(node, []):
                if neighbor in distances:
                    continue
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
        return distances


def build_path_risk_profile(
    graph: GraphView,
    node_id: str,
    metadata: Mapping[str, Any],
) -> PathRiskProfile:
    distances_from_node = graph.distances_from(node_id)
    target_node = optional_str(metadata.get("target_node"))
    alt_viewpoint = first_str(metadata.get("alt_viewpoints"))
    nearest_recovery = nearest_node(distances_from_node, RECOVERY_NODES)
    inspection_node = alt_viewpoint or target_node

    outbound_path = graph.shortest_path(node_id, inspection_node)
    return_path = graph.shortest_path(inspection_node or node_id, nearest_recovery)
    return PathRiskProfile(
        outbound_risk=path_risk_vector(graph, outbound_path),
        return_risk=path_risk_vector(graph, return_path),
        outbound_edge_cost=path_edge_cost(graph, outbound_path),
        return_edge_cost=path_edge_cost(graph, return_path),
    )


def compare_path_risk_profiles(
    reference: PathRiskProfile,
    comparison: PathRiskProfile,
) -> PathRiskSimilarityResult:
    factor_scores = {
        "outbound_risk": path_segment_similarity(
            reference.outbound_risk,
            comparison.outbound_risk,
            reference.outbound_edge_cost,
            comparison.outbound_edge_cost,
        ),
        "return_risk": path_segment_similarity(
            reference.return_risk,
            comparison.return_risk,
            reference.return_edge_cost,
            comparison.return_edge_cost,
        ),
    }
    factor_scores["path_risk"] = (
        OUTBOUND_RISK_WEIGHT * factor_scores["outbound_risk"]
        + RETURN_RISK_WEIGHT * factor_scores["return_risk"]
    )
    return PathRiskSimilarityResult(
        score=factor_scores["path_risk"],
        factor_scores=factor_scores,
        reference_profile=reference,
        comparison_profile=comparison,
    )


def path_segment_similarity(
    left_risk: tuple[int, int, int, int],
    right_risk: tuple[int, int, int, int],
    left_edge_cost: float,
    right_edge_cost: float,
) -> float:
    return (
        CATEGORICAL_RISK_WEIGHT * risk_similarity(left_risk, right_risk)
        + EDGE_COST_RISK_WEIGHT * edge_cost_similarity(left_edge_cost, right_edge_cost)
    )


def risk_similarity(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    distance = sum(abs(left_value - right_value) for left_value, right_value in zip(left, right))
    normalizer = max(sum(left) + sum(right), 1)
    return bounded_similarity(distance, normalizer)


def edge_cost_similarity(left: float, right: float) -> float:
    return bounded_similarity(abs(left - right), max(left, right, 1.0))


def bounded_similarity(distance: float, normalizer: float) -> float:
    if normalizer <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - distance / normalizer))


def path_risk_vector(graph: GraphView, path: Sequence[str]) -> tuple[int, int, int, int]:
    if not path:
        return (0, 0, 0, 0)

    low_visibility = 0
    near_zero_visibility = 0
    partial_blockage = 0
    blocked = 0
    for node_id in path:
        visibility = str(graph.nodes.get(node_id, {}).get("visibility", "high"))
        if visibility == "low":
            low_visibility += 1
        elif visibility == "near_zero":
            near_zero_visibility += 1

    for left, right in zip(path, path[1:]):
        obstacle = str(graph.edges.get(edge_key(left, right), {}).get("obstacle", "none"))
        if obstacle == "partial_blockage":
            partial_blockage += 1
        elif obstacle == "blocked":
            blocked += 1

    return (low_visibility, near_zero_visibility, partial_blockage, blocked)


def path_edge_cost(graph: GraphView, path: Sequence[str]) -> float:
    total = 0.0
    for left, right in zip(path, path[1:]):
        edge = graph.edges.get(edge_key(left, right), {})
        total += float(edge.get("battery_cost", 0.0))
    return total


def nearest_node(distances: Mapping[str, int], candidates: Sequence[str]) -> str | None:
    reachable = [
        (distances[candidate], candidate)
        for candidate in candidates
        if candidate in distances
    ]
    if not reachable:
        return None
    return min(reachable)[1]


def node_index(map_configuration: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    nodes = {}
    for node in required_list(map_configuration, "nodes"):
        if not isinstance(node, Mapping):
            raise ValueError("Each node must be an object")
        nodes[str(node["id"])] = node
    return nodes


def edge_index(map_configuration: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    edges = {}
    for edge in required_list(map_configuration, "edges"):
        if not isinstance(edge, Mapping):
            raise ValueError("Each edge must be an object")
        nodes = edge.get("nodes")
        if not isinstance(nodes, list) or len(nodes) != 2:
            raise ValueError("Each edge must connect exactly two nodes")
        left = str(nodes[0])
        right = str(nodes[1])
        edges[edge_key(left, right)] = edge
    return edges


def adjacency_index(
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for left, right in edges:
        adjacency.setdefault(left, []).append(right)
        adjacency.setdefault(right, []).append(left)
    for neighbors in adjacency.values():
        neighbors.sort()
    return adjacency


def edge_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


def profile_cache_key(
    map_configuration: Mapping[str, Any],
    node_id: str,
    metadata: Mapping[str, Any],
) -> tuple[int, str, str | None, tuple[str, ...]]:
    return (
        id(map_configuration),
        node_id,
        optional_str(metadata.get("target_node")),
        tuple(sorted(str(value) for value in metadata.get("alt_viewpoints", []))),
    )


def first_str(value: Any) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    return str(value[0])


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def required_list(source: Mapping[str, Any], key: str) -> list[Any]:
    value = source.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def tuple_ints(values: Any, expected_length: int) -> tuple[int, ...]:
    if not isinstance(values, list) or len(values) != expected_length:
        raise ValueError(f"Expected list of length {expected_length}")
    return tuple(int(value) for value in values)
