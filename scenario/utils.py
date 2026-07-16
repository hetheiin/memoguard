from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Mapping, Sequence


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
        file.write("\n")


def load_map(map_id: str, maps_dir: Path) -> dict[str, Any]:
    direct_path = maps_dir / f"{map_id}.json"
    if direct_path.exists():
        return read_json(direct_path)

    normalized_id = normalize_id(map_id)
    for path in maps_dir.glob("*.json"):
        if normalize_id(path.stem) == normalized_id:
            return read_json(path)

    raise ValueError(f"Map '{map_id}' was not found in {maps_dir}")


def normalize_id(value: str) -> str:
    return value.lower().replace("-", "_")


def choice(rng: random.Random, values: Sequence[Any], field_name: str) -> Any:
    if not values:
        raise ValueError(f"{field_name} must contain at least one value")
    return rng.choice(list(values))


def weighted_choice(rng: random.Random, weights: Mapping[str, float], field_name: str) -> str:
    if not weights:
        raise ValueError(f"{field_name} must contain at least one weighted option")

    labels = list(weights.keys())
    values = [float(weights[label]) for label in labels]
    if any(value < 0 for value in values):
        raise ValueError(f"{field_name} cannot contain negative probabilities")
    if sum(values) <= 0:
        raise ValueError(f"{field_name} must have a positive total probability")

    return rng.choices(labels, weights=values, k=1)[0]


def required_mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def optional_mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = source.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def required_sequence(source: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = source.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{key} must be an array")
    return value


def required_str(source: Mapping[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def optional_bool(source: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = source.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def optional_int(source: Mapping[str, Any], key: str, default: int) -> int:
    value = source.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def optional_number(source: Mapping[str, Any], key: str, default: float) -> float:
    value = source.get(key, default)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)
