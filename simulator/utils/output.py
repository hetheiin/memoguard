from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def save_run_output(
    output_dir: Path,
    scenario: Mapping[str, Any],
    simulator_config: Mapping[str, Any],
    result: Mapping[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "scenario.json", scenario)
    write_json(output_dir / "simulator_config.json", simulator_config)
    write_json(output_dir / "result.json", result)
    return output_dir


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
        file.write("\n")
