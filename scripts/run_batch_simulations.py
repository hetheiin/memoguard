from __future__ import annotations

import argparse
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any, Mapping

try:
    from tqdm import tqdm
except ModuleNotFoundError:
    def tqdm(iterable, **_: Any):
        return iterable

MIN_SUCCESS_RATE = 0.05
MAX_SUCCESS_RATE = 0.95
MEMORY_BASED_POLICIES = {
    "top1_reuse",
    "threshold_reuse",
    "topk_count_reuse",
    "memo_guard",
}

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
from simulator.utils.output import write_json


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def parse_args() -> dict:
    parser = argparse.ArgumentParser(description="Run batch Memo Guard simulations.")
    parser.add_argument("scenario_root", type=Path, help="Root directory containing scenario JSON files.")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs" / "simulator" / "config.json",
        help="Path to a simulator config JSON file.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Number of trials to run per scenario.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Base random seed.")
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
        help="Policy to use for every simulation trial.",
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
        help="Directory where timestamped batch outputs are written.",
    )
    parser.add_argument(
        "--no-save-trials",
        action="store_true",
        help="Do not keep per-trial output folders. Scenario summaries are still saved.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=10,
        help="Maximum number of parallel trial workers.",
    )

    args = parser.parse_args()
    if args.trials < 1:
        raise ValueError("--trials must be at least 1")
    if args.max_workers < 1:
        raise ValueError("--max-workers must be at least 1")
    return vars(args)


def main() -> None:
    args = parse_args()
    scenario_root = args["scenario_root"]
    simulator_config = read_json(args["config"])
    batch_output_dir = args["output_root"] / datetime.now().strftime("%Y%m%d_%H%M%S")
    save_trials = not args["no_save_trials"]
    memory_retriever = create_memory_retriever(
        str(args["policy"]),
        simulator_config,
        args["memory_path"],
    )

    scenario_paths = sorted(scenario_root.rglob("scenario_*.json"))
    scenarios = [
        {
            "index": scenario_index,
            "scenario": read_json(scenario_path),
            "output_dir": batch_output_dir / scenario_path.relative_to(scenario_root).with_suffix(""),
        }
        for scenario_index, scenario_path in enumerate(scenario_paths)
    ]

    results_by_scenario = {item["index"]: [] for item in scenarios}
    stop_event = Event()
    tasks = [
        {
            "scenario_index": item["index"],
            "scenario": item["scenario"],
            "scenario_output_dir": item["output_dir"],
            "trial_index": trial_index,
            "seed": trial_seed(args["seed"], item["index"], args["trials"], trial_index),
            "save_trials": save_trials,
            "simulator_config": simulator_config,
            "policy": args["policy"],
            "memory_retriever": memory_retriever,
            "stop_event": stop_event,
        }
        for item in scenarios
        for trial_index in range(args["trials"])
    ]

    try:
        run_trials(tasks, args["max_workers"], results_by_scenario, stop_event)
    except KeyboardInterrupt:
        print("Interrupted. Cancelled pending simulations.", file=sys.stderr)
        raise SystemExit(130)

    summaries = []
    for item in scenarios:
        results = results_by_scenario[item["index"]]
        results.sort(key=lambda result: result["trial_index"])
        summary = summarize_results(item["scenario"], results)
        summary["summary_type"] = "scenario"
        summary["output_path"] = str(
            (item["output_dir"] / "summary.json").relative_to(batch_output_dir)
        )
        write_json(item["output_dir"] / "summary.json", summary)
        summaries.append(summary)

    write_group_summaries(
        batch_output_dir,
        summaries,
        results_by_scenario,
    )
    write_json(
        batch_output_dir / "summary.json",
        summarize_batch(summaries, results_by_scenario),
    )

    print(relative_to_project(batch_output_dir))


def run_trial(task: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
    trial_index = int(task["trial_index"])
    trial_output_dir = task["scenario_output_dir"] / f"trial_{trial_index}"
    result = Simulator(
        scenario=task["scenario"],
        simulator_config=task["simulator_config"],
        policy=create_policy(
            str(task["policy"]),
            task["simulator_config"],
            task.get("memory_retriever"),
        ),
        output_dir=trial_output_dir,
        seed=task["seed"],
    ).run(should_stop=task["stop_event"].is_set)
    result["trial_index"] = trial_index

    if not task["save_trials"] and trial_output_dir.exists():
        shutil.rmtree(trial_output_dir)

    return int(task["scenario_index"]), result


def run_trials(
    tasks: list[Mapping[str, Any]],
    max_workers: int,
    results_by_scenario: dict[int, list[dict[str, Any]]],
    stop_event: Event,
) -> None:
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = [executor.submit(run_trial, task) for task in tasks]
    try:
        for future in tqdm(as_completed(futures), total=len(futures), desc="simulations"):
            scenario_index, result = future.result()
            results_by_scenario[scenario_index].append(result)
    except KeyboardInterrupt:
        stop_event.set()
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)


def create_policy(
    policy_name: str,
    simulator_config: Mapping[str, Any],
    memory_retriever: MemoryRetriever | None = None,
):
    planner = Planner(simulator_config)
    if policy_name == "inspect_alternate_viewpoint":
        return InspectAlternateViewpointPolicy(planner, simulator_config)
    if policy_name == "oracle":
        return OraclePolicy(planner, simulator_config)
    if policy_name == "always_reasoning":
        return AlwaysReasoningPolicy(planner, simulator_config)
    if policy_name in MEMORY_BASED_POLICIES:
        if memory_retriever is None:
            raise ValueError(f"{policy_name} requires a memory retriever")
        if policy_name == "threshold_reuse":
            return ThresholdReusePolicy(planner, simulator_config, memory_retriever)
        if policy_name == "topk_count_reuse":
            return TopKCountReusePolicy(planner, simulator_config, memory_retriever)
        if policy_name == "memo_guard":
            return MemoGuardPolicy(planner, simulator_config, memory_retriever)
        return Top1ReusePolicy(planner, simulator_config, memory_retriever)
    raise ValueError(f"Unknown policy: {policy_name}")


def create_memory_retriever(
    policy_name: str,
    simulator_config: Mapping[str, Any],
    memory_path: Path,
) -> MemoryRetriever | None:
    if policy_name not in MEMORY_BASED_POLICIES:
        return None
    retrieval_config = memory_retrieval_config(simulator_config)
    return MemoryRetriever.from_file(
        memory_path,
        retrieval_config.get("weights", {}),
        max_samples=optional_int(retrieval_config.get("max_samples")),
        seed=optional_int(retrieval_config.get("seed")),
    )


def trial_seed(
    base_seed: int | None,
    scenario_index: int,
    trials: int,
    trial_index: int,
) -> int | None:
    if base_seed is None:
        return None
    return base_seed + scenario_index * trials + trial_index


def summarize_results(
    scenario: Mapping[str, Any],
    results: list[Mapping[str, Any]],
) -> dict[str, Any]:
    sample_count = len(results)
    metrics = sorted({key for result in results for key in result.get("metrics", {})})
    return {
        "scenario_id": scenario.get("id"),
        "initial_state": scenario.get("agent_initial_state"),
        "sample_count": sample_count,
        "average_steps": average([len(result.get("steps", [])) for result in results]),
        "average_reasoning_cost": average([reasoning_cost(result) for result in results]),
        "average_total_cost": average([total_cost(result) for result in results]),
        "memo_guard": memo_guard_summary(results),
        "metrics": {
            metric: ratio([bool(result.get("metrics", {}).get(metric)) for result in results])
            for metric in metrics
        },
    }


def summarize_batch(
    summaries: list[Mapping[str, Any]],
    results_by_scenario: Mapping[int, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    all_results = [
        result
        for results in results_by_scenario.values()
        for result in results
    ]
    metrics = sorted({key for result in all_results for key in result.get("metrics", {})})
    return {
        "scenario_count": len(summaries),
        "sample_count": len(all_results),
        "average_steps": average([len(result.get("steps", [])) for result in all_results]),
        "average_reasoning_cost": average([reasoning_cost(result) for result in all_results]),
        "average_total_cost": average([total_cost(result) for result in all_results]),
        "memo_guard": memo_guard_summary(all_results),
        "metrics": {
            metric: ratio([bool(result.get("metrics", {}).get(metric)) for result in all_results])
            for metric in metrics
        },
        "metrics_outliner_removed": summarize_without_success_outliners(
            summaries,
            results_by_scenario,
        ),
        "summaries": summaries,
    }


def summarize_without_success_outliners(
    summaries: list[Mapping[str, Any]],
    results_by_scenario: Mapping[int, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    included_indices = []
    removed_indices = []
    for index, summary in enumerate(summaries):
        success_rate = float(summary.get("metrics", {}).get("mission_success", 0.0))
        if success_rate <= MIN_SUCCESS_RATE or success_rate >= MAX_SUCCESS_RATE:
            removed_indices.append(index)
        else:
            included_indices.append(index)

    included_results = [
        result
        for index in included_indices
        for result in results_by_scenario.get(index, [])
    ]
    metrics = sorted({key for result in included_results for key in result.get("metrics", {})})
    return {
        "removed_outliner_count": len(removed_indices),
        "included_scenario_count": len(included_indices),
        "sample_count": len(included_results),
        "average_steps": average([len(result.get("steps", [])) for result in included_results]),
        "average_reasoning_cost": average(
            [reasoning_cost(result) for result in included_results]
        ),
        "average_total_cost": average([total_cost(result) for result in included_results]),
        "memo_guard": memo_guard_summary(included_results),
        "metrics": {
            metric: ratio([bool(result.get("metrics", {}).get(metric)) for result in included_results])
            for metric in metrics
        },
    }


def write_group_summaries(
    batch_output_dir: Path,
    summaries: list[Mapping[str, Any]],
    results_by_scenario: Mapping[int, list[Mapping[str, Any]]],
) -> None:
    grouped_indices: dict[Path, list[int]] = {}
    for index, summary in enumerate(summaries):
        output_path = Path(str(summary["output_path"]))
        scenario_dir = output_path.parent
        for group_dir in parent_group_dirs(scenario_dir):
            grouped_indices.setdefault(group_dir, []).append(index)

    for group_dir, indices in sorted(grouped_indices.items(), key=lambda item: str(item[0])):
        group_summaries = [summaries[index] for index in indices]
        group_results = {
            index: results_by_scenario.get(index, [])
            for index in indices
        }
        summary = summarize_batch(group_summaries, group_results)
        summary["summary_type"] = "group"
        summary["group_path"] = "." if str(group_dir) == "." else str(group_dir)
        write_json(batch_output_dir / group_dir / "summary.json", summary)


def parent_group_dirs(scenario_dir: Path) -> list[Path]:
    parts = scenario_dir.parts
    if len(parts) <= 1:
        return []
    return [Path(*parts[:length]) for length in range(1, len(parts))]


def reasoning_cost(result: Mapping[str, Any]) -> float:
    if "reasoning_cost" in result:
        return float(result["reasoning_cost"])
    return sum(float(step.get("reasoning_cost", 0.0)) for step in result.get("steps", []))


def total_cost(result: Mapping[str, Any]) -> float:
    if "total_cost" in result:
        return float(result["total_cost"])
    return sum(float(step.get("battery_cost", 0.0)) for step in result.get("steps", []))


def memo_guard_summary(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    guarded_count = 0
    reuse_count = 0
    reject_count = 0
    reason_counts: dict[str, int] = {}

    for result in results:
        for step in result.get("steps", []):
            if not isinstance(step, Mapping):
                continue
            guard = step.get("memo_guard")
            if not isinstance(guard, Mapping):
                continue

            guarded_count += 1
            if bool(guard.get("rejected", False)):
                reject_count += 1
                failed_checks = guard.get("failed_checks", [])
                if isinstance(failed_checks, list):
                    for reason in failed_checks:
                        reason_key = str(reason)
                        reason_counts[reason_key] = reason_counts.get(reason_key, 0) + 1
            else:
                reuse_count += 1

    return {
        "reuse_ratio": reuse_count / guarded_count if guarded_count else 0.0,
        "reject_ratio": reject_count / guarded_count if guarded_count else 0.0,
        "reject_reason_ratios": {
            reason: count / reject_count if reject_count else 0.0
            for reason, count in sorted(reason_counts.items())
        },
    }


def average(values: list[int | float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def ratio(values: list[bool]) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if value) / len(values)


def memory_retrieval_config(simulator_config: Mapping[str, Any]) -> Mapping[str, Any]:
    value = simulator_config.get("memory_retrieval", {})
    if not isinstance(value, Mapping):
        raise ValueError("memory_retrieval must be an object")
    return value


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def relative_to_project(path: Path) -> Path:
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(PROJECT_ROOT)
    except ValueError:
        return resolved_path


if __name__ == "__main__":
    main()
