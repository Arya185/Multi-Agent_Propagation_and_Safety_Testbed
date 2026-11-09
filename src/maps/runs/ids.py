"""Run identifiers: one generator and one validator (standalone; no I/O).

Generated format: ``YYYYMMDDTHHMMSSffffffZ-<8 hex>`` (UTC time with microseconds, then a random
suffix), for example ``20261107T170212123456Z-1a2b3c4d``. The fixed width makes generated ids sort
chronologically as plain strings. The suffix makes two launches in the same microsecond collide only
if their 32-bit suffixes also match; a collision is still caught by the run-directory guard, which
refuses an existing directory.

What this module never does: regenerate an id after a collision, choose an alternate directory, rename
an existing id, or touch the filesystem. Explicit ids (including the older second-resolution form) stay
valid under the same character rule as before: 1-128 characters from ``A-Z a-z 0-9 . _ -``; the two
names ``.`` and ``..`` are additionally refused because they are path components, not identifiers.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime

RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")
GENERATED_RUN_ID_PATTERN = re.compile(r"\d{8}T\d{12}Z-[0-9a-f]{8}")
_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
_TOKEN = re.compile(r"[0-9a-f]{8}")


class InvalidRunIdError(ValueError):
    """The run id is not acceptable. The message never repeats the offending value."""


def validate_run_id(run_id: object) -> str:
    """Return ``run_id`` unchanged if acceptable, otherwise raise ``InvalidRunIdError``."""
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise InvalidRunIdError("run_id must be 1-128 characters from A-Z a-z 0-9 . _ -")
    if run_id in (".", ".."):
        raise InvalidRunIdError("run_id must not be a relative-path component")
    return run_id


def is_valid_run_id(run_id: object) -> bool:
    try:
        validate_run_id(run_id)
    except InvalidRunIdError:
        return False
    return True


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _random_token() -> str:
    return secrets.token_hex(4)


def generate_run_id(
    *,
    clock: Callable[[], datetime] | None = None,
    token: Callable[[], str] | None = None,
) -> str:
    """A new id in the generated format. ``clock`` (timezone-aware datetime) and ``token`` (8 lowercase
    hex characters) can be injected for deterministic tests."""
    moment = (clock or _utc_now)()
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    suffix = (token or _random_token)()
    if not isinstance(suffix, str) or not _TOKEN.fullmatch(suffix):
        raise ValueError("token must return exactly 8 lowercase hexadecimal characters")
    run_id = f"{moment.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)}-{suffix}"
    return validate_run_id(run_id)
