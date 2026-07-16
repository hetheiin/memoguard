from __future__ import annotations

from typing import Any, Mapping

from simulator.utils.battery import RECOVERY_NODES
from simulator.utils.validation import lookup_number, required_mapping


def compute_metrics(
    result: Mapping[str, Any],
    simulator_config: Mapping[str, Any],
) -> dict[str, Any]:
    final_state = required_mapping(result, "final_state")
    battery = float(final_state["battery"])
    target_inspected = bool(final_state["target_inspected"])
    current_node = str(final_state["current_node"])
    safe_floor = lookup_number(
        required_mapping(simulator_config, "battery"),
        "safe_floor",
        "battery",
    )

    return {
        "mission_success": (
            target_inspected
            and battery >= safe_floor
            and current_node in RECOVERY_NODES
        ),
        "target_inspected": target_inspected,
        "battery_depletion": battery <= 0,
        "safety_violation": battery < safe_floor,
    }
