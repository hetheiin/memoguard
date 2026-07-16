from __future__ import annotations

from typing import Any, Mapping

from simulator.utils.validation import lookup_number, required_mapping


RECOVERY_NODES = {"Base", "Safe_WP"}


def settle_battery(
    simulator_config: Mapping[str, Any],
    battery: float,
    result_node: str,
    action: str | None = None,
) -> float:
    battery_config = required_mapping(simulator_config, "battery")
    if action == "wait_for_recovery" and result_node == "Safe_WP":
        battery += lookup_number(battery_config, "recovery_amount", "battery")
    elif result_node not in RECOVERY_NODES:
        battery -= lookup_number(battery_config, "step_reduction", "battery")
    return max(0.0, battery)
