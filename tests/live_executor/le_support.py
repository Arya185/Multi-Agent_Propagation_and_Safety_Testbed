"""Builders for the live-executor tests: fake clients, fake factories, fake clocks, synthetic inputs.

OFFLINE ONLY. Nothing here reads credentials or the environment, sleeps, or reaches a network. The synthetic
configuration and scenarios under tests/synthetic/data are the only inputs; the real runner
(``run_experiment``) is used with fake model clients that delegate to the offline ``MockClient``.
"""

from __future__ import annotations

import json
from pathlib import Path

from maps.config import load_config
from maps.experiments.receiver import build_grid, run_experiment
from maps.logging_utils import JsonlWriter
from maps.mock_client import MockClient
from maps.runs.live_executor import execute_live_run
from maps.runs.live_policy import AccountingBasis, LivePolicy
from maps.scenarios import load_scenario_dir
from maps.schemas import ChatMessage, ChatRequest, EpisodeResult, EpisodeSpec, LLMResult, PlanItem, ReceiverResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_DATA = REPO_ROOT / "tests" / "synthetic" / "data"
PLANNED = 96                                     # 2 models x 4 scenarios x 2 variants x 6 conditions x 1 repetition
SENTINEL = "SENTINEL-SECRET-VALUE-4242"
FIXED_TIME = "2026-01-01T00:00:00Z"
CLOCK = lambda: FIXED_TIME  # noqa: E731


def load_inputs():
    cfg = load_config(SYNTHETIC_DATA / "config_synthetic.json")
    scenarios = load_scenario_dir(SYNTHETIC_DATA / "scenarios", REPO_ROOT)
    return cfg, scenarios


def live_cfg(cfg, *, max_retries=0, enabled=True):
    return cfg.model_copy(update={"api": cfg.api.model_copy(update={"enabled": enabled, "max_retries": max_retries})})


def grid_ids(cfg, scenarios) -> list[str]:
    return [spec.episode_id for spec in build_grid(cfg, scenarios)]


def make_policy(**overrides) -> LivePolicy:
    """A SYNTHETIC test policy. These numbers are test fixtures, not proposed or approved values."""
    values = dict(
        approval_reference="test-fixture", planned_episodes=PLANNED, max_episodes=PLANNED, max_request_attempts=PLANNED,
        max_retries=0, deadline_seconds=100_000, max_consecutive_nonfatal_errors=5,
        accounting_basis=AccountingBasis.CLIENT_ATTEMPTS, nonfatal_4xx_statuses=frozenset({408, 429}), fatal_3xx=True,
    )
    values.update(overrides)
    return LivePolicy(**values)


def provenance_options(**overrides) -> dict:
    options = dict(source_files=["src/maps/runs/live_executor.py"], lock_file="requirements.lock", include_git=False,
                   package_provider=lambda: [("pkg", "1")], created_utc=FIXED_TIME)
    options.update(overrides)
    return options


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ScriptedClient:
    """A fake model client. By default it delegates to the offline MockClient (valid receiver responses).

    ``script`` maps a 1-based call number to an ``LLMResult``, an exception to raise, or a callable returning
    either. ``advance`` runs inside every call (for example to move a fake clock). ``strip_usage`` removes the
    token counts. ``leak`` appends a string to the response ``reasoning`` (to test redaction)."""

    def __init__(self, script=None, *, name="fake-live", max_retries=0, redirects_disabled=None, advance=None,
                 strip_usage=False, leak=None):
        self.script = dict(script or {})
        self.name = name
        self.max_retries = max_retries
        if redirects_disabled is not None:
            self.redirects_disabled = redirects_disabled
        self.advance = advance
        self.strip_usage = strip_usage
        self.leak = leak
        self.calls = 0
        self.requests: list[ChatRequest] = []
        self._mock = MockClient()

    def complete(self, request):
        self.calls += 1
        self.requests.append(request)
        if self.advance:
            self.advance()
        step = self.script.get(self.calls)
        if callable(step):
            step = step()
        if isinstance(step, BaseException):
            raise step
        if step is not None:
            return step
        result = self._mock.complete(request)
        updates = {}
        if self.leak:
            data = json.loads(result.content)
            data["reasoning"] = f"{data['reasoning']} {self.leak}"
            updates["content"] = json.dumps(data)
        if self.strip_usage:
            updates.update(prompt_tokens=None, completion_tokens=None, total_tokens=None)
        return result.model_copy(update=updates) if updates else result


class Factory:
    """A counting client factory (called with no arguments, as the executor must call it)."""

    def __init__(self, client=None, *, raises: BaseException | None = None):
        self.client = client if client is not None else ScriptedClient()
        self.raises = raises
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.client


class RunnerSpy:
    """Wraps the real runner and records what it was given."""

    def __init__(self, runner=run_experiment):
        self.runner = runner
        self.calls = 0
        self.clients = []
        self.secrets = []

    def __call__(self, cfg, scenarios, client, out_dir, secrets=None, repo_root=REPO_ROOT):
        self.calls += 1
        self.clients.append(client)
        self.secrets.append(secrets)
        return self.runner(cfg, scenarios, client, out_dir, secrets, repo_root)


class CallingRunner:
    """A small runner for exact call-count tests: makes ``n_calls`` client calls and records one episode per
    returned call (like the real runner), so extra calls beyond the plan can be exercised."""

    def __init__(self, n_calls, ids=None):
        self.n_calls = n_calls
        self.ids = ids
        self.calls = 0

    def __call__(self, cfg, scenarios, client, out_dir, secrets=None, repo_root=REPO_ROOT):
        self.calls += 1
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        writer = JsonlWriter(out / "episodes.jsonl", secrets or [])
        results = []
        for i in range(self.n_calls):
            client.complete(ChatRequest(model="a/b", messages=[ChatMessage(role="user", content="SYNTHETIC")], temperature=0.0, max_tokens=10, seed=i))
            result = small_result(i + 1)
            writer.write(result.model_dump(mode="json"))
            results.append(result)
        return results


def small_result(i: int) -> EpisodeResult:
    spec = EpisodeSpec(
        episode_id=f"ep_{i:012d}", model_alias="alpha", model_id="synthetic/alpha", scenario_id="s1", pair_id="p1", truth_status="true",
        condition_id="C1", n_messages=1, n_roots=1, prompt_variant="neutral", repetition=i, seed=i,
        message_plan=[PlanItem(position=0, relay_id="Relay-1", template_idx=0, root_id="s1-R1")],
    )
    response = ReceiverResponse(accepts_claim=True, confidence=80, estimated_independent_roots=1, evidence_used=[], reasoning="SYNTHETIC")
    return EpisodeResult(spec=spec, status="ok", response=response)


def small_ids(n: int) -> list[str]:
    return [f"ep_{i:012d}" for i in range(1, n + 1)]


def run_live(tmp_path, *, inputs=None, factory=None, policy=None, runner=None, run_id="live-001", ids=None, **kwargs):
    """Run execute_live_run against the synthetic inputs and the real runner. Returns (outcome, factory, runner)."""
    cfg, scenarios = inputs or load_inputs()
    cfg = kwargs.pop("cfg", None) or live_cfg(cfg, max_retries=policy.max_retries if policy is not None else 0)
    policy = policy or make_policy()
    factory = factory or Factory()
    runner = runner or RunnerSpy()
    outcome = execute_live_run(
        run_fn=runner, cfg=cfg, scenarios=scenarios, client_factory=factory, policy=policy, run_dir=tmp_path / "run",
        run_id=run_id, repo_root=REPO_ROOT, expected_episode_ids=ids if ids is not None else grid_ids(cfg, scenarios),
        provenance_options=kwargs.pop("provenance_options", provenance_options()), clock=CLOCK, **kwargs,
    )
    return outcome, factory, runner


def read_events(run_dir) -> list[dict]:
    return [json.loads(line) for line in (Path(run_dir) / "run_events.jsonl").read_text(encoding="utf-8").splitlines()]


def event_names(run_dir) -> list[str]:
    return [e["event"] for e in read_events(run_dir)]


def read_report(run_dir) -> dict:
    return json.loads((Path(run_dir) / "run_integrity.json").read_text(encoding="utf-8"))


def line_count(path) -> int:
    path = Path(path)
    return path.read_text(encoding="utf-8").count("\n") if path.is_file() else 0
