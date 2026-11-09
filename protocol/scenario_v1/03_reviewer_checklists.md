# 03 — Reviewer Checklists

| Field | Value |
|---|---|
| Protocol version | scenario_v1 (draft 1) |
| Document | 03_reviewer_checklists.md |
| Document version | 1 (draft) |
| Status | **DRAFT — NOT APPROVED** |
| Drafted on | 2026-11-08 |
| Source of decisions | `docs/stage_reports/owner_decision_ledger.md` (Group 1 `REVIEW_PROCEDURE`, `INDEPENDENT_REVIEW_AND_SOLO_FALLBACK_RULE`; Group 4 `ANSWER_KEY_CUSTODY`) |

Legend: `[APPROVED]` owner-approved as recorded in the ledger; `[DRAFTED]` newly drafted in Stage 4J.1 and not owner-approved; `[PENDING]` undecided. This document is a draft and not protocol approval.

## 1. Stages

`[APPROVED]` Review uses four stages: **fact, cue, pair and independence.** Solo execution by the owner is a documented self-check recorded as `AUTHOR_CHECKED_ONLY`. It is not independent review.

`[DRAFTED]` The checklists below are drafted from the five reviewer questions in the existing blinded-package README (`data/review/blinded/README.md`) and from the rules in document 01. They are not owner-approved.

## 2. Fact stage — evidence and measurement

Reviewer sees: the scenario record and its evidence document, with the truth label absent.

- [ ] Does the evidence document support or contradict the claim?
- [ ] Can each root's method measure the exact quantity as defined?
- [ ] Is the quantity definition precise enough that one value is correct?
- [ ] Is the calendar convention stated wherever a date or year is involved?

## 3. Cue stage — messages only

Reviewer sees: message templates and stated origins only. No evidence, no truth label, no pair partner.

- [ ] Does any message or stated origin signal credibility or authority beyond the claim?
- [ ] Does any template differ from the others in content, not only wording?
- [ ] Does any wording carry an unintended clue to truth?
- [ ] Are the templates of similar length (see document 01, section 6)?

The code filters in document 01 (section 5) are not a substitute for this check. No automated cue detector is added (`MACHINE_CUE_CHECK = NONE`).

## 4. Pair stage — matched pair

Reviewer sees: both members of a pair, truth label absent.

- [ ] Are the members matched on domain, attribute and calendar convention?
- [ ] Do the roots match on origin form, acquisition process, instrument class, artifact type and quality tier?
- [ ] Do the two false/true values satisfy the false-value rule (document 01, section 6)?
- [ ] Is the evidence document of comparable length and form in both members?

## 5. Independence stage — roots

Reviewer sees: the four roots, their processes and the shared-factor list.

- [ ] Are the four roots genuinely independent, beyond differing identifiers?
- [ ] Is the shared-factor list complete?
- [ ] Is any root derived from another root's output or from a shared record?
- [ ] Is the reasoning behind the independence assessment recorded?

The result is the reviewer's judgment about the synthetic construction. It does not show that nominally distinct roots in the experiment reflect real independent acquisition.

## 6. Conditions of review

- `[APPROVED]` Independent reviewers record their scores **before** discussion.
- `[APPROVED]` Reviewers receive only the blinded package (`data/review/blinded`). They receive no answer key, truth label or other unblinded material.
- `[DRAFTED]` Each reviewer records answers in the reviewer form and does not consult other reviewers until scores are recorded.
- `[DRAFTED]` **Conflict-of-interest declaration.** Before reviewing, each reviewer states whether they authored, edited or received information about the truth labels of any scenario they review, and states any relationship that could bias the review. A reviewer who declares such a conflict does not review that scenario independently.
- `[DRAFTED]` Required evidence of a review: reviewer identity, date, the stage, answers per checklist item, scores per criterion (scale pending, document 02) and any ambiguity or clue noted.
- `[APPROVED]` The sole researcher currently performs all checks. Those checks are labelled `AUTHOR_CHECKED_ONLY` and cannot be described as blind or independent.

## 7. Pending items

| Item | Status |
|---|---|
| Reviewer form layout and fields | `[PENDING]` Stages 4J.2 and 4J.4 (review-record extension and exports) |
| Message-only and pair-comparison exports (the current export covers the first stage only) | `[PENDING]` Stage 4J.4 |
| Reviewer recruitment | `[PENDING]` Recruitment may be considered later; no reviewer has been recruited |
| Source note: the existing blinded README ends "Do not open the answer key until all items are reviewed", which implies reviewers may later receive it. Under the approved custody rule external reviewers receive no answer key. | `[PENDING]` Reconcile when exports are revised (Stage 4J.4). The README is not modified by Stage 4J.1. |
