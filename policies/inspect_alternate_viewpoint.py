from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from policies.base_policy import BasePolicy

if TYPE_CHECKING:
    from simulator.state import AgentState


class InspectAlternateViewpointPolicy(BasePolicy):
    def _decide(
        self,
        agent_state: AgentState,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        if agent_state.target_inspected:
            return self._abort_action(agent_state, context)

        alternate_action = self._alternate_viewpoint_action(agent_state, context)
        if alternate_action is not None:
            return alternate_action
        return self._follow_planner_action(agent_state, context)
