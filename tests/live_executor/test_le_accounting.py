"""Budget accounting through the live executor, with the real client CLASS over a fake transport.

The real ``OpenRouterClient`` class is instantiated here with a DUMMY literal key and a stock
``requests.Session`` whose adapters are replaced by a fake; the socket functions are patched to raise, so no
provider request can occur.
"""

from __future__ import annotations

import json
import socket

import pytest
import requests
from requests.adapters import HTTPAdapter

from maps.llm_client import OpenRouterClient
from maps.runs.live_budget import BudgetSummary
from maps.runs.live_policy import AccountingBasis
from maps.schemas import LLMResult

from le_support import PLANNED, SENTINEL, Factory, ScriptedClient, event_names, make_policy, read_report, run_live

DUMMY_KEY = "DUMMY-NOT-A-SECRET"
RECEIVER_JSON = json.dumps({"accepts_claim": True, "confidence": 50, "estimated_independent_roots": 1, "evidence_used": [], "reasoning": "x"})
OK_BODY = {"model": "a/b", "choices": [{"message": {"content": RECEIVER_JSON}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class FakeTransport(HTTPAdapter):
    """Replaces the transport; ``responder(n, request)`` returns (status, body) for the n-th physical send."""

    def __init__(self, responder):
        super().__init__()
        self.responder = responder
        self.sent = 0

    def send(self, request, **kwargs):
        n = self.sent
        self.sent += 1
        status, body = self.responder(n, request)
        response = requests.Response()
        response.status_code = status
        response._content = (body if isinstance(body, bytes) else json.dumps(body).encode("utf-8"))
        response._content_consumed = True
        response.url, response.request, response.raw = request.url, request, None
        return response


def stock_session(responder):
    session = requests.Session()
    transport = FakeTransport(responder)
    session.mount("https://", transport)
    session.mount("http://", transport)
    return session, transport


def real_client_factory(session, *, max_retries):
    def build():
        return OpenRouterClient(DUMMY_KEY, base_url="https://example.invalid/api/v1", enabled=True, session=session,
                                max_retries=max_retries, sleep=lambda s: None)

    return _CountingFactory(build)


class _CountingFactory:
    """A counting factory around ``build``."""

    def __init__(self, build):
        self.build, self.calls = build, 0

    def __call__(self):
        self.calls += 1
        return self.build()


STRICT = dict(accounting_basis=AccountingBasis.STRICT_PHYSICAL)


def test_retries_are_accounted_per_attempt_and_the_cap_is_never_exceeded(tmp_path):
    session, transport = stock_session(lambda n, request: (503, b"busy") if n % 2 == 0 else (200, OK_BODY))
    policy = make_policy(max_retries=2, max_request_attempts=3 * PLANNED)
    outcome, factory, runner = run_live(tmp_path, factory=real_client_factory(session, max_retries=2), policy=policy)
    budget = read_report(tmp_path / "run")["live"]["budget"]
    assert outcome.status == "complete" and transport.sent == 2 * PLANNED
    assert budget["attempts_charged"] == 2 * PLANNED and budget["reserved_attempts_per_call"] == 3 and budget["attempt_count_untrusted"] == 0
    assert budget["attempts_charged"] <= policy.max_request_attempts and budget["logical_calls_started"] == PLANNED


def test_exhausted_retries_charge_every_attempt_and_the_consecutive_error_rule_still_applies(tmp_path):
    session, transport = stock_session(lambda n, request: (503, b"busy"))
    policy = make_policy(max_retries=2, max_request_attempts=3 * PLANNED, max_consecutive_nonfatal_errors=3)
    outcome, factory, runner = run_live(tmp_path, factory=real_client_factory(session, max_retries=2), policy=policy)
    report = read_report(tmp_path / "run")
    assert outcome.failed_stage == "policy_stop" and report["live"]["policy_stop_reason"] == "consecutive_errors"
    assert transport.sent == 9 == report["live"]["budget"]["attempts_charged"]                    # 3 calls x 3 attempts
    assert report["live"]["budget"]["error_category_counts"] == {"http_503": 3}


def test_a_client_whose_retry_setting_differs_from_the_policy_is_refused_before_the_runner(tmp_path):
    session, transport = stock_session(lambda n, request: (200, OK_BODY))
    outcome, factory, runner = run_live(tmp_path, factory=real_client_factory(session, max_retries=2), policy=make_policy(max_retries=0))
    assert (outcome.status, outcome.failed_stage) == ("failed", "client_construction") and runner.calls == 0 and transport.sent == 0
    assert event_names(tmp_path / "run") == ["run_claimed", "provenance_recorded", "client_construction_failed", "integrity_report_written"]


def test_strict_physical_accepts_a_stock_session_and_labels_the_accounting_as_bounded(tmp_path):
    session, transport = stock_session(lambda n, request: (200, OK_BODY))
    outcome, factory, runner = run_live(tmp_path, factory=real_client_factory(session, max_retries=0), policy=make_policy(**STRICT))
    budget = read_report(tmp_path / "run")["live"]["budget"]
    assert outcome.status == "complete" and transport.sent == PLANNED
    assert budget["accounting_basis"] == "strict_physical" and budget["redirect_exposure"] == "none_redirects_disabled"


def test_strict_physical_refuses_unsupported_session_types_before_the_runner_starts(tmp_path):
    class Subclass(requests.Session):
        pass

    class Posting:
        def post(self, url, **kwargs):
            raise AssertionError("a request was attempted")

    for session in (Subclass(), Posting()):
        sub = tmp_path / type(session).__name__
        sub.mkdir()
        outcome, factory, runner = run_live(sub, factory=real_client_factory(session, max_retries=0), policy=make_policy(**STRICT))
        report = read_report(sub / "run")
        assert (outcome.status, outcome.failed_stage) == ("failed", "client_construction") and runner.calls == 0
        assert report["runner"]["status"] == "not_started" and report["live"]["client_factory_called"] and not report["live"]["budget_wrapper_created"]
        assert not (sub / "run" / "episodes.jsonl").exists() and not outcome.analysis_eligible


def test_client_attempts_mode_accepts_any_session_but_does_not_claim_physical_accounting(tmp_path):
    class Subclass(requests.Session):
        pass

    session = Subclass()
    transport = FakeTransport(lambda n, request: (200, OK_BODY))
    session.mount("https://", transport)
    outcome, factory, runner = run_live(tmp_path, factory=real_client_factory(session, max_retries=0))
    budget = read_report(tmp_path / "run")["live"]["budget"]
    assert outcome.status == "complete" and budget["redirect_exposure"] == "not_counted" and "not guaranteed" in budget["accounting_claim"]


def test_missing_usage_is_unmeasured_not_zero_and_present_usage_is_summed(tmp_path):
    missing, _, _ = run_live(tmp_path, factory=Factory(ScriptedClient(strip_usage=True)))
    budget = read_report(tmp_path / "run")["live"]["budget"]
    assert (budget["usage_missing"], budget["usage_complete"]) == (PLANNED, 0) and budget["provider_reported_total_tokens"] == 0
    sub = tmp_path / "with-usage"
    sub.mkdir()
    present, _, _ = run_live(sub, factory=Factory(ScriptedClient()))
    budget = read_report(sub / "run")["live"]["budget"]
    assert (budget["usage_complete"], budget["usage_missing"]) == (PLANNED, 0) and budget["provider_reported_total_tokens"] > 0
    assert budget["requested_completion_ceiling_tokens"] > 0 and "maximum" in budget["requested_ceiling_basis"]


def test_the_persisted_budget_summary_is_bounded_and_holds_no_provider_text_prompts_or_keys(tmp_path):
    inner = ScriptedClient({3: LLMResult(error=f"http_503: {SENTINEL}", attempts=1)}, leak=SENTINEL)
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    out = tmp_path / "run"
    live = read_report(out)["live"]
    assert set(live["budget"]) == set(BudgetSummary.__dataclass_fields__)
    for name in ("run_integrity.json", "run_events.jsonl", "run_provenance.json"):
        text = (out / name).read_text(encoding="utf-8")
        assert SENTINEL not in text and DUMMY_KEY not in text and "SYNTHETIC prompt" not in text, name
    assert "prompt" not in json.dumps({k: v for k, v in live["budget"].items() if "prompt_tokens" not in k})


def test_no_accounting_state_resets_over_the_run(tmp_path):
    inner = ScriptedClient()
    outcome, factory, runner = run_live(tmp_path, factory=Factory(inner))
    budget = read_report(tmp_path / "run")["live"]["budget"]
    assert budget["logical_calls_started"] == budget["calls_returned"] == budget["attempts_charged"] == inner.calls == PLANNED
