"""Builders for the integrity-gate tests: REAL reports from the mock and live executors, then mutated copies.

OFFLINE ONLY: temporary directories, synthetic records (via ri_support), fake clients; no provider client is
constructed, nothing reads credentials or the environment, and no network is reachable.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from maps.logging_utils import JsonlWriter
from maps.runs.executor import execute_mock_run
from maps.runs.live_executor import execute_live_run
from maps.runs.live_policy import AccountingBasis, LivePolicy
from maps.schemas import ChatMessage, ChatRequest, LLMResult

import ri_support as R

REPORT = "run_integrity.json"
CLAIM = ".maps_run_claim"
FIXED_TIME = "2026-01-01T00:00:00Z"
CLOCK = lambda: FIXED_TIME  # noqa: E731


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src" / "maps").mkdir(parents=True, exist_ok=True)       # idempotent: several runs can share one test directory
    (repo / "src" / "maps" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "requirements.lock").write_text("pkg==1\n", encoding="utf-8")
    return repo


def provenance_options() -> dict:
    return dict(source_files=["src/maps/a.py"], lock_file="requirements.lock", include_git=False,
                package_provider=lambda: [("pkg", "1")], created_utc=FIXED_TIME)


def ids(n: int) -> list[str]:
    return [f"ep_{i:012d}" for i in range(1, n + 1)]


def build_mock_run(tmp_path: Path, *, n=3, after=None, fail_after: int | None = None, run_id="gate-001", inventory=None, name="run", extra_files=None):
    """A real mock-executor run in ``tmp_path/name``. Returns (run_dir, outcome). ``extra_files`` (name -> bytes) are written
    by the runner before it returns, like the real runner's calls.jsonl / manifest.json / summaries."""
    repo, out = make_repo(tmp_path), tmp_path / name

    def runner(cfg, scenarios, client, out_dir, secrets=None, repo_root=None):
        for extra_name, data in (extra_files or {}).items():
            (Path(out_dir) / extra_name).write_bytes(data)
        results = R.numbered(n)
        writer = JsonlWriter(Path(out_dir) / "episodes.jsonl")
        for k, result in enumerate(results):
            writer.write(result.model_dump(mode="json"))
            if fail_after is not None and k + 1 == fail_after:
                raise RuntimeError("runner stopped")
        if after is not None:
            after(Path(out_dir) / "episodes.jsonl")
        return results

    outcome = execute_mock_run(
        run_fn=runner, cfg=SimpleNamespace(api=SimpleNamespace(enabled=False)), scenarios=[], client=SimpleNamespace(name="mock"),
        run_dir=out, run_id=run_id, repo_root=repo, expected_episode_ids=inventory, provenance_options=provenance_options(), clock=CLOCK,
    )
    return out, outcome


class FakeLiveClient:
    def __init__(self, script=None):
        self.name, self.max_retries, self.script, self.calls = "fake-live", 0, dict(script or {}), 0

    def complete(self, request):
        self.calls += 1
        step = self.script.get(self.calls)
        if isinstance(step, BaseException):
            raise step
        return step if step is not None else LLMResult(content="ok", attempts=1)


def build_live_run(tmp_path: Path, *, n=5, script=None, run_id="live-gate-001", name="run"):
    """A real live-executor run (fake client) in ``tmp_path/name``. May raise KeyboardInterrupt if scripted. Returns (run_dir, outcome)."""
    repo, out = make_repo(tmp_path), tmp_path / name
    client = FakeLiveClient(script)

    def runner(cfg, scenarios, wrapped, out_dir, secrets=None, repo_root=None):
        results = R.numbered(n)
        writer = JsonlWriter(Path(out_dir) / "episodes.jsonl")
        for i in range(n):
            wrapped.complete(ChatRequest(model="a/b", messages=[ChatMessage(role="user", content="SYNTHETIC")], temperature=0.0, max_tokens=10, seed=i))
            writer.write(results[i].model_dump(mode="json"))
        return results

    policy = LivePolicy(
        approval_reference="gate-test", planned_episodes=n, max_episodes=n, max_request_attempts=n, max_retries=0, deadline_seconds=100_000,
        max_consecutive_nonfatal_errors=min(3, n), accounting_basis=AccountingBasis.CLIENT_ATTEMPTS,
        nonfatal_4xx_statuses=frozenset({408, 429}), fatal_3xx=True,
    )
    outcome = execute_live_run(
        run_fn=runner, cfg=SimpleNamespace(api=SimpleNamespace(enabled=True, max_retries=0)), scenarios=[], client_factory=lambda: client,
        policy=policy, run_dir=out, run_id=run_id, repo_root=repo, expected_episode_ids=ids(n), provenance_options=provenance_options(), clock=CLOCK,
    )
    return out, outcome


def read_report(run_dir) -> dict:
    return json.loads((Path(run_dir) / REPORT).read_text(encoding="utf-8"))


def write_report(run_dir, data) -> None:
    (Path(run_dir) / REPORT).write_text(json.dumps(data), encoding="utf-8")


def edit_report(run_dir, change) -> dict:
    """Load the report, apply ``change(report)``, write it back (test copies only)."""
    report = read_report(run_dir)
    change(report)
    write_report(run_dir, report)
    return report


def edit_claim(run_dir, change) -> None:
    path = Path(run_dir) / CLAIM
    claim = json.loads(path.read_text(encoding="utf-8"))
    change(claim)
    path.write_text(json.dumps(claim), encoding="utf-8")


FULL_EXTRAS = {"calls.jsonl": b'{"call": 1}\n{"call": 2}\n', "manifest.json": b'{"manifest": true}', "summary.json": b"{}", "contrast_gaps.json": b"[]"}


def rebuild_block(run_dir, change=None) -> dict:
    """Recompute the hash block from the files as they are now (optionally altering the block first) and store it in the report."""
    from maps.runs.artifact_hashes import artifact_set_digest, build_artifact_block

    block, _ = build_artifact_block(run_dir)
    if change is not None:
        change(block)
        block["artifact_digest"] = artifact_set_digest(block["files"])
    edit_report(run_dir, lambda r: r.update(artifacts=block))
    return block
