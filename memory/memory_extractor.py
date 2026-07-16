from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from memory.memory import Memory, OutcomeStatistics, memory_key
from memory.utils import build_retrieval_features, find_run_dirs, read_json, write_json
from policies.utils.path_risk_similarity import GraphView, build_path_risk_profile

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


class MemoryExtractor:
    def __init__(self, memory_path: Path) -> None:
        self._memory_path = memory_path

    def extract(
        self,
        output_paths: Iterable[Path],
        reset: bool = False,
        show_progress: bool = False,
    ) -> list[Memory]:
        memories = [] if reset else self._load_existing_memories()
        memory_index = {memory.key(): memory for memory in memories}
        run_dirs = find_run_dirs(output_paths)

        iterator = run_dirs
        if show_progress and tqdm is not None:
            iterator = tqdm(run_dirs, desc="extracting memories")

        for run_dir in iterator:
            self._update_from_run(run_dir, memory_index)

        memory_index = {
            key: memory
            for key, memory in memory_index.items()
            if memory.outcome_statistics.success_count > 0
        }
        memories = sorted(
            memory_index.values(),
            key=lambda memory: (
                memory.scenario_id,
                memory.action,
                str(memory.retrieval_features.get("node")),
                str(memory.retrieval_features.get("battery_range")),
            ),
        )
        self._write_memories(memories)
        return memories

    def _update_from_run(
        self,
        run_dir: Path,
        memory_index: dict[tuple[Any, ...], Memory],
    ) -> None:
        scenario = read_json(run_dir / "scenario.json")
        result = read_json(run_dir / "result.json")
        simulator_config = read_json(run_dir / "simulator_config.json")

        scenario_id = str(scenario.get("id", result.get("scenario_id", "")))
        trial_success = bool(result.get("metrics", {}).get("mission_success", False))

        map_configuration = _required_mapping(scenario, "map_configuration")
        metadata = dict(_required_mapping(scenario, "metadata"))
        graph = GraphView(map_configuration)

        for step in result.get("steps", []):
            if not isinstance(step, Mapping):
                continue

            action = str(step.get("action", ""))
            if not action:
                continue

            retrieval_features = build_retrieval_features(
                step,
                map_configuration,
                simulator_config,
            )
            key = memory_key(scenario_id, retrieval_features, action)
            to_node = step.get("to_node")

            if key not in memory_index:
                if not trial_success:
                    continue
                memory_index[key] = Memory(
                    retrieval_features=retrieval_features,
                    action=action,
                    reasoning=bool(step.get("reasoning", False)),
                    to_node=str(to_node) if to_node is not None else None,
                    outcome_statistics=OutcomeStatistics(),
                    scenario_id=scenario_id,
                    instruction=str(scenario.get("instruction", "")),
                    scenario_metadata=metadata,
                    map_id=str(scenario.get("map_id", "")),
                    map_class=scenario.get("map_class"),
                )

            if memory_index[key].path_risk_profile is None:
                memory_index[key].path_risk_profile = build_path_risk_profile(
                    graph,
                    str(retrieval_features["node"]),
                    metadata,
                ).to_dict()

            memory_index[key].update(
                trial_success,
                str(to_node) if to_node is not None else None,
            )

    def _load_existing_memories(self) -> list[Memory]:
        if not self._memory_path.exists():
            return []
        payload = read_json(self._memory_path)
        if not isinstance(payload, list):
            raise ValueError(f"Expected memory list in {self._memory_path}")
        return [Memory.from_dict(item) for item in payload if isinstance(item, Mapping)]

    def _write_memories(self, memories: list[Memory]) -> None:
        write_json(self._memory_path, [memory.to_dict() for memory in memories])


def _required_mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value
