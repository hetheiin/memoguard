from __future__ import annotations

from typing import Any, Mapping


def required_mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def required_list(source: Mapping[str, Any], key: str) -> list[Any]:
    value = source.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def required_str(source: Mapping[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def required_number(source: Mapping[str, Any], key: str) -> float:
    value = source.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


def lookup_number(source: Mapping[str, Any], key: str, field_name: str) -> float:
    if key not in source:
        raise ValueError(f"{field_name} does not define '{key}'")
    value = source[key]
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field_name}.{key} must be a number")
    return float(value)
