"""F13 output tiers, the blocked interfaces and the generic package's boundaries (SYNTHETIC data only)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import maps.analysis as analysis
from maps.analysis import (
    TIERS,
    aggregate_to_pair,
    aggregate_to_scenario,
    bootstrap_percentile_interval,
    check_tier,
    contrast_bounds,
    effect_sizes,
    effect_sizes_for,
    invalid_bounds,
    invalid_response_report,
    pair_completeness,
    paired_scenario_diffs,
    require_tier,
    scenario_level_bounds,
    stratified_summary,
    t_interval,
    validate_rows,
    wilson_interval,
)
from maps.analysis import provisional

from an_support import conf_rows

PACKAGE_DIR = Path(analysis.__file__).resolve().parent


def _rows():
    rows = []
    for s, (a, b) in {"s1": (50, 60), "s2": (50, 56)}.items():
        rows += conf_rows("m1", s, "C2", [a, None]) + conf_rows("m1", s, "C4", [b, b])
    return rows


def test_only_descriptive_and_sensitivity_tiers_exist():
    assert TIERS == ("descriptive", "sensitivity")
    for bad in ("primary", "confirmatory", "", None):
        with pytest.raises((ValueError, TypeError)):
            check_tier(bad)


def test_result_objects_refuse_a_primary_tier():
    from maps.analysis import Interval

    with pytest.raises(ValueError):
        Interval("t", 0.95, 4, 1.0, 0.0, 2.0, tier="primary")
    with pytest.raises(ValueError):
        require_tier(object())


def test_every_result_carries_an_allowed_tier():
    rows = _rows()
    table = aggregate_to_scenario(rows, "confidence")
    (paired,) = paired_scenario_diffs(table, "C4", "C2")
    report = invalid_response_report(rows)
    results = [
        validate_rows(rows), table, table.cells[0], paired, aggregate_to_pair(paired),
        pair_completeness(paired), effect_sizes_for(paired), effect_sizes([1, 2, 3]), t_interval([1, 2, 3]),
        wilson_interval(1, 2), bootstrap_percentile_interval([1, 2, 3], n_boot=10, seed=1),
        report, report.rows[0], report.differential[0],
        stratified_summary(rows, "confidence", interval_method="t")[0],
    ]
    assert all(require_tier(r) in TIERS for r in results)
    bounds = (
        list(invalid_bounds(rows)) + list(scenario_level_bounds(rows)) + list(contrast_bounds(rows, "C4", "C2"))
    )
    assert bounds and all(require_tier(b) == "sensitivity" for b in bounds)
    assert all(require_tier(r) == "descriptive" for r in results)


def test_no_primary_analysis_surface_exists():
    public = [name for name in dir(analysis) if not name.startswith("_")]
    assert not [n for n in public if "primary" in n.lower() or "confirmatory" in n.lower()]
    assert not [n for n in analysis.__all__ if "primary" in n.lower()]
    assert not list(PACKAGE_DIR.glob("primary*")) and not list(PACKAGE_DIR.glob("adapter*"))


def test_f10_and_f11_are_implemented_under_the_approved_contracts_but_not_re_exported():
    assert provisional.root_metrics([]) == ()
    assert provisional.coverage_report([], []).n_expected == 0
    assert "root_metrics" not in analysis.__all__ and "coverage_report" not in analysis.__all__
    assert "NOT IMPLEMENTED" not in provisional.__doc__ and "nominal" in provisional.__doc__.lower()


ALLOWED_IMPORTS = {"__future__", "collections", "dataclasses", "math", "random", "statistics", "sys", "scipy", "maps"}


def test_the_package_is_generic_and_does_no_io():
    sources = sorted(PACKAGE_DIR.glob("*.py"))
    assert len(sources) >= 9
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "EpisodeResult" not in text, path.name
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                assert module.split(".")[0] in ALLOWED_IMPORTS, (path.name, module)
                if module.split(".")[0] == "maps":
                    assert module.startswith("maps.analysis"), (path.name, module)
        assert "open(" not in text and "read_text" not in text and "write_text" not in text, path.name


def test_functions_are_deterministic_and_leave_inputs_untouched():
    rows = _rows()
    snapshot = list(rows)
    first = stratified_summary(rows, "confidence", interval_method="bootstrap", n_boot=50, seed=11)
    second = stratified_summary(list(rows), "confidence", interval_method="bootstrap", n_boot=50, seed=11)
    assert first == second and rows == snapshot
