"""Provider-reported token usage accounting (fake client)."""

from __future__ import annotations

import pytest

from maps.runs.live_budget import BudgetedClient, CEILING_BASIS, USAGE_TOTALS_BASIS
from maps.schemas import LLMResult

from lp_support import FakeClient, FakeClock, err, make_policy, make_request, ok


def run(script, n=None, **policy):
    policy.setdefault("max_consecutive_nonfatal_errors", 10)
    budget = BudgetedClient(FakeClient(script), make_policy(**policy), clock=FakeClock())
    for _ in range(n if n is not None else len(script)):
        budget.complete(make_request())
    return budget.summary()


def test_complete_usage_is_summed_per_field():
    summary = run([ok(prompt=10, completion=5, total=15), ok(prompt=1, completion=2, total=3)])
    assert (summary.usage_complete, summary.usage_partial, summary.usage_missing, summary.usage_invalid) == (2, 0, 0, 0)
    assert (summary.provider_reported_prompt_tokens, summary.provider_reported_completion_tokens, summary.provider_reported_total_tokens) == (11, 7, 18)


def test_missing_usage_is_counted_as_unmeasured_and_never_as_zero():
    summary = run([ok(prompt=None, completion=None, total=None), ok(prompt=4, completion=2, total=6)])
    assert (summary.usage_complete, summary.usage_missing) == (1, 1)
    assert summary.provider_reported_total_tokens == 6                      # the missing call contributes nothing, not a zero
    only_missing = run([ok(prompt=None, completion=None, total=None)] * 3)
    assert only_missing.usage_missing == 3 and only_missing.usage_complete == 0
    assert only_missing.provider_reported_prompt_tokens == 0 and only_missing.usage_missing != 0


def test_partial_usage_is_distinct_and_only_present_fields_are_totalled():
    summary = run([ok(prompt=9, completion=None, total=None), ok(prompt=None, completion=3, total=None)])
    assert (summary.usage_partial, summary.usage_complete, summary.usage_missing) == (2, 0, 0)
    assert (summary.provider_reported_prompt_tokens, summary.provider_reported_completion_tokens, summary.provider_reported_total_tokens) == (9, 3, 0)


@pytest.mark.parametrize("bad", [-1, True, 1.5, "7"])
def test_invalid_usage_values_are_counted_separately_and_never_totalled(bad):
    result = ok(prompt=5, completion=5, total=10)
    object.__setattr__(result, "completion_tokens", bad)          # bypass pydantic to simulate a misbehaving client
    summary = run([result])
    assert summary.usage_invalid == 1 and summary.usage_complete == 0
    assert summary.provider_reported_completion_tokens == 0
    assert summary.provider_reported_prompt_tokens == 5 and summary.provider_reported_total_tokens == 10   # the valid fields still count


def test_zero_reported_usage_is_valid_measured_usage_not_missing():
    summary = run([ok(prompt=0, completion=0, total=0)])
    assert summary.usage_complete == 1 and summary.usage_missing == 0


def test_errored_calls_without_usage_count_as_missing():
    summary = run([err("http_503: x"), err("http_429: x")])
    assert summary.usage_missing == 2 and summary.provider_reported_total_tokens == 0


def test_an_errored_call_that_does_carry_valid_usage_is_counted_as_measured():
    summary = run([LLMResult(error="http_503: x", prompt_tokens=3, completion_tokens=0, total_tokens=3, attempts=1)])
    assert summary.usage_complete == 1 and summary.provider_reported_prompt_tokens == 3


def test_the_requested_ceiling_is_reported_separately_and_labelled_as_a_maximum():
    summary = run([ok(prompt=1, completion=1, total=2)] * 3)
    assert summary.requested_completion_ceiling_tokens == 2400            # 3 started calls x 800 requested
    assert summary.provider_reported_completion_tokens == 3               # measured, a different number
    assert "maximum" in summary.requested_ceiling_basis and summary.requested_ceiling_basis == CEILING_BASIS
    assert summary.usage_totals_basis == USAGE_TOTALS_BASIS and "not counted as zero" in USAGE_TOTALS_BASIS


def test_the_ceiling_counts_started_calls_only():
    budget = BudgetedClient(FakeClient([RuntimeError("x")]), make_policy(), clock=FakeClock())
    with pytest.raises(RuntimeError):
        budget.complete(make_request(max_tokens=500))
    assert budget.summary().requested_completion_ceiling_tokens == 500
    with pytest.raises(Exception):
        budget.complete(make_request(max_tokens=500))                      # refused by the sticky stop, so not started
    assert budget.summary().requested_completion_ceiling_tokens == 500


def test_no_monetary_field_exists():
    names = set(run([ok()]).to_dict())
    assert not {n for n in names if any(w in n for w in ("cost", "price", "usd", "dollar", "money"))}


def test_a_zero_total_with_missing_usage_is_labelled_as_no_usage_supplied_not_measured_zero():
    summary = run([err("http_503: x")])
    assert summary.provider_reported_total_tokens == 0 and summary.usage_missing == 1
    label = summary.usage_totals_basis
    assert "usage_missing above 0 means none was supplied" in label and "lower bounds" in label and "not counted as zero" in label
    measured_zero = run([ok(prompt=0, completion=0, total=0)])
    assert measured_zero.provider_reported_total_tokens == 0 and measured_zero.usage_missing == 0 and measured_zero.usage_complete == 1
