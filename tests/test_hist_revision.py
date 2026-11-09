"""Pins the Stage 4J.6B revision of the hist pair (year and template lengths)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from maps import validation as v
from maps.scenarios import check_pair_matched, load_scenario_dir

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "scenarios" / "v2"
NEW_FALSE_YEAR = "1612"
TRUE_YEAR = "1583"
OWN_TRUTH_YEAR = "1694"

OTHER_EIGHT_SHA256 = {
    "biz-a.json": "1f75d66ea553dfcf4f91d48b561715ef43bf2b13ae60baf91b8dc65335d73a15",
    "biz-b.json": "208d69ee2d3b9cdde6806ef02c05be4a62c0e73210d35c0c600dac05f80bea04",
    "geo-a.json": "639e2e182b20a6ae5e3a37b79df8b1e300f8d71194482f5a49b6d05a14b0c022",
    "geo-b.json": "d58ce29d02991450894f45343a02c7dd44d27a7dcb818ef87d9fa234e5b5e0cc",
    "sci-a.json": "f0bf3aa857973413dfa6ecda0acbb1fb08d04fd3c4d7a2b38288b68413d4177b",
    "sci-b.json": "e6173bf634730c624527eda02b3509139f82618cb4fdfca9308f922f64e3290b",
    "sw-a.json": "ea03f4feb878ad94232b1a44084387b95464f8ded91fce628a124e8df5b569ed",
    "sw-b.json": "a0f4c23480d2693ea5c49b9f30af994901e4513bc4827c1ddc3f7baf0fdbe450",
}


@pytest.fixture(scope="module")
def scenarios():
    return load_scenario_dir(DIR)


@pytest.fixture(scope="module")
def hist(scenarios):
    by_id = {s.scenario_id: s for s in scenarios}
    return by_id["hist-a"], by_id["hist-b"]


def _lens(s):
    return [len(t) for t in s.message_templates]


def test_ten_scenarios_load(scenarios):
    assert len(scenarios) == 10


def test_years(hist):
    a, b = hist
    assert a.claim.asserted_value == NEW_FALSE_YEAR
    assert b.claim.asserted_value == TRUE_YEAR
    assert a.evidence.ground_truth_value == OWN_TRUTH_YEAR
    assert b.evidence.ground_truth_value == TRUE_YEAR
    assert a.truth_status == "false" and b.truth_status == "true"
    diff = abs(int(NEW_FALSE_YEAR) - int(TRUE_YEAR))
    assert 0 < diff <= 50
    assert NEW_FALSE_YEAR not in (TRUE_YEAR, OWN_TRUTH_YEAR)
    assert 1533 <= int(NEW_FALSE_YEAR) <= 1633
    assert re.fullmatch(r"\d{4}", a.claim.asserted_value) and re.fullmatch(r"\d{4}", b.claim.asserted_value)
    assert a.claim.text == f"The Treaty of Brennmoor was signed in the year {NEW_FALSE_YEAR}."
    assert b.claim.text == f"The Treaty of Halvering was signed in the year {TRUE_YEAR}."
    for s in hist:
        assert s.claim.text == s.message_templates[0]


def test_evidence_lacks_new_year():
    text = (ROOT / "data" / "evidence" / "hist-a.md").read_text(encoding="utf-8")
    assert NEW_FALSE_YEAR not in text
    assert OWN_TRUTH_YEAR in text


def test_templates_within_own_mean(hist):
    for s in hist:
        lens = _lens(s)
        assert len(lens) == 4
        mean = sum(lens) / 4
        for n in lens:
            assert abs(n - mean) / mean <= 0.15, (s.scenario_id, lens)


def test_templates_across_pair(hist):
    a, b = hist
    for x, y in zip(_lens(a), _lens(b)):
        assert abs(x - y) / ((x + y) / 2) <= 0.15


def test_template_content(hist):
    for s in hist:
        year = s.claim.asserted_value
        assert len(set(s.message_templates)) == 4
        for t in s.message_templates:
            assert t.count(year) == 1
            assert re.findall(r"\d+", t) == [year]
            assert s.claim.entity in t
            assert not re.search(
                r"records (give|show)|according to|official|as documented|reported by|per the|verified|confirmed|surveys put",
                t,
                re.I,
            )


def test_status_fields_unchanged(hist):
    for s in hist:
        assert s.status == "draft"
        assert s.evidence.verification_status == "unverified"
        assert s.evidence.sha256 is None
        assert s.scenario_version == 1
        assert s.supersedes is None
        assert s.review.reviewer is None
        assert s.review.independence_confirmed is None


def test_pair_match_and_no_hist_failure(scenarios, hist):
    a, b = hist
    check_pair_matched(b, a)  # raises ValueError on mismatch
    findings = v.mechanical_findings(scenarios, ROOT)
    bad = [f for f in findings if f.kind == v.FAILURE and "hist" in f.subjects]
    assert bad == []
    assert not [f for f in findings if f.code in ("year_threshold", "format_mismatch")]


def test_other_eight_byte_identical():
    for name, digest in OTHER_EIGHT_SHA256.items():
        assert hashlib.sha256((DIR / name).read_bytes()).hexdigest() == digest, name
