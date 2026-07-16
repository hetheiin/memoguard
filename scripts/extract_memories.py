from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory import MemoryExtractor


DEFAULT_OUTPUTS = [
    PROJECT_ROOT / "outputs" / "second",
]
DEFAULT_MEMORY_PATH = PROJECT_ROOT / "data" / "memories" / "memories.json"


def parse_args() -> dict:
    parser = argparse.ArgumentParser(description="Extract memories from simulation outputs.")
    parser.add_argument(
        "outputs",
        nargs="*",
        type=Path,
        default=DEFAULT_OUTPUTS,
        help="Output directories to scan recursively.",
    )
    parser.add_argument(
        "--memory-path",
        type=Path,
        default=DEFAULT_MEMORY_PATH,
        help="Path to the memory JSON file.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Discard existing memories before extracting.",
    )
    return vars(parser.parse_args())


def main() -> None:
    args = parse_args()
    memories = MemoryExtractor(args["memory_path"]).extract(
        args["outputs"],
        reset=args["reset"],
        show_progress=True,
    )
    print(f"wrote {len(memories)} memories to {args['memory_path']}")


if __name__ == "__main__":
    main()
