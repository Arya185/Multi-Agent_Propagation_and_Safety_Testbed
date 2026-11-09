"""LivePolicy validation and serialization (pure)."""

from __future__ import annotations

import json

import pytest

from maps.runs.live_policy import AccountingBasis, LivePolicy, PolicyError

from lp_support import make_policy, policy_dict

SECRET_LOOKING = "SENTINEL-VALUE-12345"


def test_a_valid_policy_exposes_its_fields_and_reservation():
    policy = make_policy(max_retries=2, max_request_attempts=30)
    assert policy.reservation_per_call == 3 and policy.accounting_basis is AccountingBasis.CLIENT_ATTEMPTS
    assert make_policy().reservation_per_call == 1


def test_the_policy_is_immutable():
    policy = make_policy()
    with pytest.raises(Exception):
        policy.max_episodes = 99  # type: ignore[misc]


def test_the_policy_has_no_defaults_so_missing_arguments_fail():
    with pytest.raises(TypeError):
        LivePolicy()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        LivePolicy(planned_episodes=10)  # type: ignore[call-arg]
    for field in policy_dict():
        data = policy_dict()
        del data[field]
        with pytest.raises(PolicyError, match=field):
            LivePolicy.from_mapping(data)


def test_unknown_fields_are_rejected_without_naming_their_values():
    with pytest.raises(PolicyError, match="1 unknown field"):
        LivePolicy.from_mapping({**policy_dict(), "surprise": SECRET_LOOKING})


@pytest.mark.parametrize("field", ["planned_episodes", "max_episodes", "max_request_attempts", "max_retries", "deadline_seconds", "max_consecutive_nonfatal_errors"])
@pytest.mark.parametrize("bad", [True, 1.0, 2.5, None, float("inf"), "5", [5]], ids=["bool", "float", "float2", "none", "inf", "str", "list"])
def test_numeric_fields_must_be_real_integers(field, bad):
    with pytest.raises(PolicyError, match=field):
        make_policy(**{field: bad})


@pytest.mark.parametrize(
    "overrides,field",
    [
        (dict(planned_episodes=0), "planned_episodes"),
        (dict(planned_episodes=-1), "planned_episodes"),
        (dict(max_episodes=9), "max_episodes"),
        (dict(max_retries=-1), "max_retries"),
        (dict(deadline_seconds=0), "deadline_seconds"),
        (dict(deadline_seconds=-5), "deadline_seconds"),
        (dict(max_consecutive_nonfatal_errors=0), "max_consecutive_nonfatal_errors"),
        (dict(max_consecutive_nonfatal_errors=11), "max_consecutive_nonfatal_errors"),
        (dict(max_request_attempts=0), "max_request_attempts"),
        (dict(max_request_attempts=9), "max_request_attempts"),
        (dict(max_retries=1, max_request_attempts=19), "max_request_attempts"),
    ],
)
def test_limits_and_relations_are_enforced(overrides, field):
    with pytest.raises(PolicyError, match=field):
        make_policy(**overrides)


def test_the_request_cap_must_cover_the_whole_grid_with_the_worst_case_reservation():
    make_policy(max_retries=1, max_request_attempts=20)           # exactly 10 * 2
    make_policy(max_retries=0, max_request_attempts=10)           # exactly 10 * 1
    with pytest.raises(PolicyError):
        make_policy(max_retries=1, max_request_attempts=19)


def test_the_boundaries_of_the_valid_ranges_are_accepted():
    make_policy(max_consecutive_nonfatal_errors=1)
    make_policy(max_consecutive_nonfatal_errors=10)
    make_policy(deadline_seconds=1)
    make_policy(max_episodes=11)


@pytest.mark.parametrize("bad", ["", "   ", None, 5, b"x"])
def test_the_approval_reference_must_be_a_non_empty_string(bad):
    with pytest.raises(PolicyError, match="approval_reference"):
        make_policy(approval_reference=bad)


@pytest.mark.parametrize("bad", ["client_attempts", "CLIENT_ATTEMPTS", None, 1])
def test_direct_construction_needs_a_real_enum_member(bad):
    with pytest.raises(PolicyError, match="accounting_basis"):
        make_policy(accounting_basis=bad)


@pytest.mark.parametrize("bad", [{408}, [408], (408,), {400, 500}, {99}, {600}, {True}, {"408"}, {408.0}, None, "408"])
def test_status_sets_must_be_frozensets_of_4xx_integers(bad):
    with pytest.raises(PolicyError, match="nonfatal_4xx_statuses"):
        make_policy(nonfatal_4xx_statuses=bad)


@pytest.mark.parametrize("bad", [{500}, {399}, {500, 429}, {True}, {"x"}, {408.5}])
def test_status_entries_outside_400_to_499_or_non_integers_are_rejected(bad):
    with pytest.raises(PolicyError, match="nonfatal_4xx_statuses"):
        make_policy(nonfatal_4xx_statuses=frozenset(bad))


def test_an_empty_nonfatal_status_set_is_allowed_because_it_is_explicit():
    assert make_policy(nonfatal_4xx_statuses=frozenset()).nonfatal_4xx_statuses == frozenset()


@pytest.mark.parametrize("bad", [1, 0, None, "yes"])
def test_fatal_3xx_must_be_a_boolean(bad):
    with pytest.raises(PolicyError, match="fatal_3xx"):
        make_policy(fatal_3xx=bad)


def test_error_messages_never_contain_the_supplied_value():
    for overrides in (dict(approval_reference=5), dict(max_episodes=SECRET_LOOKING), dict(deadline_seconds=SECRET_LOOKING),
                      dict(accounting_basis=SECRET_LOOKING), dict(nonfatal_4xx_statuses=frozenset({SECRET_LOOKING})),
                      dict(fatal_3xx=SECRET_LOOKING)):
        with pytest.raises(PolicyError) as caught:
            make_policy(**overrides)
        assert SECRET_LOOKING not in str(caught.value)
    with pytest.raises(PolicyError) as caught:
        LivePolicy.from_mapping(policy_dict(accounting_basis=SECRET_LOOKING))
    assert SECRET_LOOKING not in str(caught.value)


def test_serialization_is_deterministic_and_enum_values_are_plain_strings():
    policy = make_policy(nonfatal_4xx_statuses=frozenset({429, 408}))
    first, second = json.dumps(policy.to_dict()), json.dumps(make_policy(nonfatal_4xx_statuses=frozenset({408, 429})).to_dict())
    assert first == second
    data = policy.to_dict()
    assert data["accounting_basis"] == "client_attempts" and type(data["accounting_basis"]) is str
    assert data["nonfatal_4xx_statuses"] == [408, 429] and list(data) == list(policy_dict())


def test_round_trip_through_from_mapping():
    for basis in AccountingBasis:
        policy = make_policy(accounting_basis=basis, max_retries=1, max_request_attempts=20)
        assert LivePolicy.from_mapping(policy.to_dict()) == policy
        assert LivePolicy.from_mapping(json.loads(json.dumps(policy.to_dict()))) == policy


@pytest.mark.parametrize("bad", ["strict", "", "Strict_Physical", 1, None, ["client_attempts"]])
def test_from_mapping_rejects_invalid_enum_values(bad):
    with pytest.raises(PolicyError, match="accounting_basis"):
        LivePolicy.from_mapping(policy_dict(accounting_basis=bad))


def test_from_mapping_accepts_an_enum_member_and_container_types_for_statuses():
    assert LivePolicy.from_mapping(policy_dict(accounting_basis=AccountingBasis.STRICT_PHYSICAL)).accounting_basis is AccountingBasis.STRICT_PHYSICAL
    for container in ([408, 429], (408, 429), {408, 429}, frozenset({408, 429})):
        assert LivePolicy.from_mapping(policy_dict(nonfatal_4xx_statuses=container)).nonfatal_4xx_statuses == frozenset({408, 429})


@pytest.mark.parametrize("bad", ["408", 408, None, [[408]], [{}]])
def test_from_mapping_rejects_bad_status_containers(bad):
    with pytest.raises(PolicyError, match="nonfatal_4xx_statuses"):
        LivePolicy.from_mapping(policy_dict(nonfatal_4xx_statuses=bad))


@pytest.mark.parametrize("bad", [None, [], "policy", 5, [("a", 1)]])
def test_from_mapping_requires_a_mapping(bad):
    with pytest.raises(PolicyError, match="mapping"):
        LivePolicy.from_mapping(bad)
