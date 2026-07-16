from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from policies.actions import ActionType
from simulator.state import AgentState


class Agent:
    def __init__(
        self,
        policy: Any,
        state: AgentState,
        memories: list[dict[str, Any]] | None = None,
    ) -> None:
        self._policy = policy
        self._initial_state = state
        self._state = state
        self._memories = memories or []
        self._aborting = False

    @property
    def initial_state(self) -> AgentState:
        return self._initial_state

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def memories(self) -> list[dict[str, Any]]:
        return self._memories

    @property
    def is_aborting(self) -> bool:
        return self._aborting or self._has_aborted()

    def step(self, context: Mapping[str, Any]) -> dict[str, Any]:
        action = self._policy.decide(self._state, context)
        if action["type"] == ActionType.ABORT_MISSION.value:
            self._aborting = True
        return action

    def observe(self, result: Mapping[str, Any]) -> None:
        if result["action"] == ActionType.ABORT_MISSION.value:
            self._aborting = True

        action_record = {
            "from_node": result["from_node"],
            "action": result["action"],
            "result_node": result["result_node"],
            "success": result["success"],
            "reasoning": bool(result.get("reasoning", False)),
            "memory_reuse": bool(result.get("memory_reuse", False)),
        }
        if "failure_reason" in result:
            action_record["failure_reason"] = result["failure_reason"]
        self._state = replace(
            self._state,
            current_node=result["result_node"],
            battery=result["battery_after"],
            localization_confidence=result.get(
                "localization_confidence_after",
                self._state.localization_confidence,
            ),
            action_sequence=[*self._state.action_sequence, action_record],
            target_inspected=result.get("target_inspected", self._state.target_inspected),
            current_step=self._state.current_step + 1,
        )

    def _has_aborted(self) -> bool:
        return any(
            record.get("action") == ActionType.ABORT_MISSION.value
            for record in self._state.action_sequence
        )
