from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Mapping

from policies.actions import ActionType
from simulator.utils import RECOVERY_NODES, has_node
from simulator.utils.validation import lookup_number, required_mapping

if TYPE_CHECKING:
    from simulator.planner import Planner
    from simulator.state import AgentState


def reason_next_action(
    planner: Planner,
    simulator_config: Mapping[str, Any],
    agent_state: AgentState,
    context: Mapping[str, Any],
    include_reasoning_cost: bool = False,
) -> dict[str, Any]:
    if agent_state.target_inspected:
        return {"decision": "abort"}

    candidate = _best_inspection_candidate(
        planner,
        agent_state,
        context,
        include_reasoning_cost,
    )
    if candidate is None:
        return {"decision": "abort"}

    required_battery = _required_battery(
        simulator_config,
        candidate["total_expected_cost"],
        candidate["total_reasoning_cost"],
    )
    if agent_state.battery < required_battery:
        if agent_state.current_node == "Safe_WP":
            return {
                "decision": "wait_for_recovery",
                "plan": candidate["inspection_plan"],
                "required_battery": required_battery,
                "candidate": candidate,
            }
        if _has_waited_for_recovery(agent_state):
            return _execute_inspection_plan(candidate, required_battery)
        return {
            "decision": "return_to_safe_waypoint",
            "required_battery": required_battery,
            "candidate": candidate,
        }

    return _execute_inspection_plan(candidate, required_battery)


def _execute_inspection_plan(
    candidate: Mapping[str, Any],
    required_battery: float,
) -> dict[str, Any]:
    return {
        "decision": "execute_inspection_plan",
        "action_type": candidate["action_type"],
        "plan": candidate["inspection_plan"],
        "required_battery": required_battery,
        "candidate": candidate,
    }


def _has_waited_for_recovery(agent_state: AgentState) -> bool:
    return any(
        record.get("action") == ActionType.WAIT_FOR_RECOVERY.value
        for record in agent_state.action_sequence
    )


def _best_inspection_candidate(
    planner: Planner,
    agent_state: AgentState,
    context: Mapping[str, Any],
    include_reasoning_cost: bool,
) -> dict[str, Any] | None:
    candidates = [
        _inspection_candidate(
            planner,
            agent_state,
            context,
            inspection_node=agent_state.target_node,
            action_type=ActionType.FOLLOW_PLANNER,
            include_reasoning_cost=include_reasoning_cost,
        )
    ]

    alternate_viewpoint = _alternate_viewpoint(context)
    if alternate_viewpoint is not None:
        candidates.append(
            _inspection_candidate(
                planner,
                agent_state,
                context,
                inspection_node=alternate_viewpoint,
                action_type=ActionType.INSPECT_ALTERNATE_VIEWPOINT,
                include_reasoning_cost=include_reasoning_cost,
            )
        )

    reachable_candidates = [candidate for candidate in candidates if candidate is not None]
    if not reachable_candidates:
        return None
    return min(
        reachable_candidates,
        key=lambda candidate: candidate["total_cost_with_reasoning"],
    )


def _inspection_candidate(
    planner: Planner,
    agent_state: AgentState,
    context: Mapping[str, Any],
    inspection_node: str,
    action_type: ActionType,
    include_reasoning_cost: bool,
) -> dict[str, Any] | None:
    inspection_plan = _plan(
        planner,
        context,
        agent_state.current_node,
        inspection_node,
        agent_state.localization_confidence,
    )
    if not inspection_plan["reachable"]:
        return None

    return_plan = _nearest_recovery_return_plan(
        planner,
        context,
        inspection_node,
        agent_state.localization_confidence,
    )
    if not return_plan["reachable"]:
        return None

    total_steps = inspection_plan["steps"] + return_plan["steps"]
    total_expected_cost = inspection_plan["expected_cost"] + return_plan["expected_cost"]
    total_reasoning_cost = (
        _estimated_reasoning_cost(context, total_steps)
        if include_reasoning_cost
        else 0.0
    )
    return {
        "action_type": action_type,
        "inspection_plan": inspection_plan,
        "return_plan": return_plan,
        "total_expected_cost": total_expected_cost,
        "total_reasoning_cost": total_reasoning_cost,
        "total_cost_with_reasoning": total_expected_cost + total_reasoning_cost,
    }


def _nearest_recovery_return_plan(
    planner: Planner,
    context: Mapping[str, Any],
    start_node: str,
    localization_confidence: float,
) -> Mapping[str, Any]:
    map_configuration = required_mapping(context, "map_configuration")
    plans = [
        _plan(planner, context, start_node, candidate, localization_confidence)
        for candidate in RECOVERY_NODES
        if has_node(map_configuration, candidate)
    ]
    reachable_plans = [plan for plan in plans if plan["reachable"]]
    if not reachable_plans:
        return {
            "path": [],
            "expected_cost": math.inf,
            "steps": 0,
            "reachable": False,
        }
    return min(reachable_plans, key=lambda plan: (plan["expected_cost"], plan["steps"]))


def _plan(
    planner: Planner,
    context: Mapping[str, Any],
    start_node: str,
    goal_node: str,
    localization_confidence: float,
) -> Mapping[str, Any]:
    return planner.plan(
        required_mapping(context, "map_configuration"),
        start_node,
        goal_node,
        localization_confidence,
        _inspection_cost(context),
    )


def _required_battery(
    simulator_config: Mapping[str, Any],
    expected_cost: float,
    reasoning_cost: float,
) -> float:
    if math.isinf(expected_cost):
        return 100.0
    safe_floor = lookup_number(
        required_mapping(simulator_config, "battery"),
        "safe_floor",
        "battery",
    )
    return min(expected_cost * 1.5 + reasoning_cost + safe_floor, 100.0)


def _estimated_reasoning_cost(context: Mapping[str, Any], steps: float) -> float:
    if math.isinf(steps):
        return math.inf
    simulator_config = required_mapping(context, "simulator_config")
    return steps * lookup_number(simulator_config, "reasoning_cost", "reasoning_cost")


def _alternate_viewpoint(context: Mapping[str, Any]) -> str | None:
    metadata = required_mapping(context, "metadata")
    viewpoints = metadata.get("alt_viewpoints", [])
    if not isinstance(viewpoints, list) or not viewpoints:
        return None
    return str(viewpoints[0])


def _inspection_cost(context: Mapping[str, Any]) -> float:
    metadata = required_mapping(context, "metadata")
    value = metadata.get("inspect_target_cost", 2.0)
    if not isinstance(value, (int, float)):
        raise ValueError("metadata.inspect_target_cost must be a number")
    return float(value)
