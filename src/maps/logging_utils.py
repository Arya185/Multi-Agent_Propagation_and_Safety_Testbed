"""JSONL logging with secret redaction."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REDACTED = "[REDACTED]"
_PATTERNS = [
    re.compile(r"sk-or-[A-Za-z0-9_\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Remove known secrets and common API-key shapes from text."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    text = _PATTERNS[0].sub(REDACTED, text)
    text = _PATTERNS[1].sub(REDACTED, text)
    return _PATTERNS[2].sub(lambda m: m.group(1) + REDACTED, text)


def redact_obj(obj: Any, secrets: Iterable[str] = ()) -> Any:
    secrets = tuple(secrets)
    if isinstance(obj, str):
        return redact(obj, secrets)
    if isinstance(obj, dict):
        return {k: redact_obj(v, secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v, secrets) for v in obj]
    return obj


class JsonlWriter:
    """Append-only JSONL writer. Every record is redacted before it hits disk."""

    def __init__(self, path: str | Path, secrets: Iterable[str] = ()):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._secrets = tuple(s for s in secrets if s)

    def write(self, record: dict[str, Any]) -> None:
        clean = redact_obj(record, self._secrets)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(clean, ensure_ascii=False) + "\n")
