from __future__ import annotations

import heapq
import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from memory.memory import Memory
from memory.utils import read_json
from memory.utils.features import (
    battery_range,
    edge_obstacle,
    localization_confidence_level,
    node_visibility,
)

if TYPE_CHECKING:
    from simulator.state import AgentState


DEFAULT_RERANK_WEIGHTS = {
    "one_step": 8.0,
    "agent_status": 2.0,
}


@dataclass
class RetrievedMemory:
    memory: Memory
    score: float
    factor_scores: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = self.memory.to_dict()
        payload["similarity_score"] = self.score
        payload["factor_scores"] = self.factor_scores
        return payload


class MemoryRetriever:
    def __init__(
        self,
        memories: Sequence[Memory],
        weights: Mapping[str, float] | None = None,
    ) -> None:
        self._memories = list(memories)
        self._weights = normalized_rerank_weights(weights)
        total_weight = sum(max(0.0, float(weight)) for weight in self._weights.values())
        if total_weight <= 0:
            raise ValueError("memory retrieval weights must have a positive total")
        self._total_weight = total_weight

    @classmethod
    def from_file(
        cls,
        memory_path: Path,
        weights: Mapping[str, float] | None = None,
        max_samples: int | None = None,
        seed: int | None = None,
    ) -> "MemoryRetriever":
        payload = read_json(memory_path)
        if not isinstance(payload, list):
            raise ValueError(f"Expected memory list in {memory_path}")
        memories = [Memory.from_dict(item) for item in payload if isinstance(item, Mapping)]
        memories = sample_memories(memories, max_samples, seed)
        return cls(memories, weights)

    def retrieve(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
        top_k: int = 5,
        allowed_actions: set[str] | None = None,
        excluded_actions: set[str] | None = None,
        min_score: float | None = None,
    ) -> list[RetrievedMemory]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        memories = [
            memory
            for memory in self._memories
            if memory_passes_filter(
                memory,
                agent_state,
                allowed_actions,
                excluded_actions,
            )
        ]
        scored = scored_memories_above_threshold(
            (
                self._score_memory(memory, agent_state, context)
                for memory in memories
            ),
            min_score,
        )
        if top_k == 1:
            best = max(
                scored,
                key=retrieved_memory_sort_key,
                default=None,
            )
            return [] if best is None else [best]

        return heapq.nlargest(
            top_k,
            scored,
            key=retrieved_memory_sort_key,
        )

    def _score_memory(
        self,
        memory: Memory,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> RetrievedMemory:
        map_configuration = self._map_configuration(context)
        one_step_scores = {
            "visibility": ranked_score(
                self._memory_feature(memory, "visibility"),
                node_visibility(map_configuration, agent_state.current_node),
                {"near_zero": 0, "low": 1, "high": 2},
            ),
            "obstacle": ranked_score(
                self._memory_feature(memory, "obstacle"),
                edge_obstacle(
                    map_configuration,
                    agent_state.current_node,
                    memory.to_node,
                ),
                {"none": 0, "partial_blockage": 1, "blocked": 2},
            ),
            "edge_cost": edge_cost_similarity(
                memory_edge_cost(memory),
                current_edge_cost(map_configuration, agent_state.current_node, memory.to_node),
            ),
        }
        status_scores = {
            "battery_range": battery_range_similarity(
                self._memory_feature(memory, "battery_range"),
                battery_range(agent_state.battery),
            ),
            "localization_confidence": ranked_score(
                self._memory_feature(memory, "localization_confidence_level"),
                localization_confidence_level(
                    self._simulator_config(context),
                    agent_state.localization_confidence,
                ),
                {"low": 0, "medium": 1, "high": 2},
            ),
        }
        factor_scores = {
            "one_step": average_score(one_step_scores.values()),
            "agent_status": average_score(status_scores.values()),
            "one_step_details": one_step_scores,
            "agent_status_details": status_scores,
            "target_node": exact_score(
                self._target_node(memory),
                agent_state.target_node,
            ),
            "node": exact_score(
                self._memory_feature(memory, "node"),
                agent_state.current_node,
            ),
        }
        weighted_score = sum(
            float(self._weights.get(factor, 0.0)) * score
            for factor, score in {
                "one_step": factor_scores["one_step"],
                "agent_status": factor_scores["agent_status"],
            }.items()
        )
        return RetrievedMemory(
            memory=memory,
            score=weighted_score / self._total_weight,
            factor_scores=factor_scores,
        )

    @staticmethod
    def _target_node(memory: Memory) -> str | None:
        value = memory.scenario_metadata.get("target_node")
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _memory_feature(memory: Memory, name: str) -> Any:
        return memory.retrieval_features.get(name)

    @staticmethod
    def _map_configuration(context: Mapping[str, Any]) -> Mapping[str, Any]:
        value = context.get("map_configuration")
        if not isinstance(value, Mapping):
            raise ValueError("context.map_configuration must be an object")
        return value

    @staticmethod
    def _simulator_config(context: Mapping[str, Any]) -> Mapping[str, Any]:
        value = context.get("simulator_config")
        if not isinstance(value, Mapping):
            raise ValueError("context.simulator_config must be an object")
        return value


def exact_score(left: Any, right: Any) -> float:
    if left is None or right is None:
        return 0.0
    return 1.0 if left == right else 0.0


def ranked_score(left: Any, right: Any, ranks: Mapping[str, int]) -> float:
    if left is None or right is None:
        return 0.0
    left_key = str(left)
    right_key = str(right)
    if left_key not in ranks or right_key not in ranks:
        return 0.0
    return 1.0 - abs(ranks[left_key] - ranks[right_key]) / 2.0


def normalized_rerank_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    if not weights:
        return dict(DEFAULT_RERANK_WEIGHTS)
    if any(key in weights for key in DEFAULT_RERANK_WEIGHTS):
        return {
            key: float(weights.get(key, DEFAULT_RERANK_WEIGHTS[key]))
            for key in DEFAULT_RERANK_WEIGHTS
        }
    return dict(DEFAULT_RERANK_WEIGHTS)


def memory_passes_filter(
    memory: Memory,
    agent_state: AgentState,
    allowed_actions: set[str] | None,
    excluded_actions: set[str] | None,
) -> bool:
    return (
        action_is_allowed(memory.action, allowed_actions, excluded_actions)
        and exact_score(memory_target_node(memory), agent_state.target_node) == 1.0
        and exact_score(
            memory.retrieval_features.get("node"),
            agent_state.current_node,
        ) == 1.0
    )


def action_is_allowed(
    action: str,
    allowed_actions: set[str] | None,
    excluded_actions: set[str] | None,
) -> bool:
    if allowed_actions is not None and action not in allowed_actions:
        return False
    if excluded_actions is not None and action in excluded_actions:
        return False
    return True


def memory_target_node(memory: Memory) -> str | None:
    value = memory.scenario_metadata.get("target_node")
    if value is None:
        return None
    return str(value)


def average_score(values) -> float:
    scores = list(values)
    if not scores:
        return 0.0
    return sum(float(score) for score in scores) / len(scores)


def edge_cost_similarity(left: float | None, right: float | None) -> float:
    if left is None and right is None:
        return 1.0
    if left is None or right is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - abs(left - right) / max(left, right, 1.0)))


def memory_edge_cost(memory: Memory) -> float | None:
    stored_edge_cost = memory.retrieval_features.get("edge_cost")
    if isinstance(stored_edge_cost, (int, float)):
        return float(stored_edge_cost)

    from_node = memory.retrieval_features.get("node")
    to_node = memory.to_node
    if (
        memory.map_configuration is None
        or from_node is None
        or to_node is None
        or str(from_node) == str(to_node)
    ):
        return None
    return edge_cost_between(memory.map_configuration, str(from_node), str(to_node))


def current_edge_cost(
    map_configuration: Mapping[str, Any],
    current_node: str,
    to_node: Any,
) -> float | None:
    if to_node is None or str(to_node) == current_node:
        return None
    return edge_cost_between(map_configuration, current_node, str(to_node))


def edge_cost_between(
    map_configuration: Mapping[str, Any],
    left: str,
    right: str,
) -> float | None:
    edges = map_configuration.get("edges")
    if not isinstance(edges, list):
        return None
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        nodes = edge.get("nodes")
        if isinstance(nodes, list) and set(str(node) for node in nodes) == {left, right}:
            value = edge.get("battery_cost")
            if isinstance(value, (int, float)):
                return float(value)
            return None
    return None


def battery_range_similarity(left: Any, right: Any) -> float:
    left_bounds = range_bounds(left)
    right_bounds = range_bounds(right)
    if left_bounds is None or right_bounds is None:
        return 0.0
    left_mid = (left_bounds[0] + left_bounds[1]) / 2.0
    right_mid = (right_bounds[0] + right_bounds[1]) / 2.0
    normalizer = max(left_bounds[1], right_bounds[1], 1.0)
    return max(0.0, min(1.0, 1.0 - abs(left_mid - right_mid) / normalizer))


def range_bounds(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    return float(value[0]), float(value[1])


def retrieved_memory_sort_key(retrieved: RetrievedMemory) -> tuple[float, float, int]:
    return (
        retrieved.score,
        retrieved.memory.outcome_statistics.success_rate,
        retrieved.memory.outcome_statistics.success_count,
    )


def scored_memories_above_threshold(
    scored_memories,
    min_score: float | None,
):
    for scored_memory in scored_memories:
        if min_score is None or scored_memory.score >= min_score:
            yield scored_memory


def sample_memories(
    memories: Sequence[Memory],
    max_samples: int | None,
    seed: int | None,
) -> list[Memory]:
    memory_list = list(memories)
    if max_samples is None:
        return memory_list
    if max_samples < 1:
        raise ValueError("memory_retrieval.max_samples must be at least 1")
    if len(memory_list) <= max_samples:
        return memory_list
    return random.Random(seed).sample(memory_list, max_samples)
