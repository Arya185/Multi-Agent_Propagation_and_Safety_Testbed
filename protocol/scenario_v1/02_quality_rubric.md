# 02 — Scenario Quality Rubric

| Field | Value |
|---|---|
| Protocol version | scenario_v1 (draft 1) |
| Document | 02_quality_rubric.md |
| Document version | 1 (draft) |
| Status | **DRAFT — NOT APPROVED** |
| Drafted on | 2026-11-08 |
| Source of decisions | `docs/stage_reports/owner_decision_ledger.md` (Group 1 `REVIEW_PROCEDURE`, `PILOT_PATH_RUBRIC_SCORING`; Group 2 `RUBRIC_THRESHOLDS`) |

Legend: `[APPROVED]` owner-approved as recorded in the ledger; `[DRAFTED]` newly drafted in Stage 4J.1 and not owner-approved; `[PENDING]` undecided. This document is a draft and not protocol approval.

## 1. Criteria

`[APPROVED]` The rubric has seven criteria: **truth, manipulation, cues, provenance, pair, equivalence, ambiguity.** The ledger records their names and thresholds. It does not record their definitions.

`[DRAFTED]` The descriptions below are working paraphrases of what each criterion is meant to judge. They are not owner-approved and are to be confirmed or replaced at protocol approval.

| Criterion | Working description (drafted) |
|---|---|
| Truth | The evidence document agrees with the scenario's truth label, and the false value is wrong by construction |
| Manipulation | The roots and messages realize the intended condition structure (repeated versus nominally distinct roots) |
| Cues | Nothing in the messages or origins signals credibility or truth beyond the claim itself |
| Provenance | Each root's method and upstream artifacts support the claimed independence structure, including the shared-factor list |
| Pair | The true and false members of a pair are matched on everything except truth |
| Equivalence | The four message templates state the same content and are interchangeable |
| Ambiguity | The claimed quantity is defined precisely enough that one value is correct |

## 2. Thresholds and aggregation `[APPROVED]`

Lowest-score gate. Every scenario must score:

| Criterion group | Minimum score |
|---|---|
| Truth, manipulation, cues, provenance | at least 3 |
| Pair, equivalence, ambiguity | at least 2 |

- One score below its threshold fails the scenario, whatever the average.
- Thresholds are not weakened to make existing scenarios pass, and are not lowered to reach a sample size.
- `[DRAFTED]` The rubric does not replace the code checks listed in document 01; it adds human judgment.

## 3. Scale `[PENDING]`

The ledger fixes only minimum scores. The range of the scoring scale and the level descriptors (what a 0, 1, 2, 3 and so on mean for each criterion) are **not recorded in any owner-approved decision**. They are pending and must be settled before scoring begins. No scenario has been scored.

## 4. Who scores, and how the result is labelled

- `[APPROVED]` Existing ten scenarios (pilot path): author-scored against the existing rubric with unchanged thresholds, every result labelled `AUTHOR_CHECKED_ONLY`, failures reported transparently. Scoring is not waived because independent reviewers are unavailable.
- `[APPROVED]` The sole researcher is the author and the only reviewer at present. Cue and independence checks by the author cannot be blind. A passing self-check is weaker evidence than an independent pass.
- `[APPROVED]` Independent review needs reviewers separate from the author, who record scores before any discussion. Solo checks cannot satisfy confirmatory acceptance.

## 5. Outcomes

- `[APPROVED]` A failure, or an inadequate score, results in revision or rejection. No self-adjudication is presented as independent adjudication.
- `[DRAFTED]` A revised scenario is scored again from the start on every criterion. A rejected scenario is replaced, not edited to pass.
- `[DRAFTED]` Disagreement trigger for independent review: an adjudicator is called when two reviewers' scores on a criterion differ by 2 or more points or when any reviewer gives 0. This default comes from the earlier decision brief and is **not** part of the owner-approved `REVIEW_PROCEDURE` wording. It depends on the scale (section 3) and is pending approval.

## 6. Pending items

| Item | Status |
|---|---|
| Scale range and level descriptors | `[PENDING]` before scoring |
| Final criterion definitions | `[PENDING]` at protocol approval |
| Disagreement trigger for adjudication | `[PENDING]` approval of the drafted default |
