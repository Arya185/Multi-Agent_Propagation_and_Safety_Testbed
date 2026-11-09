"""Generic, synthetic-tested analysis building blocks (descriptive and sensitivity tiers only).

No primary estimand, hypothesis, multiplicity procedure or inferential model is implemented, and no
adapter from experiment results exists. See ``maps.analysis.provisional`` for blocked interfaces.
"""

from maps.analysis.aggregate import Cell, CellTable, aggregate_to_scenario, outcome_value
from maps.analysis.contrasts import (
    Dropped,
    IncompletePair,
    PairAggregate,
    PairCompleteness,
    PairDiff,
    PairedDiffs,
    ScenarioDiff,
    aggregate_to_pair,
    pair_completeness,
    paired_scenario_diffs,
)
from maps.analysis.effect_size import EffectSizes, effect_sizes, effect_sizes_for, hedges_correction
from maps.analysis.intervals import (
    Interval,
    bootstrap_percentile_interval,
    compute_interval,
    t_interval,
    wilson_interval,
)
from maps.analysis.quality import (
    BinaryBounds,
    ContrastBounds,
    Differential,
    InvalidReport,
    InvalidRow,
    ScenarioBounds,
    contrast_bounds,
    invalid_bounds,
    invalid_response_report,
    scenario_level_bounds,
)
from maps.analysis.rows import (
    UNLABELLED,
    AnalysisRow,
    DuplicateRowError,
    InvalidRowsError,
    Issue,
    ValidationReport,
    is_complete,
    require_wellformed,
    validate_rows,
)
from maps.analysis.summary import StratumSummary, stratified_summary
from maps.analysis.tiers import DESCRIPTIVE, SENSITIVITY, TIERS, check_tier, require_tier

__all__ = [
    "AnalysisRow", "BinaryBounds", "Cell", "CellTable", "ContrastBounds", "DESCRIPTIVE", "Differential",
    "Dropped", "DuplicateRowError", "EffectSizes", "IncompletePair", "Interval", "InvalidReport",
    "InvalidRow", "InvalidRowsError", "Issue", "PairAggregate", "PairCompleteness", "PairDiff",
    "PairedDiffs", "SENSITIVITY", "ScenarioBounds", "ScenarioDiff", "StratumSummary", "TIERS",
    "UNLABELLED", "ValidationReport", "aggregate_to_pair", "aggregate_to_scenario",
    "bootstrap_percentile_interval", "check_tier", "compute_interval", "contrast_bounds", "effect_sizes",
    "effect_sizes_for", "hedges_correction", "invalid_bounds", "invalid_response_report", "is_complete",
    "outcome_value", "pair_completeness", "paired_scenario_diffs", "require_tier", "require_wellformed",
    "scenario_level_bounds", "stratified_summary", "t_interval", "validate_rows", "wilson_interval",
]
