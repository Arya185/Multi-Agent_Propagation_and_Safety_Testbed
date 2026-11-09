"""Offline tests for maps.validation (mechanical scenario checks)."""

from __future__ import annotations

import itertools
import json
import random
from pathlib import Path

import pytest

from maps import validation as v
from maps.scenarios import REPO_ROOT, load_scenario_dir
from maps.schemas import Scenario

BASE = json.loads((REPO_ROOT / "data" / "scenarios" / "v2" / "biz-a.json").read_text(encoding="utf-8"))
ORIGINS = ["Tessaly Group", "Dunmere Group", "Ostrel Group", "Quillan Group"]
ATTR = "employees present at the open-yard safety assembly"


_counter = itertools.count()


def word(label: str) -> str:
    """Digits are not allowed in entity names (the schema checks numerals); map them to letters."""
    return "".join(chr(97 + int(c)) if c.isdigit() else c for c in label)


def org_set(k: int) -> list[str]:
    """Four stated origins that are pairwise far apart (edit distance 6) from every other set."""
    return [f"{chr(97 + (4 * k + j) % 26) * 6} Group" for j in range(4)]


def make(
    sid, pair, truth, value, true_value=None, entity=None, origins=None, version=1, supersedes=None,
    check="pending", attribute=ATTR, ev="ok",
) -> Scenario:
    """Mutated copy of biz-a. `value` is this scenario's asserted value; true_value is the pair's true one."""
    text = json.dumps(BASE)
    text = text.replace("Tolvane Mill", entity or f"Entity {word(sid)}").replace("342", "777")
    for old, new in zip(ORIGINS, origins or ORIGINS):
        text = text.replace(old, new)
    d = json.loads(text)
    d["scenario_id"], d["pair_id"], d["truth_status"] = sid, pair, truth
    d["scenario_version"], d["supersedes"], d["name_collision_check"] = version, supersedes, check
    d["claim"]["attribute"] = attribute
    d["evidence"]["reference"] = f"ev/{sid}-{version}.md"
    d["evidence"]["supports_claim"] = truth == "true"
    d["evidence"]["ground_truth_value"] = "777" if truth == "true" else "1000"
    s = Scenario.model_validate(d)
    # Set the real value afterwards: the schema's message checks reject some digit strings
    # (for example "0" or "1" collide with the context numbers), and these tests need them.
    return s.model_copy(update={
        "claim": s.claim.model_copy(update={"asserted_value": value}),
        "evidence": s.evidence.model_copy(update={"ground_truth_value": value if truth == "true" else (true_value or "1000")}),
    })


def write_ev(root: Path, s: Scenario, text: str) -> None:
    p = root / s.evidence.reference
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


def make_pair(root, pair, t_value, f_value, text="SYNTHETIC DOCUMENT\nbody a\n", f_text=None, attribute=ATTR, **kw):
    origins = org_set(next(_counter))
    t = make(f"{pair}-t", pair, "true", t_value, entity=f"Alpha {word(pair)}x", origins=origins, attribute=attribute, **kw.get("t", {}))
    f = make(f"{pair}-f", pair, "false", f_value, true_value=t_value, entity=f"Zeta {word(pair)}q", origins=origins, attribute=attribute, **kw.get("f", {}))
    write_ev(root, t, text)
    write_ev(root, f, f_text if f_text is not None else text)
    return t, f


def codes(findings, kind=None):
    return sorted({f.code for f in findings if kind is None or f.kind == kind})


# ------------------------------------------------------------------ evidence length


def test_normalize_crlf_cr_trailing():
    assert v.normalize_evidence_text("a\r\nb\rc\r\n\r\n  \n") == "a\nb\nc"
    assert v.evidence_length("a\r\nb\n\n\n") == 3
    assert v.evidence_length("") == 0


def test_label_line_counted():
    assert v.evidence_length("SYNTHETIC DOCUMENT\nx") == len("SYNTHETIC DOCUMENT\nx")


def test_relative_difference():
    assert v.relative_difference(0, 0) == 0.0
    assert v.relative_difference(10, 10) == 0.0
    assert v.relative_difference(9, 11) == pytest.approx(0.2)
    assert v.relative_difference(0, 5) == 2.0


def test_length_boundary_exact():
    # 20*|a-b| <= a+b : (95,105) diff 10, mean 100 -> exactly 10%
    assert v.evidence_lengths_match("x" * 95, "x" * 105)
    assert not v.evidence_lengths_match("x" * 94, "x" * 105)
    assert not v.evidence_lengths_match("x" * 95, "x" * 106)
    assert v.evidence_lengths_match("x" * 100, "x" * 100)


def test_length_zero_lengths():
    assert v.evidence_lengths_match("", "\n\n")
    assert not v.evidence_lengths_match("", "x")


def test_length_ignores_line_ending_style():
    assert v.evidence_lengths_match("a\nb\nc", "a\r\nb\r\nc\r\n\r\n")


def test_repetition_lines_and_sentences():
    assert v.repeated_lines_or_sentences("One.\nTwo.\nOne.\n") == ["One."]
    text = "A fact here. Other thing! A fact here? no. A fact here."
    assert "A fact here." in v.repeated_lines_or_sentences(text)
    assert v.repeated_lines_or_sentences("a\nb\n\n\nc") == []
    assert v.repeated_lines_or_sentences("") == []
    assert v.repeated_lines_or_sentences("x  \nx\n") == ["x"]


def test_set_level_length_failure_and_repetition_flag(tmp_path):
    t, f = make_pair(tmp_path, "p1", "100", "150", text="SYNTHETIC\n" + "a" * 100, f_text="SYNTHETIC\n" + "a" * 130)
    found = v.mechanical_findings([t, f], tmp_path)
    assert "evidence_length" in codes(found, "failure")
    t, f = make_pair(tmp_path, "p2", "100", "150", text="SYNTHETIC\nSame line\nSame line\n")
    found = v.mechanical_findings([t, f], tmp_path)
    assert "evidence_length" not in codes(found)
    rep = [x for x in found if x.code == "evidence_repetition"]
    assert rep and all(x.kind == "flag" for x in rep)


def test_missing_evidence_is_failure(tmp_path):
    t, f = make_pair(tmp_path, "p1", "100", "150")
    (tmp_path / t.evidence.reference).unlink()
    assert "evidence_missing" in codes(v.mechanical_findings([t, f], tmp_path), "failure")


# ------------------------------------------------------------------ direction balance


def ratio_pairs(root, spec):
    """spec: list of (true, false) values; returns scenarios."""
    out = []
    for i, (tv, fv) in enumerate(spec):
        t, f = make_pair(root, f"r{i}", tv, fv)
        out += [t, f]
    return out


@pytest.mark.parametrize(
    "spec,failed",
    [
        ([("100", "150"), ("100", "150"), ("100", "60"), ("100", "60")], False),
        ([("100", "150"), ("100", "150"), ("100", "150"), ("100", "60")], True),  # 3/1: difference 2 > 1
        ([("100", "150"), ("100", "150"), ("100", "150"), ("100", "60"), ("100", "60")], False),  # 3/2
        ([("100", "150"), ("100", "150"), ("100", "150"), ("100", "150")], True),
        ([("100", "150"), ("100", "150"), ("100", "150")], True),
        ([("100", "150"), ("100", "150"), ("100", "60")], False),
        ([("100", "150")], False),
    ],
)
def test_direction_balance_sets(tmp_path, spec, failed):
    found = v.mechanical_findings(ratio_pairs(tmp_path, spec), tmp_path)
    assert ("direction_imbalance" in codes(found, "failure")) is failed


def test_is_balanced():
    assert v.is_balanced(2, 2) and v.is_balanced(3, 2) and v.is_balanced(3, 4)
    assert not v.is_balanced(0, 2) and v.is_balanced(0, 1) and v.is_balanced(0, 0)


def test_equal_value_failure(tmp_path):
    found = v.mechanical_findings(ratio_pairs(tmp_path, [("100", "100")]), tmp_path)
    fails = [f for f in found if f.kind == "failure" and f.code == "false_equals_true"]
    assert len(fails) == 1
    t, f = make_pair(tmp_path, "z", "100", "100")
    assert v.direction_balance([(t, f)])["ratio"] == {"over": 0, "under": 0}
    assert v.direction_balance([(t, f)])["equal"] == ["z"]


def test_year_pairs_reported_separately(tmp_path):
    attr = "year of treaty signing"
    yt, yf = make_pair(tmp_path, "y", "1583", "1600", attribute=attr)
    rt, rf = make_pair(tmp_path, "r", "100", "150")
    ot, of = make_pair(tmp_path, "o", "alpha", "beta")
    report = v.direction_balance([(yt, yf), (rt, rf), (ot, of)])
    assert report["ratio"] == {"over": 1, "under": 0}
    assert report["year"] == [("y", 17)]
    assert report["other"] == ["o"]
    assert v.scale_kind(yt) == "year" and v.scale_kind(rt) == "ratio" and v.scale_kind(ot) == "other"


def test_year_regex_is_word_bounded():
    s = make("s", "p", "true", "100", attribute="yearly average count")
    assert v.scale_kind(s) == "ratio"
    s = make("s", "p", "true", "100", attribute="Year of signing")
    assert v.scale_kind(s) == "year"


def test_year_pairs_do_not_unbalance(tmp_path):
    scs = []
    for i in range(4):
        scs += list(make_pair(tmp_path, f"y{i}", "1583", "1600", attribute="year of event"))
    assert "direction_imbalance" not in codes(v.mechanical_findings(scs, tmp_path))


def test_parse_number():
    assert v.parse_number("1,234.5") == 1234.5
    for bad in ["", "abc", "-3", "1.", ".5", "1e3", "12 apples"]:
        assert v.parse_number(bad) is None


# ------------------------------------------------------------------ avoid extremes


def fails(tmp_path, tv, fv, **kw):
    t, f = make_pair(tmp_path, "e", tv, fv, **kw)
    return v.extreme_failures(t, f)


def flags(tmp_path, tv, fv, **kw):
    t, f = make_pair(tmp_path, "e", tv, fv, **kw)
    return [c for c, _ in v.screening_flags(t, f)]


def test_factor_two_edges(tmp_path):
    assert fails(tmp_path, "100", "200") == []
    assert fails(tmp_path, "100", "50") == []
    assert [c for c, _ in fails(tmp_path, "100", "201")] == ["factor_two"]
    assert [c for c, _ in fails(tmp_path, "100", "49")] == ["factor_two"]
    assert [c for c, _ in fails(tmp_path, "0", "5")] == ["factor_two"]


def test_year_threshold_edges(tmp_path):
    kw = {"attribute": "year of treaty"}
    assert fails(tmp_path, "1583", "1633", **kw) == []
    assert fails(tmp_path, "1583", "1533", **kw) == []
    assert [c for c, _ in fails(tmp_path, "1583", "1634", **kw)] == ["year_threshold"]
    assert [c for c, _ in fails(tmp_path, "1583", "1532", **kw)] == ["year_threshold"]
    assert [c for c, _ in fails(tmp_path, "1583", "1583", **kw)] == ["year_threshold"]
    assert "year_threshold" in [c for c, _ in fails(tmp_path, "1583.0", "1590.0", **kw)]


def test_year_hist_like_values(tmp_path):
    assert [c for c, _ in fails(tmp_path, "1583", "1741", attribute="year of treaty signing")] == ["year_threshold"]


def test_format_mismatch(tmp_path):
    assert "format_mismatch" in [c for c, _ in fails(tmp_path, "100", "150.5")]
    assert "format_mismatch" in [c for c, _ in fails(tmp_path, "10.5", "12.25")]
    assert fails(tmp_path, "10.5", "12.5") == []
    assert "format_mismatch" in [c for c, _ in fails(tmp_path, "1583", "999", attribute="year of x")]
    assert fails(tmp_path, "alpha", "beta") == []


def test_four_screening_flags(tmp_path):
    assert flags(tmp_path, "123", "456") == []
    assert "digit_count_mismatch" in flags(tmp_path, "95", "105")
    assert "round_mismatch" in flags(tmp_path, "100", "123")
    assert "round_mismatch" in flags(tmp_path, "40", "43")
    assert "round_mismatch" not in flags(tmp_path, "5", "7")
    assert "round_mismatch" not in flags(tmp_path, "100", "200")
    assert "round_mismatch" not in flags(tmp_path, "10", "20")
    assert "false_value_zero_or_one" in flags(tmp_path, "2", "1")
    assert "false_value_zero_or_one" in flags(tmp_path, "2", "0")
    assert "false_value_zero_or_one" not in flags(tmp_path, "2", "3")
    assert "integer_noninteger_mismatch" in flags(tmp_path, "100", "150.5")
    assert "integer_noninteger_mismatch" not in flags(tmp_path, "10.5", "12.5")


def test_flags_are_never_failures(tmp_path):
    t, f = make_pair(tmp_path, "e", "95", "105")
    found = v.mechanical_findings([t, f], tmp_path)
    assert "digit_count_mismatch" in codes(found, "flag")
    assert "digit_count_mismatch" not in codes(found, "failure")
    assert v.mechanical_failures([t, f], tmp_path) == []


# ------------------------------------------------------------------ exceptions


def test_exception_requires_reason():
    with pytest.raises(ValueError):
        v.ScreeningException("e", "digit_count_mismatch", "")
    with pytest.raises(ValueError):
        v.ScreeningException("e", "digit_count_mismatch", "   ")


def test_exception_downgrades_only_matching_flag(tmp_path):
    t, f = make_pair(tmp_path, "e", "95", "105")
    ex = v.ScreeningException("e", "digit_count_mismatch", "reviewed, acceptable")
    found = v.mechanical_findings([t, f], tmp_path, [ex])
    assert [x.kind for x in found if x.code == "digit_count_mismatch"] == ["excepted"]
    other = v.ScreeningException("other", "digit_count_mismatch", "why")
    wrong_code = v.ScreeningException("e", "round_mismatch", "why")
    found = v.mechanical_findings([t, f], tmp_path, [other, wrong_code])
    assert [x.kind for x in found if x.code == "digit_count_mismatch"] == ["flag"]


def test_exception_never_removes_failure(tmp_path):
    t, f = make_pair(tmp_path, "e", "100", "500")
    ex = [v.ScreeningException("e", "factor_two", "please"), v.ScreeningException(v.scenario_key(t), "factor_two", "please")]
    found = v.mechanical_findings([t, f], tmp_path, ex)
    assert "factor_two" in codes(found, "failure")
    assert v.mechanical_failures([t, f], tmp_path, ex)


# ------------------------------------------------------------------ names


def test_normalize_name_unicode():
    assert v.normalize_name("ＴＯＬＶＡＮＥ　Mill") == "tolvane mill"
    assert v.normalize_name("Tolvane MILL") == "tolvane mill"
    assert v.normalize_name("Café") == v.normalize_name("Cafe") == "cafe"
    assert v.normalize_name("Café") == "cafe"
    assert v.normalize_name("  Tolvane,  Mill.-- ") == "tolvane mill"
    assert v.normalize_name("Tolvane Mill") == "tolvane mill"
    assert v.normalize_name("Straße") == "strasse"
    assert v.normalize_name("") == ""
    assert v.normalize_name("...") == ""


def test_normalize_name_mixed_scripts_and_long():
    assert v.normalize_name("Лондон Мill") == "лондон мill"
    assert v.normalize_name("東京 Group") == "東京 group"
    long = "a " * 50000
    assert v.normalize_name(long) == long.strip()


@pytest.mark.parametrize(
    "bad",
    ["a​b", "a‍b", "a‎b", "a‮b", "a⁦b", "a⁩b", "a⁠b", "a﻿b", "a\x00b", "a\nb", "a\tb", "a\x7fb", "a­b"],
)
def test_normalize_name_refuses_invisible(bad):
    with pytest.raises(v.NameRefused):
        v.normalize_name(bad)
    assert issubclass(v.NameRefused, ValueError)


def test_levenshtein():
    assert v.levenshtein("", "") == 0
    assert v.levenshtein("kitten", "sitting") == 3
    assert v.levenshtein("a", "") == 1
    rng = random.Random(1)
    for _ in range(300):
        a = "".join(rng.choice("ab") for _ in range(rng.randint(0, 5)))
        b = "".join(rng.choice("ab") for _ in range(rng.randint(0, 5)))
        assert v.levenshtein_at_most_one(a, b) == (v.levenshtein(a, b) <= 1)
    assert v.levenshtein_at_most_one("x" * 100000, "x" * 100001)


def two_pairs(tmp_path, ent=("Alpha One", "Beta Two", "Gamma Three", "Delta Four"), orig_a=None, orig_b=None, checks=("pending",) * 4):
    oa = orig_a or org_set(0)
    ob = orig_b or org_set(1)
    out = []
    for pair, (te, fe), origs, (ck_t, ck_f) in (("p1", ent[:2], oa, checks[:2]), ("p2", ent[2:], ob, checks[2:])):
        t = make(f"{pair}-t", pair, "true", "100", entity=te, origins=origs, check=ck_t)
        f = make(f"{pair}-f", pair, "false", "150", true_value="100", entity=fe, origins=origs, check=ck_f)
        write_ev(tmp_path, t, "SYNTHETIC\nbody\n")
        write_ev(tmp_path, f, "SYNTHETIC\nbody\n")
        out += [t, f]
    return out


def hard(found):
    return [f for f in found if f.code == "name_collision_hard"]


def test_no_collision_baseline(tmp_path):
    found = v.mechanical_findings(two_pairs(tmp_path), tmp_path)
    assert hard(found) == [] and "name_near_duplicate" not in codes(found)


def test_entity_collision_across_lineages_and_normalized(tmp_path):
    scs = two_pairs(tmp_path, ent=("Alpha One", "Beta Two", "ＡＬＰＨＡ  one", "Delta Four"))
    h = hard(v.mechanical_findings(scs, tmp_path))
    assert len(h) == 1 and h[0].kind == "failure" and set(h[0].subjects) == {"p1-t@1", "p2-t@1"}


def test_entity_collision_within_one_pair(tmp_path):
    scs = two_pairs(tmp_path, ent=("Alpha One", "alpha one", "Gamma Three", "Delta Four"))
    h = hard(v.mechanical_findings(scs, tmp_path))
    assert len(h) == 1 and "one pair" in h[0].message


def test_origin_shared_in_pair_not_reported(tmp_path):
    assert hard(v.mechanical_findings(two_pairs(tmp_path), tmp_path)) == []


def test_origin_shared_across_pairs(tmp_path):
    scs = two_pairs(tmp_path, orig_b=[org_set(0)[0]] + org_set(1)[1:])
    h = hard(v.mechanical_findings(scs, tmp_path))
    assert len(h) == 1 and h[0].subjects == ("p1", "p2")


def test_origin_refused_is_failure(tmp_path):
    scs = two_pairs(tmp_path, orig_a=["A​x Group", "Ab Group", "Ac Group", "Ad Group"])
    found = v.mechanical_findings(scs, tmp_path)
    assert "name_refused" in codes(found, "failure")


def test_entity_refused_and_empty(tmp_path):
    scs = two_pairs(tmp_path, ent=("Alpha‮One", "...", "Gamma Three", "Delta Four"))
    refused = [f for f in v.mechanical_findings(scs, tmp_path) if f.code == "name_refused"]
    assert len(refused) == 2


def test_supersession_excludes_ancestors(tmp_path):
    scs = two_pairs(tmp_path)
    old = make("p1-t", "p1", "true", "100", entity="Gamma Three", origins=org_set(0))
    write_ev(tmp_path, old, "SYNTHETIC\nbody\n")
    # old p1-t@1 has the same entity as p2-t but is replaced by p1-t@2 (already in scs as version 1 -> rebuild)
    new = make("p1-t", "p1", "true", "100", entity="Alpha One", origins=org_set(0), version=2, supersedes="p1-t@1")
    write_ev(tmp_path, new, "SYNTHETIC\nbody\n")
    others = [s for s in scs if s.scenario_id != "p1-t"]
    found = v.mechanical_findings(others + [old, new], tmp_path)
    assert hard(found) == []
    # without the supersession the ancestor would collide
    plain = make("p1-t", "p1", "true", "100", entity="Gamma Three", origins=org_set(0))
    assert len(hard(v.mechanical_findings(others + [plain], tmp_path))) == 1


def test_same_lineage_never_collides(tmp_path):
    scs = two_pairs(tmp_path)
    old = [s for s in scs if s.scenario_id == "p1-t"][0]
    new = make("p1-t", "p1", "true", "100", entity="Alpha One", origins=org_set(0), version=2, supersedes="p1-t@1")
    write_ev(tmp_path, new, "SYNTHETIC\nbody\n")
    found = v.mechanical_findings([s for s in scs if s is not old] + [old, new], tmp_path)
    assert hard(found) == []
    assert [s.scenario_version for s in v.current_scenarios([old, new])] == [2]


def test_near_duplicates_flag_not_hard(tmp_path):
    scs = two_pairs(tmp_path, ent=("Alpha One", "Beta Two", "Alpha Onf", "Delta Four"))
    found = v.mechanical_findings(scs, tmp_path)
    near = [f for f in found if f.code == "name_near_duplicate"]
    assert len(near) == 1 and near[0].kind == "flag" and hard(found) == []
    scs = two_pairs(tmp_path, ent=("Alpha One", "Beta Two", "Alpha Pne", "Delta Four"))
    assert any(f.code == "name_near_duplicate" for f in v.mechanical_findings(scs, tmp_path))
    scs = two_pairs(tmp_path, ent=("Alpha One", "Beta Two", "Alpha Xyz", "Delta Four"))
    assert "name_near_duplicate" not in codes(v.mechanical_findings(scs, tmp_path))


def test_near_duplicate_origins_and_exception(tmp_path):
    scs = two_pairs(tmp_path, orig_a=org_set(0), orig_b=[org_set(0)[0].replace("aaaaaa", "aaaaab")] + org_set(1)[1:])
    found = v.mechanical_findings(scs, tmp_path)
    near = [f for f in found if f.code == "name_near_duplicate"]
    assert near and all(f.kind == "flag" for f in near)
    ex = [v.ScreeningException(f.subjects[0], "name_near_duplicate", "different on purpose") for f in near]
    after = v.mechanical_findings(scs, tmp_path, ex)
    assert {f.kind for f in after if f.code == "name_near_duplicate"} == {"excepted"}


def test_collision_status_rules(tmp_path):
    clash = ("Alpha One", "Beta Two", "alpha one", "Delta Four")
    found = v.mechanical_findings(two_pairs(tmp_path, ent=clash, checks=("clear", "pending", "pending", "pending")), tmp_path)
    status = [f for f in found if f.code == "name_collision_status"]
    assert len(status) == 1 and status[0].kind == "failure" and status[0].subjects == ("p1-t@1",)
    found = v.mechanical_findings(two_pairs(tmp_path, ent=clash, checks=("pending",) * 4), tmp_path)
    assert "name_collision_status" not in codes(found)
    found = v.mechanical_findings(two_pairs(tmp_path, checks=("collision", "pending", "pending", "pending")), tmp_path)
    unconfirmed = [f for f in found if f.code == "name_collision_status_unconfirmed"]
    assert len(unconfirmed) == 1 and unconfirmed[0].kind == "flag"
    found = v.mechanical_findings(two_pairs(tmp_path, ent=clash, checks=("collision", "pending", "collision", "pending")), tmp_path)
    assert "name_collision_status_unconfirmed" not in codes(found)
    found = v.mechanical_findings(two_pairs(tmp_path, checks=("clear",) * 4), tmp_path)
    assert "name_collision_status" not in codes(found)


def test_incomplete_pair(tmp_path):
    t, f = make_pair(tmp_path, "p", "100", "150")
    assert "pair_incomplete" in codes(v.mechanical_findings([t], tmp_path), "failure")


# ------------------------------------------------------------------ determinism, purity


def test_determinism_order_and_no_mutation(tmp_path):
    scs = two_pairs(tmp_path, ent=("Alpha One", "alpha one", "Alpha Onf", "Delta Four"))
    snapshot = [s.model_dump_json() for s in scs]
    first = v.mechanical_findings(scs, tmp_path)
    assert v.mechanical_findings(scs, tmp_path) == first
    assert v.mechanical_findings(list(reversed(scs)), tmp_path) == first
    shuffled = scs[:]
    random.Random(3).shuffle(shuffled)
    assert v.mechanical_findings(shuffled, tmp_path) == first
    assert [s.model_dump_json() for s in scs] == snapshot
    assert v.mechanical_failures(scs, tmp_path) == [f.message for f in first if f.kind == "failure"]
    assert [f.kind for f in first] == sorted((f.kind for f in first), key=lambda k: {"failure": 0, "flag": 1, "excepted": 2}[k])


def test_empty_set():
    assert v.mechanical_findings([]) == []


def test_very_long_names_do_not_hang(tmp_path):
    long_a, long_b = "q" * 20000, "q" * 20000 + "r"
    scs = two_pairs(tmp_path, ent=(long_a, "Beta Two", long_b, "Delta Four"))
    assert "name_near_duplicate" in codes(v.mechanical_findings(scs, tmp_path))


# ------------------------------------------------------------------ end to end on the real set


def test_real_scenarios():
    scs = load_scenario_dir(REPO_ROOT / "data" / "scenarios" / "v2")
    found = v.mechanical_findings(scs)
    by_pair = {}
    for s in scs:
        by_pair.setdefault(s.pair_id, {})[s.truth_status] = s
    pairs = [(m["true"], m["false"]) for _, m in sorted(by_pair.items())]

    # all five evidence pairs satisfy the length rule
    assert len(pairs) == 5
    assert "evidence_length" not in codes(found)
    for t, f in pairs:
        assert v.evidence_lengths_match(
            (REPO_ROOT / t.evidence.reference).read_text(encoding="utf-8"),
            (REPO_ROOT / f.evidence.reference).read_text(encoding="utf-8"),
        )

    # directions follow from recorded values
    report = v.direction_balance(pairs)
    expected = {"over": 0, "under": 0}
    for t, f in pairs:
        if v.scale_kind(t) == "ratio":
            expected[v.direction(v.parse_number(t.claim.asserted_value), v.parse_number(f.claim.asserted_value))] += 1
    assert report["ratio"] == expected
    assert report["year"] == [("hist", 1612 - 1583)]   # Stage 4J.6B: hist-a revised from 1741 (158 years) to 1612 (29 years)
    assert ("direction_imbalance" in codes(found, "failure")) is (not v.is_balanced(expected["over"], expected["under"]))

    # hist: the Stage 4J.6B revision removed the automatic year_threshold failure (the rule itself is still
    # exercised by test_year_hist_like_values and the seeded confirmatory-gate test)
    assert [f for f in found if f.code == "year_threshold"] == []

    # no hard name collisions
    assert hard(found) == []


# ------------------------------------------------------------------ reviewer-identifier audit

from maps.schemas import Adjudication, ReviewerAssignment  # noqa: E402


def with_ids(s: Scenario, author=None, reviewers=(), adjudicator=None) -> Scenario:
    """Copy of s carrying only the given ids (model_copy skips the status-gate checks on purpose)."""
    upd = {
        "author_id": author,
        "reviewer_assignments": [
            ReviewerAssignment(reviewer_id=r, stages=["fact"], assigned_on="2026-12-01T10:00:00+00:00") for r in reviewers
        ],
    }
    if adjudicator is not None:
        upd["adjudication"] = Adjudication(
            reason="split", adjudicator_id=adjudicator, decided_on="2026-12-05T10:00:00+00:00",
            outcome="revise", rationale="because",
        )
    return s.model_copy(update=upd)


def id_pair(tmp_path, pair="p", t_ids=None, f_ids=None):
    t, f = make_pair(tmp_path, pair, "100", "150")
    return with_ids(t, **(t_ids or {})), with_ids(f, **(f_ids or {}))


def audit(scs):
    return v.id_audit_findings(scs)


def test_id_valid_distinct_pass(tmp_path):
    t, f = id_pair(tmp_path, t_ids={"author": "auth-1", "reviewers": ["rev-a"]}, f_ids={"author": "auth-1", "reviewers": ["rev-b"], "adjudicator": "adj-1"})
    assert audit([t, f]) == []
    assert not [x for x in v.mechanical_findings([t, f], tmp_path) if x.code.startswith("id_")]


def test_id_case_only_duplicate_fails(tmp_path):
    t, f = id_pair(tmp_path, t_ids={"reviewers": ["rev-a"]}, f_ids={"reviewers": ["Rev-A"]})
    res = audit([t, f])
    assert [(x.kind, x.code, x.subjects) for x in res] == [("failure", "id_case_collision", ("Rev-A", "rev-a"))]
    assert "Rev-A" in res[0].message and "rev-a" in res[0].message
    assert "id_case_collision" in codes(v.mechanical_findings([t, f], tmp_path), "failure")
    assert v.mechanical_failures([t, f], tmp_path)


def test_id_case_author_vs_reviewer_fails(tmp_path):
    t, f = id_pair(tmp_path, t_ids={"author": "Auth-1"}, f_ids={"reviewers": ["auth-1"]})
    assert "id_case_collision" in codes(audit([t, f]), "failure")


def test_id_case_collision_across_pairs(tmp_path):
    a, b = id_pair(tmp_path, "p", t_ids={"reviewers": ["rev-a"]})
    c, d = id_pair(tmp_path, "q", t_ids={"reviewers": ["REV-A"]})
    assert "id_case_collision" in codes(audit([a, b, c, d]), "failure")


@pytest.mark.parametrize("t_ids,f_ids", [
    ({"author": "x-1", "reviewers": ["x-1"]}, {}),
    ({"author": "x-1", "adjudicator": "x-1"}, {}),
    ({"reviewers": ["x-1"], "adjudicator": "x-1"}, {}),
    ({"author": "x-1"}, {"reviewers": ["x-1"]}),
    ({"reviewers": ["x-1"]}, {"author": "x-1"}),
    ({"author": "x-1"}, {"adjudicator": "x-1"}),
    ({"reviewers": ["x-1"]}, {"adjudicator": "x-1"}),
])
def test_id_pair_role_overlap_fails(tmp_path, t_ids, f_ids):
    t, f = id_pair(tmp_path, t_ids=t_ids, f_ids=f_ids)
    res = audit([t, f])
    assert [(x.kind, x.code, x.subjects) for x in res] == [("failure", "id_pair_role_overlap", ("p", "x-1"))]


def test_id_same_reviewer_on_both_members_ok(tmp_path):
    t, f = id_pair(tmp_path, t_ids={"reviewers": ["rev-a"]}, f_ids={"reviewers": ["rev-a"]})
    assert audit([t, f]) == []


def test_id_cross_pair_overlap_is_flag(tmp_path):
    a, b = id_pair(tmp_path, "p", t_ids={"author": "x-1"})
    c, d = id_pair(tmp_path, "q", t_ids={"reviewers": ["x-1"]})
    res = audit([a, b, c, d])
    assert [(x.kind, x.code) for x in res] == [("flag", "id_cross_pair_overlap")]
    assert res[0].subjects == ("p", "q", "x-1")
    assert not [x for x in v.mechanical_findings([a, b, c, d], tmp_path) if x.code.startswith("id_") and x.kind == "failure"]
    a2, b2 = id_pair(tmp_path, "p", t_ids={"author": "x-1"})
    c2, d2 = id_pair(tmp_path, "q", f_ids={"adjudicator": "x-1"})
    assert codes(audit([a2, b2, c2, d2]), "flag") == ["id_cross_pair_overlap"]


def test_id_same_role_across_pairs_not_flagged(tmp_path):
    for role in ("author", "reviewers", "adjudicator"):
        val = "x-1" if role == "author" or role == "adjudicator" else ["x-1"]
        a, b = id_pair(tmp_path, "p", t_ids={role: val})
        c, d = id_pair(tmp_path, "q", t_ids={role: val})
        assert audit([a, b, c, d]) == []


def test_id_same_pair_overlap_not_also_flagged(tmp_path):
    a, b = id_pair(tmp_path, "p", t_ids={"author": "x-1", "reviewers": ["x-1"]})
    c, d = id_pair(tmp_path, "q", t_ids={"reviewers": ["x-1"]})
    res = audit([a, b, c, d])
    assert codes(res, "failure") == ["id_pair_role_overlap"]
    assert codes(res, "flag") == []


def test_id_superseded_ignored(tmp_path):
    t, f = id_pair(tmp_path, t_ids={"author": "x-1", "reviewers": ["x-1"]})
    new = make("p-t", "p", "true", "100", entity="Alpha px", version=2, supersedes=v.scenario_key(t))
    assert audit([t, f, new]) == []


def test_id_flag_exception_and_failure_exception(tmp_path):
    a, b = id_pair(tmp_path, "p", t_ids={"author": "x-1"})
    c, d = id_pair(tmp_path, "q", t_ids={"reviewers": ["x-1"]})
    scs = [a, b, c, d]
    exc = v.ScreeningException("x-1", "id_cross_pair_overlap", "owner reviewed the roster")
    got = v.mechanical_findings(scs, tmp_path, [exc])
    assert [x.kind for x in got if x.code == "id_cross_pair_overlap"] == ["excepted"]
    e, g = id_pair(tmp_path, "r", t_ids={"author": "y-1", "reviewers": ["y-1"]})
    fx = v.ScreeningException("y-1", "id_pair_role_overlap", "no")
    fx2 = v.ScreeningException("r", "id_pair_role_overlap", "no")
    got = v.mechanical_findings([e, g], tmp_path, [fx, fx2])
    assert [x.kind for x in got if x.code == "id_pair_role_overlap"] == ["failure"]


def test_id_determinism_no_mutation(tmp_path):
    a, b = id_pair(tmp_path, "p", t_ids={"author": "x-1", "reviewers": ["Rev-a"]}, f_ids={"reviewers": ["rev-a"]})
    c, d = id_pair(tmp_path, "q", t_ids={"reviewers": ["x-1"]})
    scs = [a, b, c, d]
    snap = [s.model_dump_json() for s in scs]
    first = v.mechanical_findings(scs, tmp_path)
    assert v.mechanical_findings(list(reversed(scs)), tmp_path) == first
    shuffled = scs[:]
    random.Random(5).shuffle(shuffled)
    assert v.mechanical_findings(shuffled, tmp_path) == first
    assert audit(shuffled) == audit(scs)
    assert [s.model_dump_json() for s in scs] == snap


def test_id_real_scenarios_have_no_id_findings():
    scs = load_scenario_dir(REPO_ROOT / "data" / "scenarios" / "v2")
    assert audit(scs) == []
    assert not [x for x in v.mechanical_findings(scs) if x.code.startswith("id_")]


def test_id_messages_print_ids_not_claim_values(tmp_path):
    t, f = id_pair(tmp_path, t_ids={"author": "x-1", "reviewers": ["x-1"]}, f_ids={"reviewers": ["X-1"]})
    res = audit([t, f])
    assert res and any("x-1" in x.message for x in res)
    for x in res:
        for s in (t, f):
            assert s.claim.asserted_value not in x.message.replace("x-1", "")
            assert s.claim.entity not in x.message and s.claim.attribute not in x.message


def test_id_empty_and_single():
    assert audit([]) == []
    s = make("solo-t", "solo", "true", "100", entity="Solo Alpha")
    assert audit([s]) == []
    assert audit([with_ids(s, author="a-1", reviewers=["a-2"])]) == []
    assert codes(audit([with_ids(s, author="a-1", reviewers=["a-1"])]), "failure") == ["id_pair_role_overlap"]
