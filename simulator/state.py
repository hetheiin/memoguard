from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentState:
    target_node: str
    current_node: str
    battery: float
    localization_confidence: float
    action_sequence: list[dict[str, Any]] = field(default_factory=list)
    target_inspected: bool = False
    current_step: int = 0
