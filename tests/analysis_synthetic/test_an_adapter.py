"""EpisodeResult -> AnalysisRow adapter (SYNTHETIC episode results built in code; no files, no real data)."""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

import maps.adapters.episode_results as adapter_module
import maps.analysis as analysis
from maps.adapters.episode_results import InconsistentModelMappingError, TracedRow, episode_results_to_rows
from maps.analysis import AnalysisRow, DuplicateRowError, InvalidRowsError, aggregate_to_scenario, validate_rows
from maps.schemas import EpisodeResult, EpisodeSpec, PlanItem, ReceiverResponse

from an_support import ok

SHAPES = {"C0": (0, 0), "C1": (1, 1), "C2": (2, 1), "C3": (4, 1), "C4": (2, 2), "C5": (4, 4)}


def make_result(
    *, alias="alpha", model_id="synthetic/alpha", scenario="s1", pair="p1", truth="true", cond="C4",
    variant="neutral", rep=0, episode_id="ep_000000000001", seed=1234, status="ok",
    accepts=True, confidence=80, roots=3, error="ignored failure text",
) -> EpisodeResult:
    n_messages, n_roots = SHAPES[cond]
    plan = [
        PlanItem(position=k, relay_id=f"Relay-{k + 1}", template_idx=k, root_id=f"{scenario}-R{k % n_roots + 1}")
        for k in range(n_messages)
    ]
    spec = EpisodeSpec(
        episode_id=episode_id, model_alias=alias, model_id=model_id, scenario_id=scenario, pair_id=pair,
        truth_status=truth, condition_id=cond, n_messages=n_messages, n_roots=n_roots, prompt_variant=variant,
        repetition=rep, seed=seed, message_plan=plan,
    )
    if status == "ok":
        response = ReceiverResponse(
            accepts_claim=accepts, confidence=confidence, estimated_independent_roots=roots,
            evidence_used=["message 1"], reasoning="SYNTHETIC reasoning that must not leak",
        )
        return EpisodeResult(spec=spec, status="ok", response=response)
    return EpisodeResult(spec=spec, status=status, error=error)


def test_a_successful_episode_maps_field_by_field():
    result = make_result(variant="source-aware", rep=3, accepts=False, confidence=35, roots=3, episode_id="ep_abc")
    (row,) = episode_results_to_rows([result])
    assert isinstance(row, AnalysisRow) and isinstance(row, TracedRow)
    assert (row.model_alias, row.prompt_variant, row.scenario_id, row.pair_id) == ("alpha", "source-aware", "s1", "p1")
    assert (row.condition_id, row.repetition, row.status) == ("C4", 3, "ok")
    assert (row.accepts_claim, row.confidence, row.estimated_roots) == (False, 35, 3)
    assert (row.n_messages, row.n_roots) == (2, 2)
    assert row.episode_id == "ep_abc"
    assert row.key == ("alpha", "source-aware", "s1", "C4", 3)


@pytest.mark.parametrize("status", ["call_error", "parse_error"])
def test_failed_episodes_keep_their_status_and_carry_no_outcomes(status):
    (row,) = episode_results_to_rows([make_result(status=status, error="boom: model said something private")])
    assert row.status == status
    assert (row.accepts_claim, row.confidence, row.estimated_roots) == (None, None, None)
    assert "boom" not in repr(row) and "private" not in repr(row)  # error text is never exposed


def test_zero_message_control_keeps_zero_roots():
    (row,) = episode_results_to_rows([make_result(cond="C0", roots=0)])
    assert (row.n_messages, row.n_roots, row.estimated_roots) == (0, 0, 0)


def test_truth_labels_are_absent_by_default_and_present_when_opted_in():
    results = [make_result(scenario="s1", truth="true"), make_result(scenario="s2", truth="false")]
    assert [r.truth_label for r in episode_results_to_rows(results)] == [None, None]
    assert [r.truth_label for r in episode_results_to_rows(results, include_truth_labels=True)] == ["true", "false"]


def test_episode_id_is_optional_traceability_metadata_outside_the_key():
    result = make_result(episode_id="ep_trace")
    assert episode_results_to_rows([result])[0].episode_id == "ep_trace"
    assert episode_results_to_rows([result], include_episode_id=False)[0].episode_id is None
    # the generic key does not include it: two rows differing only in episode_id are duplicates
    twin = make_result(episode_id="ep_other")
    with pytest.raises(DuplicateRowError):
        episode_results_to_rows([result, twin])


def test_only_the_approved_fields_are_exposed_and_rotation_is_not_inferred():
    (row,) = episode_results_to_rows([make_result()])
    generic = {f.name for f in dataclasses.fields(AnalysisRow)}
    assert {f.name for f in dataclasses.fields(row)} == generic | {"episode_id"}
    for hidden in ("rotation", "seed", "message_plan", "error", "reasoning", "evidence_used", "model_id"):
        assert not hasattr(row, hidden)
    assert "rotation" not in EpisodeSpec.model_fields  # the source representation has no rotation field
    assert row.repetition == 0 and make_result(rep=2).spec.repetition == 2
    assert episode_results_to_rows([make_result(rep=2)])[0].repetition == 2  # copied, not reinterpreted


def test_input_order_is_preserved_and_nothing_is_imputed():
    results = [make_result(rep=2), make_result(rep=0), make_result(rep=1, status="parse_error")]
    rows = episode_results_to_rows(results)
    assert [r.repetition for r in rows] == [2, 0, 1]
    assert len(rows) == 3 and rows[2].confidence is None


def test_duplicate_analysis_keys_are_rejected():
    with pytest.raises(DuplicateRowError):
        episode_results_to_rows([make_result(episode_id="ep_1"), make_result(episode_id="ep_2")])


def test_an_alias_must_map_to_one_model_id():
    good = [make_result(model_id="synthetic/alpha", rep=0), make_result(model_id="synthetic/alpha", rep=1)]
    assert len(episode_results_to_rows(good)) == 2
    bad = [make_result(model_id="synthetic/alpha", rep=0), make_result(model_id="synthetic/other", rep=1)]
    with pytest.raises(InconsistentModelMappingError, match="alpha"):
        episode_results_to_rows(bad)
    two_aliases_one_id = [make_result(alias="a", rep=0), make_result(alias="b", rep=0)]
    assert len(episode_results_to_rows(two_aliases_one_id)) == 2  # only alias -> id must be single-valued


def test_the_existing_row_validation_contract_is_applied():
    inconsistent_pair = [make_result(cond="C2", pair="p1", roots=1), make_result(cond="C4", pair="p9", roots=2)]
    with pytest.raises(InvalidRowsError) as exc:
        episode_results_to_rows(inconsistent_pair)
    assert exc.value.issues[0].code == "pair_id_inconsistent"
    with pytest.raises(TypeError):
        episode_results_to_rows([{"not": "an EpisodeResult"}])


def test_empty_input_gives_no_rows():
    assert episode_results_to_rows([]) == []
    assert episode_results_to_rows(iter(())) == []


def test_the_output_feeds_the_generic_functions_unchanged():
    results = [
        make_result(cond="C2", rep=0, confidence=50, roots=1), make_result(cond="C2", rep=1, confidence=60, roots=1),
        make_result(cond="C4", rep=0, confidence=70, roots=2), make_result(cond="C4", rep=1, confidence=90, roots=2, status="parse_error"),
    ]
    rows = episode_results_to_rows(results)
    assert validate_rows(rows).ok
    cells = {c.condition_id: c for c in aggregate_to_scenario(rows, "confidence").cells}
    assert (cells["C2"].value, cells["C2"].n_valid) == (55.0, 2)
    assert (cells["C4"].value, cells["C4"].n_valid, cells["C4"].n_invalid) == (70.0, 1, 1)


def test_the_generic_package_does_not_depend_on_the_adapter_and_the_adapter_does_no_io():
    package_dir = Path(analysis.__file__).resolve().parent
    for path in package_dir.glob("*.py"):
        assert "adapters" not in path.read_text(encoding="utf-8"), path.name
    tree = ast.parse(Path(adapter_module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "collections", "dataclasses", "maps"}


# ---------------------------------------------------------------------------
# Edge cases and interoperability (v2.3.17)
# ---------------------------------------------------------------------------
from maps.analysis import invalid_bounds, invalid_response_report, paired_scenario_diffs, stratified_summary  # noqa: E402
from maps.analysis.provisional import coverage_report, root_metrics  # noqa: E402


def test_a_result_mutated_into_an_inconsistent_state_is_rejected():
    failed_with_outcomes = make_result()
    failed_with_outcomes.status = "parse_error"          # the response is still attached
    with pytest.raises(InvalidRowsError) as exc:
        episode_results_to_rows([failed_with_outcomes])
    assert exc.value.issues[0].code == "outcome_on_failed_row"
    ok_without_response = make_result()
    ok_without_response.response = None                   # status stays "ok"
    with pytest.raises(InvalidRowsError) as exc:
        episode_results_to_rows([ok_without_response])
    assert exc.value.issues[0].code == "missing_outcome"


def test_both_optional_flags_together():
    results = [make_result(scenario="s1", truth="true", episode_id="ep_a"), make_result(scenario="s2", truth="false", episode_id="ep_b")]
    rows = episode_results_to_rows(results, include_truth_labels=True, include_episode_id=False)
    assert [(r.truth_label, r.episode_id) for r in rows] == [("true", None), ("false", None)]
    rows = episode_results_to_rows(results, include_truth_labels=False, include_episode_id=True)
    assert [(r.truth_label, r.episode_id) for r in rows] == [(None, "ep_a"), (None, "ep_b")]


def test_a_traced_row_and_a_plain_row_with_the_same_generic_key_are_duplicates():
    (traced,) = episode_results_to_rows([make_result(episode_id="ep_traced")])
    plain = ok("alpha", "s1", "C4", 0)
    assert type(traced) is TracedRow and type(plain) is AnalysisRow and traced.key == plain.key
    assert traced != plain  # different classes compare unequal, yet the generic key still collides
    for rows in ([traced, plain], [plain, traced]):
        with pytest.raises(DuplicateRowError):
            validate_rows(rows)


def test_generic_functions_consume_traced_rows_without_relying_on_episode_id():
    results = [
        make_result(cond="C2", rep=0, confidence=50, roots=1, episode_id="ep_1"), make_result(cond="C2", rep=1, confidence=60, roots=2, episode_id="ep_2"),
        make_result(cond="C4", rep=0, confidence=70, roots=2, episode_id="ep_3"), make_result(cond="C4", rep=1, status="call_error", episode_id="ep_4"),
        make_result(cond="C0", rep=0, roots=0, episode_id="ep_5"),
    ]
    with_ids = episode_results_to_rows(results)
    without_ids = episode_results_to_rows(results, include_episode_id=False)
    assert [r.episode_id for r in with_ids] == ["ep_1", "ep_2", "ep_3", "ep_4", "ep_5"] and {r.episode_id for r in without_ids} == {None}
    keys = [r.key for r in with_ids]
    for compute in (
        lambda rows: aggregate_to_scenario(rows, "confidence"),
        lambda rows: paired_scenario_diffs(aggregate_to_scenario(rows, "confidence"), "C4", "C2"),
        lambda rows: invalid_response_report(rows),
        lambda rows: invalid_bounds(rows),
        lambda rows: stratified_summary(rows, "confidence", interval_method=None),
        lambda rows: root_metrics(rows),
        lambda rows: coverage_report(rows, keys),
    ):
        assert compute(with_ids) == compute(without_ids)
    # hand values: C2 cell (50 + 60) / 2; C4 cell 70 with one failed episode; C0 is zero-root
    cells = {c.condition_id: c for c in aggregate_to_scenario(with_ids, "confidence").cells}
    assert (cells["C2"].value, cells["C4"].value, cells["C4"].n_invalid) == (55.0, 70.0, 1)
    metrics = {m.condition_id: m for m in root_metrics(with_ids)}
    assert metrics["C0"].n_zero_root == 1 and metrics["C0"].mean_error is None
    assert metrics["C2"].mean_error == 0.5 and metrics["C4"].mean_error == 0.0 and metrics["C4"].n_invalid == 1


def test_traced_and_plain_rows_can_be_mixed_when_their_keys_differ():
    (traced,) = episode_results_to_rows([make_result(cond="C4", rep=0, confidence=70, roots=2)])
    plain = ok("alpha", "s1", "C2", 0, conf=50, roots=1)
    mixed = aggregate_to_scenario([plain, traced], "confidence")
    assert {c.condition_id: c.value for c in mixed.cells} == {"C2": 50.0, "C4": 70.0}
    (diff,) = paired_scenario_diffs(mixed, "C4", "C2")
    assert diff.values == (20.0,)
