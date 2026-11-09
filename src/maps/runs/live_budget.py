"""Budgeted client wrapper: request-attempt accounting, stop rules, error classification, usage reporting.

``BudgetedClient`` wraps an INJECTED client (this module never builds one, never reads credentials or
the environment, never touches the network) and exposes the same ``name`` / ``complete`` surface, so it
can sit between the runner and a client unchanged. It enforces a ``LivePolicy``:

  * before each call it refuses if a stop is already in force, the deadline has been reached, the
    episode cap is reached, or reserving the worst case (``1 + max_retries`` attempts) would exceed the
    request cap; otherwise it reserves that worst case;
  * on a returned result it charges the client's own ``attempts`` (only if that is a plausible integer
    within the reservation, else the full reservation); if the call raises, the actual attempt count is
    unknown, so it charges the full reservation, exactly once;
  * it classifies each result, counts consecutive nonfatal errors (reset by any success) and stops.

STOPS ARE STICKY AND TAKE EFFECT AT THE NEXT CALL. The call whose result triggers a stop is still
returned (so the runner can record that episode); the next ``complete`` raises ``BudgetAbort`` without
calling the client. ``summary().stop_reason`` shows the stop even if no later call happens.

LIMITS, stated plainly:
  * The deadline is checked only BETWEEN calls. A call already in flight is never cancelled; if it
    finishes after the deadline its result is returned normally and ``deadline_crossed_by_inflight_call``
    is set. Overshoot is at most one call's worst case.
  * ``CLIENT_ATTEMPTS`` counts the attempts the client reports. Redirect hops are NOT guaranteed to be
    counted (``redirect_exposure == "not_counted"``). ``STRICT_PHYSICAL`` is accepted only for a client
    that explicitly exposes ``redirects_disabled is True``; nothing is inferred.
  * Classification reads the client's existing error strings (anchored at the start; provider text after
    the prefix never matters). That grammar is a client-internal convention. An HTTP 200 reply carrying a
    provider error object (``api_error``) has no status code and is treated as nonfatal.
  * ``STRICT_PHYSICAL`` is BOUNDED accounting, not an independent count of sockets or physical sends: it requires the exact
    stock ``requests.Session`` class and relies on the client passing ``allow_redirects=False`` on every attempt, and it counts
    the attempts the client reports. It does not inspect the session's adapters, so an adapter that retries on its own would
    send requests the wrapper cannot see.
  * The consecutive-error counter is GLOBAL (one wrapper serves every model and the grid order is shuffled) and any success
    resets it. One model's outage can therefore go unnoticed while another model's successes keep resetting the counter.
    Per-model or per-cell limits are not implemented (owner decision PS-21: deferred).
  * There is NO cumulative token cap (owner decision PS-06-BUDGET: none for this research stage).
  * Token totals are PROVIDER-REPORTED values from calls that supplied them; missing usage is never
    zero. ``requested_completion_ceiling_tokens`` is a configured maximum, not consumption.
  * No monetary cost is computed or capped. Passing every check says nothing about statistical validity
    and does not make a live run safe or authorized.

Summaries and ``BudgetAbort`` messages hold counts, enumerated strings, bounded category tokens and
exception CLASS NAMES only: never prompts, model output, keys, headers, provider error bodies or raw
exception messages.
"""

from __future__ import annotations

import enum
import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from maps.llm_client import ApiDisabledError
from maps.runs.live_policy import AccountingBasis, LivePolicy, PolicyError
from maps.schemas import LLMResult

_HTTP_PREFIX = re.compile(r"http_([0-9]{3}): ")
_REDIRECT_LOOP = re.compile(r"request_exception: TooManyRedirects\Z")
_REQUEST_EXCEPTION_PREFIX = "request_exception: "
_API_ERROR_PREFIX = "api_error: "
_MALFORMED_PREFIX = "malformed_api_response: "

IN_FLIGHT_NOTE = "the deadline is checked between calls only; a call already in flight is not cancelled"
USAGE_TOTALS_BASIS = (
    "provider-reported usage from calls that supplied it; missing usage is not counted as zero (a total of 0 with "
    "usage_missing above 0 means none was supplied); totals are lower bounds"
)
CEILING_BASIS = "sum of the configured max_tokens of calls started; a requested maximum, not measured usage"
CLAIM_CLIENT_ATTEMPTS = "client-level attempts; redirect hops are not guaranteed to be counted"
CLAIM_STRICT_PHYSICAL = (
    "bounded count of client-reported attempts; exact stock requests.Session, redirects off on every attempt; "
    "sockets and sends are not counted independently"
)


class ErrorClass(enum.Enum):
    SUCCESS = "success"
    FATAL = "fatal"
    NONFATAL = "nonfatal"


class AbortReason(enum.Enum):
    FATAL_ERROR = "fatal_error"
    DISABLED_CLIENT = "disabled_client"
    CONSECUTIVE_ERRORS = "consecutive_errors"
    REQUEST_BUDGET = "request_budget"
    EPISODE_CAP = "episode_cap"
    DEADLINE = "deadline"
    UNEXPECTED_CLIENT_EXCEPTION = "unexpected_client_exception"


_ABORT_TEXT = {
    AbortReason.FATAL_ERROR: "stopped after a fatal client error",
    AbortReason.DISABLED_CLIENT: "stopped: the client is disabled",
    AbortReason.CONSECUTIVE_ERRORS: "stopped after the consecutive-error threshold was reached",
    AbortReason.REQUEST_BUDGET: "stopped: the request-attempt budget cannot cover another call",
    AbortReason.EPISODE_CAP: "stopped: the episode cap was reached",
    AbortReason.DEADLINE: "stopped: the wall-clock deadline was reached",
    AbortReason.UNEXPECTED_CLIENT_EXCEPTION: "stopped after an unexpected client exception",
}


class BudgetAbort(RuntimeError):
    """A policy limit stopped the run. The message is fixed text for the reason, never provider text."""

    def __init__(self, reason: AbortReason):
        super().__init__(_ABORT_TEXT[reason])
        self.reason = reason


def classify_result(result: LLMResult, policy: LivePolicy) -> tuple[ErrorClass, str]:
    """Classify a returned result as (class, bounded category token).

    The existing result type has no typed error fields, so classification uses the client's error
    strings, matched at the START only. Nothing after the prefix can change the class."""
    error = result.error
    if error is None:
        if isinstance(result.content, str):
            return ErrorClass.SUCCESS, "ok"
        return ErrorClass.NONFATAL, "empty_response"
    if not isinstance(error, str):
        return ErrorClass.NONFATAL, "unclassified"
    match = _HTTP_PREFIX.match(error)
    if match:
        code = int(match.group(1))
        category = f"http_{code}"
        if 300 <= code <= 399:
            return (ErrorClass.FATAL if policy.fatal_3xx else ErrorClass.NONFATAL), category
        if 400 <= code <= 499:
            return (ErrorClass.NONFATAL if code in policy.nonfatal_4xx_statuses else ErrorClass.FATAL), category
        return ErrorClass.NONFATAL, category
    if _REDIRECT_LOOP.match(error):
        return ErrorClass.FATAL, "request_exception_too_many_redirects"
    if error.startswith(_REQUEST_EXCEPTION_PREFIX):
        return ErrorClass.NONFATAL, "request_exception"
    if error.startswith(_API_ERROR_PREFIX):
        return ErrorClass.NONFATAL, "api_error"
    if error.startswith(_MALFORMED_PREFIX):
        return ErrorClass.NONFATAL, "malformed_api_response"
    return ErrorClass.NONFATAL, "unclassified"


def _valid_tokens(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


@dataclass(frozen=True)
class BudgetSummary:
    """Bounded, non-sensitive snapshot. Mapping-like fields are tuples of (key, count) pairs."""

    accounting_basis: str
    accounting_claim: str
    redirect_exposure: str                      # "not_counted" | "none_redirects_disabled"
    attempts_cap: int
    reserved_attempts_per_call: int
    attempts_charged: int
    attempt_count_untrusted: int
    logical_calls_started: int
    calls_returned: int
    calls_success: int
    calls_fatal: int
    calls_nonfatal: int
    calls_raised: int
    error_category_counts: tuple[tuple[str, int], ...]
    consecutive_errors_current: int
    consecutive_errors_peak: int
    max_consecutive_nonfatal_errors: int
    stop_reason: str | None
    deadline_seconds: int
    elapsed_seconds_at_last_check: float
    deadline_crossed_by_inflight_call: bool
    in_flight_note: str
    usage_complete: int
    usage_partial: int
    usage_missing: int
    usage_invalid: int
    provider_reported_prompt_tokens: int
    provider_reported_completion_tokens: int
    provider_reported_total_tokens: int
    usage_totals_basis: str
    requested_completion_ceiling_tokens: int
    requested_ceiling_basis: str
    exception_class_counts: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict:
        data = dict(self.__dict__)
        data["error_category_counts"] = dict(self.error_category_counts)
        data["exception_class_counts"] = dict(self.exception_class_counts)
        return data


class BudgetedClient:
    """Wrap an injected client with the policy's budget and stop rules (see the module docstring)."""

    def __init__(self, client, policy: LivePolicy, *, clock: Callable[[], float] = time.monotonic):
        if not isinstance(policy, LivePolicy):
            raise PolicyError("policy: must be a LivePolicy")
        name = getattr(client, "name", None)
        if not isinstance(name, str) or not name:
            raise PolicyError("client.name: must be a non-empty string")
        retries = getattr(client, "max_retries", None)
        if isinstance(retries, bool) or not isinstance(retries, int):
            raise PolicyError("client.max_retries: must be exposed as an integer")
        if retries != policy.max_retries:
            raise PolicyError("client.max_retries: does not match the approved policy retry count")
        if policy.accounting_basis is AccountingBasis.STRICT_PHYSICAL and getattr(client, "redirects_disabled", None) is not True:
            raise PolicyError("client.redirects_disabled: strict physical accounting needs a client that declares redirects disabled")
        self._client = client
        self._policy = policy
        self._clock = clock
        self.name = name
        self._t0 = clock()
        self._elapsed = 0.0
        self._stop: AbortReason | None = None
        self._charged = 0
        self._untrusted = 0
        self._started = 0
        self._success = self._fatal = self._nonfatal = self._raised = 0
        self._consecutive = self._peak = 0
        self._crossed = False
        self._categories: Counter[str] = Counter()
        self._exceptions: Counter[str] = Counter()
        self._usage = Counter(complete=0, partial=0, missing=0, invalid=0)
        self._tokens = Counter(prompt=0, completion=0, total=0)
        self._ceiling = 0

    def __repr__(self) -> str:
        return f"BudgetedClient(name={self.name!r}, basis={self._policy.accounting_basis.value!r})"

    # -- internals -------------------------------------------------------------------------------
    def _set_stop(self, reason: AbortReason) -> None:
        if self._stop is None:
            self._stop = reason

    def _refuse(self, reason: AbortReason):
        self._set_stop(reason)
        raise BudgetAbort(self._stop)  # the first recorded stop stays the reason

    def _record_usage(self, result: LLMResult) -> None:
        names = ("prompt", "completion", "total")
        values = [getattr(result, f"{n}_tokens", None) for n in names]
        present = [v is not None for v in values]
        valid = [_valid_tokens(v) for v in values]
        for name, value, ok in zip(names, values, valid):
            if ok:
                self._tokens[name] += value
        if any(p and not ok for p, ok in zip(present, valid)):
            self._usage["invalid"] += 1
        elif all(valid):
            self._usage["complete"] += 1
        elif any(valid):
            self._usage["partial"] += 1
        else:
            self._usage["missing"] += 1

    # -- the client surface ----------------------------------------------------------------------
    def complete(self, request) -> LLMResult:
        if self._stop is not None:
            raise BudgetAbort(self._stop)
        self._elapsed = self._clock() - self._t0
        if self._elapsed >= self._policy.deadline_seconds:
            self._refuse(AbortReason.DEADLINE)
        if self._started >= self._policy.max_episodes:
            self._refuse(AbortReason.EPISODE_CAP)
        reservation = self._policy.reservation_per_call
        if self._charged + reservation > self._policy.max_request_attempts:
            self._refuse(AbortReason.REQUEST_BUDGET)
        self._started += 1
        ceiling = getattr(request, "max_tokens", None)
        if _valid_tokens(ceiling):
            self._ceiling += ceiling
        try:
            result = self._client.complete(request)
        except ApiDisabledError:
            self._charged += reservation
            self._raised += 1
            self._exceptions["ApiDisabledError"] += 1
            self._set_stop(AbortReason.DISABLED_CLIENT)
            raise BudgetAbort(AbortReason.DISABLED_CLIENT) from None
        except BaseException as exc:  # the attempts used are unknown: charge the full reservation, keep the exception as is
            self._charged += reservation
            self._raised += 1
            self._exceptions[type(exc).__name__] += 1
            self._set_stop(AbortReason.UNEXPECTED_CLIENT_EXCEPTION)
            raise
        if not isinstance(result, LLMResult):
            self._charged += reservation
            self._raised += 1
            self._exceptions["InvalidResultType"] += 1
            self._set_stop(AbortReason.UNEXPECTED_CLIENT_EXCEPTION)
            raise BudgetAbort(AbortReason.UNEXPECTED_CLIENT_EXCEPTION)
        attempts = result.attempts
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= reservation:
            self._charged += reservation
            self._untrusted += 1
        else:
            self._charged += attempts
        error_class, category = classify_result(result, self._policy)
        self._categories[category] += 1
        if error_class is ErrorClass.SUCCESS:
            self._success += 1
            self._consecutive = 0
        else:
            self._consecutive += 1
            self._peak = max(self._peak, self._consecutive)
            if error_class is ErrorClass.FATAL:
                self._fatal += 1
                self._set_stop(AbortReason.FATAL_ERROR)
            else:
                self._nonfatal += 1
                if self._consecutive >= self._policy.max_consecutive_nonfatal_errors:
                    self._set_stop(AbortReason.CONSECUTIVE_ERRORS)
        self._record_usage(result)
        self._elapsed = self._clock() - self._t0
        if self._elapsed > self._policy.deadline_seconds:
            self._crossed = True
        if self._elapsed >= self._policy.deadline_seconds:
            self._set_stop(AbortReason.DEADLINE)
        return result

    def summary(self) -> BudgetSummary:
        strict = self._policy.accounting_basis is AccountingBasis.STRICT_PHYSICAL
        return BudgetSummary(
            accounting_basis=self._policy.accounting_basis.value,
            accounting_claim=CLAIM_STRICT_PHYSICAL if strict else CLAIM_CLIENT_ATTEMPTS,
            redirect_exposure="none_redirects_disabled" if strict else "not_counted",
            attempts_cap=self._policy.max_request_attempts,
            reserved_attempts_per_call=self._policy.reservation_per_call,
            attempts_charged=self._charged,
            attempt_count_untrusted=self._untrusted,
            logical_calls_started=self._started,
            calls_returned=self._success + self._fatal + self._nonfatal,
            calls_success=self._success,
            calls_fatal=self._fatal,
            calls_nonfatal=self._nonfatal,
            calls_raised=self._raised,
            error_category_counts=tuple(sorted((k, v) for k, v in self._categories.items() if k != "ok")),
            consecutive_errors_current=self._consecutive,
            consecutive_errors_peak=self._peak,
            max_consecutive_nonfatal_errors=self._policy.max_consecutive_nonfatal_errors,
            stop_reason=self._stop.value if self._stop else None,
            deadline_seconds=self._policy.deadline_seconds,
            elapsed_seconds_at_last_check=self._elapsed,
            deadline_crossed_by_inflight_call=self._crossed,
            in_flight_note=IN_FLIGHT_NOTE,
            usage_complete=self._usage["complete"],
            usage_partial=self._usage["partial"],
            usage_missing=self._usage["missing"],
            usage_invalid=self._usage["invalid"],
            provider_reported_prompt_tokens=self._tokens["prompt"],
            provider_reported_completion_tokens=self._tokens["completion"],
            provider_reported_total_tokens=self._tokens["total"],
            usage_totals_basis=USAGE_TOTALS_BASIS,
            requested_completion_ceiling_tokens=self._ceiling,
            requested_ceiling_basis=CEILING_BASIS,
            exception_class_counts=tuple(sorted(self._exceptions.items())),
        )
