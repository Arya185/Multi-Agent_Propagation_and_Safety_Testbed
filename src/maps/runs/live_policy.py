"""Validated, immutable live-execution policy (standalone; no I/O, no client, no defaults).

A ``LivePolicy`` is built from explicit values and is rejected unless every limit is present, of the
right type and mutually consistent. There are NO defaults and no way to express "unlimited": zero,
``None``, floats, booleans and infinity are all refused for the numeric limits. The values themselves
are the project owner's decisions; this module only checks that they are complete and coherent.
``approval_reference`` records which approved decision a policy implements.

``PolicyError`` messages name the field and the rule. They never repeat the supplied value.
Nothing here authorizes or performs a live run.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, fields

_INT_FIELDS = (
    "planned_episodes", "max_episodes", "max_request_attempts", "max_retries", "deadline_seconds",
    "max_consecutive_nonfatal_errors",
)


class AccountingBasis(enum.Enum):
    """What the request cap counts.

    CLIENT_ATTEMPTS: attempts reported by the client's own retry loop. Redirect hops are NOT guaranteed
    to be counted.
    STRICT_PHYSICAL: bounded accounting of client-reported attempts for a client that declares redirects disabled (the exact
    stock requests.Session class, redirects off on every attempt). It is not an independent count of sockets or physical sends
    and does not inspect the session's adapters.
    """

    CLIENT_ATTEMPTS = "client_attempts"
    STRICT_PHYSICAL = "strict_physical"


class PolicyError(ValueError):
    """The policy (or a policy-related precondition) is incomplete, invalid or inconsistent."""


def _fail(field: str, rule: str) -> None:
    raise PolicyError(f"{field}: {rule}")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, kw_only=True)
class LivePolicy:
    approval_reference: str
    planned_episodes: int
    max_episodes: int
    max_request_attempts: int
    max_retries: int
    deadline_seconds: int
    max_consecutive_nonfatal_errors: int
    accounting_basis: AccountingBasis
    nonfatal_4xx_statuses: frozenset[int]
    fatal_3xx: bool

    def __post_init__(self) -> None:
        if not isinstance(self.approval_reference, str) or not self.approval_reference.strip():
            _fail("approval_reference", "must be a non-empty string")
        for name in _INT_FIELDS:
            if not _is_int(getattr(self, name)):
                _fail(name, "must be an integer (not a boolean or float)")
        if not isinstance(self.accounting_basis, AccountingBasis):
            _fail("accounting_basis", "must be an AccountingBasis member")
        if not isinstance(self.fatal_3xx, bool):
            _fail("fatal_3xx", "must be a boolean")
        if not isinstance(self.nonfatal_4xx_statuses, frozenset):
            _fail("nonfatal_4xx_statuses", "must be a frozenset of integers")
        if not all(_is_int(s) and 400 <= s <= 499 for s in self.nonfatal_4xx_statuses):
            _fail("nonfatal_4xx_statuses", "every entry must be an integer HTTP status from 400 through 499")
        if self.planned_episodes < 1:
            _fail("planned_episodes", "must be at least 1")
        if self.max_episodes < self.planned_episodes:
            _fail("max_episodes", "must be at least planned_episodes")
        if self.max_retries < 0:
            _fail("max_retries", "must not be negative")
        if self.max_request_attempts < self.planned_episodes * (1 + self.max_retries):
            _fail("max_request_attempts", "must cover planned_episodes * (1 + max_retries)")
        if self.deadline_seconds < 1:
            _fail("deadline_seconds", "must be at least 1")
        if not 1 <= self.max_consecutive_nonfatal_errors <= self.planned_episodes:
            _fail("max_consecutive_nonfatal_errors", "must be between 1 and planned_episodes")

    @property
    def reservation_per_call(self) -> int:
        """Worst-case client attempts one logical call can use."""
        return 1 + self.max_retries

    def to_dict(self) -> dict:
        """Deterministic, JSON-compatible form. The accounting basis is its string value."""
        return {
            "approval_reference": self.approval_reference,
            "planned_episodes": self.planned_episodes,
            "max_episodes": self.max_episodes,
            "max_request_attempts": self.max_request_attempts,
            "max_retries": self.max_retries,
            "deadline_seconds": self.deadline_seconds,
            "max_consecutive_nonfatal_errors": self.max_consecutive_nonfatal_errors,
            "accounting_basis": self.accounting_basis.value,
            "nonfatal_4xx_statuses": sorted(self.nonfatal_4xx_statuses),
            "fatal_3xx": self.fatal_3xx,
        }

    @classmethod
    def from_mapping(cls, mapping: Mapping) -> LivePolicy:
        """Build a policy from a mapping (for example ``to_dict()`` output).

        Rejects missing fields, unknown fields (only their number is reported) and invalid enum values.
        Nothing is defaulted. ``accounting_basis`` may be a member or its string value;
        ``nonfatal_4xx_statuses`` may be a list, tuple, set or frozenset of integers."""
        if not isinstance(mapping, Mapping):
            raise PolicyError("policy: must be a mapping")
        known = tuple(f.name for f in fields(cls))
        missing = [name for name in known if name not in mapping]
        if missing:
            raise PolicyError("missing field(s): " + ", ".join(missing))
        unknown = sum(1 for key in mapping if key not in known)
        if unknown:
            raise PolicyError(f"{unknown} unknown field(s)")
        values = {name: mapping[name] for name in known}
        basis = values["accounting_basis"]
        if not isinstance(basis, AccountingBasis):
            if not isinstance(basis, str):
                raise PolicyError("accounting_basis: must be an AccountingBasis member or its string value")
            try:
                values["accounting_basis"] = AccountingBasis(basis)
            except ValueError:
                raise PolicyError("accounting_basis: not a valid accounting basis") from None
        statuses = values["nonfatal_4xx_statuses"]
        if not isinstance(statuses, (list, tuple, set, frozenset)):
            raise PolicyError("nonfatal_4xx_statuses: must be a list, tuple, set or frozenset of integers")
        try:
            values["nonfatal_4xx_statuses"] = frozenset(statuses)
        except TypeError:
            raise PolicyError("nonfatal_4xx_statuses: entries must be integers") from None
        return cls(**values)
