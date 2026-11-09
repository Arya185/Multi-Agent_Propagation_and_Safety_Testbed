"""F10 (nominal root comparison) and F11 (coverage report), implemented under the v2.3.15 contracts.

The module keeps its historical name ``provisional`` (renaming or adding modules was not authorized);
the two functions are no longer stubs. They are generic: they read only ``AnalysisRow`` records and
caller-supplied keys, never the experiment grid, scenario files or any truth-bearing material, and
they are not re-exported from ``maps.analysis``.

F10  root_metrics(rows, policy="exclude_undefined")
  Question: how does the receiver's estimated number of independent roots compare with the NOMINAL
  number of roots presented (``n_roots``)? It does not measure, derive or infer substantive
  independence; a nominal count can exceed the number of substantively independent roots.
  Per valid episode with n_roots >= 1:  error = estimated_roots - n_roots,
  inflation = max(0, error), deflation = max(0, -error)  (all in "roots").
  Aggregation: scenario cell = mean over the valid episodes of that scenario; stratum
  (model, prompt variant, condition) = equal-weight mean over scenarios that have a cell. Models and
  variants are never pooled. Inflation and deflation are reported separately so they cannot cancel.
  Policy ``exclude_undefined`` (the only approved policy and the default): episodes with n_roots == 0
  (no-message control) or n_roots unknown (None) contribute to no metric; they are reported in their
  own counters. Any other policy name raises.
  Counters are EPISODE-level counts (``counter_unit="episode"``), each defined on its own and NOT
  mutually exclusive, so they may overlap and must not be added together as categories:
    ``n_rows``         every row in the stratum
    ``n_invalid``      rows that are not complete (is_complete is false), whatever their n_roots
    ``n_zero_root``    rows with n_roots == 0, whatever their validity
    ``n_unknown_root`` rows whose n_roots is unknown (None), whatever their validity
    ``n_used``         complete rows with n_roots >= 1; the subset that feeds the scenario cells
  A row can be counted in several counters (for example an invalid row with n_roots == 0 is in both
  ``n_invalid`` and ``n_zero_root``). Rows excluded from the metrics = ``n_rows - n_used``, which is
  not the sum of the three exclusion counters when they overlap.
  The mean_* fields (``unit="scenario"``) are equal-weight means of scenario cells, not
  episode-weighted means: a scenario with one used episode counts as much as one with four, and
  ``cells[].n_used`` shows how many episodes each cell contains.

F11  coverage_report(rows, expected_keys)
  Question: which of the caller's expected episodes are present, invalid, incomplete, absent or
  duplicated, and which observed episodes were not expected?
  Keys are the five-field episode key (model, prompt variant, scenario, condition, repetition).
  Per distinct expected key: absent (no row); duplicate (two or more rows); valid (one row,
  is_complete); incomplete (one row, status ok but an outcome missing); invalid (one row, any other
  status). Observed keys that are not expected are unexpected. Duplicate expected keys are reported
  and counted once. Duplicate observed keys are reported, never merged or validated further.
  Structural problems in the (first) row of each key raise, as elsewhere; a malformed expected key
  raises ValueError. Unit: episode key, with scenario counts per stratum.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from maps.analysis.rows import AnalysisRow, RowKey, is_complete, require_wellformed
from maps.analysis.tiers import DESCRIPTIVE, check_tier

ROOT_POLICIES = ("exclude_undefined",)
ROOT_BASELINE = "nominal_n_roots"


# ---------------------------------------------------------------------------
# F10
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RootCell:
    scenario_id: str
    n_used: int
    error: float
    inflation: float
    deflation: float


@dataclass(frozen=True)
class RootMetrics:
    """F10 result for one (model, prompt variant, condition) stratum, nominal-root baseline.

    Counter fields (``counter_unit="episode"``) may overlap; see the module docstring for the exact
    definitions. ``mean_*`` fields (``unit="scenario"``) are equal-weight means of ``cells``."""

    model_alias: str
    prompt_variant: str
    condition_id: str
    n_rows: int
    n_invalid: int
    n_zero_root: int
    n_unknown_root: int
    n_used: int
    n_scenarios_total: int
    n_scenarios_with_value: int
    mean_error: float | None
    mean_inflation: float | None
    mean_deflation: float | None
    cells: tuple[RootCell, ...]
    baseline: str = ROOT_BASELINE
    policy: str = "exclude_undefined"
    unit: str = "scenario"
    counter_unit: str = "episode"
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


def _mean(values: list[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def root_metrics(rows: Iterable[AnalysisRow], policy: str = "exclude_undefined") -> tuple[RootMetrics, ...]:
    """F10. See the module docstring for the contract. Raises DuplicateRowError / InvalidRowsError on
    structural problems and ValueError for a policy other than ``exclude_undefined``."""
    if policy not in ROOT_POLICIES:
        raise ValueError(f"unsupported root policy {policy!r}; approved: {ROOT_POLICIES}")
    rows = require_wellformed(rows)
    groups: dict[tuple[str, str, str], list[AnalysisRow]] = {}
    for r in rows:
        groups.setdefault((r.model_alias, r.prompt_variant, r.condition_id), []).append(r)
    out: list[RootMetrics] = []
    for (model, variant, cond), rs in sorted(groups.items()):
        used = [r for r in rs if is_complete(r) and r.n_roots is not None and r.n_roots >= 1]
        errors: dict[str, list[int]] = {}
        for r in used:
            errors.setdefault(r.scenario_id, []).append(r.estimated_roots - r.n_roots)
        cells = tuple(
            RootCell(
                scenario_id=sid,
                n_used=len(es),
                error=math.fsum(es) / len(es),
                inflation=math.fsum(max(0, e) for e in es) / len(es),
                deflation=math.fsum(max(0, -e) for e in es) / len(es),
            )
            for sid, es in sorted(errors.items())
        )
        out.append(
            RootMetrics(
                model_alias=model,
                prompt_variant=variant,
                condition_id=cond,
                n_rows=len(rs),
                n_invalid=sum(not is_complete(r) for r in rs),
                n_zero_root=sum(r.n_roots == 0 for r in rs),
                n_unknown_root=sum(r.n_roots is None for r in rs),
                n_used=len(used),
                n_scenarios_total=len({r.scenario_id for r in rs}),
                n_scenarios_with_value=len(cells),
                mean_error=_mean([c.error for c in cells]),
                mean_inflation=_mean([c.inflation for c in cells]),
                mean_deflation=_mean([c.deflation for c in cells]),
                cells=cells,
                policy=policy,
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# F11
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CoverageStratum:
    model_alias: str
    prompt_variant: str
    condition_id: str
    n_expected: int
    n_observed: int
    n_valid: int
    n_incomplete: int
    n_invalid: int
    n_duplicate: int
    n_absent: int
    n_unexpected_keys: int
    coverage_rate: float | None  # n_valid / n_expected; None when nothing was expected
    n_scenarios_expected: int
    n_scenarios_without_valid: int
    unit: str = "episode"
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


@dataclass(frozen=True)
class CoverageReport:
    n_expected: int  # distinct expected keys
    n_observed: int  # distinct expected keys with at least one row
    n_valid: int
    n_incomplete: int
    n_invalid: int
    n_duplicate: int
    n_absent: int
    n_unexpected_keys: int
    n_unexpected_rows: int
    coverage_rate: float | None
    strata: tuple[CoverageStratum, ...]
    absent_keys: tuple[RowKey, ...]
    invalid_keys: tuple[tuple[RowKey, str], ...]  # (key, status)
    incomplete_keys: tuple[RowKey, ...]
    duplicate_observed_keys: tuple[tuple[RowKey, int], ...]  # (key, number of rows)
    duplicate_expected_keys: tuple[tuple[RowKey, int], ...]  # (key, times listed)
    unexpected_keys: tuple[RowKey, ...]
    unit: str = "episode"
    tier: str = DESCRIPTIVE

    def __post_init__(self) -> None:
        check_tier(self.tier)


def _check_key(key: object) -> RowKey:
    ok = (
        isinstance(key, tuple)
        and len(key) == 5
        and all(isinstance(part, str) and part for part in key[:4])
        and isinstance(key[4], int)
        and not isinstance(key[4], bool)
        and key[4] >= 0
    )
    if not ok:
        raise ValueError(f"malformed expected key {key!r}: need (model, variant, scenario, condition, repetition)")
    return key  # type: ignore[return-value]


def _stratum_of(key: RowKey) -> tuple[str, str, str]:
    return (key[0], key[1], key[3])


def coverage_report(rows: Iterable[AnalysisRow], expected_keys: Iterable[RowKey]) -> CoverageReport:
    """F11. See the module docstring for the contract."""
    expected_counts = Counter(_check_key(k) for k in expected_keys)
    expected = set(expected_counts)
    rows = list(rows)
    by_key: dict[RowKey, list[AnalysisRow]] = {}
    for r in rows:
        by_key.setdefault(r.key, []).append(r)
    require_wellformed([rs[0] for rs in by_key.values()], tolerate=("missing_outcome", "unknown_status"))

    status: dict[RowKey, str] = {}
    invalid_status: dict[RowKey, str] = {}
    for key in expected:
        rs = by_key.get(key)
        if rs is None:
            status[key] = "absent"
        elif len(rs) > 1:
            status[key] = "duplicate"
        elif is_complete(rs[0]):
            status[key] = "valid"
        elif rs[0].status == "ok":
            status[key] = "incomplete"
        else:
            status[key] = "invalid"
            invalid_status[key] = rs[0].status
    unexpected = sorted(k for k in by_key if k not in expected)

    def count(label: str, keys: Iterable[RowKey]) -> int:
        return sum(1 for k in keys if status[k] == label)

    strata_keys = sorted({_stratum_of(k) for k in expected} | {_stratum_of(k) for k in unexpected})
    strata = []
    for sk in strata_keys:
        exp = [k for k in expected if _stratum_of(k) == sk]
        unx = [k for k in unexpected if _stratum_of(k) == sk]
        scenarios = {k[2] for k in exp}
        with_valid = {k[2] for k in exp if status[k] == "valid"}
        valid, absent = count("valid", exp), count("absent", exp)
        strata.append(
            CoverageStratum(
                model_alias=sk[0], prompt_variant=sk[1], condition_id=sk[2],
                n_expected=len(exp), n_observed=len(exp) - absent, n_valid=valid,
                n_incomplete=count("incomplete", exp), n_invalid=count("invalid", exp),
                n_duplicate=count("duplicate", exp), n_absent=absent, n_unexpected_keys=len(unx),
                coverage_rate=valid / len(exp) if exp else None,
                n_scenarios_expected=len(scenarios), n_scenarios_without_valid=len(scenarios - with_valid),
            )
        )
    n_expected = len(expected)
    n_absent = count("absent", expected)
    n_valid = count("valid", expected)
    return CoverageReport(
        n_expected=n_expected,
        n_observed=n_expected - n_absent,
        n_valid=n_valid,
        n_incomplete=count("incomplete", expected),
        n_invalid=count("invalid", expected),
        n_duplicate=count("duplicate", expected),
        n_absent=n_absent,
        n_unexpected_keys=len(unexpected),
        n_unexpected_rows=sum(len(by_key[k]) for k in unexpected),
        coverage_rate=n_valid / n_expected if n_expected else None,
        strata=tuple(strata),
        absent_keys=tuple(sorted(k for k in expected if status[k] == "absent")),
        invalid_keys=tuple((k, invalid_status[k]) for k in sorted(invalid_status)),
        incomplete_keys=tuple(sorted(k for k in expected if status[k] == "incomplete")),
        duplicate_observed_keys=tuple((k, len(by_key[k])) for k in sorted(by_key) if len(by_key[k]) > 1),
        duplicate_expected_keys=tuple((k, c) for k, c in sorted(expected_counts.items()) if c > 1),
        unexpected_keys=tuple(unexpected),
    )
