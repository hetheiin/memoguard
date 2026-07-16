from __future__ import annotations

import math
from typing import Any, Mapping

from simulator.utils.validation import lookup_number, required_mapping


def expected_movement_cost(
    simulator_config: Mapping[str, Any],
    base_cost: float,
    visibility: str,
    obstacle: str,
    localization_confidence: float | None = None,
    visibility_success_bonus: float = 0.0,
) -> float:
    visibility_config = required_mapping(simulator_config, "visibility")
    obstacle_config = required_mapping(simulator_config, "obstacle")

    visibility_success = visibility_success_probability(
        simulator_config,
        visibility,
        visibility_success_bonus,
    )
    obstacle_success = lookup_number(
        required_mapping(obstacle_config, "movement_success"),
        obstacle,
        "obstacle.movement_success",
    )
    localization_success = localization_movement_success(
        simulator_config,
        localization_confidence,
    )

    success_prob = visibility_success * obstacle_success * localization_success
    if success_prob <= 0:
        return math.inf

    adjusted_cost = (
        base_cost
        * lookup_number(
            required_mapping(visibility_config, "cost_multiplier"),
            visibility,
            "visibility.cost_multiplier",
        )
        * lookup_number(
            required_mapping(obstacle_config, "cost_multiplier"),
            obstacle,
            "obstacle.cost_multiplier",
        )
    )
    return adjusted_cost / success_prob


def expected_inspection_cost(
    simulator_config: Mapping[str, Any],
    base_cost: float,
    visibility: str,
    localization_confidence: float | None = None,
    visibility_success_bonus: float = 0.0,
) -> float:
    success_prob = inspection_success_probability(
        simulator_config,
        visibility,
        localization_confidence,
        visibility_success_bonus,
    )
    if success_prob <= 0:
        return math.inf
    return inspection_attempt_cost(simulator_config, base_cost, visibility) / success_prob


def inspection_success_probability(
    simulator_config: Mapping[str, Any],
    visibility: str,
    localization_confidence: float | None = None,
    visibility_success_bonus: float = 0.0,
) -> float:
    return (
        visibility_success_probability(
            simulator_config,
            visibility,
            visibility_success_bonus,
        )
        * localization_movement_success(simulator_config, localization_confidence)
    )


def inspection_attempt_cost(
    simulator_config: Mapping[str, Any],
    base_cost: float,
    visibility: str,
) -> float:
    visibility_config = required_mapping(simulator_config, "visibility")
    return (
        base_cost
        * lookup_number(
            required_mapping(visibility_config, "cost_multiplier"),
            visibility,
            "visibility.cost_multiplier",
        )
    )


def movement_success_probability(
    simulator_config: Mapping[str, Any],
    visibility: str,
    obstacle: str,
    localization_confidence: float | None = None,
    visibility_success_bonus: float = 0.0,
) -> float:
    obstacle_config = required_mapping(simulator_config, "obstacle")

    return (
        visibility_success_probability(
            simulator_config,
            visibility,
            visibility_success_bonus,
        )
        * lookup_number(
            required_mapping(obstacle_config, "movement_success"),
            obstacle,
            "obstacle.movement_success",
        )
        * localization_movement_success(simulator_config, localization_confidence)
    )


def visibility_success_probability(
    simulator_config: Mapping[str, Any],
    visibility: str,
    visibility_success_bonus: float = 0.0,
) -> float:
    visibility_config = required_mapping(simulator_config, "visibility")
    base_success = lookup_number(
        required_mapping(visibility_config, "movement_success"),
        visibility,
        "visibility.movement_success",
    )
    return min(1.0, max(0.0, base_success + visibility_success_bonus))


def movement_attempt_cost(
    simulator_config: Mapping[str, Any],
    base_cost: float,
    visibility: str,
    obstacle: str,
) -> float:
    visibility_config = required_mapping(simulator_config, "visibility")
    obstacle_config = required_mapping(simulator_config, "obstacle")

    return (
        base_cost
        * lookup_number(
            required_mapping(visibility_config, "cost_multiplier"),
            visibility,
            "visibility.cost_multiplier",
        )
        * lookup_number(
            required_mapping(obstacle_config, "cost_multiplier"),
            obstacle,
            "obstacle.cost_multiplier",
        )
    )


def localization_movement_success(
    simulator_config: Mapping[str, Any],
    localization_confidence: float | None,
) -> float:
    if localization_confidence is None:
        return 1.0

    localization_config = required_mapping(simulator_config, "localization_confidence")
    ranges = required_mapping(localization_config, "ranges")
    movement_success = required_mapping(localization_config, "movement_success")

    for level, bounds in ranges.items():
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("localization_confidence.ranges values must be [min, max]")
        lower = float(bounds[0])
        upper = float(bounds[1])
        if lower <= localization_confidence <= upper:
            return lookup_number(
                movement_success,
                str(level),
                "localization_confidence.movement_success",
            )

    raise ValueError(f"localization_confidence is out of configured ranges: {localization_confidence}")
