# 05 — Review and Adjudication

| Field | Value |
|---|---|
| Protocol version | scenario_v1 (draft 1) |
| Document | 05_review_and_adjudication.md |
| Document version | 1 (draft) |
| Status | **DRAFT — NOT APPROVED** |
| Drafted on | 2026-11-08 |
| Source of decisions | `docs/stage_reports/owner_decision_ledger.md` (Group 1, Group 3, Group 4 and the schema-lifecycle direction) |

Legend: `[APPROVED]` owner-approved as recorded in the ledger; `[DRAFTED]` newly drafted in Stage 4J.1 and not owner-approved; `[PENDING]` undecided. This document is a draft and not protocol approval.

## 1. Roles `[APPROVED]`

- A single researcher is currently available. The owner is the sole author and reviewer. No independent reviewers and no separate adjudicator are currently available.
- External reviewer recruitment may be considered later. No reviewer has been recruited, and none is named here.

## 2. Two review pathways `[APPROVED]`

| Pathway | Who reviews | Label | May satisfy |
|---|---|---|---|
| Solo (pilot) | The owner, as a structured self-check | `AUTHOR_CHECKED_ONLY` | The restricted pilot pathway for the existing ten scenarios only |
| Independent | Reviewers separate from the author | Independent review | Confirmatory acceptance (together with the other approved conditions) |

- Independent reviewers record their scores before discussion.
- Solo checks cannot satisfy confirmatory acceptance.
- No self-adjudication is presented as independent adjudication.
- The existing ten scenarios cannot qualify as independently reviewed.

## 3. Stages and what each reviewer sees

The four stages are fact, cue, pair and independence (checklists in document 03).

| Stage | Reviewer sees | Reviewer must not see |
|---|---|---|
| Fact | Scenario record and evidence document | Truth label, answer key |
| Cue | Message templates and stated origins | Evidence, truth label, pair partner |
| Pair | Both pair members | Truth label, answer key |
| Independence | Roots, processes, shared-factor list | Truth label, answer key |

`[APPROVED]` (custody) External reviewers receive only the blinded package (`data/review/blinded`) and never the answer key, truth labels or other unblinded material. The stage-by-stage separation above is `[DRAFTED]`. It is not owner-approved and depends on exports that do not yet exist (the current export covers the first stage only, Stage 4J.4).

## 4. Scoring and outcomes

- Criteria, thresholds and the lowest-score gate are in document 02.
- `[APPROVED]` A failure or inadequate score means revision or rejection. Thresholds are never weakened.
- `[APPROVED]` The pilot path: the owner scores all ten existing scenarios against the existing rubric with unchanged thresholds, labels results `AUTHOR_CHECKED_ONLY` and reports failures transparently.
- `[APPROVED]` Acceptance of scenarios rests on pre-specified criteria and review outcomes, never on model results.

## 5. Adjudication

- `[APPROVED]` No separate adjudicator exists. Nothing the owner does alone is called independent adjudication.
- `[DRAFTED]` For independent review, an adjudicator who did not author the scenario and did not review it at the stages in dispute decides when reviewers' scores differ by 2 or more points on a criterion or when any reviewer scores 0. This trigger is the earlier decision-brief default and is **not** owner-approved. It depends on the scoring scale (document 02, `[PENDING]`).
- `[DRAFTED]` An adjudicator's decision is recorded with the scores that preceded it. The scores recorded before discussion are never overwritten.

## 6. Accepting, revising and rejecting `[DRAFTED]` unless noted

Not owner-approved except where marked.

1. **Accept:** every criterion meets its threshold.
2. **Revise:** a criterion misses its threshold and the cause can be fixed without changing the scenario's purpose. The revised scenario is reviewed again from the start `[DRAFTED]`. (That failures require revision or rejection is `[APPROVED]`.)
3. **Reject:** the cause cannot be fixed within the pair's domain criterion. A rejected pair is replaced, not edited to pass.
4. `[APPROVED]` Confirmatory family: pairs are reviewed in an order fixed beforehand and accepted until 15 are accepted. Authoring stops at 20 pairs. With fewer than 15 accepted, work stops and returns to the owner.
5. `[APPROVED]` Revised versions of pilot-family scenarios stay in the pilot family and are never reused as confirmatory.

## 7. Review records and freeze

- The current record holds a reviewer, a blindness flag, a review date and an `independence_confirmed` flag. `independently_checked` and `frozen` statuses currently require a complete record with `independence_confirmed = true`.
- `[APPROVED]` design direction, **not implemented**: content freeze and review independence are represented separately. A pilot-family scenario may be content-frozen after author checks, keeps `AUTHOR_CHECKED_ONLY` status and `independence_confirmed = false`, and is never shown as independently reviewed. A confirmatory scenario needs a complete independent-review record before a confirmatory freeze. `independence_confirmed` is never set automatically. Contradictory combinations are rejected. Implementation is Stage 4J.2, which is not authorized.
- `[PENDING]` Whether the original `FREEZE` wording ("only after review and adjudication, with hashes") is replaced by two freezes (pilot-family content freeze; confirmatory freeze). Not yet decided.

## 8. Pending items

| Item | Status |
|---|---|
| Scoring scale and level descriptors | `[PENDING]` |
| Adjudication trigger | `[PENDING]` approval |
| `FREEZE` definition | `[PENDING]` before Stage 4J.2 |
| `SCHEMA_EXTENSION` scope | `[PENDING]` before Stage 4J.2 |
| Stage-specific exports | `[PENDING]` Stage 4J.4 |
