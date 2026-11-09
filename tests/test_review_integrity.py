"""Content binding and the tightened independently_checked gate, seen from outside the schema (Stage 4J.5).
Offline; no provider calls. Detailed field-level cases live in test_review_records.py and test_pair_review.py."""

import copy
from pathlib import Path

import pytest
from pydantic import ValidationError

from maps.scenarios import load_scenario_dir
from maps.schemas import Scenario, independent_review_problems, scenario_content_sha256

SCEN_DIR = Path(__file__).resolve().parents[1] / "data" / "scenarios" / "v2"


@pytest.fixture(scope="module")
def real():
    return load_scenario_dir(SCEN_DIR)


def test_the_hash_is_a_stable_digest_for_every_real_scenario(real):
    hashes = [scenario_content_sha256(s) for s in real]
    assert all(len(h) == 64 and h == h.lower() for h in hashes)
    assert hashes == [scenario_content_sha256(s) for s in real]
    assert len(set(hashes)) == len(real)          # distinct scenarios never share a content hash


def test_the_hash_ignores_status_review_and_lifecycle_fields(real):
    s = real[0]
    base = scenario_content_sha256(s)
    assert scenario_content_sha256(s.model_copy(update={"status": "author_checked"})) == base
    assert scenario_content_sha256(s.model_copy(update={"name_collision_check": "clear"})) == base


def test_the_hash_changes_with_claim_text_and_version(real):
    s = real[0]
    base = scenario_content_sha256(s)
    claim = s.claim.model_copy(update={"text": s.claim.text + " "})
    assert scenario_content_sha256(s.model_copy(update={"claim": claim})) != base
    assert scenario_content_sha256(s.model_copy(update={"scenario_version": s.scenario_version + 1})) != base


def test_real_scenarios_without_reviews_have_no_qualifying_independent_review(real):
    for s in real:
        assert s.status == "draft"
        assert independent_review_problems(s, bound=True)       # nothing is reviewed, so nothing qualifies


def test_a_draft_cannot_be_promoted_to_independently_checked_by_a_summary_flag_alone(real):
    raw = copy.deepcopy(real[0].model_dump(mode="json"))
    raw["status"] = "independently_checked"
    raw["review"] = {"reviewer": "x", "blind_to_truth": True, "reviewed_on": "2026-01-01", "independence_confirmed": True}
    raw["evidence"]["verification_status"] = "independently_checked"
    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)
