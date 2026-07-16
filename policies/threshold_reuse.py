from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from policies.top1_reuse import Top1ReusePolicy
from policies.utils import reason_next_action

if TYPE_CHECKING:
    from simulator.state import AgentState


SIMILARITY_THRESHOLD = 0.8


class ThresholdReusePolicy(Top1ReusePolicy):
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
            top_k=1,
            excluded_actions=self._excluded_actions(agent_state),
        )
        if not retrieved or retrieved[0].score < SIMILARITY_THRESHOLD:
            return self._reasoning_action(agent_state, context)

        return self._action_from_retrieved_memory(retrieved[0], agent_state, context)

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
