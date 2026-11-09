"""Run-id generation and validation (pure; no filesystem)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

import maps.runs.executor as executor_module
import maps.runs.ids as ids_module
import maps.runs.integrity_report as report_module
import maps.runs.provenance as provenance_module
import maps.pipeline.mock_pipeline as pipeline_module
from maps.runs.ids import GENERATED_RUN_ID_PATTERN, InvalidRunIdError, generate_run_id, is_valid_run_id, validate_run_id

FIXED = datetime(2026, 11, 7, 17, 2, 12, 123456, tzinfo=UTC)


def test_generated_id_uses_the_approved_format_with_injected_clock_and_token():
    run_id = generate_run_id(clock=lambda: FIXED, token=lambda: "1a2b3c4d")
    assert run_id == "20261107T170212123456Z-1a2b3c4d"
    assert GENERATED_RUN_ID_PATTERN.fullmatch(run_id) and len(run_id) == 31
    assert validate_run_id(run_id) == run_id


def test_default_clock_and_token_produce_a_valid_generated_id():
    run_id = generate_run_id()
    assert GENERATED_RUN_ID_PATTERN.fullmatch(run_id) and is_valid_run_id(run_id)


def test_a_non_utc_clock_is_converted_to_utc():
    local = FIXED.astimezone(timezone(timedelta(hours=-5)))
    assert generate_run_id(clock=lambda: local, token=lambda: "00000000") == "20261107T170212123456Z-00000000"


@pytest.mark.parametrize("clock", [lambda: datetime(2026, 1, 1), lambda: "2026-01-01", lambda: None])
def test_a_clock_without_a_timezone_is_rejected(clock):
    with pytest.raises(ValueError):
        generate_run_id(clock=clock, token=lambda: "1a2b3c4d")


@pytest.mark.parametrize("token", ["", "1a2b3c4", "1a2b3c4d5", "1A2B3C4D", "zzzzzzzz", None, 12345678])
def test_a_malformed_token_is_rejected(token):
    with pytest.raises(ValueError):
        generate_run_id(clock=lambda: FIXED, token=lambda: token)


def test_generated_ids_sort_chronologically_as_strings():
    moments = [FIXED + timedelta(microseconds=n) for n in (0, 1, 999_999, 1_000_000, 86_400_000_000)]
    generated = [generate_run_id(clock=lambda m=m: m, token=lambda: "ffffffff") for m in moments]
    assert generated == sorted(generated)
    older = generate_run_id(clock=lambda: FIXED, token=lambda: "ffffffff")
    newer = generate_run_id(clock=lambda: FIXED + timedelta(microseconds=1), token=lambda: "00000000")
    assert older < newer                                     # the time part dominates the random suffix


def test_same_instant_ids_differ_through_the_random_suffix():
    generated = {generate_run_id(clock=lambda: FIXED) for _ in range(100)}
    assert len(generated) == 100


@pytest.mark.parametrize("legacy", ["20261107T170212", "mock-001", "a.b_c-d", "R", "x" * 128, "2026-11-07T17.02.12"])
def test_legacy_and_explicit_ids_remain_valid(legacy):
    assert validate_run_id(legacy) == legacy and is_valid_run_id(legacy)


@pytest.mark.parametrize("bad", ["", "has space", "../x", "a/b", "a\\b", "x" * 129, None, 5, b"abc", ".", "..", "line\nbreak", "ünï"])
def test_invalid_ids_are_rejected_without_echoing_the_value(bad):
    with pytest.raises(InvalidRunIdError) as caught:
        validate_run_id(bad)
    assert isinstance(caught.value, ValueError)
    assert not is_valid_run_id(bad)
    if isinstance(bad, str) and bad:
        assert bad not in str(caught.value)


def test_the_provenance_recorder_uses_the_shared_validator():
    with pytest.raises(ValueError):
        provenance_module.collect_provenance(run_id="../x", repo_root=".")
    with pytest.raises(ValueError):
        provenance_module.collect_provenance(run_id="..", repo_root=".")


def test_the_validation_rule_is_defined_in_exactly_one_module():
    rule = "A-Za-z0-9._-"
    for module in (provenance_module, executor_module, pipeline_module, report_module):
        assert rule not in Path(module.__file__).read_text(encoding="utf-8"), module.__name__
    assert rule in Path(ids_module.__file__).read_text(encoding="utf-8")


def test_the_id_module_has_no_io_network_or_process_imports():
    tree = ast.parse(Path(ids_module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert not imported & {"os", "socket", "urllib", "http", "requests", "subprocess", "shutil", "pathlib"}
