from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from policies.top1_reuse import Top1ReusePolicy

if TYPE_CHECKING:
    from memory import RetrievedMemory
    from simulator.state import AgentState


TOP_K = 10


class TopKCountReusePolicy(Top1ReusePolicy):
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
            top_k=TOP_K,
            excluded_actions=self._excluded_actions(agent_state),
        )
        if not retrieved:
            if agent_state.target_inspected:
                return self._abort_action(agent_state, context)
            return self._follow_planner_action(agent_state, context)

        selected = max(
            enumerate(retrieved),
            key=lambda item: (memory_attempt_count(item[1]), -item[0]),
        )[1]
        return self._action_from_retrieved_memory(selected, agent_state, context)


def memory_attempt_count(retrieved_memory: RetrievedMemory) -> int:
    statistics = retrieved_memory.memory.outcome_statistics
    return statistics.success_count + statistics.failure_count
