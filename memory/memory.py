from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class OutcomeStatistics:
    success_count: int = 0
    failure_count: int = 0

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OutcomeStatistics":
        return cls(
            success_count=int(payload.get("success_count", 0)),
            failure_count=int(payload.get("failure_count", 0)),
        )

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def update(self, success: bool) -> None:
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate,
        }


@dataclass
class Memory:
    retrieval_features: dict[str, Any]
    action: str
    reasoning: bool
    to_node: str | None
    outcome_statistics: OutcomeStatistics
    scenario_id: str
    instruction: str
    scenario_metadata: dict[str, Any]
    map_id: str
    map_class: str | None
    map_configuration: dict[str, Any] | None = None
    path_risk_profile: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Memory":
        path_risk_profile = payload.get("path_risk_profile", payload.get("map_role_profile"))
        return cls(
            retrieval_features=dict(payload["retrieval_features"]),
            action=str(payload["action"]),
            reasoning=bool(payload.get("reasoning", False)),
            to_node=payload.get("to_node"),
            outcome_statistics=OutcomeStatistics.from_dict(
                payload.get("outcome_statistics", {})
            ),
            scenario_id=str(payload["scenario_id"]),
            instruction=str(payload.get("instruction", "")),
            scenario_metadata=dict(payload.get("scenario_metadata", {})),
            map_id=str(payload.get("map_id", "")),
            map_class=payload.get("map_class"),
            map_configuration=(
                dict(payload["map_configuration"])
                if isinstance(payload.get("map_configuration"), Mapping)
                else None
            ),
            path_risk_profile=(
                dict(path_risk_profile)
                if isinstance(path_risk_profile, Mapping)
                else None
            ),
        )

    def update(self, success: bool, to_node: str | None) -> None:
        self.outcome_statistics.update(success)
        if self.to_node is None and to_node is not None:
            self.to_node = to_node

    def key(self) -> tuple[Any, ...]:
        return memory_key(self.scenario_id, self.retrieval_features, self.action)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "retrieval_features": self.retrieval_features,
            "action": self.action,
            "reasoning": self.reasoning,
            "to_node": self.to_node,
            "outcome_statistics": self.outcome_statistics.to_dict(),
            "scenario_id": self.scenario_id,
            "instruction": self.instruction,
            "scenario_metadata": self.scenario_metadata,
            "map_id": self.map_id,
            "map_class": self.map_class,
        }
        if self.path_risk_profile is not None:
            payload["path_risk_profile"] = self.path_risk_profile
        return payload


def memory_key(
    scenario_id: str,
    retrieval_features: Mapping[str, Any],
    action: str,
) -> tuple[Any, ...]:
    battery_range = retrieval_features.get("battery_range", retrieval_features.get("battery"))
    if isinstance(battery_range, list):
        battery_range = tuple(battery_range)
    return (
        scenario_id,
        retrieval_features.get("node"),
        retrieval_features.get("visibility"),
        retrieval_features.get("obstacle"),
        retrieval_features.get("localization_confidence_level"),
        battery_range,
        action,
    )
