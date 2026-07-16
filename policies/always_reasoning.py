from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

from policies.base_policy import BasePolicy
from policies.utils import reason_next_action

if TYPE_CHECKING:
    from simulator.state import AgentState


class AlwaysReasoningPolicy(BasePolicy):
    def _decide(
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
