# 01 — Scenario Authoring Protocol

| Field | Value |
|---|---|
| Protocol version | scenario_v1 (draft 1) |
| Document | 01_authoring_protocol.md |
| Document version | 1 (draft) |
| Status | **DRAFT — NOT APPROVED** |
| Drafted on | 2026-11-08 |
| Source of decisions | `docs/stage_reports/owner_decision_ledger.md` (the sections named below) |

**Legend.** `[APPROVED]` is a rule the owner approved, as recorded in the ledger. `[CODE]` is behavior enforced today by repository code, described from reading the code, not from a test run. `[DRAFTED]` is procedural wording newly drafted in Stage 4J.1; it is **not** owner-approved. `[PENDING]` is undecided, with the stage that decides it. This document is a draft. It is not protocol approval, a design freeze, a scenario freeze or permission to run anything.

## 1. Purpose and scope

Project: "Provenance Laundering in Multi-Agent LLM Networks: Testing Repetition, Independent Corroboration, and Belief Formation."

This document sets the rules for authoring the synthetic scenarios used in the receiver experiment.

The experiment concerns **receiver belief formation under nominally stated source labels**. A receiver model reads messages that name sources and reports what it believes. The experiment does **not**:

- establish that nominally distinct roots reflect substantively independent acquisition;
- test sender authentication; or
- test evidence verification, because the evidence document is withheld from the receiver (`evidence_visible_to_receiver` is `false` in `configs/receiver_experiment.json`).

Nominally distinct roots can agree on the same wrong value. In the false-world scenarios, accepting a false claim is therefore not necessarily a process error.

## 2. Design context

`[CODE]` (`configs/receiver_experiment.json`, read, not run): six conditions.

| Condition | Messages | Roots |
|---|---|---|
| C0 | 0 | 0 |
| C1 | 1 | 1 |
| C2 | 2 | 1, repeated |
| C3 | 4 | 1, repeated |
| C4 | 2 | 2, nominally distinct |
| C5 | 4 | 4, nominally distinct |

- Primary contrasts: C4−C2 and C5−C3. Secondary contrasts: C2−C1 and C3−C1.
- Two models, two prompt variants (`neutral`, `source-aware`), temperature 0.
- `[APPROVED]` (ledger, Group 5): one repetition; `neutral` is the primary variant; the source-aware variant is outside the primary analysis family.
- Four message-template rotations of one scenario are pseudo-replicates, not independent scenarios.
- `[PENDING]` The analysis plan, `MEANINGFUL_EFFECT_THRESHOLD` and `C0_TOLERANCE` are outside this document. They are decided before any pilot results are examined.

## 3. Scenario families and counts

- `[APPROVED]` (ledger, Group 1 and Group 3): the existing ten scenarios form five matched true/false pairs. They belong to the **pilot family** and use the `AUTHOR_CHECKED_ONLY` pathway. They cannot be described as independently reviewed and cannot satisfy confirmatory acceptance.
- `[APPROVED]` Revised versions of pilot-family scenarios remain in the pilot family. No pilot scenario is reused in the confirmatory set.
- `[APPROVED]` Confirmatory family: target 15 accepted matched pairs (30 scenarios), at most 20 authored pairs (40 scenarios). Acceptance rests on pre-specified scenario criteria and review outcomes, never on model results. The target is not a power guarantee.
- `[APPROVED]` The pair-review order is fixed before acceptance outcomes are reviewed. Pairs are accepted in that order until 15 eligible pairs are accepted. Authoring stops at 20 authored pairs. With fewer than 15 accepted, work stops and returns to the owner. Thresholds are not lowered to reach the target, and pairs are not chosen on model results or observed effects. Surplus pairs after 15 are not used.
- `[APPROVED]` Pilot cohort: complete matched pairs only, at least four eligible pairs, fixed and recorded before execution, up to the five existing pairs. `hist` joins only after it is corrected and re-checked.
- `[APPROVED]` Authoring timing: pilot-family scenarios are authored, checked against the approved rules and frozen before pilot execution. They need no independent review for the restricted pilot pathway. Confirmatory scenarios are authored, independently reviewed and frozen before confirmatory execution.
- `[PENDING]` How a pilot-family content freeze is recorded (for example by file hashes) is not yet decided (`FREEZE`, before Stage 4J.2).

## 4. Domains

`[APPROVED]` (ledger, Group 2, `DOMAIN_LIST`): five existing pairs, one per domain. This classifies the pairs. It does not approve their scores or validate their evidence.

| Domain | Pair | Scenarios | Inclusion criterion |
|---|---|---|---|
| Business: headcount at an organisational event | `biz` | biz-a, biz-b | A count of people at a dated organisational event, measured directly by independent observation methods, with no company-produced records |
| Geography: physical measurement of a natural feature | `geo` | geo-a, geo-b | A single physical measurement of a named natural feature under a stated survey condition |
| History: dating a documented event | `hist` | hist-b, hist-a | A calendar year assigned to a documented event under a stated calendar convention, from period witness documents |
| Science: event count in a defined observation window | `sci` | sci-a, sci-b | A count of detections meeting a stated threshold rule in a defined interval |
| Software: file count of a published artifact | `sw` | sw-b, sw-a | A count of files in a published release archive under a stated counting rule |

Restrictions: one pair per domain; no domain-level statistical comparisons; no claim that the pairs represent their wider domains; no domain quotas or targets are implied for future or confirmatory scenarios. All five domains share one numeric-claim, direct-observation structure, and that limitation must be disclosed with any result. `[PENDING]` Confirmatory domains and pair counts need a separate owner decision.

## 5. Scenario construction rules enforced today `[CODE]`

From reading `src/maps/schemas.py` and `src/maps/scenarios.py` (schema version `2.1-draft`). This describes the code. It is not a validation result.

**Per scenario.**
- Exactly four communication roots and four message templates. Templates are unique.
- Every root is synthetic, asserts the claim, has acquisition kind `direct_observation`, follows the standard procedure, does not read another root's output, and has a method able to measure the exact claimed quantity.
- Roots differ in root id, stated origin, acquisition process, operator id and instrument id. Their `upstream_ids` are disjoint and no root lists another root as upstream.
- All roots share one quality tier. Stated origins share one form (same final word) and must not contain credibility terms (a fixed list in the schema, for example "official", "survey", "archive").
- The evidence document type must differ from every root's artifact type.
- Each message (and the claim text) contains the asserted value exactly once, no other numeral except those listed in `context_numbers`, and none of the fixed authority phrases (for example "according to", "verified", "official").
- A shared-factor analysis is required and must name the inherent shared subject.
- A claim with an event date requires a calendar convention.
- Evidence must exist and be labelled synthetic. The ground-truth value equals the asserted value if and only if the claim is true.
- Status ladder: `draft`, `author_checked`, `independently_checked`, `frozen`. A scenario's status may not exceed its evidence verification status. `independently_checked` and `frozen` currently require a complete review record and `independence_confirmed = true`. `frozen` also requires an evidence SHA-256. `[PENDING]` Stage 4J.2 is to separate content freeze from review independence (owner-approved direction, recorded in the ledger, not implemented).

**Per pair** (`load_scenario_dir`, `check_pair_matched`).
- Each `pair_id` has exactly one true and one false scenario.
- The members match on domain, attribute, calendar convention, and on each root's stated origin, acquisition process, instrument class, artifact type and quality tier. If an event date exists, both members need one and the weekdays must match.
- The evidence file must open with the label "SYNTHETIC DOCUMENT", contain the ground-truth value, and contain the asserted value if and only if the scenario is true (a coarse text-containment check).

## 6. Approved construction rules

**False value** `[APPROVED]` (`FALSE_VALUE_RULE`, `HISTORICAL_YEAR_THRESHOLD`).
- The false value uses the same format as the true value, avoids extreme or obviously implausible values, and its direction is balanced across pairs.
- Ratio-scale quantities (counts and physical measurements): compare the false value with the **paired true scenario's value**, and keep it within a factor of two. Direction balance is assessed against the paired true value.
- Calendar years and other non-ratio values: no factor-of-two test. Years are never compared by ratio. For calendar years the maximum absolute difference between the paired true and false year is **50 years**, an owner-selected protocol threshold, not an empirically established one.
- The rule is fixed before authoring. For the existing ten, which were not authored under it, it is a scoring check, and they must not be described as originally authored under it.

**Length tolerances** `[APPROVED]` (`LENGTH_TOLERANCES`).
- Each scenario's four templates must each be within ±15% of that scenario's four-template mean character length, applied to both members of every pair.
- Corresponding templates (same list position) across a pair must satisfy `abs(a − b) / ((a + b) / 2) ≤ 0.15`.
- Evidence length must stay within ±10% inside a matched pair. A pair outside tolerance is revised before it counts.

**Cue checking** `[APPROVED]` (`MACHINE_CUE_CHECK = NONE`). No automated cue detector is added beyond the schema's lexical filters (section 5). Cue detection depends on the author's non-blind self-check, so some cue risks may remain undetected. Reports must say so.

## 7. Drafted authoring workflow `[DRAFTED]`

This section is newly drafted procedural wording and is not owner-approved.

1. **Eligibility.** A scenario concerns a synthetic entity and a measurable quantity observed directly. It must not depend on world knowledge a receiver could look up.
2. **Order of work.** Fix the quantity definition, calendar convention and domain criterion first. Then fix the true value, then the false value by the rule in section 6, then the evidence document, then the four roots, then the four message templates.
3. **Paraphrase and interchangeability.** The four templates must state the same content so that any template may be used for any message slot. Differences are limited to wording and word order.
4. **Ambiguity.** Any ambiguity found is recorded in the decision log and removed by revising the quantity definition or wording, not by explaining it to the receiver.
5. **Decision log.** Each authoring action that changes a scenario (creation, revision, rejection) is recorded with the date, the scenario id and the reason, in an append-only log (see document 06).
6. **Self-check.** The author's check of the existing ten is recorded as `AUTHOR_CHECKED_ONLY` (document 05).

## 8. Known revision triggers (not scored)

`[APPROVED]` rules applied to values recorded in the ledger at drafting time. No scenario has been scored and none has passed the full rubric.

- `hist`: the false year differs from the paired true year by 158 years against the 50-year maximum, so the pair must be revised and re-checked. Its templates also deviate from their mean by more than 15%.
- The other four pairs: further checks (same format, extremes, templates, evidence length) are unverified.

## 9. Pending items

| Item | Status | Decided in |
|---|---|---|
| Evidence-length formula (how "±10%" is measured) | `[PENDING]` | Before Stage 4J.3 |
| Direction-balance measure | `[PENDING]` | Before Stage 4J.3 |
| "Avoid extremes" test | `[PENDING]` | Before Stage 4J.3 |
| Name-collision check procedure (the field is `pending` in every scenario record) | `[PENDING]` | Not yet assigned to a stage |
| Confirmatory domains and counts per domain | `[PENDING]` | Separate owner decision |
| `SCHEMA_EXTENSION` | `[PENDING]` | Before Stage 4J.2 |
