"""SYNTHETIC fixture integrity and schema-validation tests (no real data is read)."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from maps.config import get_api_key
from maps.scenarios import REPO_ROOT, check_evidence_file, check_pair_matched, load_scenario, load_scenario_dir
from maps.schemas import Scenario

from synthetic_support import (  # noqa: F401  (fixtures are imported by name)
    CONFIG_PATH,
    DATA_DIR,
    EVID_DIR,
    EVIDENCE_REF_PREFIX,
    EXPECTED_SCENARIO_IDS,
    README_PATH,
    SCEN_DIR,
    SYN_ROOT,
    forbidden_source_patterns,
    syn_cfg,
    syn_scenarios,
)


def _raw(sid: str) -> dict:
    return json.loads((SCEN_DIR / f"{sid}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fixture inventory and labelling
# ---------------------------------------------------------------------------
def test_exact_fixture_file_set():
    assert sorted(p.name for p in SCEN_DIR.glob("*")) == sorted(f"{i}.json" for i in EXPECTED_SCENARIO_IDS)
    assert sorted(p.name for p in EVID_DIR.glob("*")) == sorted(f"{i}.md" for i in EXPECTED_SCENARIO_IDS)
    assert CONFIG_PATH.is_file() and README_PATH.is_file()


def test_readme_is_marked_synthetic():
    first = README_PATH.read_text(encoding="utf-8").splitlines()[0]
    assert first == "SYNTHETIC FIXTURES - NOT RESEARCH DATA"


@pytest.mark.parametrize("sid", EXPECTED_SCENARIO_IDS)
def test_scenario_is_marked_synthetic(sid):
    raw = _raw(sid)
    assert raw["scenario_id"] == sid and re.fullmatch(r"syn-p\d-[ab]", sid)
    assert re.fullmatch(r"synpair\d", raw["pair_id"])
    assert raw["domain"].startswith("synthetic_domain_")
    assert raw["construction_note"].startswith("SYNTHETIC FIXTURE")
    assert raw["independence_assessment"].startswith("SYNTHETIC")
    assert raw["claim"]["entity"].startswith("Synthetic ")
    assert raw["claim"]["quantity_definition"].startswith("SYNTHETIC")
    assert raw["status"] == "draft"
    assert raw["evidence"]["verification_status"] == "unverified" and raw["evidence"]["sha256"] is None
    assert raw["evidence"]["is_synthetic"] is True
    assert raw["name_collision_check"] == "pending"
    assert all(v is None for v in raw["review"].values())
    for root in raw["communication_roots"]:
        assert root["root_id"].startswith(sid + "-R")
        assert root["description"].startswith("Synthetic")
        assert root["stated_origin"].startswith("Synthetic ")
        assert root["is_synthetic"] is True
        assert all(u.startswith(sid + ":synthetic-") for u in root["upstream_ids"])


@pytest.mark.parametrize("sid", EXPECTED_SCENARIO_IDS)
def test_evidence_is_marked_synthetic(sid):
    first = next(ln for ln in (EVID_DIR / f"{sid}.md").read_text(encoding="utf-8").splitlines() if ln.strip())
    assert "SYNTHETIC DOCUMENT" in first and "Not real" in first and "Not research data" in first


def test_config_is_marked_synthetic(syn_cfg):
    assert syn_cfg.experiment_id.startswith("synthetic_")
    assert syn_cfg.config_version.startswith("synthetic")
    assert [m.model_id for m in syn_cfg.models] == ["synthetic/mock-alpha", "synthetic/mock-beta"]
    assert all(m.family == "synthetic" for m in syn_cfg.models)


def test_config_contract(syn_cfg):
    shapes = [(c.id, c.n_messages, c.n_roots) for c in syn_cfg.design.conditions]
    assert shapes == [("C0", 0, 0), ("C1", 1, 1), ("C2", 2, 1), ("C3", 4, 1), ("C4", 2, 2), ("C5", 4, 4)]
    assert syn_cfg.design.prompt_variants == ["neutral", "source-aware"]
    assert syn_cfg.design.repetitions == 1 and syn_cfg.design.rotate_templates_and_roots is True
    assert syn_cfg.design.evidence_visible_to_receiver is False
    assert syn_cfg.api.enabled is False and ".invalid" in syn_cfg.api.base_url
    assert syn_cfg.output.stage == "pilot"
    assert get_api_key(syn_cfg, environ={}) is None  # explicit empty environment: no key is read


def test_fixture_files_use_lf_and_end_with_newline():
    for path in sorted(p for p in DATA_DIR.rglob("*") if p.is_file() and "golden" not in p.parts):
        data = path.read_bytes()
        assert b"\r" not in data, path.name
        assert data.endswith(b"\n"), path.name


# ---------------------------------------------------------------------------
# Loading and validation through the existing production validators
# ---------------------------------------------------------------------------
def test_directory_loads_two_matched_pairs(syn_scenarios):
    assert [s.scenario_id for s in syn_scenarios] == list(EXPECTED_SCENARIO_IDS)
    pairs: dict[str, list[str]] = {}
    for s in syn_scenarios:
        pairs.setdefault(s.pair_id, []).append(s.truth_status)
    assert {k: sorted(v) for k, v in pairs.items()} == {"synpair1": ["false", "true"], "synpair2": ["false", "true"]}


@pytest.mark.parametrize("sid", EXPECTED_SCENARIO_IDS)
def test_each_file_validates_individually(sid):
    assert load_scenario(SCEN_DIR / f"{sid}.json").scenario_id == sid


def test_truth_evidence_consistency_recomputed_independently(syn_scenarios):
    for s in syn_scenarios:
        text = (REPO_ROOT / s.evidence.reference).read_text(encoding="utf-8")
        assert (s.claim.asserted_value in text) == (s.truth_status == "true")
        assert s.evidence.ground_truth_value in text
        assert s.evidence.supports_claim == (s.truth_status == "true")
        check_evidence_file(s)


def test_pair_matching_passes(syn_scenarios):
    by_pair: dict[str, dict[str, Scenario]] = {}
    for s in syn_scenarios:
        by_pair.setdefault(s.pair_id, {})[s.truth_status] = s
    for members in by_pair.values():
        check_pair_matched(members["true"], members["false"])


def test_every_message_carries_exactly_the_asserted_value(syn_scenarios):
    for s in syn_scenarios:
        assert s.claim.text == s.message_templates[0]
        for t in s.message_templates:
            assert t.count(s.claim.asserted_value) == 1
            assert not re.findall(r"\d", t.replace(s.claim.asserted_value, ""))


def _m_version(r): r["schema_version"] = "2.0-draft"
def _m_upstream(r): r["communication_roots"][1]["upstream_ids"] = list(r["communication_roots"][0]["upstream_ids"])
def _m_operator(r): r["communication_roots"][1]["operator_id"] = r["communication_roots"][0]["operator_id"]
def _m_credibility(r): r["communication_roots"][0]["stated_origin"] = "Synthetic Expert Unit"
def _m_origin_form(r): r["communication_roots"][0]["stated_origin"] = "Synthetic Echo Team"
def _m_authority(r): r["message_templates"][1] = "According to Synthetic Bin Alfa there are 12 tokens."
def _m_numeral(r): r["message_templates"][1] = r["message_templates"][1] + " Lot 7."
def _m_value_missing(r): r["message_templates"][1] = "No number here."
def _m_doctype(r): r["evidence"]["document_type"] = r["communication_roots"][0]["artifact_type"]
def _m_no_inherent(r):
    for f in r["shared_factors"]:
        f["severity"] = "minor"
def _m_unknown_root(r): r["shared_factors"][0]["affects_roots"] = ["nope"]
def _m_date(r): r["claim"]["event_date"] = "2031-05-12"
def _m_supports(r): r["evidence"]["supports_claim"] = False
def _m_frozen(r): r["status"] = "frozen"
def _m_not_synthetic(r): r["communication_roots"][0]["is_synthetic"] = False
def _m_measure(r): r["communication_roots"][0]["measurement"]["can_establish_exact_quantity"] = False
def _m_tier(r): r["communication_roots"][0]["quality_tier"] = "premium"
def _m_three_templates(r): r["message_templates"] = r["message_templates"][:3]


MUTATIONS = [
    ("schema_version", _m_version, "schema_version"),
    ("upstream_overlap", _m_upstream, "share upstream provenance"),
    ("duplicate_operator", _m_operator, "duplicate operator_id"),
    ("credibility_term", _m_credibility, "signals credibility"),
    ("origin_form", _m_origin_form, "same final word"),
    ("authority_phrase", _m_authority, "authority-loaded"),
    ("stray_numeral", _m_numeral, "unexpected numerals"),
    ("value_missing", _m_value_missing, "exactly once"),
    ("doctype_equals_artifact", _m_doctype, "document_type must differ"),
    ("no_inherent_factor", _m_no_inherent, "inherent"),
    ("unknown_root_in_factor", _m_unknown_root, "unknown roots"),
    ("date_without_calendar", _m_date, "calendar_convention"),
    ("supports_claim_flipped", _m_supports, "supports_claim"),
    ("frozen_without_review", _m_frozen, "status"),
    ("root_not_synthetic", _m_not_synthetic, "synthetic"),
    ("measurement_flag_false", _m_measure, "measure the exact claimed quantity"),
    ("quality_tier_mismatch", _m_tier, "quality_tier"),
    ("three_templates", _m_three_templates, "templates"),
]


@pytest.mark.parametrize("name,mutate,expected", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_validators_reject_invalid_variants(name, mutate, expected):
    raw = _raw("syn-p1-a")
    mutate(raw)
    with pytest.raises(ValidationError) as exc:
        Scenario.model_validate(raw)
    assert re.search(expected, str(exc.value)), name


def test_pair_mismatch_is_rejected(syn_scenarios):
    by_id = {s.scenario_id: s for s in syn_scenarios}
    true_s, false_s = by_id["syn-p1-a"], by_id["syn-p1-b"]
    bad = false_s.model_copy(deep=True)
    bad.communication_roots[0].stated_origin = "Synthetic Other Unit"
    with pytest.raises(ValueError, match="stated_origin"):
        check_pair_matched(true_s, bad)
    bad = false_s.model_copy(deep=True)
    bad.domain = "synthetic_domain_other"
    with pytest.raises(ValueError, match="domain"):
        check_pair_matched(true_s, bad)


def test_loader_rejects_unpaired_directory(tmp_path):
    for sid in EXPECTED_SCENARIO_IDS:
        if sid != "syn-p1-b":
            shutil.copy(SCEN_DIR / f"{sid}.json", tmp_path / f"{sid}.json")
    with pytest.raises(ValueError, match="exactly one true and one false"):
        load_scenario_dir(tmp_path)


def test_evidence_tampering_is_detected(tmp_path, syn_scenarios):
    s = next(x for x in syn_scenarios if x.truth_status == "false")
    copy_dir = tmp_path / EVIDENCE_REF_PREFIX
    copy_dir.mkdir(parents=True)
    target = copy_dir / f"{s.scenario_id}.md"
    shutil.copy(EVID_DIR / f"{s.scenario_id}.md", target)
    check_evidence_file(s, tmp_path)
    target.write_text(target.read_text(encoding="utf-8") + f"\nAlso: {s.claim.asserted_value}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="disagrees"):
        check_evidence_file(s, tmp_path)
    target.write_text("no marker here " + s.evidence.ground_truth_value, encoding="utf-8")
    with pytest.raises(ValueError, match="SYNTHETIC"):
        check_evidence_file(s, tmp_path)


# ---------------------------------------------------------------------------
# Containment and source self-audit
# ---------------------------------------------------------------------------
def test_paths_are_contained_in_the_synthetic_directory(syn_scenarios, syn_cfg):
    for s in syn_scenarios:
        ref = s.evidence.reference
        assert ref.startswith(EVIDENCE_REF_PREFIX) and ".." not in ref and not Path(ref).is_absolute()
        resolved = (REPO_ROOT / ref).resolve()
        assert EVID_DIR.resolve() in resolved.parents and resolved.is_file()
    assert (REPO_ROOT / syn_cfg.design.scenario_dir).resolve() == SCEN_DIR.resolve()
    assert SYN_ROOT.resolve() in CONFIG_PATH.resolve().parents


def test_wp2_python_sources_name_no_restricted_paths():
    patterns = forbidden_source_patterns()
    sources = sorted(SYN_ROOT.glob("*.py"))
    assert len(sources) >= 5
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for pat in patterns:
            assert not pat.search(text), f"{path.name} matches a restricted-path pattern"
