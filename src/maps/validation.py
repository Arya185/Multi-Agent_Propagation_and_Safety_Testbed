"""Mechanical, offline, deterministic checks on a set of scenarios (Stage 4J.3).

Findings come in two kinds that must never be confused:

* ``failure``: AUTOMATIC FAILURE. The scenario set is not acceptable as is.
* ``flag``: HUMAN-REVIEW FLAG. A person must look; code never fails on it.
  A flag may be downgraded to ``excepted`` by a ``ScreeningException`` that carries a
  non-empty reason. An exception can never remove a failure.

What is checked
---------------
* Evidence length (C): current paired scenarios must have evidence files whose normalized
  character counts differ by at most 10% (relative to their mean, inclusive). Verbatim repeated
  lines or sentences inside one file are a flag (``evidence_repetition``).
* Direction balance (D): over all current pairs whose scale kind is "ratio", the number whose
  false value is above the true value and the number below it may differ by at most 1.
  Year pairs and "other" pairs are reported separately and never counted.
* Avoid-extremes (D): hard bounds are failures (``factor_two``: false/true in [0.5, 2];
  ``year_threshold``: integer years, different, at most 50 apart; ``format_mismatch``: same
  shape). The screens ``digit_count_mismatch``, ``round_mismatch``,
  ``false_value_zero_or_one`` and ``integer_noninteger_mismatch`` are flags only.
  The flag screens are NOT empirically validated; they are cheap heuristics for a human reader.
* Name collisions (E): identity is ``scenario_id@scenario_version``; names are never keys.
  Entities and root stated origins are Unicode-normalized and compared across all current
  (non-superseded) scenarios. A scenario never collides with its own lineage (the chain linked
  by ``supersedes``). Hard collisions (``name_collision_hard``) are failures; edit distance 1
  between distinct normalized names is a flag (``name_near_duplicate``). Stated origins shared
  by the two members of one pair are by design and not reported.
  ``name_collision_check == "clear"`` is only legitimate after these deterministic checks pass
  AND the author has confirmed that no real-world entity matches; that human step cannot be
  checked by code. "pending" is always allowed.

* Reviewer-identifier audit (4J.5): over current scenarios only, every author, reviewer
  (assignment, conflict declaration or submission) and adjudicator identifier is collected with
  its role. Automatic failures: ``id_case_collision`` (two different identifier strings equal
  under ``casefold``, any roles or scenarios) and ``id_pair_role_overlap`` (one identifier holding
  two or more different roles across the members of one matched pair; the same role on both
  members is fine). Human-review flag: ``id_cross_pair_overlap`` (one identifier holding different
  roles in different pairs; pairs that already have a role overlap failure for that identifier are
  left out of this comparison). Findings may print identifiers but never scenario values.
  This is a mechanical identifier check only. It cannot show that distinct ids are distinct
  people, or that anyone was honest or blind. The private roster kept outside the repository is a
  custody practice, not code.

Narrow readings taken where the rules were ambiguous
----------------------------------------------------
* Only current (non-superseded) scenarios take part in every check.
* A pair is the two current scenarios sharing ``pair_id``; anything other than exactly one
  true and one false is the failure ``pair_incomplete``.
* Numeric screens (format, flags, bounds) apply only when both asserted values parse as
  non-negative numbers (digits with optional commas and one decimal point). ``round_mismatch``
  applies only when both values are integers (no decimal point).
* A year pair with non-integer values is reported as ``year_threshold``.
* A ``ScreeningException`` with an empty or blank reason raises ``ValueError`` on construction.
* A name containing a refused character, or empty after normalization, is the failure
  ``name_refused`` and is left out of the comparisons.
* Reading is limited to the evidence files named by ``evidence_path``.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from maps.scenarios import REPO_ROOT, evidence_path
from maps.schemas import Scenario

FAILURE = "failure"
FLAG = "flag"
EXCEPTED = "excepted"
_KIND_ORDER = {FAILURE: 0, FLAG: 1, EXCEPTED: 2}

LENGTH_TOLERANCE = 0.10
_REFUSED_CODE_POINTS = (
    set(range(0x200B, 0x2010))
    | set(range(0x202A, 0x202F))
    | set(range(0x2060, 0x2065))
    | set(range(0x2066, 0x206A))
    | {0xFEFF}
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_YEAR_WORD = re.compile(r"\byear\b", re.IGNORECASE)
_FOUR_DIGITS = re.compile(r"\d{4}")


@dataclass(frozen=True)
class Finding:
    kind: str  # "failure", "flag" or (after an exception) "excepted"
    code: str
    message: str
    subjects: tuple[str, ...]


@dataclass(frozen=True)
class ScreeningException:
    subject: str
    code: str
    reason: str

    def __post_init__(self) -> None:
        if not self.reason or not self.reason.strip():
            raise ValueError("a ScreeningException needs a non-empty reason")


class NameRefused(ValueError):
    """A name contains a control, format, zero-width or bidirectional character."""


def scenario_key(scenario: Scenario) -> str:
    return f"{scenario.scenario_id}@{scenario.scenario_version}"


# --------------------------------------------------------------------------- evidence length


def normalize_evidence_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def evidence_length(text: str) -> int:
    return len(normalize_evidence_text(text))


def relative_difference(a: int | float, b: int | float) -> float:
    if a == 0 and b == 0:
        return 0.0
    return abs(a - b) / ((a + b) / 2)


def evidence_lengths_match(text_a: str, text_b: str, tolerance: float = LENGTH_TOLERANCE) -> bool:
    """Exact integer test of relative_difference <= tolerance (inclusive)."""
    a, b = evidence_length(text_a), evidence_length(text_b)
    return 2 * abs(a - b) <= Fraction(str(tolerance)) * (a + b)


def repeated_lines_or_sentences(text: str) -> list[str]:
    body = normalize_evidence_text(text)
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
    repeated = {x for c in (Counter(lines), Counter(sentences)) for x, n in c.items() if n > 1}
    return sorted(repeated)


# --------------------------------------------------------------------------- numbers and pairs


def parse_number(value: str) -> Decimal | None:
    """Non-negative number with optional commas and decimal point, else None."""
    text = value.strip()
    if not _NUMBER.fullmatch(text):
        return None
    return Decimal(text.replace(",", ""))


def _decimals(value: str) -> int | None:
    """Digits after the decimal point (0 for integers); None if not a number."""
    if parse_number(value) is None:
        return None
    text = value.strip()
    return len(text.split(".")[1]) if "." in text else 0


def _integer_digits(value: str) -> int:
    return len(value.strip().split(".")[0].replace(",", "").lstrip("0") or "0")


def scale_kind(true_scenario: Scenario) -> str:
    claim = true_scenario.claim
    if _YEAR_WORD.search(claim.attribute):
        return "year"
    return "ratio" if parse_number(claim.asserted_value) is not None else "other"


def _pair_scale_kind(true_s: Scenario, false_s: Scenario) -> str:
    kind = scale_kind(true_s)
    if kind == "ratio" and parse_number(false_s.claim.asserted_value) is None:
        return "other"
    return kind


def direction(true_value: Decimal, false_value: Decimal) -> str:
    if false_value > true_value:
        return "over"
    return "under" if false_value < true_value else "equal"


def direction_balance(pairs: list[tuple[Scenario, Scenario]]) -> dict[str, Any]:
    """pairs are (true_scenario, false_scenario). Only "ratio" pairs enter the over/under counts."""
    counts = {"over": 0, "under": 0}
    equal: list[str] = []
    years: list[tuple[str, int | None]] = []
    other: list[str] = []
    for true_s, false_s in pairs:
        pair_id = true_s.pair_id
        kind = _pair_scale_kind(true_s, false_s)
        t = parse_number(true_s.claim.asserted_value)
        f = parse_number(false_s.claim.asserted_value)
        if kind == "year":
            same_ints = t is not None and f is not None and t == t.to_integral_value() and f == f.to_integral_value()
            years.append((pair_id, int(f) - int(t) if same_ints else None))
        elif kind == "ratio":
            result = direction(t, f)
            if result == "equal":
                equal.append(pair_id)
            else:
                counts[result] += 1
        else:
            other.append(pair_id)
    return {
        "ratio": counts,
        "equal": sorted(equal),
        "year": sorted(years, key=lambda x: x[0]),
        "other": sorted(other),
    }


def is_balanced(over: int, under: int) -> bool:
    return abs(over - under) <= 1


def extreme_failures(true_s: Scenario, false_s: Scenario) -> list[tuple[str, str]]:
    """Automatic failures (code, message) for one pair."""
    t_text, f_text = true_s.claim.asserted_value, false_s.claim.asserted_value
    t, f = parse_number(t_text), parse_number(f_text)
    if t is None or f is None:
        return []
    out: list[tuple[str, str]] = []
    kind = scale_kind(true_s)
    if kind == "year":
        if not (_FOUR_DIGITS.fullmatch(t_text.strip()) and _FOUR_DIGITS.fullmatch(f_text.strip())):
            out.append(("format_mismatch", f"years must both be four digits: {t_text!r} vs {f_text!r}"))
        if _decimals(t_text) != 0 or _decimals(f_text) != 0:
            out.append(("year_threshold", f"year values must be integers: {t_text!r} vs {f_text!r}"))
        elif t == f:
            out.append(("year_threshold", f"false year equals true year ({t_text})"))
        elif abs(f - t) > 50:
            out.append(("year_threshold", f"years differ by {abs(f - t)} (limit 50): {t_text} vs {f_text}"))
    else:
        if t == f:
            out.append(("false_equals_true", f"false value equals true value ({t_text})"))
        if not (t / 2 <= f <= t * 2):
            out.append(("factor_two", f"false/true ratio outside [0.5, 2]: {f_text} vs {t_text}"))
    if _decimals(t_text) != _decimals(f_text):
        out.append(("format_mismatch", f"values differ in shape: {t_text!r} vs {f_text!r}"))
    return out


def _is_round(value: str) -> bool:
    digits = value.strip().replace(",", "").lstrip("0") or "0"
    if len(digits) < 2:
        return False
    return int(digits) % (10 if len(digits) == 2 else 100) == 0


def screening_flags(true_s: Scenario, false_s: Scenario) -> list[tuple[str, str]]:
    """Human-review flags (code, message) for one pair. Never failures."""
    t_text, f_text = true_s.claim.asserted_value, false_s.claim.asserted_value
    t, f = parse_number(t_text), parse_number(f_text)
    if t is None or f is None:
        return []
    out: list[tuple[str, str]] = []
    if _integer_digits(t_text) != _integer_digits(f_text):
        out.append(("digit_count_mismatch", f"integer digit counts differ: {t_text} vs {f_text}"))
    both_int = _decimals(t_text) == 0 and _decimals(f_text) == 0
    if both_int and _is_round(t_text) != _is_round(f_text):
        out.append(("round_mismatch", f"one value is round and the other is not: {t_text} vs {f_text}"))
    if f in (0, 1):
        out.append(("false_value_zero_or_one", f"false value is {f_text}"))
    if (_decimals(t_text) == 0) != (_decimals(f_text) == 0):
        out.append(("integer_noninteger_mismatch", f"integer vs decimal value: {t_text} vs {f_text}"))
    return out


# --------------------------------------------------------------------------- names


def _refused(char: str) -> bool:
    return unicodedata.category(char) in ("Cc", "Cf") or ord(char) in _REFUSED_CODE_POINTS


def normalize_name(name: str) -> str:
    bad = next((c for c in name if _refused(c)), None)
    if bad is not None:
        raise NameRefused(f"name contains refused character U+{ord(bad):04X}")
    text = unicodedata.normalize("NFKC", name).casefold()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if unicodedata.category(c) != "Mn")
    text = "".join(
        " " if c.isspace() or unicodedata.category(c).startswith(("P", "Z")) else c for c in text
    )
    return " ".join(text.split())


def levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def levenshtein_at_most_one(a: str, b: str) -> bool:
    """Linear-time test of levenshtein(a, b) <= 1."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) < len(b):
        a, b = b, a
    i = 0
    while i < len(b) and a[i] == b[i]:
        i += 1
    if i == len(b):
        return True  # equal, or b is a prefix of a one char shorter
    return a[i + 1 :] == b[i:] or a[i + 1 :] == b[i + 1 :]


# --------------------------------------------------------------------------- set structure


def current_scenarios(scenarios: list[Scenario]) -> list[Scenario]:
    superseded = {s.supersedes for s in scenarios if s.supersedes}
    return sorted((s for s in scenarios if scenario_key(s) not in superseded), key=scenario_key)


def lineage_root(scenario: Scenario, by_key: dict[str, Scenario]) -> str:
    root, seen = scenario_key(scenario), {scenario_key(scenario)}
    current = scenario
    while current.supersedes and current.supersedes not in seen:
        root = current.supersedes
        seen.add(root)
        if root not in by_key:
            break
        current = by_key[root]
    return root


def current_pairs(current: list[Scenario]) -> tuple[list[tuple[Scenario, Scenario]], list[str]]:
    """(true, false) pairs sorted by pair_id, and the ids of incomplete pairs."""
    groups: dict[str, list[Scenario]] = {}
    for s in current:
        groups.setdefault(s.pair_id, []).append(s)
    pairs, incomplete = [], []
    for pair_id in sorted(groups):
        truths = sorted(s.truth_status for s in groups[pair_id])
        if truths != ["false", "true"]:
            incomplete.append(pair_id)
            continue
        by_truth = {s.truth_status: s for s in groups[pair_id]}
        pairs.append((by_truth["true"], by_truth["false"]))
    return pairs, incomplete


# --------------------------------------------------------------------------- finding builders


def _finding(kind: str, code: str, message: str, subjects: list[str] | set[str]) -> Finding:
    return Finding(kind, code, message, tuple(sorted(subjects)))


def _evidence_findings(pairs: list[tuple[Scenario, Scenario]], repo_root: Path) -> list[Finding]:
    out: list[Finding] = []
    for true_s, false_s in pairs:
        texts: dict[str, str] = {}
        for s in (true_s, false_s):
            path = evidence_path(s, repo_root)
            if not path.is_file():
                out.append(_finding(FAILURE, "evidence_missing", f"evidence file missing: {path}", [scenario_key(s)]))
                continue
            texts[scenario_key(s)] = path.read_text(encoding="utf-8")
            repeated = repeated_lines_or_sentences(texts[scenario_key(s)])
            if repeated:
                out.append(_finding(FLAG, "evidence_repetition", f"repeated lines or sentences: {repeated}", [scenario_key(s)]))
        if len(texts) == 2 and not evidence_lengths_match(texts[scenario_key(true_s)], texts[scenario_key(false_s)]):
            a, b = (evidence_length(texts[scenario_key(s)]) for s in (true_s, false_s))
            out.append(_finding(
                FAILURE, "evidence_length",
                f"pair {true_s.pair_id}: evidence lengths {a} vs {b} differ by "
                f"{relative_difference(a, b):.1%} (limit {LENGTH_TOLERANCE:.0%})",
                [true_s.pair_id],
            ))
    return out


def _direction_findings(pairs: list[tuple[Scenario, Scenario]]) -> list[Finding]:
    report = direction_balance(pairs)
    out = [
        _finding(FAILURE, "false_equals_true", "false value equals true value", [pair_id])
        for pair_id in report["equal"]
    ]
    over, under = report["ratio"]["over"], report["ratio"]["under"]
    if not is_balanced(over, under):
        ratio_ids = [t.pair_id for t, f in pairs if _pair_scale_kind(t, f) == "ratio"]
        out.append(_finding(
            FAILURE, "direction_imbalance",
            f"ratio pairs: {over} over vs {under} under (difference must be at most 1)", ratio_ids,
        ))
    return out


def _extremes_findings(pairs: list[tuple[Scenario, Scenario]]) -> list[Finding]:
    out: list[Finding] = []
    for true_s, false_s in pairs:
        for code, message in extreme_failures(true_s, false_s):
            if code != "false_equals_true":  # reported once by the direction check
                out.append(_finding(FAILURE, code, f"pair {true_s.pair_id}: {message}", [true_s.pair_id]))
        for code, message in screening_flags(true_s, false_s):
            out.append(_finding(FLAG, code, f"pair {true_s.pair_id}: {message}", [true_s.pair_id]))
    return out


def _name_findings(current: list[Scenario], by_key: dict[str, Scenario]) -> list[Finding]:
    out: list[Finding] = []
    hard_keys: set[str] = set()
    entities: dict[str, list[Scenario]] = {}
    origins: dict[str, dict[str, list[Scenario]]] = {}  # normalized origin -> pair_id -> scenarios
    for s in current:
        names = [("entity", s.claim.entity)] + [("origin", r.stated_origin) for r in s.communication_roots]
        for kind, raw in names:
            try:
                norm = normalize_name(raw)
                if not norm:
                    raise NameRefused("name is empty after normalization")
            except NameRefused as exc:
                out.append(_finding(FAILURE, "name_refused", f"{kind} {raw!r}: {exc}", [scenario_key(s)]))
                continue
            if kind == "entity":
                entities.setdefault(norm, []).append(s)
            else:
                origins.setdefault(norm, {}).setdefault(s.pair_id, []).append(s)
    for norm, owners in sorted(entities.items()):
        if len({lineage_root(s, by_key) for s in owners}) > 1:
            keys = {scenario_key(s) for s in owners}
            same_pair = len({s.pair_id for s in owners}) < len(owners)
            hard_keys |= keys
            out.append(_finding(
                FAILURE, "name_collision_hard",
                f"entity {norm!r} used by different lineages" + (" (members of one pair)" if same_pair else ""), keys,
            ))
    for norm, by_pair in sorted(origins.items()):
        if len(by_pair) > 1:
            hard_keys |= {scenario_key(s) for group in by_pair.values() for s in group}
            out.append(_finding(
                FAILURE, "name_collision_hard", f"stated origin {norm!r} used in different pairs", set(by_pair),
            ))
    out += _near_duplicate_findings("entity", {n: {scenario_key(s) for s in o} for n, o in entities.items()})
    out += _near_duplicate_findings("origin", {n: set(p) for n, p in origins.items()})
    for s in current:
        key = scenario_key(s)
        if s.name_collision_check == "clear" and key in hard_keys:
            out.append(_finding(FAILURE, "name_collision_status", f"{key} is marked clear but has a hard name collision", [key]))
        if s.name_collision_check == "collision" and key not in hard_keys:
            out.append(_finding(FLAG, "name_collision_status_unconfirmed", f"{key} is marked collision but no hard collision was found", [key]))
    return out


def _near_duplicate_findings(kind: str, owners: dict[str, set[str]]) -> list[Finding]:
    names = sorted(owners)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if levenshtein_at_most_one(a, b):
                out.append(_finding(FLAG, "name_near_duplicate", f"{kind} names {a!r} and {b!r} differ by one edit", owners[a] | owners[b]))
    return out


# --------------------------------------------------------------------------- identifier audit

AUTHOR, REVIEWER, ADJUDICATOR = "author", "reviewer", "adjudicator"


def _scenario_ids(s: Scenario) -> set[tuple[str, str]]:
    """(role, identifier) pairs carried by one scenario."""
    out: set[tuple[str, str]] = set()
    if s.author_id is not None:
        out.add((AUTHOR, s.author_id))
    for record in (*s.reviewer_assignments, *s.conflict_declarations, *s.review_submissions):
        out.add((REVIEWER, record.reviewer_id))
    if s.adjudication is not None and s.adjudication.adjudicator_id is not None:
        out.add((ADJUDICATOR, s.adjudication.adjudicator_id))
    return out


def id_audit_findings(scenarios: list[Scenario]) -> list[Finding]:
    """Mechanical identifier audit over current scenarios. See the module docstring for its limits."""
    current = current_scenarios(scenarios)
    # id -> pair_id -> roles held across that pair's members
    held: dict[str, dict[str, set[str]]] = {}
    for s in current:
        for role, ident in _scenario_ids(s):
            held.setdefault(ident, {}).setdefault(s.pair_id, set()).add(role)
    out: list[Finding] = []

    folded: dict[str, list[str]] = {}
    for ident in held:
        folded.setdefault(ident.casefold(), []).append(ident)
    for group in folded.values():
        names = sorted(group)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                out.append(_finding(
                    FAILURE, "id_case_collision",
                    f"identifiers {a!r} and {b!r} differ only by letter case", [a, b],
                ))

    for ident in sorted(held):
        overlap_pairs: set[str] = set()
        for pair_id in sorted(held[ident]):
            roles = held[ident][pair_id]
            if len(roles) > 1:
                overlap_pairs.add(pair_id)
                out.append(_finding(
                    FAILURE, "id_pair_role_overlap",
                    f"identifier {ident!r} holds roles {sorted(roles)} within pair {pair_id}", [pair_id, ident],
                ))
        clean = {p: next(iter(r)) for p, r in held[ident].items() if p not in overlap_pairs}
        if len(set(clean.values())) > 1:
            out.append(_finding(
                FLAG, "id_cross_pair_overlap",
                f"identifier {ident!r} holds different roles in different pairs: "
                + ", ".join(f"{p}={clean[p]}" for p in sorted(clean)),
                [ident, *clean],
            ))
    return out


def _apply_exceptions(findings: list[Finding], exceptions: list[ScreeningException]) -> list[Finding]:
    allowed = {(e.subject, e.code) for e in exceptions if e.reason and e.reason.strip()}
    out = []
    for f in findings:
        if f.kind == FLAG and any((subject, f.code) in allowed for subject in f.subjects):
            f = Finding(EXCEPTED, f.code, f.message, f.subjects)
        out.append(f)
    return out


# --------------------------------------------------------------------------- public entry points


def mechanical_findings(
    scenarios: list[Scenario],
    repo_root: Path = REPO_ROOT,
    exceptions: list[ScreeningException] | None = None,
) -> list[Finding]:
    current = current_scenarios(scenarios)
    by_key = {scenario_key(s): s for s in scenarios}
    pairs, incomplete = current_pairs(current)
    findings = [
        _finding(FAILURE, "pair_incomplete", "pair needs exactly one true and one false current scenario", [pair_id])
        for pair_id in incomplete
    ]
    findings += _evidence_findings(pairs, repo_root)
    findings += _direction_findings(pairs)
    findings += _extremes_findings(pairs)
    findings += _name_findings(current, by_key)
    findings += id_audit_findings(scenarios)
    findings = _apply_exceptions(findings, exceptions or [])
    return sorted(findings, key=lambda f: (_KIND_ORDER[f.kind], f.code, f.subjects, f.message))


def mechanical_failures(
    scenarios: list[Scenario],
    repo_root: Path = REPO_ROOT,
    exceptions: list[ScreeningException] | None = None,
) -> list[str]:
    return [f.message for f in mechanical_findings(scenarios, repo_root, exceptions) if f.kind == FAILURE]
