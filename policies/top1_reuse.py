from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from policies.actions import ActionType
from policies.base_policy import BasePolicy
from simulator.utils import get_node
from simulator.utils.validation import required_mapping

if TYPE_CHECKING:
    from simulator.state import AgentState


class Top1ReusePolicy(BasePolicy):
    def _decide(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        inspection_action = self._inspection_action_at_current_node(agent_state, context)
        if inspection_action is not None:
            return inspection_action

        if self._memory_retriever is None:
            return self._follow_planner_action(agent_state, context)

        retrieved = self._memory_retriever.retrieve(
            agent_state,
            context,
            top_k=1,
            excluded_actions=self._excluded_actions(agent_state),
        )
        if not retrieved:
            if agent_state.target_inspected:
                return self._abort_action(agent_state, context)
            return self._follow_planner_action(agent_state, context)

        retrieved_memory = retrieved[0]
        return self._action_from_retrieved_memory(retrieved_memory, agent_state, context)

    def _action_from_retrieved_memory(
        self,
        retrieved_memory,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        memory = retrieved_memory.memory
        if memory.action == ActionType.ABORT_MISSION.value:
            return self._abort_action(agent_state, context)

        return {
            "type": memory.action,
            "to_node": self._to_node_for_memory(memory, agent_state),
            "retrieved_memory": retrieved_memory.to_dict(),
            "memory_reuse": True,
        }

    @staticmethod
    def _to_node_for_memory(memory, agent_state: AgentState) -> str | None:
        if memory.action in {
            ActionType.INSPECT_TARGET.value,
            ActionType.WAIT_FOR_RECOVERY.value,
        }:
            return agent_state.current_node
        return memory.to_node

    @staticmethod
    def _excluded_actions(agent_state: AgentState) -> set[str]:
        if agent_state.target_inspected:
            return {
                ActionType.FOLLOW_PLANNER.value,
                ActionType.INSPECT_ALTERNATE_VIEWPOINT.value,
                ActionType.INSPECT_TARGET.value,
            }
        return {ActionType.ABORT_MISSION.value}

    def _inspection_action_at_current_node(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if agent_state.target_inspected:
            return None

        node = get_node(
            required_mapping(context, "map_configuration"),
            agent_state.current_node,
        )
        if bool(node.get("has_target", False)):
            return self._inspect_target_action(agent_state)
        if bool(node.get("has_alt_viewpoint", False)):
            return self._inspect_target_action(agent_state)
        return None
