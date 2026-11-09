"""EpisodeResult -> AnalysisRow adapter (pure; no I/O; lives outside ``maps.analysis``).

Field mapping (source: ``EpisodeResult`` and its ``EpisodeSpec`` / ``ReceiverResponse``):

  AnalysisRow.model_alias      <- spec.model_alias          (model_id is checked, not carried)
  AnalysisRow.prompt_variant   <- spec.prompt_variant
  AnalysisRow.scenario_id      <- spec.scenario_id
  AnalysisRow.pair_id          <- spec.pair_id
  AnalysisRow.condition_id     <- spec.condition_id
  AnalysisRow.repetition       <- spec.repetition           (copied as is; never read as a rotation)
  AnalysisRow.status           <- status                    (ok / parse_error / call_error)
  AnalysisRow.accepts_claim    <- response.accepts_claim    (None when there is no response)
  AnalysisRow.confidence       <- response.confidence       (None when there is no response)
  AnalysisRow.estimated_roots  <- response.estimated_independent_roots (None when there is no response)
  AnalysisRow.n_messages       <- spec.n_messages
  AnalysisRow.n_roots          <- spec.n_roots              (nominal roots; always a known integer here)
  AnalysisRow.truth_label      <- spec.truth_status         ONLY when include_truth_labels=True
  TracedRow.episode_id         <- spec.episode_id           optional traceability metadata

Deliberately not exposed: error text, reasoning, evidence content, seeds, message plans, model ids.
There is no rotation field in the source representation (the realized order exists only inside the
message plan), so none is created and nothing is inferred from ``repetition``.

``TracedRow`` is an ``AnalysisRow`` subclass that adds only ``episode_id``; the generic aggregation
key (model, variant, scenario, condition, repetition) is unchanged, so every generic function accepts
it and two rows that differ only in ``episode_id`` are duplicates.

Validation (no repair, no imputation): items must be ``EpisodeResult``; duplicate analysis keys raise
``DuplicateRowError``; one ``model_alias`` must map to one ``model_id`` (otherwise
``InconsistentModelMappingError``); the mapped rows must satisfy the existing ``validate_rows``
contract (otherwise ``InvalidRowsError``). Input order is preserved.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from maps.analysis.rows import AnalysisRow, InvalidRowsError, validate_rows
from maps.schemas import EpisodeResult


class InconsistentModelMappingError(ValueError):
    """One model alias appears with more than one model id."""


@dataclass(frozen=True)
class TracedRow(AnalysisRow):
    """AnalysisRow plus optional traceability metadata; not part of the aggregation key."""

    episode_id: str | None = None


def episode_results_to_rows(
    results: Iterable[EpisodeResult],
    *,
    include_truth_labels: bool = False,
    include_episode_id: bool = True,
) -> list[TracedRow]:
    """Map episode results to analysis rows. See the module docstring for the contract."""
    rows: list[TracedRow] = []
    model_ids: dict[str, str] = {}
    for result in results:
        if not isinstance(result, EpisodeResult):
            raise TypeError(f"expected EpisodeResult, got {type(result).__name__}")
        spec, response = result.spec, result.response
        previous = model_ids.setdefault(spec.model_alias, spec.model_id)
        if previous != spec.model_id:
            raise InconsistentModelMappingError(
                f"model alias {spec.model_alias!r} maps to both {previous!r} and {spec.model_id!r}"
            )
        rows.append(
            TracedRow(
                model_alias=spec.model_alias,
                prompt_variant=spec.prompt_variant,
                scenario_id=spec.scenario_id,
                pair_id=spec.pair_id,
                condition_id=spec.condition_id,
                repetition=spec.repetition,
                status=result.status,
                accepts_claim=response.accepts_claim if response is not None else None,
                confidence=response.confidence if response is not None else None,
                estimated_roots=response.estimated_independent_roots if response is not None else None,
                n_messages=spec.n_messages,
                n_roots=spec.n_roots,
                truth_label=spec.truth_status if include_truth_labels else None,
                episode_id=spec.episode_id if include_episode_id else None,
            )
        )
    report = validate_rows(rows)  # raises DuplicateRowError on duplicate keys
    if not report.ok:
        raise InvalidRowsError(report.issues)
    return rows
