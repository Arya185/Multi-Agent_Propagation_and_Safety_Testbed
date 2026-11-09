"""Stop rules, consecutive errors, deadline semantics, sticky stops (fake client, fake clock, no sleeps)."""

from __future__ import annotations

import pytest

from maps.runs.live_budget import AbortReason, BudgetAbort, BudgetedClient
from maps.schemas import LLMResult

from lp_support import FakeClient, FakeClock, SENTINEL, err, make_policy, make_request, ok


def build(script, *, clock=None, on_call=None, **policy):
    clock = clock or FakeClock()
    client = FakeClient(script, on_call=on_call)
    return BudgetedClient(client, make_policy(**policy), clock=clock), client, clock


def call(budget):
    return budget.complete(make_request())


# ---- fatal results --------------------------------------------------------------------------
def test_a_fatal_result_is_returned_and_the_next_call_is_refused_without_reaching_the_client():
    budget, client, _ = build([ok(), err("http_401: bad credentials"), ok()])
    assert call(budget).error is None
    returned = call(budget)
    assert returned.error == "http_401: bad credentials"            # the runner still gets to record the failed episode
    assert budget.summary().stop_reason == "fatal_error"            # visible even if there is no further call
    with pytest.raises(BudgetAbort) as caught:
        call(budget)
    assert caught.value.reason is AbortReason.FATAL_ERROR and client.calls == 2


def test_the_fatal_message_never_contains_provider_text():
    budget, client, _ = build([err(f"http_403: {SENTINEL}")])
    call(budget)
    with pytest.raises(BudgetAbort) as caught:
        call(budget)
    assert SENTINEL not in str(caught.value) and SENTINEL not in repr(budget.summary())


# ---- consecutive nonfatal errors ---------------------------------------------------------------
def test_consecutive_errors_stop_at_exactly_n():
    budget, client, _ = build([err("http_503: x")] * 5, max_consecutive_nonfatal_errors=3)
    call(budget)
    call(budget)
    assert budget.summary().stop_reason is None and budget.summary().consecutive_errors_current == 2
    call(budget)                                                    # the Nth error is still returned
    assert budget.summary().stop_reason == "consecutive_errors" and budget.summary().consecutive_errors_current == 3
    with pytest.raises(BudgetAbort) as caught:
        call(budget)
    assert caught.value.reason is AbortReason.CONSECUTIVE_ERRORS and client.calls == 3


def test_n_equal_to_one_stops_after_the_first_nonfatal_error():
    budget, client, _ = build([err("http_503: x"), ok()], max_consecutive_nonfatal_errors=1)
    call(budget)
    with pytest.raises(BudgetAbort):
        call(budget)
    assert client.calls == 1


def test_a_success_resets_the_consecutive_error_counter():
    script = [err("http_503: x"), err("http_503: x"), ok(), err("http_503: x"), err("http_503: x"), ok()]
    budget, client, _ = build(script, max_consecutive_nonfatal_errors=3)
    for _ in range(6):
        call(budget)
    summary = budget.summary()
    assert summary.stop_reason is None and summary.consecutive_errors_current == 0 and summary.consecutive_errors_peak == 2
    assert (summary.calls_success, summary.calls_nonfatal, summary.calls_fatal) == (2, 4, 0)


def test_empty_responses_and_provider_errors_count_toward_n():
    budget, client, _ = build([LLMResult(attempts=1), err("api_error: {}"), err("malformed_api_response: x")], max_consecutive_nonfatal_errors=3)
    for _ in range(3):
        call(budget)
    assert budget.summary().stop_reason == "consecutive_errors"
    assert dict(budget.summary().error_category_counts) == {"empty_response": 1, "api_error": 1, "malformed_api_response": 1}


# ---- deadline -----------------------------------------------------------------------------------
def test_a_call_before_the_deadline_proceeds_and_the_deadline_refuses_the_next_call():
    clock = FakeClock()
    budget, client, _ = build([ok(), ok()], clock=clock, deadline_seconds=100)
    clock.advance(99.9)
    call(budget)
    clock.advance(0.1)                                              # elapsed is exactly the deadline
    with pytest.raises(BudgetAbort) as caught:
        call(budget)
    assert caught.value.reason is AbortReason.DEADLINE and client.calls == 1


def test_exactly_at_the_deadline_a_new_call_is_refused_and_one_tick_before_it_is_allowed():
    clock = FakeClock()
    budget, client, _ = build([ok()], clock=clock, deadline_seconds=50)
    clock.advance(49.999)
    call(budget)
    clock2 = FakeClock()
    budget2, client2, _ = build([ok()], clock=clock2, deadline_seconds=50)
    clock2.advance(50)
    with pytest.raises(BudgetAbort):
        call(budget2)
    assert client2.calls == 0


def test_an_in_flight_call_that_finishes_after_the_deadline_is_returned_flagged_and_not_called_cancelled():
    clock = FakeClock()
    budget, client, _ = build([ok(), ok()], clock=clock, deadline_seconds=100, on_call=lambda: clock.advance(60))
    call(budget)                                                    # ends at 60 s: before the deadline
    assert budget.summary().deadline_crossed_by_inflight_call is False
    result = call(budget)                                           # ends at 120 s: the call was already running
    assert result.content == "SYNTHETIC answer"                     # returned normally
    summary = budget.summary()
    assert summary.deadline_crossed_by_inflight_call is True and summary.stop_reason == "deadline"
    assert summary.calls_success == 2 and summary.calls_raised == 0
    assert "not cancelled" in summary.in_flight_note and "cancelled" not in summary.stop_reason
    with pytest.raises(BudgetAbort) as caught:
        call(budget)
    assert caught.value.reason is AbortReason.DEADLINE and client.calls == 2


def test_a_call_that_ends_exactly_at_the_deadline_is_not_reported_as_crossing_it_but_still_stops_the_run():
    clock = FakeClock()
    budget, client, _ = build([ok()], clock=clock, deadline_seconds=100, on_call=lambda: clock.advance(100))
    call(budget)
    summary = budget.summary()
    assert summary.deadline_crossed_by_inflight_call is False and summary.stop_reason == "deadline"
    with pytest.raises(BudgetAbort):
        call(budget)


def test_the_first_recorded_stop_reason_is_kept():
    clock = FakeClock()
    budget, client, _ = build([err("http_401: x")], clock=clock, deadline_seconds=10, on_call=lambda: clock.advance(60))
    call(budget)
    assert budget.summary().stop_reason == "fatal_error" and budget.summary().deadline_crossed_by_inflight_call is True
    with pytest.raises(BudgetAbort) as caught:
        call(budget)
    assert caught.value.reason is AbortReason.FATAL_ERROR


# ---- sticky stops and the final episode -------------------------------------------------------
def test_stops_are_sticky_for_every_reason():
    cases = [
        ([err("http_404: x")], {}, "fatal_error"),
        ([err("http_503: x")], dict(max_consecutive_nonfatal_errors=1), "consecutive_errors"),
    ]
    for script, policy, reason in cases:
        budget, client, _ = build(script + [ok()] * 3, **policy)
        call(budget)
        for _ in range(3):
            with pytest.raises(BudgetAbort) as caught:
                call(budget)
            assert caught.value.reason.value == reason
        assert client.calls == 1 and budget.summary().logical_calls_started == 1


def test_a_stop_triggered_by_the_final_permitted_episode_is_visible_without_a_later_call():
    budget, client, _ = build([ok(), ok(), err("http_401: x")], planned_episodes=3, max_episodes=3, max_request_attempts=3)
    for _ in range(3):
        call(budget)
    summary = budget.summary()
    assert summary.stop_reason == "fatal_error" and summary.logical_calls_started == 3


def test_a_clean_run_has_no_stop_reason():
    budget, client, _ = build([ok()] * 3, planned_episodes=3, max_episodes=3, max_request_attempts=3, max_consecutive_nonfatal_errors=1)
    for _ in range(3):
        call(budget)
    assert budget.summary().stop_reason is None


def test_an_unexpected_exception_is_sticky_and_preserved():
    boom = ValueError(f"client bug {SENTINEL}")
    budget, client, _ = build([boom, ok()])
    with pytest.raises(ValueError) as first:
        call(budget)
    assert first.value is boom
    with pytest.raises(BudgetAbort) as second:
        call(budget)
    assert second.value.reason is AbortReason.UNEXPECTED_CLIENT_EXCEPTION and SENTINEL not in str(second.value)
    assert SENTINEL not in repr(budget.summary()) and client.calls == 1


def test_counts_in_the_summary_are_consistent():
    budget, client, _ = build([ok(), err("http_503: x"), err("http_404: x"), ok()], max_consecutive_nonfatal_errors=5)
    for _ in range(3):
        call(budget)
    summary = budget.summary()
    assert summary.logical_calls_started == 3 == summary.calls_returned + summary.calls_raised
    assert (summary.calls_success, summary.calls_nonfatal, summary.calls_fatal) == (1, 1, 1)
    assert dict(summary.error_category_counts) == {"http_503": 1, "http_404": 1}


# ---- documented limits (Stage 4G: PS-21 deferred, PS-06-BUDGET no cumulative cap) ---------------------------------------------
def test_a_global_consecutive_counter_does_not_expose_one_models_outage():
    """CHARACTERIZATION of a limit. One wrapper serves every model and any success resets the counter, so a model that fails
    every call is invisible while another model keeps succeeding. Per-model limits are deferred (PS-21)."""
    from maps.schemas import ChatMessage, ChatRequest

    def request_for(model):
        return ChatRequest(model=model, messages=[ChatMessage(role="user", content="x")], temperature=0.0, max_tokens=10, seed=1)

    script = [err("http_503: down"), ok()] * 5                                   # model A always fails, model B always succeeds
    budget, client, _ = build(script, max_consecutive_nonfatal_errors=2, max_episodes=10, max_request_attempts=10)
    for i in range(10):
        budget.complete(request_for("model-a" if i % 2 == 0 else "model-b"))
    summary = budget.summary()
    assert summary.calls_nonfatal == 5 and summary.calls_success == 5              # half of all calls failed ...
    assert summary.stop_reason is None                                             # ... and the consecutive rule never fired
    assert summary.consecutive_errors_peak == 1


def test_there_is_no_cumulative_token_cap_in_the_policy_the_stop_reasons_or_the_summary():
    import dataclasses

    from maps.runs.live_policy import LivePolicy

    assert not [f.name for f in dataclasses.fields(LivePolicy) if "token" in f.name]
    assert not [r.value for r in AbortReason if "token" in r.value]
    summary_fields = set(build([ok()])[0].summary().to_dict())
    assert "requested_completion_ceiling_tokens" in summary_fields                    # reported, not enforced
    assert not [n for n in summary_fields if "token" in n and any(w in n for w in ("cap", "limit", "budget", "max"))]
