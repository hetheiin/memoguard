from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


MIN_SUCCESS_RATE = 0.05
MAX_SUCCESS_RATE = 0.95
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "filtered_scenarios"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def parse_args() -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Filter generated scenarios by success rate.")
    parser.add_argument("scenario_dir", type=Path, help="Directory containing scenario_<idx>.json files.")
    parser.add_argument(
        "output_dirs",
        type=Path,
        nargs="+",
        help="One or more batch output directories containing scenario summaries.",
    )
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=MIN_SUCCESS_RATE,
        help="Minimum mission_success rate to keep.",
    )
    parser.add_argument(
        "--max-success-rate",
        type=float,
        default=MAX_SUCCESS_RATE,
        help="Maximum mission_success rate to keep.",
    )
    parser.add_argument(
        "--filtered-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory where filtered scenarios are copied.",
    )

    args = parser.parse_args()
    if args.min_success_rate > args.max_success_rate:
        raise ValueError("--min-success-rate cannot be greater than --max-success-rate")
    return vars(args)


def main() -> None:
    args = parse_args()
    scenario_dir = args["scenario_dir"]
    batch_output_dirs = args["output_dirs"]
    destination_dir = args["filtered_root"] / scenario_dir.name
    destination_dir.mkdir(parents=True, exist_ok=True)

    kept_paths = filter_scenarios(
        scenario_dir=scenario_dir,
        batch_output_dirs=batch_output_dirs,
        destination_dir=destination_dir,
        min_success_rate=args["min_success_rate"],
        max_success_rate=args["max_success_rate"],
    )

    print(f"kept {len(kept_paths)} scenarios")
    print(destination_dir.relative_to(PROJECT_ROOT))


def filter_scenarios(
    scenario_dir: Path,
    batch_output_dirs: list[Path],
    destination_dir: Path,
    min_success_rate: float,
    max_success_rate: float,
) -> list[Path]:
    seen_payloads = set()
    kept_paths = []

    for scenario_path in sorted(scenario_dir.glob("scenario_*.json"), key=scenario_index):
        if not passes_all_outputs(
            scenario_path.stem,
            batch_output_dirs,
            min_success_rate,
            max_success_rate,
        ):
            continue

        scenario = read_json(scenario_path)
        payload_key = canonical_payload(scenario)
        if payload_key in seen_payloads:
            continue

        seen_payloads.add(payload_key)
        destination_path = destination_dir / scenario_path.name
        shutil.copy2(scenario_path, destination_path)
        kept_paths.append(destination_path)

    return kept_paths


def passes_all_outputs(
    scenario_name: str,
    batch_output_dirs: list[Path],
    min_success_rate: float,
    max_success_rate: float,
) -> bool:
    for batch_output_dir in batch_output_dirs:
        summary_path = batch_output_dir / scenario_name / "summary.json"
        if not summary_path.exists():
            return False
        summary = read_json(summary_path)
        success_rate = float(summary.get("metrics", {}).get("mission_success", 0.0))
        if not min_success_rate <= success_rate <= max_success_rate:
            return False
    return True


def canonical_payload(payload: dict[str, Any]) -> str:
    comparable_payload = dict(payload)
    comparable_payload.pop("id", None)
    return json.dumps(comparable_payload, sort_keys=True, separators=(",", ":"))


def scenario_index(path: Path) -> int:
    try:
        return int(path.stem.split("_")[-1])
    except ValueError:
        return sys.maxsize


if __name__ == "__main__":
    main()
