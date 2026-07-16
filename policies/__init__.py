from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "ActionType": ("policies.actions", "ActionType"),
    "AlwaysReasoningPolicy": ("policies.always_reasoning", "AlwaysReasoningPolicy"),
    "BasePolicy": ("policies.base_policy", "BasePolicy"),
    "InspectAlternateViewpointPolicy": (
        "policies.inspect_alternate_viewpoint",
        "InspectAlternateViewpointPolicy",
    ),
    "MemoGuardPolicy": ("policies.memo_guard", "MemoGuardPolicy"),
    "OraclePolicy": ("policies.oracle", "OraclePolicy"),
    "ThresholdReusePolicy": ("policies.threshold_reuse", "ThresholdReusePolicy"),
    "Top1ReusePolicy": ("policies.top1_reuse", "Top1ReusePolicy"),
    "TopKCountReusePolicy": ("policies.topk_count_reuse", "TopKCountReusePolicy"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module 'policies' has no attribute {name!r}")
    module_name, attribute_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
