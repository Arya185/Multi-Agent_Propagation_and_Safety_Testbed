"""Redirect hardening of OpenRouterClient (v2.3.46): one client attempt must not follow redirects.

OFFLINE ONLY. The real ``OpenRouterClient`` class is instantiated here with a DUMMY literal key and a fake
transport (a stock ``requests.Session`` whose adapters are replaced by a recording fake, or a fake session
object). ``socket`` connection functions are patched to raise, so no provider request can occur. Nothing
here reads credentials or the environment.
"""

from __future__ import annotations

import ast
import json
import socket
from pathlib import Path

import pytest
import requests
from requests.adapters import HTTPAdapter

import maps.llm_client as llm_client_module
from maps.llm_client import OpenRouterClient
from maps.runs.live_budget import AbortReason, BudgetAbort, BudgetedClient, ErrorClass, classify_result
from maps.runs.live_policy import AccountingBasis, PolicyError
from maps.schemas import ChatMessage, ChatRequest

from lp_support import FakeClock, make_policy

DUMMY_KEY = "DUMMY-NOT-A-SECRET"
BASE_URL = "https://example.invalid/api/v1"
LOCATION = {"Location": "https://example.invalid/elsewhere"}
OK_BODY = {
    "model": "a/b-actual",
    "choices": [{"message": {"content": "hello"}}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted during an offline redirect test")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def request_obj() -> ChatRequest:
    return ChatRequest(model="a/b", messages=[ChatMessage(role="user", content="hi")], temperature=0.0, max_tokens=10, seed=1)


class RecordingAdapter(HTTPAdapter):
    """Replaces the transport: records each physical send and returns scripted responses (or raises)."""

    def __init__(self, plan):
        super().__init__()
        self.plan = list(plan)
        self.sent = []

    def send(self, request, **kwargs):
        self.sent.append((request.method, request.url))
        step = self.plan.pop(0)
        if isinstance(step, BaseException):
            raise step
        status, headers, body = step
        response = requests.Response()
        response.status_code = status
        response.headers.update(headers)
        response._content = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        response._content_consumed = True
        response.url = request.url
        response.request = request
        response.raw = None
        return response


def stock_session(plan, **attributes):
    session = requests.Session()
    adapter = RecordingAdapter(plan)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    for name, value in attributes.items():
        setattr(session, name, value)
    return session, adapter


def make_client(session, *, max_retries=0, sleeps=None):
    return OpenRouterClient(
        DUMMY_KEY, base_url=BASE_URL, enabled=True, session=session, max_retries=max_retries,
        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
    )


class KeywordRecordingSession:
    """A fake session object that records the keyword arguments of every post."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.kwargs = []

    def post(self, url, **kwargs):
        self.kwargs.append(kwargs)
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._body


# ---- the call itself -------------------------------------------------------------------------------
def test_every_attempt_passes_allow_redirects_false():
    session = KeywordRecordingSession([FakeResp(503), FakeResp(503), FakeResp(200, OK_BODY)])
    result = make_client(session, max_retries=2).complete(request_obj())
    assert result.error is None and result.attempts == 3
    assert [k["allow_redirects"] for k in session.kwargs] == [False, False, False]
    assert all(k["timeout"] == 60.0 for k in session.kwargs)                   # the other arguments are unchanged


def test_the_client_has_one_request_path_and_it_disables_redirects_explicitly():
    tree = ast.parse(Path(llm_client_module.__file__).read_text(encoding="utf-8"))
    posts = [c for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "post"]
    assert len(posts) == 1
    flags = [k for k in posts[0].keywords if k.arg == "allow_redirects"]
    assert len(flags) == 1 and isinstance(flags[0].value, ast.Constant) and flags[0].value.value is False
    transport_calls = []
    for c in ast.walk(tree):
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute):
            receiver = ast.unparse(c.func.value)
            if receiver in ("requests", "self._session") or receiver.startswith("requests."):
                transport_calls.append(f"{receiver}.{c.func.attr}")
    assert sorted(transport_calls) == ["requests.Session", "self._session.post"]   # the stock default session and the one post


# ---- 3xx handling -------------------------------------------------------------------------------------
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_3xx_is_not_followed_and_reaches_the_existing_error_path(status):
    session, adapter = stock_session([(status, LOCATION, b"moved"), (200, {}, OK_BODY)])
    result = make_client(session).complete(request_obj())
    assert len(adapter.sent) == 1 and adapter.sent[0][0] == "POST"             # the redirect target was never requested
    assert result.error == f"http_{status}: moved" and result.content is None and result.attempts == 1


@pytest.mark.parametrize("status", [302, 307])
def test_a_3xx_is_not_retried_even_when_retries_are_allowed(status):
    sleeps = []
    session, adapter = stock_session([(status, LOCATION, b"moved"), (200, {}, OK_BODY)])
    result = make_client(session, max_retries=2, sleeps=sleeps).complete(request_obj())
    assert len(adapter.sent) == 1 and result.attempts == 1 and sleeps == []
    assert result.error.startswith(f"http_{status}: ")


def test_a_3xx_without_a_location_header_is_also_one_request():
    session, adapter = stock_session([(302, {}, b"no location")])
    result = make_client(session, max_retries=2).complete(request_obj())
    assert len(adapter.sent) == 1 and result.error == "http_302: no location"


def test_the_error_body_is_still_bounded_and_the_key_is_still_redacted():
    session, adapter = stock_session([(302, LOCATION, ("x" * 500 + DUMMY_KEY).encode())])
    result = make_client(session).complete(request_obj())
    assert len(result.error) <= len("http_302: ") + 300 and DUMMY_KEY not in result.error


# ---- unchanged behavior --------------------------------------------------------------------------------
def test_a_normal_success_through_a_stock_session_is_parsed_as_before():
    session, adapter = stock_session([(200, {}, OK_BODY)])
    result = make_client(session).complete(request_obj())
    assert len(adapter.sent) == 1 and result.error is None and result.content == "hello" and result.attempts == 1
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (3, 2, 5) and result.response_model_id == "a/b-actual"


@pytest.mark.parametrize(
    "plan,max_retries,sends,error,sleeps",
    [
        ([(429, {}, b"slow"), (200, {}, OK_BODY)], 2, 2, None, [1.0]),
        ([(503, {}, b"x"), (503, {}, b"x"), (503, {}, b"x")], 2, 3, "http_503: x", [1.0, 2.0]),
        ([(503, {}, b"x"), (200, {}, OK_BODY)], 0, 1, "http_503: x", []),
        ([(408, {}, b"t"), (200, {}, OK_BODY)], 2, 1, "http_408: t", []),               # 408 is not in RETRY_STATUS
        ([(404, {}, b"n"), (200, {}, OK_BODY)], 2, 1, "http_404: n", []),
        ([(501, {}, b"n"), (200, {}, OK_BODY)], 2, 1, "http_501: n", []),               # nor is 501
    ],
    ids=["429-then-ok", "503-exhausted", "503-no-retries", "408-not-retried", "404-not-retried", "501-not-retried"],
)
def test_existing_status_retry_behavior_is_unchanged(plan, max_retries, sends, error, sleeps):
    recorded = []
    session, adapter = stock_session(plan)
    result = make_client(session, max_retries=max_retries, sleeps=recorded).complete(request_obj())
    assert len(adapter.sent) == sends and result.error == error and recorded == sleeps


@pytest.mark.parametrize("exception", [requests.Timeout("t"), requests.ConnectionError("c"), requests.exceptions.InvalidURL("u")], ids=["timeout", "connection", "invalid-url"])
def test_request_exceptions_are_still_retried_and_reported(exception):
    recorded = []
    session, adapter = stock_session([exception, exception, exception])
    result = make_client(session, max_retries=2, sleeps=recorded).complete(request_obj())
    assert len(adapter.sent) == 3 and result.attempts == 3 and recorded == [1.0, 2.0]
    assert result.error == f"request_exception: {type(exception).__name__}"


def test_a_connection_error_followed_by_success_still_recovers():
    session, adapter = stock_session([requests.ConnectionError("c"), (200, {}, OK_BODY)])
    result = make_client(session, max_retries=2).complete(request_obj())
    assert result.error is None and result.attempts == 2 and len(adapter.sent) == 2


# ---- the declaration -------------------------------------------------------------------------------------
def test_redirects_disabled_is_true_only_for_an_exact_stock_session():
    stock, _ = stock_session([])

    class Subclass(requests.Session):
        pass

    assert make_client(stock).redirects_disabled is True
    assert make_client(KeywordRecordingSession([])).redirects_disabled is False
    assert make_client(Subclass()).redirects_disabled is False
    assert make_client(None).redirects_disabled is True                        # the default session is the stock class (no request is made)
    swapped = make_client(stock)
    swapped._session = KeywordRecordingSession([])
    assert swapped.redirects_disabled is False                                 # evaluated against the session actually in use


def test_the_declaration_is_a_property_and_not_a_class_constant():
    assert isinstance(OpenRouterClient.__dict__["redirects_disabled"], property)
    assert not hasattr(llm_client_module.OpenRouterClient, "redirects_disabled") or isinstance(OpenRouterClient.redirects_disabled, property)


# ---- Stage 1 strict-physical integration ---------------------------------------------------------------------
STRICT = dict(accounting_basis=AccountingBasis.STRICT_PHYSICAL)


def test_budgeted_client_accepts_a_real_client_over_a_stock_session_in_strict_mode():
    session, adapter = stock_session([(302, LOCATION, b"moved"), (200, {}, OK_BODY)])
    budget = BudgetedClient(make_client(session), make_policy(**STRICT), clock=FakeClock())
    result = budget.complete(request_obj())
    assert len(adapter.sent) == 1 and result.attempts == 1                     # attempts now equal physical requests
    summary = budget.summary()
    assert summary.attempts_charged == 1 and summary.accounting_basis == "strict_physical" and summary.redirect_exposure == "none_redirects_disabled"
    assert dict(summary.error_category_counts) == {"http_302": 1} and summary.stop_reason == "fatal_error"
    with pytest.raises(BudgetAbort) as caught:
        budget.complete(request_obj())
    assert caught.value.reason is AbortReason.FATAL_ERROR and len(adapter.sent) == 1


def test_budgeted_client_refuses_a_fake_session_or_a_subclass_in_strict_mode():
    class Subclass(requests.Session):
        pass

    for session in (KeywordRecordingSession([]), Subclass()):
        with pytest.raises(PolicyError, match="redirects_disabled"):
            BudgetedClient(make_client(session), make_policy(**STRICT), clock=FakeClock())
    BudgetedClient(make_client(KeywordRecordingSession([])), make_policy(), clock=FakeClock())     # client-attempts mode still accepts it


# ---- the residual case ------------------------------------------------------------------------------------------
def test_a_session_with_max_redirects_zero_surfaces_as_too_many_redirects_after_one_send():
    session, adapter = stock_session([(302, LOCATION, b"moved"), (302, LOCATION, b"moved"), (302, LOCATION, b"moved")], max_redirects=0)
    result = make_client(session, max_retries=0).complete(request_obj())
    assert len(adapter.sent) == 1 and result.error == "request_exception: TooManyRedirects" and result.attempts == 1
    assert classify_result(result, make_policy()) == (ErrorClass.FATAL, "request_exception_too_many_redirects")


def test_even_then_each_attempt_is_still_at_most_one_physical_send():
    session, adapter = stock_session([(302, LOCATION, b"m")] * 3, max_redirects=0)
    result = make_client(session, max_retries=2).complete(request_obj())
    assert result.attempts == 3 and len(adapter.sent) == 3                      # retried (any RequestException is), one send per attempt


# ---- documented limit of strict mode (Stage 4G, PS-08) ------------------------------------------------------------
class RetryingAdapter(RecordingAdapter):
    """A stock-session adapter that retries on its own: the 503 never reaches the client, which sees one 200 reply."""

    def send(self, request, **kwargs):
        first = super().send(request, **kwargs)
        return super().send(request, **kwargs) if first.status_code == 503 else first


def test_strict_mode_accepts_a_stock_session_whose_adapter_retries_and_the_extra_sends_are_not_counted():
    """CHARACTERIZATION of a limit, not a feature. Strict mode checks the session TYPE and a declared flag; it does not inspect
    adapters. An adapter-level retry therefore sends a request that the wrapper cannot see: the accounting is a bounded count of
    client-reported attempts, not an independent count of sockets or physical sends."""
    adapter = RetryingAdapter([(503, {}, b"busy"), (200, {}, OK_BODY)])
    session = requests.Session()
    session.mount("https://", adapter)
    budget = BudgetedClient(make_client(session), make_policy(**STRICT), clock=FakeClock())     # accepted: exact stock type
    result = budget.complete(request_obj())
    assert result.error is None and result.attempts == 1
    assert budget.summary().attempts_charged == 1                                                # what the wrapper can see
    assert len(adapter.sent) == 2                                                                # what was actually sent


def test_the_strict_claim_is_stated_as_bounded_and_not_as_independent_counting():
    from maps.runs.live_budget import CLAIM_STRICT_PHYSICAL

    text = CLAIM_STRICT_PHYSICAL
    assert "bounded" in text and "client-reported attempts" in text and "stock requests.Session" in text and "redirects off" in text
    assert "not counted independently" in text
    assert not text.startswith("physical HTTP requests")                                         # the earlier, stronger wording


# ---- safety ---------------------------------------------------------------------------------------------------
def test_the_tripwire_is_active_so_an_unmounted_transport_cannot_reach_the_network():
    with pytest.raises(AssertionError, match="network access attempted"):
        socket.socket()
    session = requests.Session()
    session.mount("https://", RecordingAdapter([]))
    assert make_client(session).redirects_disabled is True
