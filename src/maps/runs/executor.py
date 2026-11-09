"""Mock-only run executor: the mock input policy around the shared run lifecycle.

``execute_mock_run`` applies the MOCK-ONLY input checks (valid run id, a client named ``"mock"``, a
configuration that does not enable live API calls, a well-formed inventory and provenance options) and
then hands the run to ``maps.runs.lifecycle.run_lifecycle``, which performs the integrity sequence: claim
the directory, record pre-run provenance (the runner is not started if that fails), call the injected
runner exactly once, check provenance drift, load and validate the results, and write the integrity
report. See that module for the exact order and for what a passing run does and does not establish.

Nothing is retried, resumed, appended to, cleaned up or overwritten, and partial output is always left in
place. A run directory without ``run_integrity.json`` is incomplete and never eligible for analysis.

Boundaries: this module never constructs a model client, never imports the CLI (``receiver``) or any
live client, and has no network or subprocess code. It accepts only a client named ``"mock"``; there is
no live option. The collaborators it passes down (provenance collection and writing, the event-log class)
are looked up here at call time, so they can be substituted on this module.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

from maps.runs.ids import validate_run_id
from maps.runs.integrity_report import EventLog
from maps.runs.lifecycle import (
    ALLOWED_PROVENANCE_OPTIONS,
    ExecutionOutcome,
    RunNotEligibleError,
    provenance_drift,
    refused,
    run_lifecycle,
    validate_inventory,
    validate_provenance_options,
)
from maps.runs.provenance import collect_provenance, write_provenance

MODE = "mock"

__all__ = [
    "ALLOWED_PROVENANCE_OPTIONS", "MODE", "ExecutionOutcome", "RunNotEligibleError", "execute_mock_run", "provenance_drift",
]


def execute_mock_run(
    *,
    run_fn: Callable,
    cfg,
    scenarios: Sequence,
    client,
    run_dir: str | Path,
    run_id: str,
    repo_root: str | Path,
    expected_episode_ids: Iterable[str] | None = None,
    provenance_options: Mapping | None = None,
    clock: Callable[[], str] | None = None,
) -> ExecutionOutcome:
    """Run ``run_fn`` once inside the integrity lifecycle (see the module docstring).

    ``run_fn`` has the signature of the existing runner: ``run_fn(cfg, scenarios, client, run_dir,
    secrets, repo_root) -> list[EpisodeResult]``. The caller constructs ``client``; this function never
    does. ``clock`` (returns a UTC time string) can be injected for deterministic tests.
    """
    out = Path(run_dir)
    inventory = list(expected_episode_ids) if expected_episode_ids is not None else None

    # mock-only input policy (nothing is written if any of these fails)
    try:
        validate_run_id(run_id)
        if getattr(client, "name", None) != MODE:
            raise ValueError("only a client named 'mock' is allowed")
        if cfg.api.enabled:
            raise ValueError("the configuration enables live API calls; the mock executor refuses it")
        validate_inventory(inventory)
        options = validate_provenance_options(provenance_options)
    except ValueError as exc:
        return refused(run_id, out, "inputs", str(exc))

    return run_lifecycle(
        run_dir=out, run_id=run_id, execution_mode=MODE, repo_root=repo_root,
        invoke_runner=lambda: run_fn(cfg, list(scenarios), client, out, None, Path(repo_root)),
        inventory=inventory, options=options, clock=clock,
        collect_provenance_fn=collect_provenance, write_provenance_fn=write_provenance, event_log_factory=EventLog,
    )
