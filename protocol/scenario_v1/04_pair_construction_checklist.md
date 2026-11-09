# 04 — Pair Construction Checklist

| Field | Value |
|---|---|
| Protocol version | scenario_v1 (draft 1) |
| Document | 04_pair_construction_checklist.md |
| Document version | 1 (draft) |
| Status | **DRAFT — NOT APPROVED** |
| Drafted on | 2026-11-08 |
| Source of decisions | `docs/stage_reports/owner_decision_ledger.md` (Group 2 `FALSE_VALUE_RULE`, `HISTORICAL_YEAR_THRESHOLD`, `LENGTH_TOLERANCES`, `MACHINE_CUE_CHECK`) |

Legend: `[APPROVED]` owner-approved as recorded in the ledger; `[CODE]` enforced today by repository code, from reading the code and not from a test run; `[HUMAN]` a check only a person can do today; `[PENDING]` undecided or not yet implemented. This document is a draft and not protocol approval.

## 1. How to use this checklist

A matched pair is one true and one false scenario that differ in truth and in nothing else the design controls. For each item, record pass, fail or not assessed. Tick marks in this document are not results. No scenario has been checked against it.

## 2. Checks enforced by code today `[CODE]`

Enforced when a scenario directory is loaded (`src/maps/schemas.py`, `src/maps/scenarios.py`). They run only if the loader is executed. Stage 4J.1 did not execute it.

| # | Check | Enforced by |
|---|---|---|
| 1 | Exactly one true and one false scenario per `pair_id` | `load_scenario_dir` |
| 2 | Same domain and attribute | `check_pair_matched` |
| 3 | Same calendar convention | `check_pair_matched` |
| 4 | Each root position matches on stated origin, acquisition process, instrument class, artifact type and quality tier | `check_pair_matched` |
| 5 | If an event date exists, both members have one and the weekdays match | `check_pair_matched` |
| 6 | Evidence file opens with "SYNTHETIC DOCUMENT", contains the ground-truth value, and contains the asserted value if and only if the scenario is true (coarse text containment) | `check_evidence_file` |
| 7 | Four unique templates, each with the asserted value exactly once and no other numeral outside `context_numbers` | `Scenario` validators |
| 8 | No authority phrase in messages; no credibility term in stated origins | `Scenario` validators |
| 9 | Evidence document type differs from every root's artifact type | `Scenario` validators |

## 3. Checks that need a person today `[HUMAN]`

| # | Check | Rule |
|---|---|---|
| 10 | Same format for the true and false value | `[APPROVED]` false-value rule |
| 11 | Ratio-scale values: false value within a factor of two of the paired true value | `[APPROVED]` |
| 12 | Calendar years: absolute difference from the paired true year at most 50 years | `[APPROVED]` |
| 13 | No extreme or obviously implausible false value | `[APPROVED]` rule; the operational test is `[PENDING]` |
| 14 | Direction of the false value balanced across pairs, measured against the paired true value | `[APPROVED]` rule; the measure is `[PENDING]` |
| 15 | Each scenario's four templates each within ±15% of the scenario's four-template mean length | `[APPROVED]` |
| 16 | Corresponding templates across the pair satisfy `abs(a − b) / ((a + b) / 2) ≤ 0.15` | `[APPROVED]` |
| 17 | Evidence length within ±10% inside the pair | `[APPROVED]` rule; the formula is `[PENDING]` |
| 18 | Templates are interchangeable paraphrases of one content | Drafted in document 01, section 7 (not owner-approved) |
| 19 | Same quantity definition wording across the pair, apart from the entity | Drafted (not owner-approved) |
| 20 | Name collision check completed (the record field is `pending`) | `[PENDING]` procedure |

Items 15 to 17 are not enforced by code today. `check_pair_matched` does not compare lengths. Stage 4J.3 is the stage planned for mechanical length and false-value checks.

## 4. Order of construction `[DRAFTED]`

Not owner-approved. Fix the quantity definition and calendar convention. Choose the true value. Choose the false value by items 10 to 14. Write the evidence documents, keeping their lengths within tolerance. Write the roots in matching order. Write the four templates and check items 15 and 16. Run the code checks. Record the author's self-check.

## 5. Pending items

| Item | Status | Decided in |
|---|---|---|
| Evidence-length formula | `[PENDING]` | Before Stage 4J.3 |
| Direction-balance measure | `[PENDING]` | Before Stage 4J.3 |
| "Avoid extremes" test | `[PENDING]` | Before Stage 4J.3 |
| Name-collision procedure | `[PENDING]` | Not yet assigned |
