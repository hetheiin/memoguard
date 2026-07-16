from __future__ import annotations

from pathlib import Path
from typing import Iterable


def find_run_dirs(output_paths: Iterable[Path]) -> list[Path]:
    run_dirs = set()
    for output_path in output_paths:
        path = output_path.resolve()
        if is_run_dir(path):
            run_dirs.add(path)
        if path.is_dir():
            for result_path in path.rglob("result.json"):
                candidate = result_path.parent
                if is_run_dir(candidate):
                    run_dirs.add(candidate)
    return sorted(run_dirs)


def is_run_dir(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "result.json").exists()
        and (path / "scenario.json").exists()
        and (path / "simulator_config.json").exists()
    )
