"""F13: output-tier enforcement for the generic analysis building blocks.

Every result object produced by this package carries a ``tier``. Only two tiers exist here:
``descriptive`` (summaries of observed data) and ``sensitivity`` (alternative treatments of missing
or undefined data). There is deliberately no ``primary`` tier: no primary estimand, hypothesis,
multiplicity procedure or inferential model has been approved, so this package cannot label any
output as primary. Output in these tiers makes no inferential-validity claim.
"""

from __future__ import annotations

DESCRIPTIVE = "descriptive"
SENSITIVITY = "sensitivity"
TIERS = (DESCRIPTIVE, SENSITIVITY)


def check_tier(tier: str) -> str:
    """Return ``tier`` if it is an allowed tier, otherwise raise ValueError."""
    if tier not in TIERS:
        raise ValueError(f"unsupported output tier {tier!r}; allowed tiers: {TIERS}")
    return tier


def require_tier(result: object) -> str:
    """Return the tier of a result object, raising if it is missing or not allowed."""
    tier = getattr(result, "tier", None)
    if tier is None:
        raise ValueError(f"{type(result).__name__} carries no output tier")
    return check_tier(tier)
