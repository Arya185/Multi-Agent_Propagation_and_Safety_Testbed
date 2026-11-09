"""CLI hardening (v2.3.29): contradictory flags, clean configuration errors, run-directory guard.

Synthetic configuration, temporary directories and recording doubles only. The live path is only ever
exercised up to a REFUSAL (unsafe directory, missing gate or key); no test can reach a live client
or the network.
"""

from __future__ import annotations

import json
import re

import pytest

from maps.runs.ids import GENERATED_RUN_ID_PATTERN, validate_run_id

import maps.experiments.receiver as receiver
from maps.mock_client import MockClient

from cs_support import FAKE_KEY_ENV, harness, policy_args, write_config  # noqa: F401  (harness is a fixture)


def tree(path):
    import hashlib

    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------
# A. Contradictory flags
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("extra", [[], ["--confirm-spend"], ["--run-id", "x"], ["--export-grid", "SKIP"]], ids=["bare", "confirm", "run-id", "export"])
def test_mock_and_live_together_are_rejected_before_anything_is_loaded(harness, extra):
    extra = [str(harness.tmp_path / "grid.tsv") if a == "SKIP" else a for a in extra]
    absent_config = harness.tmp_path / "no-such-config.json"      # reading it would give a different error
    code, out, err = harness.invoke("--mock", "--live", *extra, config=absent_config)
    assert code == 2 and "mutually exclusive" in err and "configuration" not in err and out == ""
    harness.assert_no_inputs_loaded()                            # not even the configuration was opened
    harness.assert_nothing_executed()
    harness.assert_no_output()
    assert not (harness.tmp_path / "grid.tsv").exists()


def test_single_flags_keep_their_meaning(harness):
    plan, _, _ = harness.invoke(config=write_config(harness.tmp_path))[0:3]
    assert plan == 0
    code, out, err = harness.invoke("--mock", config=write_config(harness.tmp_path))
    assert code == 0 and "MOCK RUN" in out
    config = write_config(harness.tmp_path, enabled=True)
    refused = harness.invoke("--live", *policy_args(harness.tmp_path, config), config=config)
    assert refused[0] == 2 and "FINAL REFUSAL" in refused[2]                # Stage 4E: --live ends in the final refusal


# ---------------------------------------------------------------------------
# B. Controlled configuration errors
# ---------------------------------------------------------------------------
def assert_clean_failure(harness, code, out, err, *, phrase):
    assert code == 2 and phrase in err and err.startswith("error:") and "Traceback" not in err and out == ""
    harness.assert_nothing_executed()
    harness.assert_no_output()


def test_missing_configuration_file(harness):
    code, out, err = harness.invoke("--mock", config=harness.tmp_path / "missing.json")
    assert_clean_failure(harness, code, out, err, phrase="configuration file not found")


def test_a_directory_or_unreadable_path_as_configuration(harness):
    code, out, err = harness.invoke("--mock", config=harness.tmp_path)
    assert_clean_failure(harness, code, out, err, phrase="could not be read")


def test_malformed_json_configuration(harness):
    broken = harness.tmp_path / "broken.json"
    broken.write_text('{"experiment_id": ', encoding="utf-8")
    code, out, err = harness.invoke("--mock", config=broken)
    assert_clean_failure(harness, code, out, err, phrase="not valid JSON")
    assert "line 1" in err


def test_configuration_that_is_not_utf8(harness):
    bad = harness.tmp_path / "bad.json"
    bad.write_bytes(b'{"seed": "\xff\xfe"}')
    code, out, err = harness.invoke("--mock", config=bad)
    assert_clean_failure(harness, code, out, err, phrase="not valid UTF-8")


def test_schema_invalid_configuration_names_fields_and_types_only(harness):
    sentinel = "SYN-VALUE-SENTINEL"
    config = write_config(harness.tmp_path, mutate=lambda c: c.update(seed=sentinel, unexpected_setting=sentinel))
    code, out, err = harness.invoke("--mock", config=config)
    assert_clean_failure(harness, code, out, err, phrase="configuration is invalid")
    assert "seed:" in err and "unexpected_setting: extra_forbidden" in err
    assert sentinel not in err                                      # offending values are never echoed


def test_invalid_values_in_the_configuration(harness):
    config = write_config(harness.tmp_path, mutate=lambda c: c["sampling"].update(temperature=5.0, max_tokens=0))
    code, out, err = harness.invoke("--mock", config=config)
    assert_clean_failure(harness, code, out, err, phrase="sampling.max_tokens")
    assert "sampling.temperature" in err


def test_unreadable_scenarios_are_reported_without_their_content(harness):
    bad_dir = harness.tmp_path / "scenarios"
    bad_dir.mkdir()
    (bad_dir / "broken.json").write_text('{"scenario_id": "SYN-CONTENT-SENTINEL", ', encoding="utf-8")
    config = write_config(harness.tmp_path, mutate=lambda c: c["design"].update(scenario_dir=str(bad_dir)))
    code, out, err = harness.invoke("--mock", config=config)
    assert_clean_failure(harness, code, out, err, phrase="scenario files could not be loaded")
    assert "SYN-CONTENT-SENTINEL" not in err and "details withheld" in err


def test_a_design_check_refusal_is_clean(harness):
    code, out, err = harness.invoke("--mock", config=write_config(harness.tmp_path, stage="main"))
    assert_clean_failure(harness, code, out, err, phrase="refused by a design check")
    assert "frozen" in err


def test_configuration_errors_never_print_the_key_or_its_value(harness, monkeypatch):
    monkeypatch.setenv(FAKE_KEY_ENV, "SYN-SECRET-NOT-A-REAL-KEY")
    config = write_config(harness.tmp_path, enabled=True, mutate=lambda c: c["api"].update(max_retries=-1))
    code, out, err = harness.invoke("--live", "--confirm-spend", config=config)
    assert code == 2 and "SYN-SECRET-NOT-A-REAL-KEY" not in out + err
    code, out, err = harness.invoke("--live", "--confirm-spend", config=write_config(harness.tmp_path, enabled=False))
    assert code == 2 and "SYN-SECRET-NOT-A-REAL-KEY" not in out + err
    harness.assert_nothing_executed()


def test_expected_failures_keep_the_original_exception_as_their_cause(harness):
    with pytest.raises(receiver.CliInputError) as exc:
        receiver._load_inputs(str(harness.tmp_path / "missing.json"))
    assert isinstance(exc.value.__cause__, FileNotFoundError)


def test_unexpected_programming_errors_are_not_swallowed(harness):
    config = write_config(harness.tmp_path)

    def raising(exc):
        def raiser(*args, **kwargs):
            raise exc

        return raiser

    cases = (
        ("load_config", AttributeError("bug in load_config"), AttributeError),
        ("load_scenario_dir", TypeError("bug in the scenario loader"), TypeError),
        ("build_grid", RuntimeError("bug in build_grid"), RuntimeError),
        ("build_grid", ValueError("some other value error"), ValueError),   # a ValueError that is NOT a design refusal
    )
    for name, exc, expected in cases:
        with pytest.MonkeyPatch.context() as mp:                  # the harness doubles stay in place
            mp.setattr(receiver, name, raising(exc))
            with pytest.raises(expected, match=str(exc)):
                receiver.main(["--config", str(config), "--mock", "--run-id", "bug-run"])
    harness.assert_nothing_executed()
    harness.assert_no_output()


def test_an_error_inside_the_mock_runner_is_reported_as_a_failed_run_and_the_claimed_directory_is_preserved(harness, monkeypatch):
    """Changed in v2.3.33: the executor catches runner exceptions and reports them (exit code 1) instead of propagating."""
    def failing_runner(cfg, scenarios, client, out_dir, secrets=None, *a, **k):
        (out_dir / "partial.txt").write_text("partial output", encoding="utf-8")
        raise RuntimeError("runner crashed SENTINEL")

    monkeypatch.setattr(receiver, "run_experiment", failing_runner)
    code, out, err = harness.invoke("--mock", "--run-id", "crashed", config=write_config(harness.tmp_path))
    assert code == 1 and "failed:" in err and "stage: runner" in err and "done:" not in out
    assert "SENTINEL" not in err and "SENTINEL" not in out                       # the exception message is withheld
    run_dir = harness.results_dir / "mock" / "crashed"
    assert sorted(p.name for p in run_dir.iterdir()) == [
        ".maps_run_claim", "partial.txt", "run_events.jsonl", "run_integrity.json", "run_provenance.json"]   # nothing cleaned up
    assert (run_dir / "partial.txt").read_text(encoding="utf-8") == "partial output"
    assert json.loads((run_dir / "run_integrity.json").read_text(encoding="utf-8"))["analysis_eligible"] is False


# ---------------------------------------------------------------------------
# C. Run-directory guard integration
# ---------------------------------------------------------------------------
def test_a_new_run_directory_is_claimed_and_used(harness):
    code, out, err = harness.invoke("--mock", "--run-id", "fresh", config=write_config(harness.tmp_path))
    assert code == 0 and len(harness.calls.run_experiment) == 1 and isinstance(harness.calls.run_experiment[0], MockClient)
    run_dir = harness.results_dir / "mock" / "fresh"
    assert (run_dir / ".maps_run_claim").is_file() and (run_dir / "episodes.jsonl").is_file()
    assert json.loads((run_dir / ".maps_run_claim").read_text(encoding="utf-8"))["run_id"] == "fresh"


def test_an_existing_empty_run_directory_is_accepted(harness):
    (harness.results_dir / "mock" / "empty-run").mkdir(parents=True)
    code, out, err = harness.invoke("--mock", "--run-id", "empty-run", config=write_config(harness.tmp_path))
    assert code == 0 and "done: 96/96 valid" in out and len(harness.calls.run_experiment) == 1


def test_a_non_empty_run_directory_is_refused_before_the_runner_and_left_untouched(harness):
    run_dir = harness.results_dir / "mock" / "taken"
    run_dir.mkdir(parents=True)
    (run_dir / "episodes.jsonl").write_text("records of an earlier, possibly failed run\n", encoding="utf-8")
    before = tree(run_dir)
    code, out, err = harness.invoke("--mock", "--run-id", "taken", config=write_config(harness.tmp_path))
    assert code == 2 and err.startswith("refused: Refusing to use run directory") and "episodes.jsonl" in err and "done:" not in out
    harness.assert_nothing_executed()                                # the runner was never called
    assert tree(run_dir) == before and sorted(p.name for p in run_dir.iterdir()) == ["episodes.jsonl"]   # no claim, no new file


def test_a_repeated_run_with_the_same_run_id_is_refused_and_the_first_run_is_untouched(harness):
    config = write_config(harness.tmp_path)
    assert harness.invoke("--mock", "--run-id", "once", config=config)[0] == 0
    run_dir = harness.results_dir / "mock" / "once"
    before = tree(run_dir)
    code, out, err = harness.invoke("--mock", "--run-id", "once", config=config)
    assert code == 2 and "Refusing to use run directory" in err and len(harness.calls.run_experiment) == 1
    assert tree(run_dir) == before                                   # not overwritten, resumed or appended to


def test_partial_outputs_of_a_failed_earlier_run_are_preserved(harness):
    run_dir = harness.results_dir / "mock" / "failed-earlier"
    run_dir.mkdir(parents=True)
    (run_dir / "episodes.jsonl").write_text('{"half": "written"}\n', encoding="utf-8")
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    before = tree(run_dir)
    assert harness.invoke("--mock", "--run-id", "failed-earlier", config=write_config(harness.tmp_path))[0] == 2
    assert tree(run_dir) == before


def test_live_path_with_an_existing_directory_ends_in_the_final_refusal_and_the_directory_is_untouched(harness):
    run_dir = harness.results_dir / "pilot" / "taken"
    run_dir.mkdir(parents=True)
    (run_dir / "old.txt").write_text("x", encoding="utf-8")
    before = tree(run_dir)
    config = write_config(harness.tmp_path, enabled=True)
    code, out, err = harness.invoke("--live", "--confirm-spend", "--run-id", "taken", *policy_args(harness.tmp_path, config), config=config)
    assert code == 2 and "FINAL REFUSAL" in err and "done:" not in out
    harness.assert_nothing_executed()                                # no .env read, no key lookup, no live client, no runner
    assert tree(run_dir) == before                                   # the directory is not even inspected, let alone claimed


def test_a_refused_live_attempt_does_not_leave_a_run_directory(harness):
    config = write_config(harness.tmp_path, enabled=True)
    code, out, err = harness.invoke("--live", "--confirm-spend", "--run-id", "no-key", *policy_args(harness.tmp_path, config), config=config)
    assert code == 2 and "FINAL REFUSAL" in err
    harness.assert_nothing_executed()
    harness.assert_no_output()                                       # nothing is checked, claimed or created


def test_plan_only_and_export_modes_never_claim_a_run_directory(harness):
    config = write_config(harness.tmp_path, enabled=True)
    assert harness.invoke("--run-id", "plan", config=config)[0] == 0
    assert harness.invoke("--run-id", "plan", "--confirm-spend", config=config)[0] == 0
    assert harness.invoke("--run-id", "grid", "--export-grid", str(harness.tmp_path / "g.tsv"), config=config)[0] == 0
    assert harness.invoke("--run-id", "bal", "--export-balance", str(harness.tmp_path / "b.json"), config=config)[0] == 0
    harness.assert_nothing_executed()
    harness.assert_no_output()


@pytest.mark.parametrize("bad", ["", "../escape", "a/b", "has space", "x" * 129, "é"], ids=["empty", "traversal", "slash", "space", "too-long", "non-ascii"])
def test_invalid_run_ids_are_rejected_before_the_configuration_is_loaded(harness, bad):
    code, out, err = harness.invoke("--mock", "--run-id", bad, config=harness.tmp_path / "no-such-config.json")
    assert code == 2 and "--run-id" in err and "configuration" not in err
    harness.assert_no_inputs_loaded()
    harness.assert_nothing_executed()
    harness.assert_no_output()


def test_the_default_run_id_is_accepted_by_the_run_id_rule(harness):
    code, out, err = harness.invoke("--mock", config=write_config(harness.tmp_path))
    assert code == 0
    (run_dir,) = (harness.results_dir / "mock").iterdir()
    assert GENERATED_RUN_ID_PATTERN.fullmatch(run_dir.name) and validate_run_id(run_dir.name) == run_dir.name   # v2.3.33: shared generator
    assert (run_dir / ".maps_run_claim").is_file()


def test_design_refusal_is_still_a_value_error_for_existing_callers():
    assert issubclass(receiver.DesignRefusal, ValueError)
