from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scenario import ScenarioGenerator
from scenario.utils import read_json, required_str, write_json


DEFAULT_MAPS_DIR = PROJECT_ROOT / "data" / "maps"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "scenarios"


def parse_args() -> dict:
    parser = argparse.ArgumentParser(description="Generate Memo Guard scenarios from a config.")
    parser.add_argument("config", type=Path, help="Path to a scenario generator config JSON file.")
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Number of scenarios to generate.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible output.")
    parser.add_argument(
        "--maps-dir",
        type=Path,
        default=DEFAULT_MAPS_DIR,
        help="Directory containing map template JSON files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root output directory. Scenarios are written under <root>/<scenario_type>.",
    )

    args = parser.parse_args()
    if args.count < 1:
        raise ValueError("--count must be at least 1")

    return vars(args)


def main() -> None:
    args = parse_args()
    config = read_json(args["config"])
    scenario_type = required_str(config, "scenario_type")
    output_dir = args["output_root"] / scenario_type
    generator = ScenarioGenerator(args["maps_dir"], random.Random(args["seed"]))

    for index in range(args["count"]):
        scenario = generator.generate(config, index)
        output_path = output_dir / f"scenario_{index}.json"
        write_json(output_path, scenario)
        try:
            print(output_path.resolve().relative_to(PROJECT_ROOT))
        except ValueError:
            print(output_path)


if __name__ == "__main__":
    main()
