from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from policies.actions import ActionType
from simulator.agent import Agent
from simulator.metrics import compute_metrics
from simulator.state import AgentState
from simulator.utils import (
    RECOVERY_NODES,
    get_edge_between,
    get_node,
    inspection_attempt_cost,
    inspection_success_probability,
    movement_attempt_cost,
    movement_success_probability,
    save_run_output,
    settle_battery,
)
from simulator.utils.validation import lookup_number, required_mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "latest"


class Simulator:
    def __init__(
        self,
        scenario: Mapping[str, Any],
        simulator_config: Mapping[str, Any],
        policy: Any,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        seed: int | None = None,
    ) -> None:
        self._scenario = deepcopy(dict(scenario))
        self._simulator_config = deepcopy(dict(simulator_config))
        self._map_configuration = deepcopy(required_mapping(self._scenario, "map_configuration"))
        self._output_dir = output_dir
        self._policy = policy
        self._rng = random.Random(seed)
        self._agent = self._build_agent()
        self._steps: list[dict[str, Any]] = []
        self._done = False
        self._termination_reason: str | None = None
        self._visibility_recovery_node: str | None = None
        self._visibility_recovery_amount = 0.0

    @property
    def agent(self) -> Agent:
        return self._agent

    def step(self) -> dict[str, Any]:
        if self._done:
            raise ValueError("Simulation has already finished")

        action = self._agent.step(self._policy_context())
        result = self._execute_action(action)
        self._reset_visibility_recovery_after_departure(result)
        self._agent.observe(result)
        self._steps.append(result)
        self._update_done_status(result)
        return result

    def run(self, should_stop: Any | None = None) -> dict[str, Any]:
        max_steps = int(self._simulator_config.get("max_steps", 100))
        while not self._done and self._agent.state.current_step < max_steps:
            if should_stop is not None and should_stop():
                self._done = True
                self._termination_reason = "cancelled"
                break
            self.step()
            if should_stop is not None and should_stop():
                self._done = True
                self._termination_reason = "cancelled"
                break

        if not self._done:
            self._done = True
            self._termination_reason = "max_steps_reached"

        result = self._result()
        result["metrics"] = compute_metrics(result, self._simulator_config)
        self._save_output(result)
        return result

    def _build_agent(self) -> Agent:
        initial_state = required_mapping(self._scenario, "agent_initial_state")
        metadata = required_mapping(self._scenario, "metadata")

        state = AgentState(
            target_node=str(metadata["target_node"]),
            current_node=str(initial_state["start_node"]),
            battery=float(initial_state["battery"]),
            localization_confidence=float(initial_state["localization_confidence"]),
        )
        return Agent(
            policy=self._policy,
            state=state,
            memories=[],
        )

    def _policy_context(self) -> dict[str, Any]:
        return {
            "map_configuration": self._map_configuration,
            "metadata": required_mapping(self._scenario, "metadata"),
            "map_id": self._scenario.get("map_id"),
            "map_class": self._scenario.get("map_class"),
            "simulator_config": self._simulator_config,
        }

    def _execute_action(self, action: Mapping[str, Any]) -> dict[str, Any]:
        action_type = str(action["type"])
        if action_type == ActionType.WAIT_FOR_RECOVERY.value:
            return self._wait_for_recovery(action)

        to_node = action.get("to_node")
        if to_node is None:
            return self._blocked_action(action_type, action)
        if (
            action_type == ActionType.INSPECT_TARGET.value
            and to_node == self._agent.state.current_node
        ):
            return self._inspect_target(action)
        if to_node == self._agent.state.current_node:
            return self._arrived_action(action_type, action)
        return self._move(action, str(to_node))

    def _move(self, action: Mapping[str, Any], to_node: str) -> dict[str, Any]:
        state = self._agent.state
        action_type = str(action["type"])
        try:
            edge = get_edge_between(self._map_configuration, state.current_node, to_node)
        except ValueError:
            return self._blocked_action(
                action_type,
                action,
                attempted_to_node=to_node,
                failure_reason="invalid_transition",
            )
        source_node = get_node(self._map_configuration, state.current_node)
        visibility = str(source_node["visibility"])
        obstacle = str(edge["obstacle"])
        action_cost = movement_attempt_cost(
            self._simulator_config,
            float(edge["battery_cost"]),
            visibility,
            obstacle,
        )
        reasoning_cost = self._reasoning_cost_for(action)
        battery_cost = action_cost + reasoning_cost
        if state.battery - battery_cost <= 0:
            return self._failed_move_from_depleted_battery(
                action_type,
                to_node,
                action_cost,
                reasoning_cost,
                action,
            )

        success_prob = movement_success_probability(
            self._simulator_config,
            visibility,
            obstacle,
            state.localization_confidence,
            self._visibility_bonus_for_node(state.current_node),
        )
        success = self._rng.random() < success_prob
        result_node = to_node if success else state.current_node
        target_inspected = state.target_inspected

        battery_after = settle_battery(
            self._simulator_config,
            state.battery - battery_cost,
            result_node,
            action_type,
        )

        return {
            "step": state.current_step,
            "action": action_type,
            "from_node": state.current_node,
            "to_node": to_node,
            "result_node": result_node,
            "success": success,
            "success_probability": success_prob,
            "battery_before": state.battery,
            "battery_cost": battery_cost,
            "action_cost": action_cost,
            "reasoning_cost": reasoning_cost,
            "battery_after": battery_after,
            "localization_confidence_before": state.localization_confidence,
            "localization_confidence_after": self._localization_confidence_after(result_node),
            "target_inspected": target_inspected,
            **self._action_metadata(action),
        }

    def _inspect_target(self, action: Mapping[str, Any]) -> dict[str, Any]:
        state = self._agent.state
        action_type = str(action["type"])
        node = get_node(self._map_configuration, state.current_node)
        if not (
            bool(node.get("has_target", False))
            or bool(node.get("has_alt_viewpoint", False))
        ):
            return self._blocked_action(action_type, action)

        visibility = str(node["visibility"])
        action_cost = inspection_attempt_cost(
            self._simulator_config,
            self._inspection_cost(),
            visibility,
        )
        reasoning_cost = self._reasoning_cost_for(action)
        battery_cost = action_cost + reasoning_cost
        if state.battery - battery_cost <= 0:
            return self._failed_inspection_from_depleted_battery(
                action_type,
                action_cost,
                reasoning_cost,
                action,
            )

        success_prob = inspection_success_probability(
            self._simulator_config,
            visibility,
            state.localization_confidence,
            self._visibility_bonus_for_node(state.current_node),
        )
        success = self._rng.random() < success_prob
        battery_after = settle_battery(
            self._simulator_config,
            state.battery - battery_cost,
            state.current_node,
            action_type,
        )
        return {
            "step": state.current_step,
            "action": action_type,
            "from_node": state.current_node,
            "to_node": state.current_node,
            "result_node": state.current_node,
            "success": success,
            "success_probability": success_prob,
            "battery_before": state.battery,
            "battery_cost": battery_cost,
            "action_cost": action_cost,
            "reasoning_cost": reasoning_cost,
            "battery_after": battery_after,
            "localization_confidence_before": state.localization_confidence,
            "localization_confidence_after": self._localization_confidence_after(
                state.current_node
            ),
            "target_inspected": state.target_inspected or success,
            **self._action_metadata(action),
        }

    def _failed_inspection_from_depleted_battery(
        self,
        action: str,
        action_cost: float,
        reasoning_cost: float,
        action_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        state = self._agent.state
        battery_cost = action_cost + reasoning_cost
        return {
            "step": state.current_step,
            "action": action,
            "from_node": state.current_node,
            "to_node": state.current_node,
            "result_node": state.current_node,
            "success": False,
            "success_probability": 0.0,
            "battery_before": state.battery,
            "battery_cost": battery_cost,
            "action_cost": action_cost,
            "reasoning_cost": reasoning_cost,
            "battery_after": 0.0,
            "localization_confidence_before": state.localization_confidence,
            "localization_confidence_after": self._localization_confidence_after(
                state.current_node
            ),
            "target_inspected": state.target_inspected,
            "failure_reason": "insufficient_battery",
            **self._action_metadata(action_payload),
        }

    def _failed_move_from_depleted_battery(
        self,
        action: str,
        to_node: str,
        action_cost: float,
        reasoning_cost: float,
        action_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        state = self._agent.state
        battery_cost = action_cost + reasoning_cost
        return {
            "step": state.current_step,
            "action": action,
            "from_node": state.current_node,
            "to_node": to_node,
            "result_node": state.current_node,
            "success": False,
            "success_probability": 0.0,
            "battery_before": state.battery,
            "battery_cost": battery_cost,
            "action_cost": action_cost,
            "reasoning_cost": reasoning_cost,
            "battery_after": 0.0,
            "localization_confidence_before": state.localization_confidence,
            "localization_confidence_after": self._localization_confidence_after(state.current_node),
            "target_inspected": state.target_inspected,
            "failure_reason": "insufficient_battery",
            **self._action_metadata(action_payload),
        }

    def _wait_for_recovery(self, action: Mapping[str, Any]) -> dict[str, Any]:
        state = self._agent.state
        action_type = str(action["type"])
        action_cost = 0.0
        reasoning_cost = self._reasoning_cost_for(action)
        battery_cost = action_cost + reasoning_cost
        if state.battery - battery_cost <= 0:
            return {
                "step": state.current_step,
                "action": action_type,
                "from_node": state.current_node,
                "to_node": state.current_node,
                "result_node": state.current_node,
                "success": False,
                "success_probability": 0.0,
                "battery_before": state.battery,
                "battery_cost": battery_cost,
                "action_cost": action_cost,
                "reasoning_cost": reasoning_cost,
                "battery_after": 0.0,
                "localization_confidence_before": state.localization_confidence,
                "localization_confidence_after": self._localization_confidence_after(
                    state.current_node
                ),
                "target_inspected": state.target_inspected,
                "failure_reason": "insufficient_battery",
                **self._action_metadata(action),
            }

        battery_after = settle_battery(
            self._simulator_config,
            state.battery - battery_cost,
            state.current_node,
            action_type,
        )
        visibility_recovery = self._recover_visibility_at_current_node()
        return {
            "step": state.current_step,
            "action": action_type,
            "from_node": state.current_node,
            "to_node": state.current_node,
            "result_node": state.current_node,
            "success": True,
            "battery_before": state.battery,
            "battery_cost": battery_cost,
            "action_cost": action_cost,
            "reasoning_cost": reasoning_cost,
            "battery_after": battery_after,
            "localization_confidence_before": state.localization_confidence,
            "localization_confidence_after": self._localization_confidence_after(state.current_node),
            "target_inspected": state.target_inspected,
            **self._action_metadata(action),
            **visibility_recovery,
        }

    def _localization_confidence_after(self, result_node: str) -> float:
        node = get_node(self._map_configuration, result_node)
        visibility = str(node["visibility"])
        change_amount = required_mapping(
            required_mapping(self._simulator_config, "localization_confidence"),
            "change_amount",
        )
        change = lookup_number(
            change_amount,
            visibility,
            "localization_confidence.change_amount",
        )
        return min(1.0, max(0.0, self._agent.state.localization_confidence + change))

    def _inspection_cost(self) -> float:
        metadata = required_mapping(self._scenario, "metadata")
        value = metadata.get("inspect_target_cost", 2.0)
        if not isinstance(value, (int, float)):
            raise ValueError("metadata.inspect_target_cost must be a number")
        return float(value)

    def _reasoning_cost(self) -> float:
        return lookup_number(self._simulator_config, "reasoning_cost", "reasoning_cost")

    def _reasoning_cost_for(self, action: Mapping[str, Any]) -> float:
        if bool(action.get("reasoning", False)):
            return self._reasoning_cost()
        return 0.0

    @staticmethod
    def _action_metadata(action: Mapping[str, Any]) -> dict[str, Any]:
        reasoning = bool(action.get("reasoning", False))
        fields = {"reasoning": reasoning}
        if reasoning and "reasoning_details" in action:
            fields["reasoning_details"] = action["reasoning_details"]
        if "memory_reuse" in action:
            fields["memory_reuse"] = bool(action["memory_reuse"])
        if "retrieved_memory" in action:
            fields["retrieved_memory"] = Simulator._stored_retrieved_memory(
                action["retrieved_memory"]
            )
        if "memo_guard" in action:
            fields["memo_guard"] = action["memo_guard"]
        return fields

    @staticmethod
    def _stored_retrieved_memory(retrieved_memory: Any) -> Any:
        if not isinstance(retrieved_memory, Mapping):
            return retrieved_memory
        payload = dict(retrieved_memory)
        payload.pop("map_configuration", None)
        return payload

    def _recover_visibility_at_current_node(self) -> dict[str, Any]:
        state = self._agent.state
        recovery_amount = lookup_number(
            required_mapping(self._simulator_config, "visibility"),
            "recovery_amount",
            "visibility",
        )
        if self._visibility_recovery_node != state.current_node:
            self._visibility_recovery_node = state.current_node
            self._visibility_recovery_amount = 0.0
        self._visibility_recovery_amount = min(
            1.0,
            self._visibility_recovery_amount + recovery_amount,
        )
        return {
            "visibility_recovery_amount": recovery_amount,
            "visibility_recovery_total": self._visibility_recovery_amount,
        }

    def _visibility_bonus_for_node(self, node_id: str) -> float:
        if node_id != self._visibility_recovery_node:
            return 0.0
        return self._visibility_recovery_amount

    def _reset_visibility_recovery_after_departure(self, result: Mapping[str, Any]) -> None:
        if result["result_node"] != result["from_node"]:
            self._visibility_recovery_node = None
            self._visibility_recovery_amount = 0.0

    def _blocked_action(
        self,
        action: str,
        action_payload: Mapping[str, Any],
        attempted_to_node: str | None = None,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        state = self._agent.state
        action_cost = 0.0
        reasoning_cost = self._reasoning_cost_for(action_payload)
        battery_cost = action_cost + reasoning_cost
        if state.battery - battery_cost <= 0:
            battery_after = 0.0
            failure_reason = "insufficient_battery"
        else:
            battery_after = settle_battery(
                self._simulator_config,
                state.battery - battery_cost,
                state.current_node,
                action,
            )
            failure_reason = None
        result = {
            "step": state.current_step,
            "action": action,
            "from_node": state.current_node,
            "to_node": None,
            "attempted_to_node": attempted_to_node,
            "result_node": state.current_node,
            "success": False,
            "battery_before": state.battery,
            "battery_cost": battery_cost,
            "action_cost": action_cost,
            "reasoning_cost": reasoning_cost,
            "battery_after": battery_after,
            "localization_confidence_before": state.localization_confidence,
            "localization_confidence_after": self._localization_confidence_after(state.current_node),
            "target_inspected": state.target_inspected,
            **self._action_metadata(action_payload),
        }
        if failure_reason is not None:
            result["failure_reason"] = failure_reason
        return result

    def _arrived_action(self, action: str, action_payload: Mapping[str, Any]) -> dict[str, Any]:
        state = self._agent.state
        action_cost = 0.0
        reasoning_cost = self._reasoning_cost_for(action_payload)
        battery_cost = action_cost + reasoning_cost
        if state.battery - battery_cost <= 0:
            battery_after = 0.0
            success = False
            failure_reason = "insufficient_battery"
        else:
            battery_after = settle_battery(
                self._simulator_config,
                state.battery - battery_cost,
                state.current_node,
                action,
            )
            success = True
            failure_reason = None
        result = {
            "step": state.current_step,
            "action": action,
            "from_node": state.current_node,
            "to_node": state.current_node,
            "result_node": state.current_node,
            "success": success,
            "battery_before": state.battery,
            "battery_cost": battery_cost,
            "action_cost": action_cost,
            "reasoning_cost": reasoning_cost,
            "battery_after": battery_after,
            "localization_confidence_before": state.localization_confidence,
            "localization_confidence_after": self._localization_confidence_after(state.current_node),
            "target_inspected": state.target_inspected,
            **self._action_metadata(action_payload),
        }
        if failure_reason is not None:
            result["failure_reason"] = failure_reason
        return result

    def _update_done_status(self, result: Mapping[str, Any]) -> None:
        state = self._agent.state
        if state.battery <= 0:
            self._done = True
            self._termination_reason = "battery_depleted"
        elif state.target_inspected and state.current_node in RECOVERY_NODES:
            self._done = True
            self._termination_reason = "mission_completed"
        elif self._agent.is_aborting and state.current_node in RECOVERY_NODES:
            self._done = True
            self._termination_reason = "mission_aborted"

    def _result(self) -> dict[str, Any]:
        reasoning_cost = sum(float(step.get("reasoning_cost", 0.0)) for step in self._steps)
        total_cost = sum(float(step.get("battery_cost", 0.0)) for step in self._steps)
        return {
            "scenario_id": self._scenario.get("id"),
            "initial_state": asdict(self._agent.initial_state),
            "steps": self._steps,
            "final_state": asdict(self._agent.state),
            "termination_reason": self._termination_reason,
            "reasoning_cost": reasoning_cost,
            "total_cost": total_cost,
            "metrics": {},
        }

    def _save_output(self, result: Mapping[str, Any]) -> None:
        save_run_output(self._output_dir, self._scenario, self._simulator_config, result)
