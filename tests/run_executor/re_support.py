"""Builders for the run-executor tests (SYNTHETIC records only; temporary directories only).

The executor is exercised with deterministic runner doubles that write records through the real
``JsonlWriter`` and the real ``EpisodeResult`` schema. No model client is constructed, no network is
reachable, and no restricted file is read.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from maps.logging_utils import JsonlWriter
from maps.schemas import EpisodeResult, EpisodeSpec, PlanItem, ReceiverResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_DATA = REPO_ROOT / "tests" / "synthetic" / "data"
FIXED_TIME = "2026-01-01T00:00:00Z"
SOURCE_REL = "src/maps/example.py"
LOCK_REL = "requirements.lock"
SENTINEL = "SENTINEL-CONTENT-1234"


def make_result(i: int) -> EpisodeResult:
    spec = EpisodeSpec(
        episode_id=f"ep_{i:012d}", model_alias="alpha", model_id="synthetic/alpha", scenario_id="s1", pair_id="p1",
        truth_status="true", condition_id="C1", n_messages=1, n_roots=1, prompt_variant="neutral", repetition=i, seed=i,
        message_plan=[PlanItem(position=0, relay_id="Relay-1", template_idx=0, root_id="s1-R1")],
    )
    response = ReceiverResponse(accepts_claim=True, confidence=80, estimated_independent_roots=1, evidence_used=[], reasoning="SYNTHETIC")
    return EpisodeResult(spec=spec, status="ok", response=response)


def episode_ids(n: int) -> list[str]:
    return [f"ep_{i:012d}" for i in range(1, n + 1)]


def make_repo(tmp_path: Path) -> Path:
    """A tiny repository root for provenance (one source file and a lock file)."""
    root = tmp_path / "repo"
    (root / "src" / "maps").mkdir(parents=True)
    (root / SOURCE_REL).write_text("VALUE = 1\n", encoding="utf-8")
    (root / LOCK_REL).write_text("pkg==1\n", encoding="utf-8")
    return root


def provenance_options(**overrides) -> dict:
    options = dict(source_files=[SOURCE_REL], lock_file=LOCK_REL, package_provider=lambda: [("pkg", "1")], include_git=False, created_utc=FIXED_TIME)
    options.update(overrides)
    return options


class Runner:
    """A deterministic runner double. ``after`` runs after the records are written (to damage them)."""

    def __init__(self, n=3, *, after=None, raise_after=None, write=True, returns="results"):
        self.calls = 0
        self.n, self.after, self.raise_after, self.write, self.returns = n, after, raise_after, write, returns

    def __call__(self, cfg, scenarios, client, out_dir, secrets=None, repo_root=REPO_ROOT):
        self.calls += 1
        results = [make_result(i) for i in range(1, self.n + 1)]
        path = Path(out_dir) / "episodes.jsonl"
        if self.write:
            writer = JsonlWriter(path)
            for k, result in enumerate(results):
                writer.write(result.model_dump(mode="json"))
                if self.raise_after is not None and k + 1 == self.raise_after[0]:
                    raise self.raise_after[1]
        if self.after is not None:
            self.after(path, Path(repo_root))
        return None if self.returns is None else results


def cfg_double(enabled=False):
    return SimpleNamespace(api=SimpleNamespace(enabled=enabled))


MOCK = SimpleNamespace(name="mock")


def append_line(text: str):
    def apply(path: Path, repo: Path) -> None:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    return apply


def duplicate_first_line(path: Path, repo: Path) -> None:
    append_line(path.read_text(encoding="utf-8").splitlines()[0])(path, repo)


def schema_invalid_line(path: Path, repo: Path) -> None:
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    record["unknown_field"] = 1
    append_line(json.dumps(record))(path, repo)


def reverse_lines(path: Path, repo: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("".join(line + "\n" for line in reversed(lines)), encoding="utf-8")


def truncate(path: Path, repo: Path) -> None:
    path.write_text("", encoding="utf-8")


def tree_hashes(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(directory).rglob("*")) if p.is_file()}


def read_events(run_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (Path(run_dir) / "run_events.jsonl").read_text(encoding="utf-8").splitlines()]
