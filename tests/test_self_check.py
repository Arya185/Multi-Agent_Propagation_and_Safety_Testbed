"""Tests for the mechanical author self-check (level AUTHOR_CHECKED_ONLY). Real scenarios are never edited:
mutations use model_copy and a tmp_path copy of data/evidence."""

import shutil
from pathlib import Path

import pytest

from maps.scenarios import load_scenario_dir
from maps.self_check import (
    LEVEL, SelfCheckFailed, SelfCheckResult, author_self_check, format_report, require_self_check,
)

ROOT = Path(__file__).resolve().parents[1]
STABLE = ("biz", "geo", "sci", "sw")  # hist is being revised concurrently and is never asserted on


@pytest.fixture(scope="module")
def real():
    return load_scenario_dir(ROOT / "data/scenarios/v2")


@pytest.fixture()
def repo(tmp_path):
    shutil.copytree(ROOT / "data/evidence", tmp_path / "data/evidence")
    return tmp_path


@pytest.fixture()
def base(real):
    return [s for s in real if s.pair_id in STABLE]


def upd(s, **kw):
    return s.model_copy(update=kw)


def claim(s, **kw):
    return upd(s, claim=s.claim.model_copy(update=kw))


def ev(s, **kw):
    return upd(s, evidence=s.evidence.model_copy(update=kw))


def root(s, i, **kw):
    roots = list(s.communication_roots)
    roots[i] = roots[i].model_copy(update=kw)
    return upd(s, communication_roots=roots)


def swap(scs, sid, new):
    return [new if s.scenario_id == sid else s for s in scs]


def get(scs, sid):
    return next(s for s in scs if s.scenario_id == sid)


def res(scs, repo, sid):
    return next(r for r in author_self_check(scs, repo) if r.scenario_id == sid)


def codes(r):
    return [f.split(":", 1)[0] for f in r.failures]


def failing(scs, repo, sid, code):
    r = res(scs, repo, sid)
    hits = [f for f in r.failures if f.startswith(code + ":")]
    assert hits, (code, r.failures)
    assert sid in hits[0]
    return hits[0]


def test_baseline_passes(base, repo):
    results = author_self_check(base, repo)
    assert len(results) == 8
    assert all(r.passed for r in results), [r.failures for r in results if not r.passed]
    assert all(isinstance(r, SelfCheckResult) and r.level == "AUTHOR_CHECKED_ONLY" == LEVEL for r in results)


def test_real_ten_runs_without_status_change(real):
    before = [s.model_dump_json() for s in real]
    results = author_self_check(real)
    assert len(results) == 10
    assert [r.scenario_id for r in results] == sorted(s.scenario_id for s in real)
    assert all(r.level == LEVEL for r in results)
    assert all(s.status == "draft" for s in real)
    assert [s.model_dump_json() for s in real] == before


def test_deterministic_and_sorted(base, repo):
    a = author_self_check(list(reversed(base)), repo)
    b = author_self_check(base, repo)
    assert a == b
    assert [r.scenario_id for r in a] == sorted(s.scenario_id for s in base)
    bad = swap(base, "geo-a", claim(get(base, "geo-a"), asserted_value="85"))
    assert author_self_check(bad, repo) == author_self_check(list(reversed(bad)), repo)


def test_non_mutation_and_status_unchanged(base, repo):
    bad = swap(base, "geo-a", ev(get(base, "geo-a"), supports_claim=False))
    snap = [s.model_dump_json() for s in bad]
    ev_files = {p: p.read_bytes() for p in (repo / "data/evidence").iterdir()}
    author_self_check(bad, repo)
    with pytest.raises(SelfCheckFailed):
        require_self_check(bad, repo)
    assert [s.model_dump_json() for s in bad] == snap
    assert {p: p.read_bytes() for p in (repo / "data/evidence").iterdir()} == ev_files
    assert all(s.status == "draft" for s in bad)


def test_result_is_frozen_and_passed_property():
    r = SelfCheckResult("x", failures=("a: b",))
    assert not r.passed and SelfCheckResult("x").passed
    with pytest.raises(Exception):
        r.failures = ()  # type: ignore[misc]


# ---- required fields
def test_required_templates_count(base, repo):
    s = get(base, "geo-a")
    failing(swap(base, "geo-a", upd(s, message_templates=s.message_templates[:3])), repo, "geo-a", "message_templates")


def test_required_roots_count(base, repo):
    s = get(base, "geo-a")
    failing(swap(base, "geo-a", upd(s, communication_roots=s.communication_roots[:3])), repo, "geo-a", "communication_roots")


def test_required_nonempty_fields(base, repo):
    s = get(base, "geo-a")
    assert "independence_assessment" in failing(swap(base, "geo-a", upd(s, independence_assessment=" ")), repo, "geo-a", "required_field")
    assert "claim.entity" in failing(swap(base, "geo-a", claim(s, entity="")), repo, "geo-a", "required_field")
    assert "upstream_ids" in failing(swap(base, "geo-a", root(s, 0, upstream_ids=[])), repo, "geo-a", "required_field")
    assert "shared_factors" in failing(swap(base, "geo-a", upd(s, shared_factors=[])), repo, "geo-a", "shared_factors")


# ---- evidence
def test_evidence_missing_file(base, repo):
    (repo / "data/evidence/geo-a.md").unlink()
    failing(base, repo, "geo-a", "evidence_file")


def test_evidence_synthetic_label(base, repo):
    p = repo / "data/evidence/geo-a.md"
    p.write_text(p.read_text().replace("SYNTHETIC DOCUMENT", "NOTE", 1))
    assert "SYNTHETIC" in failing(base, repo, "geo-a", "evidence_file")


def test_evidence_ground_truth_and_asserted_presence(base, repo):
    p = repo / "data/evidence/geo-a.md"
    p.write_text(p.read_text().replace("86", "xx"))
    assert "ground_truth_value" in failing(base, repo, "geo-a", "evidence_file")
    # false scenario whose evidence contains the asserted value
    fb = get(base, "geo-b")
    q = repo / "data/evidence/geo-b.md"
    q.write_text(q.read_text() + f"\nStray {fb.claim.asserted_value}\n")
    assert "disagrees" in failing(base, repo, "geo-b", "evidence_file")


def test_hash_null_is_warning_not_failure(base, repo):
    r = res(base, repo, "geo-a")
    assert r.passed and any(w.startswith("evidence_hash_missing") for w in r.warnings)


def test_hash_recorded_good_and_bad(base, repo):
    from maps.scenarios import file_sha256
    s = get(base, "geo-a")
    good = ev(s, sha256=file_sha256(repo / "data/evidence/geo-a.md"))
    r = res(swap(base, "geo-a", good), repo, "geo-a")
    assert r.passed and not any(w.startswith("evidence_hash_missing") for w in r.warnings)
    bad = ev(s, sha256="0" * 64)
    f = failing(swap(base, "geo-a", bad), repo, "geo-a", "evidence_integrity")
    assert "mismatch" in f
    assert sum("mismatch" in x for x in res(swap(base, "geo-a", bad), repo, "geo-a").failures) == 1


def test_hash_required_status_without_hash_fails(base, repo):
    s = upd(get(base, "geo-a"), status="pilot_frozen")
    r = res(swap(base, "geo-a", s), repo, "geo-a")
    assert any(f.startswith("evidence_integrity") for f in r.failures)


# ---- evidence-to-claim consistency
def test_supports_claim_and_ground_truth_consistency(base, repo):
    s = get(base, "geo-a")
    failing(swap(base, "geo-a", ev(s, supports_claim=False)), repo, "geo-a", "evidence_claim")
    failing(swap(base, "geo-a", ev(s, ground_truth_value="87")), repo, "geo-a", "evidence_claim")


def test_asserted_value_in_every_template_once(base, repo):
    s = get(base, "geo-a")
    tpl = list(s.message_templates)
    tpl[1] = tpl[1].replace("86", "")
    assert "message_templates[1]" in failing(swap(base, "geo-a", upd(s, message_templates=tpl)), repo, "geo-a", "template_asserted_value")
    tpl = list(s.message_templates)
    tpl[2] = tpl[2] + " 86"
    failing(swap(base, "geo-a", upd(s, message_templates=tpl)), repo, "geo-a", "template_asserted_value")


# ---- pairs
def test_pair_incomplete(base, repo):
    scs = [s for s in base if s.scenario_id != "geo-b"]
    failing(scs, repo, "geo-a", "pair_incomplete")
    two_true = swap(base, "geo-b", upd(get(base, "geo-b"), truth_status="true"))
    failing(two_true, repo, "geo-a", "pair_incomplete")


def test_pair_mismatch_attached_to_both_members(base, repo):
    a = get(base, "geo-a")
    scs = swap(base, "geo-a", claim(a, attribute="other attribute"))
    failing(scs, repo, "geo-a", "pair_matched")
    failing(scs, repo, "geo-b", "pair_matched")
    scs = swap(base, "geo-a", upd(a, domain="different_domain"))
    failing(scs, repo, "geo-b", "pair_matched")


def test_pair_same_values(base, repo):
    b = get(base, "geo-b")
    scs = swap(base, "geo-b", claim(b, asserted_value=get(base, "geo-a").claim.asserted_value))
    failing(scs, repo, "geo-a", "pair_values")


# ---- mechanical findings
def test_mechanical_failure_reported_and_flags_are_warnings(base, repo):
    p = repo / "data/evidence/geo-b.md"
    p.write_text(p.read_text() + "\n" + "\n".join(f"Filler {i} sentence." for i in range(200)))
    for sid in ("geo-a", "geo-b"):  # pair-level mechanical failure reaches both members
        failing(base, repo, sid, "mechanical_evidence_length")
    # a mechanical flag (near-duplicate origin names across geo and sci) is a warning, never a failure
    clean = res(base, repo, "sci-a")
    assert any(w.startswith("mechanical_name_near_duplicate") for w in clean.warnings)
    assert not any(f.startswith("mechanical_name_near_duplicate") for f in clean.failures)


# ---- independence
def test_independence_confirmed_wording(base, repo):
    s = get(base, "geo-a")
    t = upd(s, independence_assessment="The roots are independent, confirmed by the author.")
    failing(swap(base, "geo-a", t), repo, "geo-a", "independence_claim")
    t = upd(s, independence_assessment="Independence was verified.")
    failing(swap(base, "geo-a", t), repo, "geo-a", "independence_claim")
    ok = upd(s, independence_assessment="Independence is not confirmed; human confirmation pending.")
    assert res(swap(base, "geo-a", ok), repo, "geo-a").passed


def test_independence_flag_below_rank(base, repo):
    s = get(base, "geo-a")
    t = upd(s, review=s.review.model_copy(update={"independence_confirmed": True}))
    failing(swap(base, "geo-a", t), repo, "geo-a", "independence_flag")


def test_reads_other_roots_output(base, repo):
    failing(swap(base, "geo-a", root(get(base, "geo-a"), 1, reads_other_roots_output=True)), repo, "geo-a", "independence_reads_output")


def test_shared_upstream_and_evidence_reference(base, repo):
    s = get(base, "geo-a")
    shared = root(root(s, 1, upstream_ids=list(s.communication_roots[0].upstream_ids)), 0)
    assert "independence_shared_upstream" in codes(res(swap(base, "geo-a", shared), repo, "geo-a"))
    ref = root(s, 2, upstream_ids=[s.evidence.reference])
    failing(swap(base, "geo-a", ref), repo, "geo-a", "independence_upstream_evidence")
    stem = root(s, 2, upstream_ids=["geo-a"])
    assert "independence_upstream_evidence" in codes(res(swap(base, "geo-a", stem), repo, "geo-a"))


def test_artifact_type_equals_document_type(base, repo):
    s = get(base, "geo-a")
    failing(swap(base, "geo-a", ev(s, document_type=s.communication_roots[0].artifact_type)), repo, "geo-a", "independence_artifact")


# ---- leakage
def test_ground_truth_leak_on_false_only(base, repo):
    b = get(base, "geo-b")
    gt = b.evidence.ground_truth_value
    r0 = root(b, 0, description=f"Crew measured {gt} metres.")
    failing(swap(base, "geo-b", r0), repo, "geo-b", "leak_ground_truth")
    r1 = root(b, 1, acquisition_process=b.communication_roots[1].acquisition_process + f" reading {gt}")
    failing(swap(base, "geo-b", r1), repo, "geo-b", "leak_ground_truth")
    m = b.communication_roots[2].measurement.model_copy(update={"coverage_note": f"covers {gt}"})
    failing(swap(base, "geo-b", root(b, 2, measurement=m)), repo, "geo-b", "leak_ground_truth")
    tpl = list(b.message_templates)
    tpl[0] = tpl[0] + f" {gt}"
    assert "leak_ground_truth" in codes(res(swap(base, "geo-b", upd(b, message_templates=tpl)), repo, "geo-b"))
    # a true scenario mentioning its own value is fine
    a = get(base, "geo-a")
    ok = root(a, 0, description=f"Crew measured {a.evidence.ground_truth_value} metres.")
    assert "leak_ground_truth" not in codes(res(swap(base, "geo-a", ok), repo, "geo-a"))
    # a longer number containing the value is not a leak
    safe = root(b, 0, description=f"Crew logged 1{gt}9 samples.")
    assert "leak_ground_truth" not in codes(res(swap(base, "geo-b", safe), repo, "geo-b"))


@pytest.mark.parametrize("word", ["false", "True", "correct", "incorrect", "wrong", "actual"])
def test_truth_cue_words(base, repo, word):
    s = get(base, "geo-a")
    tpl = list(s.message_templates)
    tpl[0] = tpl[0].replace("Lake", f"The {word} Lake", 1)
    failing(swap(base, "geo-a", upd(s, message_templates=tpl)), repo, "geo-a", "leak_truth_cue")


def test_truth_cue_word_boundary(base, repo):
    s = get(base, "geo-a")
    tpl = list(s.message_templates)
    tpl[0] = tpl[0] + " Trueblood Lake"
    assert "leak_truth_cue" not in codes(res(swap(base, "geo-a", upd(s, message_templates=tpl)), repo, "geo-a"))


def test_evidence_name_in_template(base, repo):
    s = get(base, "geo-a")
    tpl = list(s.message_templates)
    tpl[3] = tpl[3] + " See geo-a.md"
    failing(swap(base, "geo-a", upd(s, message_templates=tpl)), repo, "geo-a", "leak_evidence_name")


# ---- wording
@pytest.mark.parametrize("hedge", ["about", "around", "approximately", "roughly", "nearly"])
def test_hedges(base, repo, hedge):
    s = get(base, "geo-a")
    tpl = list(s.message_templates)
    tpl[0] = tpl[0].replace("86", f"{hedge} 86")
    failing(swap(base, "geo-a", upd(s, message_templates=tpl)), repo, "geo-a", "template_hedge")


def test_authority_and_numerals(base, repo):
    s = get(base, "geo-a")
    tpl = list(s.message_templates)
    tpl[0] = "According to records, " + tpl[0]
    failing(swap(base, "geo-a", upd(s, message_templates=tpl)), repo, "geo-a", "template_authority")
    tpl = list(s.message_templates)
    tpl[1] = tpl[1] + " In 1999 as well."
    failing(swap(base, "geo-a", upd(s, message_templates=tpl)), repo, "geo-a", "template_numeral")
    ctx = claim(upd(s, message_templates=tpl), context_numbers=["1999"])
    assert "template_numeral" not in codes(res(swap(base, "geo-a", ctx), repo, "geo-a"))


# ---- version and lineage
def test_lineage(base, repo):
    s = get(base, "geo-a")
    failing(swap(base, "geo-a", upd(s, scenario_version=2)), repo, "geo-a", "lineage")
    failing(swap(base, "geo-a", upd(s, scenario_version=2, supersedes="not a ref")), repo, "geo-a", "lineage")
    failing(swap(base, "geo-a", upd(s, scenario_version=2, supersedes="geo-a@2")), repo, "geo-a", "lineage")
    ok = upd(s, scenario_version=2, supersedes="geo-a@1")
    assert not any(f.startswith("lineage") for f in res(swap(base, "geo-a", ok), repo, "geo-a").failures)


def test_status_rank_consistency(base, repo):
    s = get(base, "geo-a")
    t = upd(s, status="author_checked")  # evidence is unverified
    failing(swap(base, "geo-a", t), repo, "geo-a", "status_rank")
    # Stage 4J.7: author_checked now needs evidence.sha256 as well (the single evidence-binding route)
    ok = upd(ev(s, verification_status="author_checked", sha256="a" * 64), status="author_checked")
    assert not any(f.startswith("status_rank") for f in res(swap(base, "geo-a", ok), repo, "geo-a").failures)
    no_hash = upd(ev(s, verification_status="author_checked"), status="author_checked")
    failing(swap(base, "geo-a", no_hash), repo, "geo-a", "status_rank")
    t = upd(ev(s, verification_status="independently_checked"), status="independently_checked")
    failing(swap(base, "geo-a", t), repo, "geo-a", "status_rank")


# ---- require / report
def test_require_raises_and_lists_every_failure(base, repo):
    s1 = ev(get(base, "geo-a"), supports_claim=False)
    s2 = ev(get(base, "sci-a"), supports_claim=False)
    scs = swap(swap(base, "geo-a", s1), "sci-a", s2)
    with pytest.raises(SelfCheckFailed) as ei:
        require_self_check(scs, repo)
    assert isinstance(ei.value, ValueError)
    msg = str(ei.value)
    assert "geo-a" in msg and "sci-a" in msg and "evidence_claim" in msg


def test_require_returns_results_on_pass(base, repo):
    out = require_self_check(base, repo)
    assert len(out) == 8 and all(r.level == LEVEL for r in out)


def test_format_report(base, repo):
    scs = swap(base, "geo-a", ev(get(base, "geo-a"), supports_claim=False))
    text = format_report(author_self_check(scs, repo))
    assert "AUTHOR_CHECKED_ONLY" in text
    assert any(ln.startswith("  FAIL geo-a: evidence_claim:") for ln in text.splitlines())
    assert "failed of 8" in text


def test_the_real_ten_pass_the_mechanical_self_check_after_the_hist_revision():
    # Stage 4J.6B integration check: AUTHOR_CHECKED_ONLY, mechanical, and it grants no status
    ten = load_scenario_dir(ROOT / "data/scenarios/v2")
    results = author_self_check(ten, ROOT)
    assert [r.scenario_id for r in results] == sorted(s.scenario_id for s in ten)
    assert all(r.passed for r in results), format_report(results)
    assert {s.status for s in ten} == {"draft"}
