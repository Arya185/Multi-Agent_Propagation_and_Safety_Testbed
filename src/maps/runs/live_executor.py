"""Live run executor (Stage 3): the live input policy and budget wrapper around the shared run lifecycle.

STATUS: implemented and tested OFFLINE only, with fake clients. Nothing calls this module yet (no CLI
integration), it reads no credentials and no environment, and it never builds a provider client: the caller
supplies a ``client_factory``. It does not make a run safe, authorized or live-ready by itself.

``execute_live_run`` applies the LIVE input checks and then hands the run to
``maps.runs.lifecycle.run_lifecycle`` with hooks. Order:

  1. validate inputs (run id, callables, an explicit ``LivePolicy``, ``cfg.api.enabled`` true, the config's
     retry count equal to the policy's, an explicit planned-grid inventory whose size equals the policy's
     ``planned_episodes``, redaction values, provenance options). Nothing is written and the factory is NOT
     called if any check fails;
  2. claim the directory, append ``run_claimed``, record pre-run provenance (shared lifecycle). The factory is
     NOT called if either fails;
  3. ``prepare``: call ``client_factory()`` once and wrap the result in exactly ONE ``BudgetedClient`` for the
     whole run. A refusal here (for example strict-physical accounting with an unsupported client) is stage
     ``client_construction`` and the runner is never started;
  4. ``runner_started``; call ``run_fn`` exactly once with the wrapper as its client, so every model request
     of every episode, condition, variant and model passes through the same budget state;
  5. outcomes: a ``BudgetAbort`` is stage ``policy_stop`` (a distinct event and reason code, partial output
     validated as evidence); a policy stop recorded by the wrapper while the runner still returned normally
     (for example on the final call) is ALSO stage ``policy_stop``; any other runner exception is stage
     ``runner``; a ``KeyboardInterrupt`` is recorded best-effort as stage ``interrupted`` and then re-raised;
  6. post-run provenance, drift, loader, inventory and the integrity report (shared lifecycle), with a
     ``live`` block holding the policy and the budget summary.

Every failure stage makes the run ineligible for analysis. Provider errors inside episode results
(``call_error``) stay ordinary results; they are not exceptions and not policy stops by themselves.

DECISIONS NOT MADE HERE (owner decisions): whether a COMPLETE grid whose wrapper recorded a stop reason on its
final call may be eligible (this module applies the conservative answer: ineligible), the quality rule for
``call_error`` episodes, and any recovery or continuation. There is no resume, retry, append or override.

LIMITS: the deadline starts when the wrapper is built, after the factory returns and after pre-run provenance;
one event append sits between construction and the first call. A call already in flight is never cancelled.
Per-model limits are not supported (the runner uses one client for all models). Strict-physical accounting is a
bounded accounting mode that relies on the client declaring redirects disabled and on stock-session behavior;
it is not proof of the physical request count. The redaction values are used only to scrub runner output; they
are never stored in the report, the events or this module's state beyond the call.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

from maps.runs.ids import validate_run_id
from maps.runs.integrity_report import EventLog
from maps.runs.lifecycle import (
    ExecutionOutcome,
    LifecycleHooks,
    RunnerFailure,
    refused,
    run_lifecycle,
    validate_inventory,
    validate_provenance_options,
)
from maps.runs.live_budget import BudgetAbort, BudgetedClient
from maps.runs.live_policy import LivePolicy
from maps.runs.provenance import collect_provenance, write_provenance

MODE = "live"
REPORT_EVENT = "integrity_report_written"

__all__ = ["MODE", "execute_live_run"]

_ELIGIBILITY_NOTE = (
    "A policy stop recorded by the budget wrapper makes the run ineligible, including a stop recorded on the final "
    "call of an otherwise complete grid. Whether such a grid may be eligible is an owner decision; the conservative "
    "answer is applied."
)
_REDACTION_NOTE = "Redaction values are used only to scrub runner output and are never stored."
_POLICY_RECORD_MAX_BYTES = 4096
_POLICY_RECORD_MAX_DEPTH = 3
_SECRET_WORDS = frozenset({"key", "secret", "password", "credential", "credentials", "authorization", "bearer"})
_SECRET_NAMES = frozenset({"token", "api_token", "access_token", "apikey"})


def _validate_policy_record(record, redactions: Sequence[str]) -> dict:
    """A plain, bounded, secret-free copy of the policy record (Stage 4E, PS-15 option A), else ``ValueError``.

    Keys are identifiers; values are strings, integers, booleans or nested records (depth at most 3); the JSON form is at
    most 4 KB; no key names a secret; no redaction value appears anywhere in it. The record states WHICH policy was used;
    it is not an authentication of who approved it."""
    def check(value, depth: int) -> None:
        if depth > _POLICY_RECORD_MAX_DEPTH:
            raise ValueError("policy_record is nested too deeply")
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str) or not key.isidentifier() or (set(key.lower().split("_")) & _SECRET_WORDS) or key.lower() in _SECRET_NAMES:
                    raise ValueError("policy_record has an unsupported key")
                check(item, depth + 1)
        elif not (isinstance(value, (str, bool)) or (isinstance(value, int) and not isinstance(value, bool))):
            raise ValueError("policy_record has an unsupported value type")

    if not isinstance(record, Mapping):
        raise ValueError("policy_record must be a mapping")
    plain = json.loads(json.dumps(dict(record), sort_keys=True)) if all(isinstance(k, str) for k in record) else None
    if plain is None:
        raise ValueError("policy_record has an unsupported key")
    check(plain, 1)
    text = json.dumps(plain, sort_keys=True)
    if len(text.encode("utf-8")) > _POLICY_RECORD_MAX_BYTES:
        raise ValueError("policy_record is too large")
    if any(secret and secret in text for secret in redactions):
        raise ValueError("policy_record must not contain a redaction value")
    return plain


class _RunState:
    """Mutable facts about this one run, shared by the hook closures."""

    def __init__(self) -> None:
        self.factory_called = False
        self.wrapper: BudgetedClient | None = None
        self.policy_stop_reason: str | None = None
        self.policy_stop_raised = False


def execute_live_run(
    *,
    run_fn: Callable,
    cfg,
    scenarios: Sequence,
    client_factory: Callable[[], object],
    policy: LivePolicy,
    run_dir: str | Path,
    run_id: str,
    repo_root: str | Path,
    expected_episode_ids: Iterable[str],
    redaction_values: Sequence[str] = (),
    provenance_options: Mapping | None = None,
    clock: Callable[[], str] | None = None,
    budget_clock: Callable[[], float] | None = None,
    policy_record: Mapping | None = None,
) -> ExecutionOutcome:
    """Run ``run_fn`` once inside the integrity lifecycle with a budget-enforcing client (see the module docstring).

    ``run_fn`` has the signature of the existing runner: ``run_fn(cfg, scenarios, client, run_dir, secrets,
    repo_root) -> list[EpisodeResult]``; it receives the single ``BudgetedClient`` and ``list(redaction_values)``
    as its ``secrets``. ``client_factory()`` returns the model client; this function never builds one.
    ``expected_episode_ids`` is the explicitly supplied planned grid. ``clock`` (UTC time strings for events) and
    ``budget_clock`` (seconds, for the deadline) can be injected for deterministic tests. ``policy_record`` (optional,
    Stage 4E) is a bounded, secret-free description of the policy and endpoint the caller validated; it is stored under
    ``live.policy_source`` in the report and is validated before anything is written."""
    out = Path(run_dir)

    # live input policy (nothing is written and the factory is not called if any of these fails)
    try:
        validate_run_id(run_id)
        if not callable(run_fn):
            raise ValueError("run_fn must be callable")
        if not callable(client_factory):
            raise ValueError("client_factory must be callable")
        if not isinstance(policy, LivePolicy):
            raise ValueError("policy must be a LivePolicy")
        if getattr(getattr(cfg, "api", None), "enabled", None) is not True:
            raise ValueError("the configuration does not enable live API calls")
        retries = getattr(cfg.api, "max_retries", None)
        if isinstance(retries, bool) or retries != policy.max_retries:
            raise ValueError("the configured api max_retries does not match the policy retry count")
        if expected_episode_ids is None:
            raise ValueError("expected_episode_ids is required for a live run")
        try:
            inventory = list(expected_episode_ids)
        except TypeError:
            raise ValueError("expected_episode_ids must be an iterable of episode ids") from None
        validate_inventory(inventory)
        if len(set(inventory)) != len(inventory):
            raise ValueError("expected_episode_ids must be unique")
        if len(inventory) != policy.planned_episodes:
            raise ValueError("expected_episode_ids does not match the policy planned_episodes")
        redactions = list(redaction_values)
        if not all(isinstance(v, str) and v for v in redactions):
            raise ValueError("redaction_values must be non-empty strings")
        options = validate_provenance_options(provenance_options)
        record = None if policy_record is None else _validate_policy_record(policy_record, redactions)
    except ValueError as exc:
        return refused(run_id, out, "inputs", str(exc))

    state = _RunState()

    def prepare() -> None:
        state.factory_called = True
        client = client_factory()
        kwargs = {} if budget_clock is None else {"clock": budget_clock}
        state.wrapper = BudgetedClient(client, policy, **kwargs)   # one wrapper for the whole run

    def invoke_runner():
        return run_fn(cfg, list(scenarios), state.wrapper, out, list(redactions), Path(repo_root))

    def classify_runner_exception(exc: Exception) -> RunnerFailure | None:
        if not isinstance(exc, BudgetAbort):
            return None
        state.policy_stop_reason, state.policy_stop_raised = exc.reason.value, True
        return RunnerFailure(
            stage="policy_stop", event="policy_stop", detail=f"stopped by policy: {exc.reason.value}",
            event_fields={"reason": exc.reason.value, "raised": True},
        )

    def post_runner_check() -> RunnerFailure | None:
        reason = state.wrapper.summary().stop_reason if state.wrapper is not None else None
        if reason is None:
            return None
        state.policy_stop_reason, state.policy_stop_raised = reason, False
        return RunnerFailure(
            stage="policy_stop", event="policy_stop",
            detail=f"policy stop recorded although the runner returned normally: {reason}",
            event_fields={"reason": reason, "raised": False},
        )

    def live_block() -> dict:
        summary = state.wrapper.summary() if state.wrapper is not None else None
        return {
            "policy": policy.to_dict(),
            "client_factory_called": state.factory_called,
            "budget_wrapper_created": state.wrapper is not None,
            "budget": summary.to_dict() if summary is not None else None,
            "wrapper_stop_reason": summary.stop_reason if summary is not None else None,
            "policy_stop_recorded": state.policy_stop_reason is not None,
            "policy_stop_reason": state.policy_stop_reason,
            "policy_stop_raised_by_wrapper": state.policy_stop_raised,
            "eligibility_note": _ELIGIBILITY_NOTE,
            "redaction_note": _REDACTION_NOTE,
            **({} if record is None else {"policy_source": record}),
        }

    def extra_eligibility() -> dict:
        reason = state.wrapper.summary().stop_reason if state.wrapper is not None else None
        return {"no_policy_stop": reason is None}

    hooks = LifecycleHooks(
        prepare=prepare, classify_runner_exception=classify_runner_exception, post_runner_check=post_runner_check,
        record_interruption=True, live_block=live_block, extra_eligibility=extra_eligibility, report_event=REPORT_EVENT,
    )
    return run_lifecycle(
        run_dir=out, run_id=run_id, execution_mode=MODE, repo_root=repo_root, invoke_runner=invoke_runner,
        inventory=inventory, options=options, clock=clock,
        collect_provenance_fn=collect_provenance, write_provenance_fn=write_provenance, event_log_factory=EventLog,
        hooks=hooks,
    )
