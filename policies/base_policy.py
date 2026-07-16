from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from policies.actions import ActionType
from simulator.utils import RECOVERY_NODES, has_node
from simulator.utils.validation import lookup_number, required_mapping

if TYPE_CHECKING:
    from memory import MemoryRetriever
    from simulator.planner import Planner
    from simulator.state import AgentState


class BasePolicy:
    def __init__(
        self,
        planner: Planner,
        simulator_config: Mapping[str, Any],
        memory_retriever: MemoryRetriever | None = None,
    ) -> None:
        self._planner = planner
        self._simulator_config = simulator_config
        self._memory_retriever = memory_retriever
        self._emergency_floor = lookup_number(
            required_mapping(simulator_config, "battery"),
            "emergency_floor",
            "battery",
        )

    def decide(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self.should_abort(agent_state):
            return self._abort_action(agent_state, context)
        return self._decide(agent_state, context)

    def should_abort(self, agent_state: AgentState) -> bool:
        return self._must_abort(agent_state)

    def _decide(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _must_abort(self, agent_state: AgentState) -> bool:
        return (
            agent_state.battery < self._emergency_floor
            or any(
                record.get("action") == ActionType.ABORT_MISSION.value
                for record in agent_state.action_sequence
            )
        )

    def _abort_action(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        plan = self._plan_to_nearest_recovery_node(agent_state, context)
        return self._action_from_plan(ActionType.ABORT_MISSION, agent_state, plan)

    def _follow_planner_action(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        plan = self._plan_to_goal(agent_state, context, agent_state.target_node)
        if not plan["reachable"]:
            return self._abort_action(agent_state, context)
        return self._action_from_plan(ActionType.FOLLOW_PLANNER, agent_state, plan)

    def _inspect_target_action(
        self,
        agent_state: AgentState,
        plan: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": ActionType.INSPECT_TARGET.value,
            "to_node": agent_state.current_node,
            "plan": plan or {
                "path": [agent_state.current_node],
                "expected_cost": 0.0,
                "steps": 1,
                "reachable": True,
                "goal_action": ActionType.INSPECT_TARGET.value,
            },
        }

    def _alternate_viewpoint_action(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if agent_state.target_inspected:
            return None

        alternate_viewpoint = self._alternate_viewpoint(context)
        if alternate_viewpoint is None:
            return None

        plan = self._plan_to_goal(agent_state, context, alternate_viewpoint)
        if not plan["reachable"]:
            return None
        action = self._action_from_plan(
            ActionType.INSPECT_ALTERNATE_VIEWPOINT,
            agent_state,
            plan,
        )
        return action

    def _return_to_safe_waypoint_action(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        map_configuration = required_mapping(context, "map_configuration")
        if not has_node(map_configuration, "Safe_WP"):
            return self._abort_action(agent_state, context)

        plan = self._plan_to_goal(agent_state, context, "Safe_WP")
        if not plan["reachable"]:
            return self._abort_action(agent_state, context)
        return self._action_from_plan(
            ActionType.RETURN_TO_SAFE_WAYPOINT,
            agent_state,
            plan,
        )

    def _action_from_plan(
        self,
        action_type: ActionType,
        agent_state: AgentState,
        plan: Mapping[str, Any],
    ) -> dict[str, Any]:
        next_node = self._next_node(plan, agent_state.current_node)
        if next_node is None:
            return {"type": action_type.value, "to_node": None, "plan": plan}
        if (
            next_node == agent_state.current_node
            and action_type == ActionType.INSPECT_ALTERNATE_VIEWPOINT
        ):
            return self._inspect_target_action(agent_state, plan)
        if (
            next_node == agent_state.current_node
            and action_type == ActionType.FOLLOW_PLANNER
            and not agent_state.target_inspected
            and agent_state.current_node == agent_state.target_node
        ):
            return self._inspect_target_action(agent_state, plan)
        if next_node == agent_state.current_node and action_type != ActionType.ABORT_MISSION:
            return {
                "type": ActionType.WAIT_FOR_RECOVERY.value,
                "to_node": agent_state.current_node,
                "plan": plan,
            }
        return {"type": action_type.value, "to_node": next_node, "plan": plan}

    def _action_from_reasoning(
        self,
        reasoning: Mapping[str, Any],
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        decision = reasoning["decision"]

        if decision == "return_to_nearest_recovery":
            return self._return_to_safe_waypoint_action(agent_state, context)

        if decision == "abort":
            return self._abort_action(agent_state, context)

        if decision == "wait_for_recovery":
            return {
                "type": ActionType.WAIT_FOR_RECOVERY.value,
                "to_node": agent_state.current_node,
                "plan": reasoning["plan"],
                "reasoning": reasoning,
            }

        if decision == "return_to_safe_waypoint":
            return self._return_to_safe_waypoint_action(agent_state, context)

        if decision == "execute_inspection_plan":
            return self._action_from_plan(
                reasoning["action_type"],
                agent_state,
                reasoning["plan"],
            )

        raise ValueError(f"Unknown reasoning decision: {decision}")

    def _plan_to_nearest_recovery_node(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._plan_to_goal(
            agent_state,
            context,
            self._nearest_recovery_node(agent_state, context),
        )

    def _nearest_recovery_node(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> str:
        map_configuration = required_mapping(context, "map_configuration")
        plans = [
            self._plan_to_goal(agent_state, context, candidate)
            for candidate in RECOVERY_NODES
            if has_node(map_configuration, candidate)
        ]
        reachable_plans = [plan for plan in plans if plan["reachable"]]
        if not reachable_plans:
            return "Base"
        return min(reachable_plans, key=lambda plan: (plan["expected_cost"], plan["steps"]))["path"][-1]

    def _plan_to_goal(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
        goal_node: str,
    ) -> Mapping[str, Any]:
        return self._planner.plan(
            required_mapping(context, "map_configuration"),
            agent_state.current_node,
            goal_node,
            agent_state.localization_confidence,
            self._inspection_cost(context),
        )

    def _plan_between(
        self,
        context: Mapping[str, Any],
        start_node: str,
        goal_node: str,
        localization_confidence: float,
    ) -> Mapping[str, Any]:
        return self._planner.plan(
            required_mapping(context, "map_configuration"),
            start_node,
            goal_node,
            localization_confidence,
            self._inspection_cost(context),
        )

    def _nearest_recovery_node_from(
        self,
        context: Mapping[str, Any],
        start_node: str,
        localization_confidence: float,
    ) -> str:
        map_configuration = required_mapping(context, "map_configuration")
        plans = [
            self._plan_between(context, start_node, candidate, localization_confidence)
            for candidate in RECOVERY_NODES
            if has_node(map_configuration, candidate)
        ]
        reachable_plans = [plan for plan in plans if plan["reachable"]]
        if not reachable_plans:
            return "Base"
        return min(reachable_plans, key=lambda plan: (plan["expected_cost"], plan["steps"]))["path"][-1]

    @staticmethod
    def _alternate_viewpoint(context: Mapping[str, Any]) -> str | None:
        metadata = required_mapping(context, "metadata")
        viewpoints = metadata.get("alt_viewpoints", [])
        if not isinstance(viewpoints, list) or not viewpoints:
            return None
        return str(viewpoints[0])

    @staticmethod
    def _inspection_cost(context: Mapping[str, Any]) -> float:
        metadata = required_mapping(context, "metadata")
        value = metadata.get("inspect_target_cost", 2.0)
        if not isinstance(value, (int, float)):
            raise ValueError("metadata.inspect_target_cost must be a number")
        return float(value)

    @staticmethod
    def _next_node(plan: Mapping[str, Any], current_node: str) -> str | None:
        if not plan["reachable"]:
            return None

        path = plan["path"]
        if len(path) == 0 or current_node not in path:
            return None

        current_index = path.index(current_node)
        if current_index == len(path) - 1:
            return current_node
        return path[current_index + 1]
