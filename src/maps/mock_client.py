"""Offline client for tests and dry runs. Output is synthetic, never research data."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from maps.schemas import ChatRequest, LLMResult

Mode = Literal["valid", "malformed", "error", "scripted"]


class MockClient:
    name = "mock"

    def __init__(self, mode: Mode = "valid", scripted: list[str | LLMResult] | None = None):
        if mode == "scripted" and not scripted:
            raise ValueError("scripted mode needs a non-empty list")
        self.mode = mode
        self._scripted = list(scripted or [])
        self.calls: list[ChatRequest] = []

    def complete(self, request: ChatRequest) -> LLMResult:
        self.calls.append(request)
        if self.mode == "error":
            return LLMResult(error="mock_error: simulated failure", latency_s=0.0)
        if self.mode == "malformed":
            return self._wrap(request, "```json\n{not valid}\n```")
        if self.mode == "scripted":
            item = self._scripted[(len(self.calls) - 1) % len(self._scripted)]
            return item if isinstance(item, LLMResult) else self._wrap(request, item)
        return self._wrap(request, self._valid_body(request))

    @staticmethod
    def _wrap(request: ChatRequest, content: str) -> LLMResult:
        n = len(content.split())
        return LLMResult(
            content=content,
            response_model_id=request.model,
            prompt_tokens=sum(len(m.content.split()) for m in request.messages),
            completion_tokens=n,
            total_tokens=sum(len(m.content.split()) for m in request.messages) + n,
            latency_s=0.0,
        )

    @staticmethod
    def _valid_body(request: ChatRequest) -> str:
        """Deterministic pseudo-random but schema-valid response (hash of the request)."""
        digest = hashlib.sha256(
            (request.model + "|" + "|".join(m.content for m in request.messages)).encode()
        ).digest()
        return json.dumps(
            {
                "accepts_claim": digest[0] % 2 == 0,
                "confidence": digest[1] % 101,
                "estimated_independent_roots": digest[2] % 4,
                "evidence_used": [],
                "reasoning": "MOCK synthetic response",
            }
        )
