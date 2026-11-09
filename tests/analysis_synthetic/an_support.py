"""Builders for SYNTHETIC analysis datasets (plain AnalysisRow records; no files, no experiment data).

Only constructors live here. Every expected value is written by hand in the test modules; nothing
here computes an expected result.
"""

from __future__ import annotations

from maps.analysis import AnalysisRow

PAIR_OF = {"s1": "p1", "s2": "p1", "s3": "p2", "s4": "p2", "s5": "p3", "s6": "p3", "s7": "p4", "s8": "p4"}


def ok(model, scenario, cond, rep, *, conf=50, accepts=True, roots=1, variant="neutral", n_messages=2, n_roots=1, pair=None, truth=None):
    return AnalysisRow(
        model_alias=model, prompt_variant=variant, scenario_id=scenario, pair_id=pair or PAIR_OF[scenario],
        condition_id=cond, repetition=rep, status="ok", accepts_claim=accepts, confidence=conf,
        estimated_roots=roots, n_messages=n_messages, n_roots=n_roots, truth_label=truth,
    )


def failed(model, scenario, cond, rep, *, status="parse_error", variant="neutral", n_messages=2, n_roots=1, pair=None, truth=None):
    return AnalysisRow(
        model_alias=model, prompt_variant=variant, scenario_id=scenario, pair_id=pair or PAIR_OF[scenario],
        condition_id=cond, repetition=rep, status=status, n_messages=n_messages, n_roots=n_roots, truth_label=truth,
    )


def conf_rows(model, scenario, cond, confidences, *, variant="neutral", truth=None):
    """One row per repetition. A confidence of None or a status string makes a failed row."""
    rows = []
    for rep, c in enumerate(confidences):
        if c is None:
            rows.append(failed(model, scenario, cond, rep, variant=variant, truth=truth))
        elif isinstance(c, str):
            rows.append(failed(model, scenario, cond, rep, status=c, variant=variant, truth=truth))
        else:
            rows.append(ok(model, scenario, cond, rep, conf=c, variant=variant, truth=truth))
    return rows


def accept_rows(model, scenario, cond, accepts, *, variant="neutral", truth=None):
    """One row per repetition: True/False accept or reject, a status string makes a failed row."""
    rows = []
    for rep, a in enumerate(accepts):
        if isinstance(a, str):
            rows.append(failed(model, scenario, cond, rep, status=a, variant=variant, truth=truth))
        else:
            rows.append(ok(model, scenario, cond, rep, accepts=a, variant=variant, truth=truth))
    return rows


def single_rep(model, values_by_scenario, cond, *, variant="neutral", truth_by_scenario=None):
    """One repetition per scenario: {scenario: confidence}."""
    rows = []
    for scenario, c in values_by_scenario.items():
        truth = (truth_by_scenario or {}).get(scenario)
        rows += conf_rows(model, scenario, cond, [c], variant=variant, truth=truth)
    return rows
