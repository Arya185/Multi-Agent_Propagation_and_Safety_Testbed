"""Builders for the live-policy tests: fake clients and a fake clock only.

Nothing here constructs a real client, reads credentials or the environment, sleeps, or reaches a network.
"""

from __future__ import annotations

from maps.runs.live_policy import AccountingBasis, LivePolicy
from maps.schemas import ChatMessage, ChatRequest, LLMResult

SENTINEL = "SENTINEL-SECRET-PROVIDER-BODY-98765"


def make_policy(**overrides) -> LivePolicy:
    """A SYNTHETIC test policy (small numbers). These are test fixtures, not proposed or approved values."""
    values = dict(
        approval_reference="test-fixture",
        planned_episodes=10,
        max_episodes=10,
        max_request_attempts=10,
        max_retries=0,
        deadline_seconds=100,
        max_consecutive_nonfatal_errors=3,
        accounting_basis=AccountingBasis.CLIENT_ATTEMPTS,
        nonfatal_4xx_statuses=frozenset({408, 429}),
        fatal_3xx=True,
    )
    values.update(overrides)
    return LivePolicy(**values)


def policy_dict(**overrides) -> dict:
    data = make_policy().to_dict()
    data.update(overrides)
    return data


def make_request(max_tokens: int = 800) -> ChatRequest:
    return ChatRequest(
        model="synthetic/model", messages=[ChatMessage(role="user", content="SYNTHETIC prompt text")],
        temperature=0.0, max_tokens=max_tokens, seed=1,
    )


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def ok(attempts: int = 1, *, prompt=11, completion=7, total=18, content="SYNTHETIC answer") -> LLMResult:
    return LLMResult(content=content, attempts=attempts, prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


def err(text: str, attempts: int = 1) -> LLMResult:
    return LLMResult(error=text, attempts=attempts)


class FakeClient:
    """Returns scripted outcomes in order; an Exception instance in the script is raised.

    ``on_call`` (optional) runs inside each call, for example to advance a fake clock mid-flight."""

    def __init__(self, script, *, name="fake", max_retries=0, redirects_disabled=None, on_call=None):
        self.script = list(script)
        self.name = name
        self.max_retries = max_retries
        if redirects_disabled is not None:
            self.redirects_disabled = redirects_disabled
        self.on_call = on_call
        self.calls = 0
        self.requests = []

    def complete(self, request):
        self.calls += 1
        self.requests.append(request)
        if self.on_call:
            self.on_call()
        step = self.script.pop(0) if self.script else ok()
        if isinstance(step, BaseException):
            raise step
        return step
