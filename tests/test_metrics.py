import pytest

from maps.experiments.metrics import (
    build_lookup,
    confidence_change_per_duplicate,
    confidence_diff_vs_control,
    contrast_gaps,
    corroboration_inflation,
    root_count_error,
    summarize,
)
from maps.schemas import EpisodeResult, EpisodeSpec, PlanItem, ReceiverResponse

COND = {"C0": (0, 0), "C1": (1, 1), "C2": (2, 1), "C3": (4, 1), "C4": (2, 2), "C5": (4, 4)}


def _res(cond, conf, accepts, est, truth="false", model="m", scen="s01", variant="neutral", rep=0, ok=True):
    n, roots = COND[cond]
    ids = ["r"] if roots == 1 else [f"r{i}" for i in range(roots)]
    plan = [
        PlanItem(position=k, relay_id=f"Relay-{k + 1}", template_idx=k, root_id=ids[k % len(ids)])
        for k in range(n)
    ]
    spec = EpisodeSpec(
        episode_id=f"ep_{model}{scen}{variant}{cond}{rep}", model_alias=model, model_id="a/b",
        scenario_id=scen, pair_id="p", truth_status=truth, condition_id=cond, n_messages=n,
        n_roots=roots, prompt_variant=variant, repetition=rep, seed=1, message_plan=plan,
    )
    if not ok:
        return EpisodeResult(spec=spec, status="parse_error", error="bad")
    return EpisodeResult(
        spec=spec, status="ok",
        response=ReceiverResponse(accepts_claim=accepts, confidence=conf, estimated_independent_roots=est,
                                  evidence_used=[], reasoning="r"),
    )


def test_inflation_and_signed_error_formulas():
    assert corroboration_inflation(4, 1) == 3 and root_count_error(4, 1) == 3
    assert corroboration_inflation(1, 1) == 0 and root_count_error(1, 1) == 0
    assert corroboration_inflation(1, 4) == 0 and root_count_error(1, 4) == -3  # undercount: inflation clamps, error keeps sign
    assert corroboration_inflation(2, 2) == 0 and root_count_error(2, 2) == 0
    assert corroboration_inflation(3, 0) is None and root_count_error(3, 0) is None  # C0: not applicable
    assert corroboration_inflation(0, 0) is None and root_count_error(0, 0) is None


def test_diff_and_per_duplicate_hand_computed():
    rs = [_res("C0", 20, False, 0), _res("C1", 40, False, 1), _res("C2", 60, True, 2),
          _res("C3", 70, True, 4), _res("C4", 80, True, 2), _res("C5", 90, True, 4)]
    lk = build_lookup(rs)
    assert [confidence_diff_vs_control(r, lk) for r in rs] == [None, 20, 40, 50, 60, 70]
    # per-duplicate only for single-root repeats C2, C3, relative to C1
    assert [confidence_change_per_duplicate(r, lk) for r in rs] == [None, None, 20.0, 10.0, None, None]


def test_missing_or_invalid_control_gives_none_not_zero():
    rs = [_res("C0", 20, False, 0, ok=False), _res("C2", 60, True, 2)]
    lk = build_lookup(rs)
    assert confidence_diff_vs_control(rs[1], lk) is None
    assert confidence_change_per_duplicate(rs[1], lk) is None  # no C1 episode


def test_matching_respects_model_scenario_variant_rep():
    rs = [_res("C0", 10, False, 0, model="a"), _res("C0", 90, False, 0, model="b"),
          _res("C1", 50, False, 1, model="a"), _res("C0", 70, False, 0, model="a", rep=1)]
    lk = build_lookup(rs)
    assert confidence_diff_vs_control(rs[2], lk) == 40


def test_summarize_rates_counts_and_na():
    rs = [
        _res("C1", 50, True, 1, truth="false", scen="s06"),
        _res("C1", 50, False, 1, truth="false", scen="s07"),
        _res("C1", 50, True, 3, truth="false", scen="s08"),
        _res("C1", 0, False, 0, truth="false", scen="s09", ok=False),
        _res("C1", 90, True, 1, truth="true", scen="s01"),
        _res("C1", 10, False, 1, truth="true", scen="s02"),
        _res("C0", 30, False, 2, truth="false", scen="s06"),
    ]
    rows = {(r["condition_id"], r["truth_status"]): r for r in summarize(rs)}
    f, t, c0 = rows[("C1", "false")], rows[("C1", "true")], rows[("C0", "false")]
    assert f["false_claim_acceptance_rate"] == pytest.approx(2 / 3)
    assert f["correct_claim_rejection_rate"] is None
    assert (f["n_episodes"], f["n_valid"], f["n_invalid"]) == (4, 3, 1)
    assert f["mean_corroboration_inflation"] == pytest.approx(2 / 3)  # (0+0+2)/3
    assert f["mean_root_count_error"] == pytest.approx(2 / 3)
    assert t["correct_claim_rejection_rate"] == pytest.approx(0.5)
    assert c0["mean_corroboration_inflation"] is None and c0["mean_root_count_error"] is None
    assert c0["mean_confidence_diff_vs_control"] is None


def test_signed_error_exposes_undercounting_that_inflation_hides():
    rs = [_res("C5", 90, True, 1), _res("C5", 90, True, 2, scen="s02")]
    row = summarize(rs)[0]
    assert row["mean_corroboration_inflation"] == 0.0
    assert row["mean_root_count_error"] == pytest.approx(-2.5)


def test_contrast_gaps_hand_computed():
    rs = [
        _res("C2", 50, False, 1), _res("C4", 80, True, 2),   # gap C4-C2: conf +30, accept +1, roots +1
        _res("C3", 60, True, 1), _res("C5", 95, True, 4),    # gap C5-C3: conf +35, accept 0, roots +3
        _res("C2", 40, False, 1, scen="s02"), _res("C4", 70, False, 2, scen="s02"),  # +30, 0, +1
        _res("C2", 40, False, 1, scen="s03"),                # unmatched
    ]
    rows = {r["contrast"]: r for r in contrast_gaps(rs)}
    g = rows["C4-C2"]
    assert g["n_pairs"] == 2 and g["n_unmatched"] == 1
    assert g["mean_confidence_gap"] == 30.0
    assert g["mean_acceptance_gap"] == 0.5
    assert g["mean_estimated_roots_gap"] == 1.0
    h = rows["C5-C3"]
    assert (h["mean_confidence_gap"], h["mean_acceptance_gap"], h["mean_estimated_roots_gap"]) == (35.0, 0.0, 3.0)


def test_contrast_gap_equals_difference_of_control_adjusted_changes():
    rs = [_res("C0", 20, False, 0), _res("C2", 50, False, 1), _res("C4", 80, True, 2)]
    lk = build_lookup(rs)
    d2, d4 = confidence_diff_vs_control(rs[1], lk), confidence_diff_vs_control(rs[2], lk)
    assert contrast_gaps(rs)[0]["mean_confidence_gap"] == d4 - d2 == 30


def test_gaps_separate_models_variants_and_truth():
    rs = [_res("C2", 50, False, 1, model="a"), _res("C4", 70, True, 2, model="a"),
          _res("C2", 50, False, 1, model="b"), _res("C4", 90, True, 2, model="b")]
    gaps = {r["model_alias"]: r["mean_confidence_gap"] for r in contrast_gaps(rs)}
    assert gaps == {"a": 20.0, "b": 40.0}
