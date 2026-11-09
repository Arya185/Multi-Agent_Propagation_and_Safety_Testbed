import datetime
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from maps.config import load_config
from maps.scenarios import check_evidence_file, check_pair_matched, load_scenario, load_scenario_dir
from maps.schemas import AUTHORITY_PHRASES, CREDIBILITY_TERMS

ROOT = Path(__file__).resolve().parents[1]
SCEN_DIR = ROOT / "data/scenarios/v2"
ARCH_V2 = ROOT / "data/scenarios/archive/v2_draft1"

# SHA-256 of the v1 originals at the moment they were archived (unchanged moves).
ARCHIVE_HASHES = {
    "data/scenarios/archive/receiver_scenarios_v0_draft.json":
        "47921da3c541d5180f7f0c86cee0a0e58bce3c0bcc88025b0fcb73a9891125c6",
    "configs/archive/receiver_experiment_v1.json":
        "c045dbfc12463eeecbe4d3156998f1b47471e0bfbcc1d26e973e9f811fd38187",
}
# SHA-256 of the v2 draft-1 archive manifest (which in turn lists every archived file).
ARCHIVE_V2_MANIFEST_SHA256 = "5a9a637e81f0e191fc876506d127a3b3300d5af8c20b30dd478c7745f72729ea"


@pytest.fixture(scope="module")
def scenarios():
    return load_scenario_dir(SCEN_DIR)


def _pairs(scenarios):
    d = {}
    for s in scenarios:
        d.setdefault(s.pair_id, {})[s.truth_status] = s
    return d


# ---- archive integrity ------------------------------------------------------------
def test_v0_and_v1_archive_integrity():
    for rel, expected in ARCHIVE_HASHES.items():
        p = ROOT / rel
        assert p.is_file(), f"archived original missing: {rel}"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected, f"archived file modified: {rel}"


def test_v2_draft1_archive_integrity():
    manifest = ARCH_V2 / "SHA256SUMS"
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == ARCHIVE_V2_MANIFEST_SHA256
    lines = [ln for ln in manifest.read_text().splitlines() if ln.strip()]
    assert len(lines) == 23
    for ln in lines:
        digest, rel = ln.split("  ", 1)
        f = ARCH_V2 / rel
        assert f.is_file(), f"archived file missing: {rel}"
        assert hashlib.sha256(f.read_bytes()).hexdigest() == digest, f"archived file modified: {rel}"
    listed = {ln.split("  ", 1)[1] for ln in lines}
    on_disk = {"./" + str(p.relative_to(ARCH_V2)) for p in ARCH_V2.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
    assert listed == on_disk  # nothing unlisted added, nothing removed


def test_v2_draft1_archive_keeps_audit_and_original_names():
    assert (ARCH_V2 / "AUDIT_FINDINGS.md").read_text().startswith("# MAPS v2 draft-1")
    names = sorted(p.name for p in (ARCH_V2 / "scenarios").glob("*.json"))
    assert names == sorted(f"{p}-{t}.json" for p in ("biz", "geo", "hist", "sci", "sw") for t in "TF")
    old_sw = (ARCH_V2 / "scenarios/sw-T.json").read_text()
    assert "Lumora" in old_sw and "signing-service-log" in old_sw  # the rejected sw pair is preserved


def test_active_loader_never_reads_archives(scenarios):
    ids = {s.scenario_id for s in scenarios}
    assert ids == {f"{p}-{x}" for p in ("biz", "geo", "hist", "sci", "sw") for x in "ab"}
    assert list(SCEN_DIR.glob("*/")) == []


# ---- pair structure and neutrality -------------------------------------------------
def test_ten_scenarios_five_matched_pairs(scenarios):
    assert len(scenarios) == 10
    pairs = _pairs(scenarios)
    assert len(pairs) == 5 and all(set(v) == {"true", "false"} for v in pairs.values())
    assert sum(s.truth_status == "true" for s in scenarios) == 5
    assert len({s.domain for s in scenarios}) == 5


def test_ids_and_filenames_do_not_encode_truth(scenarios):
    a_true = sum(1 for s in scenarios if s.scenario_id.endswith("-a") and s.truth_status == "true")
    assert a_true in (2, 3)  # suffix is uninformative: 3 of 5 here, never all-or-nothing
    for p in list(SCEN_DIR.glob("*")) + list((ROOT / "data/evidence").glob("*")):
        assert re.fullmatch(r"[a-z]+-[ab]\.(json|md)", p.name), p.name
    for s in scenarios:
        assert not re.search(r"(?i)[-_](t|f|true|false)\b", s.scenario_id)


def test_matched_pair_structure(scenarios):
    for pair, d in _pairs(scenarios).items():
        check_pair_matched(d["true"], d["false"])


def test_pair_matching_detects_violations(scenarios):
    d = _pairs(scenarios)["biz"]
    t, f = d["true"], d["false"]
    bad = f.model_copy(deep=True)
    bad.communication_roots[0].stated_origin = "Other Group"
    with pytest.raises(ValueError, match="stated_origin"):
        check_pair_matched(t, bad)
    bad = f.model_copy(deep=True)
    bad.domain = "elsewhere"
    with pytest.raises(ValueError, match="domain"):
        check_pair_matched(t, bad)


def test_weekday_matching_for_dated_claims(scenarios):
    d = _pairs(scenarios)["biz"]
    dates = [d[k].claim.event_date for k in ("true", "false")]
    assert all(dates)
    wd = {datetime.date.fromisoformat(x).weekday() for x in dates}
    assert len(wd) == 1 and wd == {0}  # both Monday
    # a pair whose dates fall on different weekdays must be rejected
    bad = d["false"].model_copy(deep=True)
    bad.claim.event_date = "2031-05-13"  # Tuesday
    with pytest.raises(ValueError, match="weekdays differ"):
        check_pair_matched(d["true"], bad)
    one_sided = d["false"].model_copy(deep=True)
    one_sided.claim.event_date = None
    with pytest.raises(ValueError, match="only one member"):
        check_pair_matched(d["true"], one_sided)


def test_dates_and_years_carry_calendar_convention(scenarios):
    for s in scenarios:
        has_year = bool(re.search(r"\b1[5-9]\d\d\b|\b20\d\d\b", s.claim.text + s.claim.quantity_definition))
        if has_year or s.claim.event_date:
            assert s.claim.calendar_convention, s.scenario_id


def test_names_are_neutral(scenarios):
    loaded = {"quarrel", "lumora", "concord", "accord", "true", "false", "truth", "honest", "verity",
              "faux", "fault", "bad", "good", "fact", "myth", "real", "fake"}
    for s in scenarios:
        words = re.findall(r"[a-z]+", (s.claim.entity + " " + " ".join(r.stated_origin for r in s.communication_roots)).lower())
        assert not loaded & set(words), (s.scenario_id, loaded & set(words))
    ents = [s.claim.entity for s in scenarios]
    assert len(set(ents)) == 10
    for d in _pairs(scenarios).values():
        a, b = d["true"].claim.entity, d["false"].claim.entity
        assert abs(len(a) - len(b)) <= 3  # parallel naming


def test_replaced_sw_pair_has_no_pipeline_remnants(scenarios):
    # Check what a root or claim actually says (negating notes in shared_factors may name them).
    for s in scenarios:
        blob = " ".join([s.claim.text, *s.message_templates, s.claim.quantity_definition,
                         *(r.acquisition_process + " " + r.description + " " + r.artifact_type
                           for r in s.communication_roots),
                         (ROOT / s.evidence.reference).read_text()]).lower()
        for term in ("lumora", "quarrel", "signing", "changelog", "announcement", "build run",
                     "publish timestamp", "timestamp"):
            if term == "signing" and s.pair_id == "hist":
                continue  # "signing" is the hist event itself
            assert term not in blob, (s.scenario_id, term)
    sw = _pairs(scenarios)["sw"]["true"]
    assert "file" in sw.claim.attribute


# ---- messages ----------------------------------------------------------------------
def test_templates_are_authority_free_and_information_equal(scenarios):
    for s in scenarios:
        for t in [s.claim.text, *s.message_templates]:
            low = t.lower()
            assert not any(p in low for p in AUTHORITY_PHRASES), (s.scenario_id, t)
            assert t.count(s.claim.asserted_value) == 1
        assert s.claim.text == s.message_templates[0]


# ---- evidence ---------------------------------------------------------------------
def test_truth_evidence_consistency_against_documents(scenarios):
    for s in scenarios:
        check_evidence_file(s)
        text = (ROOT / s.evidence.reference).read_text(encoding="utf-8")
        assert (s.claim.asserted_value in text) == (s.truth_status == "true")
        assert s.evidence.ground_truth_value in text
        assert s.evidence.supports_claim == (s.truth_status == "true")


def test_evidence_docs_are_synthetic_one_per_scenario_and_typed_apart(scenarios):
    files = sorted(p.name for p in (ROOT / "data/evidence").glob("*.md"))
    assert files == sorted(f"{s.scenario_id}.md" for s in scenarios)
    for s in scenarios:
        first = next(ln for ln in (ROOT / s.evidence.reference).read_text().splitlines() if ln.strip())
        assert "SYNTHETIC DOCUMENT" in first and "Not real" in first
        assert s.evidence.is_synthetic
        assert all(r.artifact_type != s.evidence.document_type for r in s.communication_roots)


def test_false_scenario_evidence_check_detects_tampering(tmp_path, scenarios):
    s = _pairs(scenarios)["biz"]["false"]
    doc_dir = tmp_path / "data/evidence"
    doc_dir.mkdir(parents=True)
    shutil.copy(ROOT / s.evidence.reference, doc_dir / f"{s.scenario_id}.md")
    check_evidence_file(s, tmp_path)
    f = doc_dir / f"{s.scenario_id}.md"
    f.write_text(f.read_text() + f"\nAlso: {s.claim.asserted_value}\n")
    with pytest.raises(ValueError, match="disagrees"):
        check_evidence_file(s, tmp_path)
    f.write_text("no marker here " + s.evidence.ground_truth_value)
    with pytest.raises(ValueError, match="SYNTHETIC"):
        check_evidence_file(s, tmp_path)


# ---- independence, feasibility, credibility balance --------------------------------
DERIVED_TERMS = ("payroll", "ledger", "roster", "filing", "annual return", "catalogue", "dispatch",
                 "timestamp", "announcement", "registry", "records of", "transcrib")


def test_independence_is_argued_beyond_ids(scenarios):
    for s in scenarios:
        roots = s.communication_roots
        ups = [u for r in roots for u in r.upstream_ids]
        assert len(ups) == len(set(ups)) == 4
        assert len({r.operator_id for r in roots}) == 4 and len({r.instrument_id for r in roots}) == 4
        assert all(r.acquisition_kind == "direct_observation" and not r.reads_other_roots_output for r in roots)
        assert len(s.independence_assessment) > 200
        assert "not by themselves" in s.independence_assessment or "do not" in s.independence_assessment \
            or "not the basis" in s.independence_assessment or "Different copy ids" in s.independence_assessment
        assert any(f.severity == "inherent" for f in s.shared_factors)
        assert all(f.note for f in s.shared_factors)
        for r in roots:  # no root is described as derived from an administrative record
            assert not any(t in r.acquisition_process.lower() for t in DERIVED_TERMS), (s.scenario_id, r.root_id)


def test_methods_are_diverse_where_independence_depends_on_it(scenarios):
    for s in scenarios:
        classes = [r.instrument_class for r in s.communication_roots]
        if s.pair_id in ("biz", "geo", "sw"):
            assert len(set(classes)) == 4, (s.scenario_id, classes)  # four distinct methods
        if s.pair_id == "sci":
            assert len(set(classes)) == 1  # standardized instrument class, separate instruments
            assert len({r.instrument_id for r in s.communication_roots}) == 4


def test_measurement_feasibility_metadata(scenarios):
    for s in scenarios:
        for r in s.communication_roots:
            m = r.measurement
            assert m.measures_claimed_quantity and m.can_establish_exact_quantity
            assert m.coverage_note and m.resolution_note
    for s in scenarios:
        blob = " ".join(r.acquisition_process + " " + r.measurement.coverage_note for r in s.communication_roots).lower()
        if s.pair_id == "geo":
            for banned in ("lidar", "gauge", "buoy"):
                assert banned not in blob
            assert all(re.search(r"entire|whole", r.measurement.coverage_note.lower()) for r in s.communication_roots)
            assert "greatest vertical distance" in s.claim.quantity_definition.lower()
        if s.pair_id == "biz":
            for banned in ("payroll", "hr ", "roster", "attendance record", "ledger", "filing"):
                assert banned not in blob
            assert "open-air" in s.claim.quantity_definition and "same moment" in s.claim.quantity_definition
        if s.pair_id == "sci":
            q = s.claim.quantity_definition
            assert "20:00 to 04:00 UTC" in q and "signal-to-noise" in q and "50 ms" in q
            assert all("counting rule" in r.acquisition_process for r in s.communication_roots)


def test_source_credibility_is_balanced(scenarios):
    for s in scenarios:
        origins = [r.stated_origin for r in s.communication_roots]
        assert {o.split()[-1] for o in origins} == {"Group"}
        assert not any(t in o.lower() for o in origins for t in CREDIBILITY_TERMS)
        assert {r.quality_tier for r in s.communication_roots} == {"standard"}
        lens = [len(o) for o in origins]
        assert max(lens) / min(lens) <= 1.3
    all_origins = [r.stated_origin for s in scenarios for r in s.communication_roots]
    assert len(set(all_origins)) == 20  # 5 pools x 4, each name used once per pool (shared within a pair)


def test_root_ids_unique_across_scenarios(scenarios):
    ids = [r.root_id for s in scenarios for r in s.communication_roots]
    assert len(ids) == len(set(ids)) == 40


# ---- no validation / freezing --------------------------------------------------------
# Table-driven status pin (Stage 4J.5): a status change must be a deliberate edit of this table, per scenario.
EXPECTED_STATUS = {sid: "draft" for sid in (
    "biz-a", "biz-b", "geo-a", "geo-b", "hist-a", "hist-b", "sci-a", "sci-b", "sw-a", "sw-b")}


def test_scenario_status_table_matches_the_real_scenarios(scenarios):
    assert {s.scenario_id: s.status for s in scenarios} == EXPECTED_STATUS


def test_all_scenarios_remain_draft_and_unvalidated(scenarios):
    for s in scenarios:
        assert s.status == EXPECTED_STATUS[s.scenario_id]
        assert s.evidence.verification_status == "unverified"
        assert s.evidence.sha256 is None
        assert s.review.reviewer is None and s.review.blind_to_truth is None
        assert s.review.reviewed_on is None and s.review.independence_confirmed is None
        assert s.name_collision_check == "pending"


def test_evidence_not_visible_to_receiver_in_primary(scenarios):
    cfg = load_config(ROOT / "configs/receiver_experiment.json")
    assert cfg.design.evidence_visible_to_receiver is False
    assert all(s.evidence.visible_to_receiver is False for s in scenarios)


def test_loader_rejects_unpaired_scenario(tmp_path, scenarios):
    drop = _pairs(scenarios)["biz"]["false"].scenario_id
    for s in scenarios:
        if s.scenario_id != drop:
            shutil.copy(SCEN_DIR / f"{s.scenario_id}.json", tmp_path / f"{s.scenario_id}.json")
    with pytest.raises(ValueError, match="exactly one true and one false"):
        load_scenario_dir(tmp_path)


def test_each_file_validates_individually():
    for p in sorted(SCEN_DIR.glob("*.json")):
        assert load_scenario(p).scenario_id == p.stem
        assert json.loads(p.read_text())["schema_version"] == "2.1-draft"
