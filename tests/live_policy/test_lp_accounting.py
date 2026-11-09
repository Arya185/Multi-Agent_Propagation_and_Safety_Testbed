"""Request-attempt accounting, reservation, retry/strict-mode preconditions (fake client, fake clock)."""

from __future__ import annotations

import pytest

from maps.llm_client import ApiDisabledError
from maps.runs.live_budget import AbortReason, BudgetAbort, BudgetedClient, CLAIM_CLIENT_ATTEMPTS, CLAIM_STRICT_PHYSICAL
from maps.runs.live_policy import AccountingBasis, PolicyError
from maps.schemas import LLMResult

from lp_support import FakeClient, FakeClock, SENTINEL, err, make_policy, make_request, ok


def wrap(client, policy=None, clock=None):
    return BudgetedClient(client, policy or make_policy(), clock=clock or FakeClock())


# ---- construction preconditions ---------------------------------------------------------------
def test_the_retry_setting_must_match_the_policy():
    with pytest.raises(PolicyError, match="max_retries"):
        wrap(FakeClient([], max_retries=2), make_policy(max_retries=0))
    with pytest.raises(PolicyError, match="max_retries"):
        wrap(FakeClient([], max_retries=0), make_policy(max_retries=1, max_request_attempts=20))
    wrap(FakeClient([], max_retries=1), make_policy(max_retries=1, max_request_attempts=20))


@pytest.mark.parametrize("value", [None, True, 0.0, "0"])
def test_a_missing_or_non_integer_client_retry_setting_is_refused(value):
    client = FakeClient([])
    client.max_retries = value
    with pytest.raises(PolicyError, match="max_retries"):
        wrap(client)
    bare = FakeClient([])
    del bare.max_retries
    with pytest.raises(PolicyError, match="max_retries"):
        wrap(bare)


def test_the_client_needs_a_name():
    client = FakeClient([])
    client.name = ""
    with pytest.raises(PolicyError, match="name"):
        wrap(client)


def test_a_policy_object_is_required():
    with pytest.raises(PolicyError, match="LivePolicy"):
        BudgetedClient(FakeClient([]), {"max_retries": 0})  # type: ignore[arg-type]


STRICT = dict(accounting_basis=AccountingBasis.STRICT_PHYSICAL)


@pytest.mark.parametrize("flag", [None, False, 1, "true", "yes"])
def test_strict_physical_refuses_a_client_that_does_not_explicitly_declare_redirects_disabled(flag):
    client = FakeClient([], redirects_disabled=flag) if flag is not None else FakeClient([])
    with pytest.raises(PolicyError, match="redirects_disabled"):
        wrap(client, make_policy(**STRICT))


def test_strict_physical_is_not_inferred_from_the_label_or_the_client_name():
    client = FakeClient([], name="openrouter-hardened-redirects-disabled")
    with pytest.raises(PolicyError, match="redirects_disabled"):
        wrap(client, make_policy(**STRICT))


def test_strict_physical_accepts_an_explicitly_hardened_client_and_labels_honestly():
    budget = wrap(FakeClient([ok()], redirects_disabled=True), make_policy(**STRICT))
    budget.complete(make_request())
    summary = budget.summary()
    assert summary.accounting_basis == "strict_physical" and summary.redirect_exposure == "none_redirects_disabled"
    assert summary.accounting_claim == CLAIM_STRICT_PHYSICAL


def test_client_attempts_mode_never_claims_physical_accounting():
    budget = wrap(FakeClient([ok()]))
    budget.complete(make_request())
    summary = budget.summary()
    assert summary.accounting_basis == "client_attempts" and summary.redirect_exposure == "not_counted"
    assert summary.accounting_claim == CLAIM_CLIENT_ATTEMPTS and "not guaranteed" in summary.accounting_claim
    assert "physical" not in summary.accounting_claim
    assert not any("physical" in name for name in summary.to_dict() if name != "accounting_claim")


def test_client_attempts_mode_does_not_require_a_redirect_declaration_and_ignores_a_false_one():
    wrap(FakeClient([]))
    wrap(FakeClient([], redirects_disabled=False))


def test_the_wrapper_exposes_the_client_name_and_behaves_like_a_client():
    budget = wrap(FakeClient([ok()], name="fake-name"))
    assert budget.name == "fake-name" and "fake-name" in repr(budget)
    result = budget.complete(make_request())
    assert isinstance(result, LLMResult) and result.content == "SYNTHETIC answer"


# ---- reservation and charging ---------------------------------------------------------------
def test_zero_retries_reserve_exactly_one_attempt_per_call():
    budget = wrap(FakeClient([ok(), ok()]))
    assert budget.summary().reserved_attempts_per_call == 1
    budget.complete(make_request())
    budget.complete(make_request())
    assert budget.summary().attempts_charged == 2


def test_nonzero_retries_reserve_one_plus_retries_but_charge_the_actual_attempts():
    policy = make_policy(max_retries=2, max_request_attempts=30)
    budget = wrap(FakeClient([ok(attempts=1), ok(attempts=3), ok(attempts=2)], max_retries=2), policy)
    for _ in range(3):
        budget.complete(make_request())
    summary = budget.summary()
    assert summary.reserved_attempts_per_call == 3 and summary.attempts_charged == 6 and summary.attempt_count_untrusted == 0


def test_the_cap_is_never_exceeded_and_a_refused_call_does_not_reach_the_client():
    policy = make_policy(planned_episodes=2, max_episodes=5, max_retries=2, max_request_attempts=6, max_consecutive_nonfatal_errors=2)
    client = FakeClient([ok(attempts=3), ok(attempts=3), ok(attempts=1)], max_retries=2)
    budget = wrap(client, policy)
    budget.complete(make_request())
    budget.complete(make_request())
    assert budget.summary().attempts_charged == 6
    with pytest.raises(BudgetAbort) as caught:
        budget.complete(make_request())
    assert caught.value.reason is AbortReason.REQUEST_BUDGET and client.calls == 2
    assert budget.summary().attempts_charged == 6 <= policy.max_request_attempts


def test_a_call_is_refused_when_the_remaining_budget_cannot_cover_the_worst_case_even_if_it_would_have_fit():
    """Cap 6, reservation 3, one attempt used per call: the 4th call fits (3 + 3 <= 6); the 5th does not (4 + 3 > 6)."""
    policy = make_policy(planned_episodes=2, max_episodes=9, max_retries=2, max_request_attempts=6, max_consecutive_nonfatal_errors=2)
    client = FakeClient([ok(attempts=1)] * 6, max_retries=2)
    budget = wrap(client, policy)
    for _ in range(4):
        budget.complete(make_request())
    assert budget.summary().attempts_charged == 4
    with pytest.raises(BudgetAbort) as caught:
        budget.complete(make_request())
    assert caught.value.reason is AbortReason.REQUEST_BUDGET and client.calls == 4


def test_the_reservation_boundary_is_charged_attempts_plus_reservation_against_the_cap():
    """Cap 3, reservation 2: call 1 (0 + 2), call 2 (1 + 2 = 3) fit; call 3 (2 + 2 = 4) does not."""
    policy = make_policy(planned_episodes=1, max_episodes=5, max_retries=1, max_request_attempts=3, max_consecutive_nonfatal_errors=1)
    client = FakeClient([ok(attempts=1), ok(attempts=1), ok(attempts=1)], max_retries=1)
    budget = wrap(client, policy)
    budget.complete(make_request())
    budget.complete(make_request())
    with pytest.raises(BudgetAbort) as caught:
        budget.complete(make_request())
    assert caught.value.reason is AbortReason.REQUEST_BUDGET and client.calls == 2


@pytest.mark.parametrize("attempts", [0, -1, 5, 99, True, None, 1.0, "1"], ids=["zero", "negative", "over", "far-over", "bool", "none", "float", "str"])
def test_an_implausible_attempt_count_charges_the_full_reservation(attempts):
    policy = make_policy(max_retries=2, max_request_attempts=30)
    budget = wrap(FakeClient([ok(attempts=1)], max_retries=2), policy)
    result = ok()
    object.__setattr__(result, "attempts", attempts)       # bypass pydantic to simulate a misbehaving client
    budget._client.script = [result]
    budget.complete(make_request())
    summary = budget.summary()
    assert summary.attempts_charged == 3 and summary.attempt_count_untrusted == 1


def test_a_valid_count_equal_to_the_reservation_is_trusted():
    policy = make_policy(max_retries=2, max_request_attempts=30)
    budget = wrap(FakeClient([ok(attempts=3)], max_retries=2), policy)
    budget.complete(make_request())
    assert budget.summary().attempts_charged == 3 and budget.summary().attempt_count_untrusted == 0


def test_a_raised_exception_charges_the_full_reservation_exactly_once_and_propagates_unchanged():
    policy = make_policy(max_retries=2, max_request_attempts=30)
    boom = RuntimeError(f"unexpected {SENTINEL}")
    client = FakeClient([boom], max_retries=2)
    budget = wrap(client, policy)
    with pytest.raises(RuntimeError) as caught:
        budget.complete(make_request())
    assert caught.value is boom
    summary = budget.summary()
    assert summary.attempts_charged == 3 and summary.calls_raised == 1 and summary.logical_calls_started == 1
    assert summary.stop_reason == "unexpected_client_exception" and summary.exception_class_counts == (("RuntimeError", 1),)
    with pytest.raises(BudgetAbort):
        budget.complete(make_request())
    assert budget.summary().attempts_charged == 3 and client.calls == 1       # nothing charged again, no new call


def test_the_disabled_client_exception_is_fatal_and_charged_once():
    client = FakeClient([ApiDisabledError(f"disabled {SENTINEL}")])
    budget = wrap(client)
    with pytest.raises(BudgetAbort) as caught:
        budget.complete(make_request())
    assert caught.value.reason is AbortReason.DISABLED_CLIENT and SENTINEL not in str(caught.value) and caught.value.__cause__ is None
    assert budget.summary().attempts_charged == 1 and budget.summary().stop_reason == "disabled_client"
    with pytest.raises(BudgetAbort) as again:
        budget.complete(make_request())
    assert again.value.reason is AbortReason.DISABLED_CLIENT and client.calls == 1


def test_a_keyboard_interrupt_in_the_client_is_charged_and_propagates():
    client = FakeClient([KeyboardInterrupt()])
    budget = wrap(client)
    with pytest.raises(KeyboardInterrupt):
        budget.complete(make_request())
    assert budget.summary().attempts_charged == 1 and budget.summary().stop_reason == "unexpected_client_exception"


def test_a_client_that_returns_something_other_than_a_result_is_treated_as_a_failure():
    client = FakeClient([])
    client.complete = lambda request: {"content": SENTINEL}      # type: ignore[assignment]
    budget = wrap(client)
    with pytest.raises(BudgetAbort) as caught:
        budget.complete(make_request())
    assert caught.value.reason is AbortReason.UNEXPECTED_CLIENT_EXCEPTION and SENTINEL not in str(caught.value)
    assert budget.summary().attempts_charged == 1 and budget.summary().exception_class_counts == (("InvalidResultType", 1),)


def test_the_episode_cap_refuses_without_a_client_call():
    policy = make_policy(planned_episodes=2, max_episodes=2, max_request_attempts=50, max_consecutive_nonfatal_errors=2)
    client = FakeClient([ok(), ok(), ok()])
    budget = wrap(client, policy)
    budget.complete(make_request())
    budget.complete(make_request())
    with pytest.raises(BudgetAbort) as caught:
        budget.complete(make_request())
    assert caught.value.reason is AbortReason.EPISODE_CAP and client.calls == 2
    assert budget.summary().stop_reason == "episode_cap" and budget.summary().logical_calls_started == 2


def test_the_summary_is_immutable_and_fixed_at_the_time_it_was_taken():
    budget = wrap(FakeClient([ok(), ok()]))
    budget.complete(make_request())
    snapshot = budget.summary()
    budget.complete(make_request())
    assert snapshot.logical_calls_started == 1 and budget.summary().logical_calls_started == 2
    with pytest.raises(Exception):
        snapshot.attempts_charged = 0  # type: ignore[misc]
