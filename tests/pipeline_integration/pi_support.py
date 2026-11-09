"""Inputs for the mock pipeline integration tests (SYNTHETIC fixtures only).

The configuration and scenarios are the invented fixtures under tests/synthetic/data; no restricted
file is read. Test doubles named "mock" stand in for the model; nothing here can reach a network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from maps.config import load_config
from maps.experiments.receiver import build_grid, run_experiment as real_run_experiment
from maps.scenarios import load_scenario_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_DATA = REPO_ROOT / "tests" / "synthetic" / "data"


def load_inputs():
    cfg = load_config(SYNTHETIC_DATA / "config_synthetic.json")
    scenarios = load_scenario_dir(SYNTHETIC_DATA / "scenarios", REPO_ROOT)
    return cfg, scenarios


def grid_ids(cfg, scenarios) -> list[str]:
    return [spec.episode_id for spec in build_grid(cfg, scenarios)]


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hashes(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): file_hash(p) for p in sorted(Path(directory).rglob("*")) if p.is_file()}


class Recorder:
    """Wraps the real mock run so a test can damage the output afterwards and count calls."""

    def __init__(self, after=None, before_error: Exception | None = None):
        self.calls = 0
        self.after = after
        self.before_error = before_error

    def __call__(self, cfg, scenarios, client, out_dir, secrets=None, repo_root=REPO_ROOT):
        self.calls += 1
        if self.before_error is not None:
            raise self.before_error
        results = real_run_experiment(cfg, scenarios, client, out_dir, secrets, repo_root)
        if self.after is not None:
            self.after(Path(out_dir) / "episodes.jsonl")
        return results


def append_line(text: str):
    def apply(path: Path) -> None:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    return apply


def duplicate_first_line(path: Path) -> None:
    first = path.read_text(encoding="utf-8").splitlines()[0]
    append_line(first)(path)


def schema_invalid_line(path: Path) -> None:
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    record["episode_id_extra"] = 1
    append_line(json.dumps(record))(path)


def reverse_lines(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("".join(line + "\n" for line in reversed(lines)), encoding="utf-8")
