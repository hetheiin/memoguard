from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scenario import TrapGenerator
from scenario.utils import read_json, write_json


DEFAULT_CONFIG_DIR = PROJECT_ROOT / "configs" / "trap_generator"
DEFAULT_SCENARIO_ROOT = PROJECT_ROOT / "data" / "filtered_scenarios"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "trap_scenarios"


def parse_args() -> dict:
    parser = argparse.ArgumentParser(description="Generate trap scenarios from existing scenarios.")
    parser.add_argument(
        "scenario_root",
        type=Path,
        nargs="?",
        default=DEFAULT_SCENARIO_ROOT,
        help="Root directory containing scenario folders that match trap config names.",
    )
    parser.add_argument(
        "output_root",
        type=Path,
        nargs="?",
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory where generated trap scenarios are written.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="Directory containing trap generator config JSON files.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed.")
    return vars(parser.parse_args())


def main() -> None:
    args = parse_args()
    generator = TrapGenerator(random.Random(args["seed"]))
    written = 0

    for config_path in sorted(args["config_dir"].glob("*.json")):
        config = read_json(config_path)
        scenario_dir = args["scenario_root"] / config_path.stem
        if not scenario_dir.exists():
            raise ValueError(f"Scenario folder not found for config {config_path.name}: {scenario_dir}")

        for scenario_path in sorted(scenario_dir.rglob("scenario_*.json")):
            scenario = read_json(scenario_path)
            relative_path = scenario_path.relative_to(scenario_dir)
            trapped_scenarios = generator.generate(scenario, config)
            for trap_type, trapped in trapped_scenarios.items():
                output_path = (
                    args["output_root"]
                    / config_path.stem
                    / trap_type
                    / relative_path
                )
                write_json(output_path, trapped)
                written += 1

    print(f"wrote {written} trap scenarios to {relative_to_project(args['output_root'])}")


def relative_to_project(path: Path) -> Path:
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(PROJECT_ROOT)
    except ValueError:
        return resolved_path


if __name__ == "__main__":
    main()
