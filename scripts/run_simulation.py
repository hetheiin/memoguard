from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from simulator import Planner, Simulator
from policies import (
    AlwaysReasoningPolicy,
    InspectAlternateViewpointPolicy,
    MemoGuardPolicy,
    OraclePolicy,
    ThresholdReusePolicy,
    Top1ReusePolicy,
    TopKCountReusePolicy,
)
from memory import MemoryRetriever


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def parse_args() -> dict:
    parser = argparse.ArgumentParser(description="Run a Memo Guard simulation.")
    parser.add_argument("scenario", type=Path, help="Path to a scenario JSON file.")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs" / "simulator" / "config.json",
        help="Path to a simulator config JSON file.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed.")
    parser.add_argument(
        "--policy",
        choices=[
            "inspect_alternate_viewpoint",
            "oracle",
            "always_reasoning",
            "top1_reuse",
            "threshold_reuse",
            "topk_count_reuse",
            "memo_guard",
        ],
        default="memo_guard",
        help="Policy to use for the simulation.",
    )
    parser.add_argument(
        "--memory-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "memories" / "memories.json",
        help="Path to memory JSON file for memory-based policies.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "outputs",
        help="Directory where timestamped run outputs are written.",
    )
    return vars(parser.parse_args())


def main() -> None:
    args = parse_args()
    simulator_config = read_json(args["config"])
    result = Simulator(
        scenario=read_json(args["scenario"]),
        simulator_config=simulator_config,
        policy=create_policy(args["policy"], simulator_config, args["memory_path"]),
        output_dir=args["output_root"] / datetime.now().strftime("%Y%m%d_%H%M%S"),
        seed=args["seed"],
    ).run()
    print(result["termination_reason"])


def create_policy(policy_name: str, simulator_config: dict, memory_path: Path):
    planner = Planner(simulator_config)
    if policy_name == "inspect_alternate_viewpoint":
        return InspectAlternateViewpointPolicy(planner, simulator_config)
    if policy_name == "oracle":
        return OraclePolicy(planner, simulator_config)
    if policy_name == "always_reasoning":
        return AlwaysReasoningPolicy(planner, simulator_config)
    if policy_name in {
        "top1_reuse",
        "threshold_reuse",
        "topk_count_reuse",
        "memo_guard",
    }:
        retrieval_config = memory_retrieval_config(simulator_config)
        retriever = MemoryRetriever.from_file(
            memory_path,
            retrieval_config.get("weights", {}),
            max_samples=optional_int(retrieval_config.get("max_samples")),
            seed=optional_int(retrieval_config.get("seed")),
        )
        if policy_name == "threshold_reuse":
            return ThresholdReusePolicy(planner, simulator_config, retriever)
        if policy_name == "topk_count_reuse":
            return TopKCountReusePolicy(planner, simulator_config, retriever)
        if policy_name == "memo_guard":
            return MemoGuardPolicy(planner, simulator_config, retriever)
        return Top1ReusePolicy(planner, simulator_config, retriever)
    raise ValueError(f"Unknown policy: {policy_name}")


def memory_retrieval_config(simulator_config: Mapping[str, Any]) -> Mapping[str, Any]:
    value = simulator_config.get("memory_retrieval", {})
    if not isinstance(value, Mapping):
        raise ValueError("memory_retrieval must be an object")
    return value


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


if __name__ == "__main__":
    main()
