from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Mapping

from memory import RetrievedMemory
from policies.actions import ActionType
from policies.top1_reuse import Top1ReusePolicy
from policies.utils import PathRiskComparator, PathRiskProfile, reason_next_action
from simulator.utils import (
    get_edge_between,
)
from simulator.utils.validation import lookup_number, required_mapping

if TYPE_CHECKING:
    from memory import Memory
    from simulator.state import AgentState


RETRIEVAL_TOP_K = 1
GUARD_TOP_K = 1
RETRIEVAL_MIN_SCORE = 0.8
TOPOLOGY_MATCH_THRESHOLD = 0.6
OUTCOME_RELIABILITY_THRESHOLD = 0.6
RESOURCE_TRAJECTORY_THRESHOLD = 0.3


class MemoGuardPolicy(Top1ReusePolicy):
    def _decide(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        inspection_action = self._inspection_action_at_current_node(agent_state, context)
        if inspection_action is not None:
            return inspection_action

        if self._memory_retriever is None:
            return self._reasoning_action(agent_state, context)

        retrieved = self._memory_retriever.retrieve(
            agent_state,
            context,
            top_k=RETRIEVAL_TOP_K,
            excluded_actions=self._excluded_actions(agent_state),
            min_score=RETRIEVAL_MIN_SCORE,
        )
        if not retrieved:
            return self._reasoning_action(agent_state, context)

        guard_candidates = self._rerank_by_path_risk(retrieved, agent_state, context)[
            :GUARD_TOP_K
        ]
        if not guard_candidates:
            return self._reasoning_action(agent_state, context)

        guard = self._memo_guard_result(guard_candidates, agent_state, context)
        if guard["rejected"]:
            action = self._reasoning_action(agent_state, context)
            action["memo_guard"] = guard
            return action

        action = self._action_from_retrieved_memory(guard_candidates[0], agent_state, context)
        action["memo_guard"] = guard
        return action

    def _rerank_by_path_risk(
        self,
        retrieved: list[RetrievedMemory],
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> list[RetrievedMemory]:
        scored = [
            (
                self._topology_match(retrieved_memory.memory, agent_state, context)["score"],
                retrieved_memory.memory.outcome_statistics.success_rate,
                retrieved_memory.memory.outcome_statistics.success_count,
                retrieved_memory,
            )
            for retrieved_memory in retrieved
        ]
        scored.sort(reverse=True, key=lambda item: item[:3])
        return [item[3] for item in scored]

    def _memo_guard_result(
        self,
        retrieved: list[RetrievedMemory],
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        top_memory = retrieved[0].memory
        topology = self._topology_match(top_memory, agent_state, context)
        outcome = outcome_reliability_match(retrieved)
        resource = self._resource_trajectory_match(top_memory, agent_state, context)
        checks = {
            "topology": topology["score"] >= TOPOLOGY_MATCH_THRESHOLD,
            "outcome_reliability": outcome >= OUTCOME_RELIABILITY_THRESHOLD,
            "resource_trajectory": resource["score"] >= RESOURCE_TRAJECTORY_THRESHOLD,
        }
        rejected = not all(checks.values())
        return {
            "rejected": rejected,
            "retrieval_min_score": RETRIEVAL_MIN_SCORE,
            "retrieval_top_k": RETRIEVAL_TOP_K,
            "guard_top_k": GUARD_TOP_K,
            "match_scores": {
                "topology": topology["score"],
                "outcome_reliability": outcome,
                "resource_trajectory": resource["score"],
            },
            "thresholds": {
                "topology": TOPOLOGY_MATCH_THRESHOLD,
                "outcome_reliability": OUTCOME_RELIABILITY_THRESHOLD,
                "resource_trajectory": RESOURCE_TRAJECTORY_THRESHOLD,
            },
            "checks": checks,
            "failed_checks": [
                name
                for name, passed in checks.items()
                if not passed
            ],
            "topology_reason": topology["reason"],
            "resource": resource,
        }

    def _topology_match(
        self,
        memory: Memory,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        current_map_class = context.get("map_class")
        if (
            current_map_class is not None
            and memory.map_class is not None
            and str(current_map_class) != str(memory.map_class)
        ):
            return {"score": 0.0, "reason": "map_class_mismatch"}

        if (
            memory.action == ActionType.INSPECT_ALTERNATE_VIEWPOINT.value
            and not has_alternate_viewpoint(context)
        ):
            return {"score": 0.0, "reason": "missing_alternate_viewpoint"}

        if self._to_node_is_blocked(memory, agent_state, context):
            return {"score": 0.0, "reason": "blocked_to_node"}

        comparator = PathRiskComparator(
            required_mapping(context, "map_configuration"),
            agent_state.current_node,
            required_mapping(context, "metadata"),
        )
        if memory.path_risk_profile is not None:
            comparison = comparator.compare_profile(
                PathRiskProfile.from_dict(memory.path_risk_profile)
            )
        elif memory.map_configuration is not None:
            comparison = comparator.compare(
                memory.map_configuration,
                str(memory.retrieval_features.get("node", "")),
                memory.scenario_metadata,
            )
        else:
            return {"score": 0.0, "reason": "missing_path_risk_profile"}
        return {
            "score": comparison.score,
            "reason": "path_risk_similarity",
            "path_risk_similarity": comparison.to_dict(),
        }

    def _to_node_is_blocked(
        self,
        memory: Memory,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> bool:
        if memory.action in {
            ActionType.INSPECT_TARGET.value,
            ActionType.WAIT_FOR_RECOVERY.value,
        }:
            return False
        to_node = memory.to_node
        if to_node is None or to_node == agent_state.current_node:
            return False
        try:
            edge = get_edge_between(
                required_mapping(context, "map_configuration"),
                agent_state.current_node,
                str(to_node),
            )
        except ValueError:
            return True
        return str(edge.get("obstacle", "none")) == "blocked"

    def _resource_trajectory_match(
        self,
        memory: Memory,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        expected_cost = self._expected_cost_for_memory_action(memory, agent_state, context)
        safe_floor = lookup_number(
            required_mapping(self._simulator_config, "battery"),
            "safe_floor",
            "battery",
        )
        if math.isinf(expected_cost):
            return {
                "score": -math.inf,
                "expected_cost": expected_cost,
                "battery_expected": -math.inf,
                "safe_floor": safe_floor,
                "margin": -math.inf,
            }

        battery_expected = agent_state.battery - expected_cost
        margin = (battery_expected - safe_floor) / safe_floor
        return {
            "score": margin,
            "expected_cost": expected_cost,
            "battery_expected": battery_expected,
            "safe_floor": safe_floor,
            "margin": margin,
        }

    def _expected_cost_for_memory_action(
        self,
        memory: Memory,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> float:
        if memory.action == ActionType.WAIT_FOR_RECOVERY.value:
            return 0.0
        if memory.action == ActionType.ABORT_MISSION.value:
            return float(
                self._plan_to_nearest_recovery_node(agent_state, context)["expected_cost"]
            )
        if memory.action == ActionType.RETURN_TO_SAFE_WAYPOINT.value:
            return float(
                self._plan_to_goal(agent_state, context, "Safe_WP")["expected_cost"]
            )
        if memory.action == ActionType.FOLLOW_PLANNER.value:
            return float(
                self._plan_to_goal(
                    agent_state,
                    context,
                    agent_state.target_node,
                )["expected_cost"]
            )
        if memory.action == ActionType.INSPECT_ALTERNATE_VIEWPOINT.value:
            alternate_viewpoint = self._alternate_viewpoint(context)
            if alternate_viewpoint is None:
                return math.inf
            return float(
                self._plan_to_goal(agent_state, context, alternate_viewpoint)[
                    "expected_cost"
                ]
            )
        if memory.action == ActionType.INSPECT_TARGET.value:
            return float(
                self._plan_to_goal(
                    agent_state,
                    context,
                    agent_state.current_node,
                )["expected_cost"]
            )
        return math.inf

    def _reasoning_action(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        reasoning = reason_next_action(
            self._planner,
            self._simulator_config,
            agent_state,
            context,
            include_reasoning_cost=True,
        )
        action = self._action_from_reasoning(reasoning, agent_state, context)
        action["reasoning"] = True
        action["reasoning_details"] = reasoning
        return action


def outcome_reliability_match(retrieved: list[RetrievedMemory]) -> float:
    if not retrieved:
        return 0.0
    return sum(
        item.memory.outcome_statistics.success_rate
        for item in retrieved
    ) / len(retrieved)


def has_alternate_viewpoint(context: Mapping[str, Any]) -> bool:
    metadata = required_mapping(context, "metadata")
    alt_viewpoints = metadata.get("alt_viewpoints", [])
    if isinstance(alt_viewpoints, list) and alt_viewpoints:
        return True
    return any(
        bool(node.get("has_alt_viewpoint", False))
        for node in required_mapping(context, "map_configuration").get("nodes", [])
        if isinstance(node, Mapping)
    )
