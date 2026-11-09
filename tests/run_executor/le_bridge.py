"""Builds a live-executor report for the schema-sharing test (fake client; offline)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from maps.logging_utils import JsonlWriter
from maps.runs.live_executor import execute_live_run
from maps.runs.live_policy import AccountingBasis, LivePolicy
from maps.schemas import ChatMessage, ChatRequest, LLMResult

from re_support import make_repo, make_result, provenance_options


def live_report_keys(tmp_path: Path) -> set[str]:
    class Client:
        name, max_retries = "fake-live", 0

        def complete(self, request):
            return LLMResult(content="ok", attempts=1)

    def runner(cfg, scenarios, client, out_dir, secrets=None, repo_root=None):
        client.complete(ChatRequest(model="a/b", messages=[ChatMessage(role="user", content="x")], temperature=0.0, max_tokens=5, seed=1))
        JsonlWriter(Path(out_dir) / "episodes.jsonl").write(make_result(1).model_dump(mode="json"))
        return [make_result(1)]

    policy = LivePolicy(approval_reference="t", planned_episodes=1, max_episodes=1, max_request_attempts=1, max_retries=0, deadline_seconds=1000,
                        max_consecutive_nonfatal_errors=1, accounting_basis=AccountingBasis.CLIENT_ATTEMPTS, nonfatal_4xx_statuses=frozenset(), fatal_3xx=True)
    outcome = execute_live_run(
        run_fn=runner, cfg=SimpleNamespace(api=SimpleNamespace(enabled=True, max_retries=0)), scenarios=[], client_factory=Client, policy=policy,
        run_dir=tmp_path / "live", run_id="live-h", repo_root=make_repo(tmp_path), expected_episode_ids=["ep_000000000001"],
        provenance_options=provenance_options(), clock=lambda: "2026-01-01T00:00:00Z",
    )
    assert outcome.analysis_eligible and outcome.report.version == 2
    return set(outcome.report.artifacts)
