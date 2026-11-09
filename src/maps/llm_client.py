"""OpenRouter-compatible chat client. Knows nothing about experiments."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

import requests

from maps.logging_utils import redact
from maps.schemas import ChatRequest, LLMResult

RETRY_STATUS = {429, 500, 502, 503, 504}


class ApiDisabledError(RuntimeError):
    """Raised when a live call is attempted while the client is not enabled."""


class LLMClient(Protocol):
    name: str

    def complete(self, request: ChatRequest) -> LLMResult: ...


class OpenRouterClient:
    name = "openrouter"

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str,
        timeout_s: float = 60.0,
        max_retries: int = 2,
        backoff_s: float = 1.0,
        enabled: bool = False,
        session: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.enabled = enabled
        if session is None:
            # Stage 4G (PR4-PROXY): the DEFAULT session must not inherit environment-derived behavior. With trust_env False,
            # ``requests`` ignores the proxy variables (HTTP(S)_PROXY, NO_PROXY), ``~/.netrc`` and the CA-bundle variables
            # (REQUESTS_CA_BUNDLE, CURL_CA_BUNDLE). It stays the exact stock class, so ``redirects_disabled`` still holds.
            # This is not a claim that every proxy or transport setting is disabled, and it was not tried against a real
            # proxy or network. A session passed in by the caller is used exactly as given.
            session = requests.Session()
            session.trust_env = False
        self._session = session
        self._sleep = sleep

    def __repr__(self) -> str:
        return f"OpenRouterClient(base_url={self.base_url!r}, enabled={self.enabled})"

    @property
    def redirects_disabled(self) -> bool:
        """True only for the exact stock ``requests.Session`` class, which honors ``allow_redirects=False``.

        This is a type check on the session in use. It does not inspect the session's adapters, so an adapter that retries
        on its own would be invisible to the caller's attempt accounting."""
        return type(self._session) is requests.Session

    def _redact(self, text: str) -> str:
        return redact(text, [self._api_key or ""])

    def complete(self, request: ChatRequest) -> LLMResult:
        if not self.enabled:
            raise ApiDisabledError("live API calls are disabled for this client")
        if not self._api_key:
            raise ApiDisabledError("no API key available")

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        start = time.perf_counter()
        attempts = 0
        error = "unknown_error"
        while True:
            attempts += 1
            retryable = False
            try:
                # Redirects are NOT followed: one client attempt must not silently issue further HTTP requests.
                # A 3xx reply is returned and handled below as an ordinary non-200 error (and is not retried).
                resp = self._session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_s,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                error = self._redact(f"request_exception: {type(exc).__name__}")
                retryable = True
            else:
                if resp.status_code == 200:
                    return self._parse(resp, attempts, time.perf_counter() - start)
                error = self._redact(f"http_{resp.status_code}: {resp.text[:300]}")
                retryable = resp.status_code in RETRY_STATUS
            if not retryable or attempts > self.max_retries:
                break
            self._sleep(self.backoff_s * 2 ** (attempts - 1))
        return LLMResult(error=error, attempts=attempts, latency_s=time.perf_counter() - start)

    def _parse(self, resp: Any, attempts: int, latency: float) -> LLMResult:
        def fail(msg: str) -> LLMResult:
            return LLMResult(error=f"malformed_api_response: {msg}", attempts=attempts, latency_s=latency)

        try:
            data = resp.json()
        except ValueError:
            return fail("body is not JSON")
        if not isinstance(data, dict):
            return fail("body is not an object")
        if "error" in data:
            return LLMResult(
                error=self._redact(f"api_error: {str(data['error'])[:300]}"),
                attempts=attempts,
                latency_s=latency,
            )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return fail("missing choices[0].message.content")
        if not isinstance(content, str):
            return fail("content is not a string")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}

        def tok(key: str) -> int | None:
            v = usage.get(key)
            return v if isinstance(v, int) and not isinstance(v, bool) else None

        model = data.get("model")
        return LLMResult(
            content=content,
            response_model_id=model if isinstance(model, str) else None,
            prompt_tokens=tok("prompt_tokens"),
            completion_tokens=tok("completion_tokens"),
            total_tokens=tok("total_tokens"),
            latency_s=latency,
            attempts=attempts,
        )
