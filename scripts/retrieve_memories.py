from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory import MemoryRetriever
from memory.utils import read_json
from simulator.state import AgentState


DEFAULT_MEMORY_PATH = PROJECT_ROOT / "data" / "memories" / "memories.json"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "simulator" / "config.json"


def parse_args() -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Retrieve similar memories for an agent state.")
    parser.add_argument(
        "query",
        type=Path,
        help="Path to a query JSON file with agent_state and context fields.",
    )
    parser.add_argument(
        "--memory-path",
        type=Path,
        default=DEFAULT_MEMORY_PATH,
        help="Path to memory JSON file.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to simulator config JSON file.",
    )
    parser.add_argument("--top-n", type=int, default=5, help="Number of memories to return.")
    return vars(parser.parse_args())


def main() -> None:
    args = parse_args()
    query = read_json(args["query"])
    if not isinstance(query, Mapping):
        raise ValueError("query JSON must be an object")

    config = read_json(args["config"])
    retrieval_config = memory_retrieval_config(config)
    agent_state = agent_state_from_query(query)
    context = query.get("context")
    if not isinstance(context, Mapping):
        raise ValueError("query.context must be an object")
    context = dict(context)
    context.setdefault("simulator_config", config)

    retriever = MemoryRetriever.from_file(
        args["memory_path"],
        retrieval_config.get("weights", {}),
        max_samples=optional_int(retrieval_config.get("max_samples")),
        seed=optional_int(retrieval_config.get("seed")),
    )
    retrieved = retriever.retrieve(agent_state, context, top_k=args["top_n"])
    print(json.dumps([item.to_dict() for item in retrieved], indent=2))


def agent_state_from_query(query: Mapping[str, Any]) -> AgentState:
    payload = query.get("agent_state")
    if not isinstance(payload, Mapping):
        raise ValueError("query.agent_state must be an object")
    return AgentState(
        target_node=str(payload["target_node"]),
        current_node=str(payload["current_node"]),
        battery=float(payload.get("battery", 0.0)),
        localization_confidence=float(payload.get("localization_confidence", 0.0)),
        action_sequence=list(payload.get("action_sequence", [])),
        target_inspected=bool(payload.get("target_inspected", False)),
        current_step=int(payload.get("current_step", 0)),
    )


def memory_retrieval_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    value = config.get("memory_retrieval", {})
    if not isinstance(value, Mapping):
        raise ValueError("memory_retrieval must be an object")
    return value


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


if __name__ == "__main__":
    main()
