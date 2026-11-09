"""Safety gates of the existing experiment CLI (maps.experiments.receiver.main).

Observed contract (from the implementation; these tests pin it, they do not redefine it):
  * flags: --config, --mock, --live, --confirm-spend, --export-grid, --export-balance, --run-id;
  * the configuration and the grid are loaded first, then --export-grid / --export-balance (which
    write a file and return 0), then the gate;
  * neither --mock nor --live prints "PLAN ONLY" and returns 0 without running anything; BOTH is
    rejected with exit code 2 (v2.3.29; before v2.3.29 it was silently treated as plan-only);
  * --mock runs the existing runner with the mock client into <results_dir>/mock/<run id>;
  * --live (Stage 4E) needs --policy, --profile and --expected-policy-digest, runs the policy and endpoint preflight and
    then returns 2 (the FINAL REFUSAL) before the .env file is read, the key is looked up or any client is built;
  * expected configuration, scenario and design failures, and an unsafe run directory, return 2 with
    a clean message (v2.3.29; before v2.3.29 they were uncaught exceptions).
These tests use a synthetic configuration, temporary directories, recording doubles and a blocked
network. They show the gates refuse what they should; they do not show that live execution is safe.
"""

from __future__ import annotations

import json

import pytest

from maps.mock_client import MockClient

from cs_support import FAKE_KEY_ENV, harness, policy_args, write_config  # noqa: F401  (harness is a fixture)


# ---------------------------------------------------------------------------
# Plan-only is the default; --confirm-spend alone changes nothing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("enabled", [False, True], ids=["api-disabled", "api-enabled"])
def test_no_flags_means_plan_only(harness, enabled):
    code, out, err = harness.invoke(config=write_config(harness.tmp_path, enabled=enabled))
    assert code == 0 and "PLAN ONLY" in out and "No calls made" in out and err == ""
    assert "episodes: 96" in out and "MOCK RUN" not in out and "done:" not in out
    harness.assert_nothing_executed()
    harness.assert_no_output()


@pytest.mark.parametrize("enabled", [False, True], ids=["api-disabled", "api-enabled"])
def test_confirm_spend_alone_does_not_activate_anything(harness, enabled):
    code, out, err = harness.invoke("--confirm-spend", config=write_config(harness.tmp_path, enabled=enabled))
    assert code == 0 and "PLAN ONLY" in out and err == ""
    harness.assert_nothing_executed()
    harness.assert_no_output()


# ---------------------------------------------------------------------------
# --live (Stage 4E): argument checks, then a PREFLIGHT (policy, digest, endpoint), then the FINAL REFUSAL. Every
# --live invocation is refused with exit 2 before the .env file, a key lookup, a client, a run directory or a run.
# ---------------------------------------------------------------------------
FINAL = "FINAL REFUSAL"
LIVE_FLAGS = [
    ([], False), ([], True), (["--confirm-spend"], False), (["--confirm-spend"], True), (["--confirm-spend", "--run-id", "any-id"], True),
]
LIVE_IDS = ["no-confirm-disabled", "no-confirm-enabled", "confirm-disabled", "confirm-enabled", "confirm-enabled-run-id"]


@pytest.mark.parametrize("flags,enabled", LIVE_FLAGS, ids=LIVE_IDS)
def test_every_live_invocation_with_a_passing_preflight_ends_in_the_final_refusal(harness, flags, enabled):
    config = write_config(harness.tmp_path, enabled=enabled)
    code, out, err = harness.invoke("--live", *flags, *policy_args(harness.tmp_path, config), config=config)
    assert code == 2 and FINAL in err and "not authorized" in err and "done:" not in out and "PLAN ONLY" not in out
    harness.assert_nothing_executed()           # no .env read, no key lookup, no client, no run
    harness.assert_no_output()                  # no run directory, no claim, no results directory


@pytest.mark.parametrize("value", [None, "", "dummy-not-a-real-key"], ids=["variable-unset", "variable-empty", "variable-dummy"])
def test_the_final_refusal_does_not_depend_on_or_read_the_key_variable(harness, monkeypatch, value):
    if value is not None:
        monkeypatch.setenv(FAKE_KEY_ENV, value)
    config = write_config(harness.tmp_path, enabled=True)
    code, out, err = harness.invoke("--live", "--confirm-spend", *policy_args(harness.tmp_path, config), config=config)
    assert code == 2 and FINAL in err and "is not set" not in err
    assert not value or value not in out + err                        # a dummy value is never echoed
    harness.assert_nothing_executed()                                 # key_lookup=False, dotenv=False
    assert harness.calls.get_api_key == [] and harness.calls.load_dotenv == []
    harness.assert_no_output()


@pytest.mark.parametrize("missing", ["--policy", "--profile", "--expected-policy-digest"])
def test_live_requires_all_three_policy_arguments(harness, missing):
    config = write_config(harness.tmp_path, enabled=True)
    args = policy_args(harness.tmp_path, config)
    index = args.index(missing)
    del args[index:index + 2]
    code, out, err = harness.invoke("--live", "--confirm-spend", *args, config=config)
    assert code == 2 and "--live requires --policy, --profile and --expected-policy-digest" in err and FINAL not in err
    harness.assert_nothing_executed()
    harness.assert_no_output()


@pytest.mark.parametrize("mode", [["--mock"], [], ["--export-grid", "X"]], ids=["mock", "plan-only", "export"])
def test_live_only_arguments_are_refused_without_live(harness, mode):
    config = write_config(harness.tmp_path, enabled=False)
    args = ["X" if a == "X" else a for a in mode]
    if "X" in args:
        args[args.index("X")] = str(harness.tmp_path / "grid.tsv")
    code, out, err = harness.invoke(*args, "--policy", "p.json", config=config)
    assert code == 2 and "only valid with --live" in err and "done:" not in out
    harness.assert_nothing_executed()
    harness.assert_no_output()


# ---------------------------------------------------------------------------
# --mock follows the mock-only path
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("extra", [[], ["--confirm-spend"]], ids=["mock", "mock-confirm-spend"])
def test_mock_runs_the_mock_client_only(harness, extra):
    code, out, err = harness.invoke("--mock", "--run-id", "cli-test-run", *extra, config=write_config(harness.tmp_path, enabled=False))
    assert code == 0 and "MOCK RUN" in out and "NOT research data" in out and "done: 96/96 valid" in out and err == ""
    assert len(harness.calls.run_experiment) == 1 and isinstance(harness.calls.run_experiment[0], MockClient)
    assert harness.calls.live_client == [] and harness.calls.get_api_key == [] and harness.calls.load_dotenv == []
    run_dir = harness.results_dir / "mock" / "cli-test-run"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["client"] == "mock" and manifest["synthetic_mock_data"] is True
    calls = [json.loads(line) for line in (run_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 96 and {c["client"] for c in calls} == {"mock"}
    assert sorted(p.name for p in harness.results_dir.iterdir()) == ["mock"]     # nothing under a "live" stage name


@pytest.mark.parametrize("extra", [[], ["--confirm-spend"]], ids=["mock", "mock-confirm-spend"])
def test_mock_with_a_configuration_that_enables_live_calls_is_refused_before_anything_runs(harness, extra):
    """Changed in v2.3.33: before the mock CLI used the run executor (mock-only), --mock tolerated api.enabled=true."""
    code, out, err = harness.invoke("--mock", "--run-id", "cli-test-run", *extra, config=write_config(harness.tmp_path, enabled=True))
    assert code == 2 and "enables live API calls" in err and "done:" not in out
    harness.assert_nothing_executed()
    harness.assert_no_output()


# ---------------------------------------------------------------------------
# Combinations: contradictory flags and export modes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("extra", [[], ["--confirm-spend"]], ids=["mock-live", "mock-live-confirm"])
def test_mock_together_with_live_is_rejected(harness, extra):
    """CHANGED in v2.3.29: this used to be plan-only with exit 0; contradictory flags are now an error."""
    code, out, err = harness.invoke("--mock", "--live", *extra, config=write_config(harness.tmp_path, enabled=True))
    assert code == 2 and "mutually exclusive" in err and out == ""
    harness.assert_nothing_executed()
    harness.assert_no_inputs_loaded()
    harness.assert_no_output()


def test_export_modes_write_a_file_and_return_before_the_gates(harness):
    grid, balance = harness.tmp_path / "grid.tsv", harness.tmp_path / "balance.json"
    config = write_config(harness.tmp_path, enabled=True)
    code, out, err = harness.invoke("--live", "--confirm-spend", "--export-grid", str(grid), config=config)
    assert code == 0 and "grid written" in out and grid.read_text(encoding="utf-8").startswith("idx\tepisode_id")
    code, out, err = harness.invoke("--live", "--export-balance", str(balance), config=config)
    assert code == 0 and "balance written" in out and "single_root_index_by_truth" in json.loads(balance.read_text(encoding="utf-8"))
    harness.assert_nothing_executed()           # even with --live the export modes never reach a client or the runner
    harness.assert_no_output()


def test_unknown_flags_exit_before_the_configuration_is_loaded(harness):
    with pytest.raises(SystemExit) as exc:
        harness.invoke("--live", "--spend-everything", config=write_config(harness.tmp_path, enabled=True))
    assert exc.value.code == 2
    harness.assert_nothing_executed()
    harness.assert_no_output()


# ---------------------------------------------------------------------------
# Invalid or incomplete configuration
# ---------------------------------------------------------------------------
def test_missing_or_malformed_configuration_is_a_clean_error_before_execution(harness):
    """CHANGED in v2.3.29: these used to be uncaught exceptions (tracebacks)."""
    code, out, err = harness.invoke("--mock", config=harness.tmp_path / "no-such-config.json")
    assert code == 2 and "configuration file not found" in err and "Traceback" not in err
    broken = harness.tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    code, out, err = harness.invoke("--live", "--confirm-spend", config=broken)
    assert code == 2 and "not valid JSON" in err and "Traceback" not in err
    harness.assert_nothing_executed()
    harness.assert_no_output()


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda c: c["api"].pop("api_key_env"), "api.api_key_env: missing"),      # incomplete live-execution settings
        (lambda c: c["api"].pop("base_url"), "api.base_url: missing"),
        (lambda c: c["api"].update(max_retries=-1), "api.max_retries: greater_than_equal"),
        (lambda c: c.update(unexpected_setting=True), "unexpected_setting: extra_forbidden"),
        (lambda c: c["output"].update(stage="live"), "output.stage: literal_error"),
    ],
    ids=["no-key-env", "no-base-url", "negative-retries", "unknown-field", "unknown-stage"],
)
def test_invalid_live_settings_are_rejected_by_configuration_validation(harness, mutate, expected):
    config = write_config(harness.tmp_path, enabled=True, mutate=mutate)
    code, out, err = harness.invoke("--live", "--confirm-spend", config=config)
    assert code == 2 and "configuration is invalid" in err and expected in err and "Traceback" not in err
    harness.assert_nothing_executed()
    harness.assert_no_output()


def test_main_stage_requires_frozen_scenarios_even_in_plan_only_mode(harness):
    config = write_config(harness.tmp_path, stage="main")
    for args in ([], ["--mock"]):
        code, out, err = harness.invoke(*args, config=config)               # the synthetic scenarios are drafts
        assert code == 2 and "frozen" in err and "Traceback" not in err
    harness.assert_nothing_executed()
    harness.assert_no_output()


def test_a_live_configuration_does_not_make_a_plan_only_invocation_live(harness):
    for args in ([], ["--confirm-spend"]):
        code, out, err = harness.invoke(*args, config=write_config(harness.tmp_path, enabled=True))
        assert code == 0 and "PLAN ONLY" in out
    harness.assert_nothing_executed()
    harness.assert_no_output()
