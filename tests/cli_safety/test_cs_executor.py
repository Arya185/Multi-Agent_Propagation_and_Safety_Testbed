"""CLI integration with the run executor (v2.3.33): run ids, the mock path, live-path isolation, structure.

Synthetic configuration, temporary directories, recording doubles and a blocked network. The live path is
only exercised up to a REFUSAL; no test reaches a live client. These tests show the mock CLI path goes
through the executor and the live path does not; they do not show that live execution is safe.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import maps.experiments.receiver as receiver
from maps.mock_client import MockClient
from maps.runs.ids import GENERATED_RUN_ID_PATTERN

from cs_support import policy_args, harness, write_config  # noqa: F401  (harness is a fixture)

FIXED_ID = "20261107T170212123456Z-1a2b3c4d"
SUCCESS_FILES = {".maps_run_claim", "calls.jsonl", "contrast_gaps.json", "episodes.jsonl", "manifest.json",
                 "run_events.jsonl", "run_integrity.json", "run_provenance.json", "summary.json"}


@pytest.fixture
def executor_spy(monkeypatch):
    """Records calls to the executor as seen by the CLI and forwards to the real one."""
    calls = []
    real = receiver.execute_mock_run

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(receiver, "execute_mock_run", spy)
    return calls


@pytest.fixture
def forbidden_executor(monkeypatch):
    calls = []

    def refuse(**kwargs):
        calls.append(kwargs)
        raise AssertionError("the mock executor must not be reached on this path")

    monkeypatch.setattr(receiver, "execute_mock_run", refuse)
    return calls


# ---------------------------------------------------------------------------
# Run ids
# ---------------------------------------------------------------------------
def test_the_mock_default_run_id_comes_from_the_shared_generator(harness, monkeypatch):
    monkeypatch.setattr(receiver, "generate_run_id", lambda: FIXED_ID)
    code, out, err = harness.invoke("--mock", config=write_config(harness.tmp_path))
    assert code == 0 and (harness.results_dir / "mock" / FIXED_ID).is_dir()
    claim = json.loads((harness.results_dir / "mock" / FIXED_ID / ".maps_run_claim").read_text(encoding="utf-8"))
    assert claim["run_id"] == FIXED_ID


def test_the_unpatched_default_run_id_has_the_generated_format(harness):
    assert harness.invoke("--mock", config=write_config(harness.tmp_path))[0] == 0
    (run_dir,) = (harness.results_dir / "mock").iterdir()
    assert GENERATED_RUN_ID_PATTERN.fullmatch(run_dir.name)


def test_a_live_attempt_with_a_generated_run_id_creates_no_run_directory(harness, monkeypatch):
    monkeypatch.setattr(receiver, "generate_run_id", lambda: FIXED_ID)
    config = write_config(harness.tmp_path, enabled=True)
    code, out, err = harness.invoke("--live", "--confirm-spend", *policy_args(harness.tmp_path, config), config=config)
    assert code == 2 and "FINAL REFUSAL" in err
    harness.assert_nothing_executed()
    harness.assert_no_output()                                   # the generated id never became a directory or a claim


@pytest.mark.parametrize("legacy", ["20261107T170212", "legacy-1", "a.b_c-d"])
@pytest.mark.parametrize("mode", ["mock", "live"])
def test_valid_explicit_legacy_run_ids_are_accepted_on_both_branches(harness, legacy, mode):
    if mode == "mock":
        assert harness.invoke("--mock", "--run-id", legacy, config=write_config(harness.tmp_path))[0] == 0
        assert (harness.results_dir / "mock" / legacy / "run_integrity.json").is_file()
    else:                                                          # a live attempt ends in the final refusal, after the id was accepted
        config = write_config(harness.tmp_path, enabled=True)
        code, out, err = harness.invoke("--live", "--confirm-spend", "--run-id", legacy, *policy_args(harness.tmp_path, config), config=config)
        assert code == 2 and "FINAL REFUSAL" in err and "--run-id" not in err
        harness.assert_nothing_executed()
        harness.assert_no_output()


@pytest.mark.parametrize("bad", [".", "..", "", "../escape", "a/b", "x" * 129, "é"], ids=["dot", "dotdot", "empty", "traversal", "slash", "too-long", "non-ascii"])
@pytest.mark.parametrize("mode", ["--mock", "--live"])
def test_invalid_run_ids_are_rejected_on_both_branches_before_anything_is_loaded_or_created(harness, bad, mode, forbidden_executor):
    code, out, err = harness.invoke(mode, "--confirm-spend", "--run-id", bad, config=harness.tmp_path / "no-such-config.json")
    assert code == 2 and "--run-id" in err and "configuration" not in err
    if bad not in ("", ".", ".."):                                  # the fixed rule text itself mentions '.' and '..'
        assert bad not in err                                       # the value is never echoed
    harness.assert_no_inputs_loaded()
    harness.assert_nothing_executed()
    harness.assert_no_output()
    assert forbidden_executor == []


# ---------------------------------------------------------------------------
# Mock path through the executor
# ---------------------------------------------------------------------------
def test_the_mock_cli_calls_the_executor_once_with_the_injected_runner_and_a_mock_client(harness, executor_spy):
    code, out, err = harness.invoke("--mock", "--run-id", "via-executor", config=write_config(harness.tmp_path))
    assert code == 0 and "done: 96/96 valid" in out and "integrity report:" in out and err == ""
    (call,) = executor_spy
    assert call["run_fn"] is receiver.run_experiment                 # the (spied) runner is injected, never called by main itself
    assert isinstance(call["client"], MockClient) and call["run_id"] == "via-executor" and call["repo_root"] == receiver.REPO_ROOT
    assert call["run_dir"] == harness.results_dir / "mock" / "via-executor" and call["expected_episode_ids"] is None if "expected_episode_ids" in call else True
    assert len(harness.calls.run_experiment) == 1                    # the runner ran exactly once
    assert harness.calls.live_client == [] and harness.calls.get_api_key == [] and harness.calls.load_dotenv == []


def test_a_successful_mock_run_leaves_the_integrity_artifacts(harness):
    harness.invoke("--mock", "--run-id", "artifacts", config=write_config(harness.tmp_path))
    run_dir = harness.results_dir / "mock" / "artifacts"
    assert {p.name for p in run_dir.iterdir()} == SUCCESS_FILES
    report = json.loads((run_dir / "run_integrity.json").read_text(encoding="utf-8"))
    assert report["analysis_eligible"] is True and report["overall_status"] == "complete" and report["run_id"] == "artifacts"
    assert report["inventory_validation"]["performed"] is False and report["statistical_validity_claimed"] is False
    provenance = json.loads((run_dir / "run_provenance.json").read_text(encoding="utf-8"))
    assert provenance["run_id"] == "artifacts" and "not an independent trust anchor" in provenance["note"]
    events = [json.loads(line)["event"] for line in (run_dir / "run_events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events == ["run_claimed", "provenance_recorded", "runner_started", "runner_finished", "post_run_validation_finished"]


def test_an_existing_output_directory_is_refused_without_running_anything(harness):
    run_dir = harness.results_dir / "mock" / "taken"
    run_dir.mkdir(parents=True)
    (run_dir / "old.txt").write_text("keep", encoding="utf-8")
    code, out, err = harness.invoke("--mock", "--run-id", "taken", config=write_config(harness.tmp_path))
    assert code == 2 and "Refusing to use run directory" in err and "done:" not in out
    assert harness.calls.run_experiment == [] and [p.name for p in run_dir.iterdir()] == ["old.txt"]


def test_a_second_mock_run_with_the_same_id_is_refused_and_not_redirected(harness):
    config = write_config(harness.tmp_path)
    assert harness.invoke("--mock", "--run-id", "once", config=config)[0] == 0
    before = {p.name: p.read_bytes() for p in (harness.results_dir / "mock" / "once").iterdir()}
    code, out, err = harness.invoke("--mock", "--run-id", "once", config=config)
    assert code == 2 and len(harness.calls.run_experiment) == 1
    assert {p.name: p.read_bytes() for p in (harness.results_dir / "mock" / "once").iterdir()} == before
    assert [p.name for p in (harness.results_dir / "mock").iterdir()] == ["once"]            # no alternate directory


def test_a_runner_failure_preserves_partial_output_and_is_not_retried(harness, monkeypatch):
    attempts = []

    def failing(cfg, scenarios, client, out_dir, secrets=None, *a, **k):
        attempts.append(1)
        (out_dir / "episodes.jsonl").write_text("", encoding="utf-8")
        raise RuntimeError("boom")

    monkeypatch.setattr(receiver, "run_experiment", failing)
    code, out, err = harness.invoke("--mock", "--run-id", "fails", config=write_config(harness.tmp_path))
    assert code == 1 and attempts == [1] and "done:" not in out
    run_dir = harness.results_dir / "mock" / "fails"
    assert (run_dir / "episodes.jsonl").is_file() and not json.loads((run_dir / "run_integrity.json").read_text(encoding="utf-8"))["analysis_eligible"]


def test_an_ineligible_run_is_not_reported_as_done(harness, monkeypatch):
    real = receiver.run_experiment

    def damaging(cfg, scenarios, client, out_dir, *a, **k):
        results = real(cfg, scenarios, client, out_dir, *a, **k)
        with open(Path(out_dir) / "episodes.jsonl", "a", encoding="utf-8") as handle:
            handle.write("{broken json\n")
        return results

    monkeypatch.setattr(receiver, "run_experiment", damaging)
    code, out, err = harness.invoke("--mock", "--run-id", "damaged", config=write_config(harness.tmp_path))
    assert code == 1 and "done:" not in out and "not eligible for analysis" in err and "structural_validation" in err
    report = json.loads((harness.results_dir / "mock" / "damaged" / "run_integrity.json").read_text(encoding="utf-8"))
    assert report["analysis_eligible"] is False and report["failure_stage"] == "structural_validation"
    assert (harness.results_dir / "mock" / "damaged" / "episodes.jsonl").read_text(encoding="utf-8").endswith("{broken json\n")


# ---------------------------------------------------------------------------
# Live path isolation (only ever exercised up to a refusal)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "args,enabled",
    [(["--live"], True), (["--live", "--confirm-spend"], False), (["--live", "--confirm-spend", "--run-id", "no-key"], True), ([], True),
     (["--mock", "--live"], True)],
    ids=["no-confirm", "api-disabled", "no-key", "plan-only", "mock-and-live"],
)
def test_live_attempts_and_other_non_mock_modes_never_reach_the_mock_executor(harness, forbidden_executor, args, enabled):
    harness.invoke(*args, config=write_config(harness.tmp_path, enabled=enabled))
    assert forbidden_executor == []
    assert harness.calls.live_client == [] and harness.calls.run_experiment == []


def test_the_final_refusal_comes_after_the_argument_input_and_preflight_checks_and_before_everything_else(harness, forbidden_executor):
    config = write_config(harness.tmp_path, enabled=True)
    contradictory = harness.invoke("--mock", "--live", config=config)
    assert contradictory[0] == 2 and "mutually exclusive" in contradictory[2]          # argument checks still come first
    bad_id = harness.invoke("--live", "--run-id", "..", config=config)
    assert bad_id[0] == 2 and "--run-id" in bad_id[2]
    missing = harness.invoke("--live", "--confirm-spend", config=config)
    assert missing[0] == 2 and "--live requires --policy" in missing[2]
    bad_digest = harness.invoke("--live", "--confirm-spend", *policy_args(harness.tmp_path, config, digest="0" * 64), config=config)
    assert bad_digest[0] == 2 and "digest" in bad_digest[2] and "FINAL REFUSAL" not in bad_digest[2]
    passed = harness.invoke("--live", "--confirm-spend", "--run-id", "gate-order", *policy_args(harness.tmp_path, config, name="ok.json"), config=config)
    assert passed[0] == 2 and "FINAL REFUSAL" in passed[2]
    harness.assert_nothing_executed()                                # no .env read, no key lookup, no client, no run
    harness.assert_no_output()
    assert forbidden_executor == []


# ---------------------------------------------------------------------------
# Structure of receiver.main (static)
# ---------------------------------------------------------------------------
def _main_function() -> ast.FunctionDef:
    tree = ast.parse(Path(receiver.__file__).read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")


def _calls(node, name) -> list[ast.Call]:
    return [c for c in ast.walk(node) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == name]


def _mock_branch(main: ast.FunctionDef) -> ast.If:
    return next(n for n in main.body if isinstance(n, ast.If) and "args.mock" in ast.unparse(n.test) and "args.live" not in ast.unparse(n.test))


def test_main_routes_the_mock_branch_through_the_executor_and_never_calls_the_runner_there():
    main, branch = _main_function(), None
    branch = _mock_branch(main)
    assert len(_calls(branch, "execute_mock_run")) == 1
    assert _calls(branch, "run_experiment") == [], "the mock branch must not call the runner directly"
    keywords = {k.arg: k.value for k in _calls(branch, "execute_mock_run")[0].keywords}
    assert isinstance(keywords["run_fn"], ast.Name) and keywords["run_fn"].id == "run_experiment"      # injected, not called
    assert isinstance(keywords["client"], ast.Call) and keywords["client"].func.id == "MockClient"
    assert isinstance(branch.body[-1], ast.Return)                    # the mock branch always returns; it never falls through to the live code


def test_main_calls_the_mock_executor_only_in_the_mock_branch_and_the_live_code_stops_at_the_final_refusal():
    main, branch = _main_function(), None
    branch = _mock_branch(main)
    assert len(_calls(main, "execute_mock_run")) == 1
    branch_lines = {n.lineno for n in ast.walk(branch) if hasattr(n, "lineno")}
    # Stage 4E: after the mock branch main may only load the policy, validate the endpoint and refuse; it never builds a client,
    # looks up a key, claims a directory, calls the live executor, the downstream flow or the runner.
    after = [c for c in ast.walk(main) if isinstance(c, ast.Call) and c.lineno > max(branch_lines)]
    names = {c.func.id for c in after if isinstance(c.func, ast.Name)} | {c.func.attr for c in after if isinstance(c.func, ast.Attribute)}
    assert names <= {"print", "compute_content_digests", "load_policy", "validate_base_url", "any"}, names
    for name in ("OpenRouterClient", "get_api_key", "run_experiment", "initialize_run_dir", "check_run_dir", "load_dotenv", "execute_live_run",
                 "run_live_after_preflight", "client_factory"):
        assert not _calls(main, name), name
    assert isinstance(main.body[-1], ast.Return) and ast.unparse(main.body[-1].value) == "REFUSED"
    assert "FINAL_REFUSAL_TEXT" in ast.unparse(main.body[-2])


def test_main_has_no_duplicate_run_id_rule_and_uses_the_shared_helpers():
    source = Path(receiver.__file__).read_text(encoding="utf-8")
    assert "A-Za-z0-9" not in source.replace("from A-Z a-z 0-9", "")        # the character rule lives in maps.runs.ids only
    assert not hasattr(receiver, "RUN_ID_PATTERN")
    main = _main_function()
    assert _calls(main, "validate_run_id") and _calls(main, "generate_run_id")
    assert "utc_now_iso().replace" not in ast.unparse(main)


def test_the_executor_does_not_import_the_cli_or_a_live_client():
    import maps.runs.executor as executor

    tree = ast.parse(Path(executor.__file__).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not {m for m in imported if m and m.startswith(("maps.experiments", "maps.llm_client", "maps.mock_client"))}
