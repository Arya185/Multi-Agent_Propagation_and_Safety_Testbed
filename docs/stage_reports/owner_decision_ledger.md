# MAPS Owner Decision Ledger

Project: "Provenance Laundering in Multi-Agent LLM Networks: Testing Repetition, Independent Corroboration, and Belief Formation."

Created: Stage 4I.29, at the owner's explicit instruction, as the first canonical repository record of owner decisions.

## How to read this ledger

- **Owner-approved** means the owner stated the decision in a message to the assistant. The statements were relayed through the Claude Code conversation, not signed here. `APPROVER_NAME` and `APPROVAL_DATE` are Group 4 fields and are NOT filled. The conversation transcript is `/Users/aryapatel/.claude/projects/-Users-aryapatel-arya-Programming-MAPS/b24f0ddb-cd85-4df6-a732-b8e2ecd567ff.jsonl`.
- A decision approves a rule. It is not evidence that any scenario passes the rule, and it is not an authorization to implement or run anything.
- Recommendations that were not approved are not recorded as decisions. Where an earlier draft wording was superseded, only the approved wording is given, and the supersession is noted.
- Nothing in this ledger is implemented. No scenario has been scored, validated or independently reviewed.

## Standing scientific safeguards

- Nominally distinct source roots do not prove independent source acquisition.
- The study tests receiver belief formation under nominal source labels. It does not test sender authentication or evidence verification.
- The sign-flip test is exact only under joint sign-invariance, not design-based, and not an isolating test of source independence. The mean pair difference is the descriptive estimand.
- No power claim is made. Thresholds are never weakened to reach a sample size.
- Pilot and confirmatory scenario families are separate.
- `AUTHOR_CHECKED_ONLY` is not independent review and cannot satisfy confirmatory acceptance.
- Conclusions are conditional on the authored scenarios, models, prompts and temperature 0.

---

## Group 1 — CLOSED (7 of 7 decided)

| Field | Approved wording | Status | Source stage |
|---|---|---|---|
| ROLES | `OWNER AMENDMENT: Single researcher currently available. The owner is the sole author and reviewer. No independent reviewers or separate adjudicator are currently available.` | APPROVED (owner amendment) | Stage 4I.20 (v2.4.04) |
| EXISTING_TEN | `OWNER AMENDMENT: AUTHOR_CHECKED_ONLY pilot pathway permitted for the existing ten scenarios. These scenarios cannot qualify as independently reviewed or satisfy confirmatory acceptance requirements.` | APPROVED (owner amendment) | Stage 4I.20 (v2.4.04) |
| SOLO_FALLBACK | `AUTHOR_CHECKED_ONLY` | APPROVED | Stage 4I.24 (v2.4.08) |
| INDEPENDENT_REVIEW_AND_SOLO_FALLBACK_RULE | Independent review requires reviewers separate from the author. Solo checks remain author-checked and cannot satisfy confirmatory acceptance. Independent reviewers record scores before discussion. | APPROVED | Stage 4I.24 (v2.4.08) |
| REVIEW_PROCEDURE | Retain the four-stage fact, cue, pair and independence rubric. Solo execution is a documented self-check. Failures require revision or rejection. No self-adjudication is presented as independent adjudication. | APPROVED | Stage 4I.24 (v2.4.08) |
| EXTERNAL_REVIEWER_RECRUITMENT_LATER | YES — recruitment may be considered later. | APPROVED | Stage 4I.24 (v2.4.08) |
| PILOT_PATH_RUBRIC_SCORING | AUTHOR-SCORED WITH UNCHANGED THRESHOLDS. Score all ten existing scenarios, label them `AUTHOR_CHECKED_ONLY`, and report failures transparently. | APPROVED | Stage 4I.24 (v2.4.08) |

Archival notes:

- The five Stage 4I.24 fields were approved by the owner's reply `ACCEPT ALL FIVE GROUP 1 RECOMMENDATIONS` to the wording shown above. Longer draft wordings in Stages 4I.21–4I.23 are superseded by it.
- Recovery of all seven fields is complete.
- Cue and independence checks by the sole author cannot be blind. A self-check pass is weaker evidence than an independent pass.

---

## Group 2 — scenario design and domains (6 of 6 decided)

### Fields approved in Stage 4I.25

| Field | Original approved rule | Status |
|---|---|---|
| RUBRIC_THRESHOLDS | Lowest-score gate. Every scenario needs at least 3 on truth, manipulation, cues and provenance, and at least 2 on pair, equivalence and ambiguity. One score below threshold fails the scenario regardless of its average. Thresholds are not weakened to make existing scenarios pass. | APPROVED, unchanged |
| LENGTH_TOLERANCES | Templates within ±15%. Evidence length within ±10% inside a matched pair. A pair outside tolerance is revised before it counts. | APPROVED; measurement clarified below |
| FALSE_VALUE_RULE | False value uses the same format as the true value, stays within a factor of 2 of the true value, avoids extreme or obviously implausible values, and its direction is balanced across pairs. It is a scoring check for the existing ten, which were not authored under this rule. The existing scenarios were not originally authored under it. | APPROVED; amended below |
| MACHINE_CUE_CHECK | `NONE`. No automated cue detector is added beyond the schema's existing lexical filters. Cue detection depends on the author's non-blind self-check, and some cue risks may go undetected. | APPROVED, unchanged |
| AUTHORING_TIMING | `BEFORE_PILOT`. All scenarios are authored, reviewed and frozen before the pilot, and the pilot waits for the complete Stage 4J.1–4J.7 path. | APPROVED; clarified in Stage 4I.29 below |

### Decisions and amendments approved in Stage 4I.28

| Field | Final effective rule | Status |
|---|---|---|
| DOMAIN_LIST | Five existing matched pairs in the pilot-family set only: `biz` (biz-a, biz-b), `geo` (geo-a, geo-b), `hist` (hist-b, hist-a), `sci` (sci-a, sci-b), `sw` (sw-b, sw-a). One pair per domain. No domain-level statistical comparisons. No claim of domain representativeness. No future or confirmatory domain quotas. All five share a numeric-claim, direct-observation structure. This classifies the pairs. It does not approve their rubric scores or validate their evidence. | APPROVED |
| FALSE_VALUE_RULE (amendment) | **Ratio-scale quantities** (counts and physical measurements; in the existing set `biz`, `geo`, `sci`, `sw`): compare the false value with the paired true scenario's value, factor-of-two limit, same-format and avoid-extremes requirements retained, direction balance assessed relative to the paired true value. **Calendar years and other non-ratio-scale values:** no factor-of-two test, and a domain-appropriate absolute-difference or plausibility criterion is used. Years are never compared by ratio. The amendment supersedes the original baseline wording. The false value's own ground-truth value is not the comparison baseline. | APPROVED (domain-aware amendment) |
| HISTORICAL_YEAR_THRESHOLD | Maximum acceptable absolute difference between the paired true and false calendar years is 50 years. This is an owner-selected protocol threshold, not an empirically established scientific threshold. | APPROVED |
| LENGTH_TOLERANCES (clarification) | Within each scenario, the mean character length of its four templates is calculated, and each template must be within ±15% of that mean, applied independently to both members of every pair. Across a matched pair, corresponding templates are compared by list position and must satisfy `abs(a - b) / ((a + b) / 2) <= 0.15`. Evidence length keeps the ±10% within-pair tolerance. | APPROVED (clarified) |

### AUTHORING_TIMING clarification (Stage 4I.29, owner-approved operational amendment)

- **Pilot-family scenarios:** all must be authored, checked against the approved rules and frozen before pilot execution. The existing ten may use the approved `AUTHOR_CHECKED_ONLY` pathway. They need no independent review to qualify for the restricted pilot pathway.
- **Confirmatory scenarios:** must be authored, independently reviewed and frozen before confirmatory execution. Independent reviewers must be separate from the author. Self-review is never counted as independent review or adjudication. Confirmatory execution is blocked until the independent-review requirement is satisfied.
- The clarification allows a qualifying pilot to proceed without representing the existing scenarios as independently reviewed. It does not waive confirmatory review.

---

## Group 3 — pilot and confirmatory counts (6 of 6 decided; Stage 4I.29)

| Field | Approved rule | Status |
|---|---|---|
| SCENARIO_COUNT | Target: 15 accepted matched pairs (30 scenarios). Maximum authored: 20 matched pairs (40 scenarios). Acceptance is based on pre-specified scenario criteria and review outcomes, never on model results. No claim that 15 pairs guarantee statistical power. Power and the inferential procedure need separate justification in the analysis plan. | APPROVED |
| CONFIRMATORY_SURPLUS_RULE | Establish the pair-review order before reviewing acceptance outcomes. Accept pairs in that order until 15 eligible pairs are accepted. Stop when 20 pairs have been authored. If fewer than 15 are accepted, stop and return to the owner. Do not lower thresholds to meet the target. Do not select pairs on model results or observed effects. Do not include surplus pairs after the target of 15 is reached. | APPROVED |
| MINIMUM_PILOT_COHORT_RULE | At least 4 complete eligible matched pairs are required for the pilot. This is a feasibility threshold, not a power claim. If fewer than four pairs qualify, the pilot is not run, and the owner receives the reasons. | APPROVED |
| PILOT_SCENARIO_POLICY | Use only existing pilot-family pairs that satisfy the approved rules after revision and checking. They stay labelled `AUTHOR_CHECKED_ONLY`. Author checks are not described as independent review. Revised versions of existing pilot-family scenarios stay in the pilot family. No pilot scenario is reused in the confirmatory set. | APPROVED |
| PILOT_COHORT | Complete matched pairs only. Never one member of a pair without the other. The exact cohort is fixed and recorded before execution. Use all eligible existing pilot-family pairs, up to the five existing pairs. Include `hist` only after its false-year value and template-length problems are corrected and the pair is re-checked. If fewer than four pairs qualify, the pilot stays blocked. | APPROVED |
| PILOT_REPETITIONS | One repetition per scenario at temperature 0. Prompt rotations and model/condition combinations are experimental design factors, not independent scenario replicates. Repetitions are not increased without a separate owner decision and documented rationale. | APPROVED |

---

## Group 4 — custody, directory, approval record and schema direction (Stage 4I.30)

Source stage for every entry below: Stage 4I.30. Implementation status for every entry: NOT IMPLEMENTED. Validation status for every entry: NOT VALIDATED.

### ANSWER_KEY_CUSTODY — APPROVED

- **Decision:** the project owner is the sole answer-key custodian. External reviewers may receive only the blinded review package at `data/review/blinded`. They must not receive the answer key, truth labels or other unblinded materials. Before any external reviewer is engaged, the answer key is moved outside the shared repository.
- **Rationale:** the key (`data/review/answer_key/answer_key.json`) sits inside the repository tree, so sharing or snapshotting the repository could leak it. The owner is unblinded by authorship regardless.
- **Scope:** the answer key and any shared repository snapshot, reviewer package or public artifact. The key must not be included in any of them.
- **Restrictions:** `.gitignore` alone is not sufficient protection if the key has previously been committed or otherwise exposed. The move and any history or security checks are deferred to a separately authorized stage. The key was not opened, printed or moved while recording this decision.
- **Implementation status:** NOT IMPLEMENTED. The key has not moved. Whether it appears in git history has not been checked. `git status` lists `data/` as untracked, so it is not in the current index.
- **Validation status:** NOT VALIDATED.

### PROTOCOL_DIRECTORY — APPROVED

- **Decision:** `protocol/scenario_v1/`.
- **Rationale:** a separate location for the normative Stage 4J.1 protocol documents and their manifest. This ledger remains a record in `docs/stage_reports/`.
- **Scope:** reserved for normative Stage 4J.1 protocol documents and their manifest.
- **Restrictions:** approving the directory does not authorize creating the protocol documents. Their creation belongs to Stage 4J.1, which is NOT AUTHORIZED. The directory does not exist yet.
- **Implementation status:** NOT IMPLEMENTED. **Validation status:** NOT VALIDATED.

### APPROVER_NAME — PENDING OWNER CONFIRMATION

- **Decision:** none. The exact name to appear in the final protocol approval record is to be supplied by the owner.
- **Rationale:** the name must not be inferred from git configuration, operating-system account names, repository ownership or conversation profile information.
- **Scope:** the final protocol approval record. **Restrictions:** left unfilled.
- **Implementation status:** NOT IMPLEMENTED. **Validation status:** NOT VALIDATED.

### APPROVAL_DATE — PENDING FINAL PROTOCOL APPROVAL

- **Decision:** none. The date must be the actual final protocol approval date, not the date of an intermediate governance discussion.
- **Rationale:** a premature date would misdate the approval.
- **Scope:** the final protocol approval record. **Restrictions:** the current date is not used by default.
- **Implementation status:** NOT IMPLEMENTED. **Validation status:** NOT VALIDATED.

### Schema lifecycle separation — OWNER-APPROVED DESIGN DIRECTION, IMPLEMENTATION DEFERRED TO STAGE 4J.2

- **Decision (design direction only):** content-freeze status and review independence are represented separately.
  - **Pilot-family scenarios** may become content-frozen after the required author checks. They retain `AUTHOR_CHECKED_ONLY` review status and `independence_confirmed = false`, and are never represented as independently reviewed.
  - **Confirmatory scenarios** must be reviewed by reviewers separate from the author and need a complete independent-review record before qualifying for confirmatory freeze. They cannot be accepted through the author-only pathway.
  - **Stage 4J.2 schema requirements:** a frozen pilot-family scenario is representable without claiming independent review. A frozen confirmatory scenario still requires valid independent-review evidence. The independent-review requirement is not weakened or bypassed. `independence_confirmed` is never set to true automatically. Review status, content-freeze status and confirmatory eligibility stay distinguishable. Validation rules reject contradictory combinations.
- **Rationale:** the current `src/maps/schemas.py` (`_status_gates`, lines 263-277) requires a `frozen` scenario to have a complete review record and `independence_confirmed is True`. That conflicts with the approved `AUTHOR_CHECKED_ONLY` pilot pathway. It resolves the open question recorded in Stage 4I.29.
- **Scope:** design only. **Restrictions:** `src/maps/schemas.py` is not modified, and Stage 4J.2 remains NOT AUTHORIZED.
- **Implementation status:** NOT IMPLEMENTED. The schema conflict still exists in the repository and is not fixed. **Validation status:** NOT VALIDATED.

---

## Group 5 — confirmatory analysis decisions (Stage 4I.31) — PARTIALLY RECORDED — OWNER INPUT REQUIRED

**Authority.** The owner delegated these decisions for Stage 4I.31: accept the proposed defaults where they are internally coherent and consistent with Groups 1–4, accept `ROOT_COUNT_CAP = UNBOUNDED`, leave `MEANINGFUL_EFFECT_THRESHOLD` and `C0_TOLERANCE` pending explicit owner input (no numeric value is to be invented), and approve no `PS-09` or `PS-12-CONSEC` deferral until its permissibility is verified. Accepted entries below are **owner-authorized decisions under that delegation**, source stage `4I.31`.

**Status for every Group 5 entry:** implementation — decision recorded, no implementation performed. Validation — ledger consistency checked only; no experiment, code or analysis validation performed. The analysis plan is not validated by being recorded here.

**Scope.** Group 5 governs the confirmatory analysis. The pilot is descriptive and feasibility-oriented, uses `AUTHOR_CHECKED_ONLY` scenarios, and establishes neither independent review nor confirmatory eligibility.

### Accepted decisions (12)

| Field | Decision | Rationale | Restrictions and scope |
|---|---|---|---|
| INFERENTIAL_STANCE | Model-conditional inference over the authored scenarios, limited to the tested models, prompts and conditions. | Findings depend on authored scenarios, models, prompts, conditions and temperature 0. | No generalization to other models, prompts, scenarios or real-world multi-agent networks. |
| REPETITIONS | `1` | Matches the approved `PILOT_REPETITIONS = 1`. | Any increase needs a separate owner decision. Prompt rotations and model/condition combinations are not independent scenario replicates. The four prompt rotations are pseudo-replicates. |
| PRIMARY_OUTCOME | Elicited estimated independent roots. | A receiver belief-formation measure. | Does not establish actual source independence, independent acquisition, evidence authenticity or sender authentication. Nominally distinct roots may agree on the same incorrect value. |
| PRIMARY_ESTIMAND | Descriptive mean pair difference across the authored scenarios. | Describes the authored set. | Not a population effect estimate. |
| PRIMARY_TEST | Two-sided sign-flip test, conditional on joint sign-invariance. | Exact only under joint sign-invariance. | Not design-based. Does not isolate genuine source independence. Minimum attainable two-sided p-value is `2^(1-m)` for `m` non-zero paired differences. With five pairs the minimum is 0.0625 and with four pairs 0.125, so the pilot cannot produce a p-value below 0.05 with this test. |
| PRIMARY_INTERVAL | Shift-model inversion, assumptions explicitly disclosed. | Gives an interval tied to the stated shift model. | Not an exact interval for a finite mean. |
| PRIMARY_VARIANT | `neutral` | Fixes the primary analysis to one prompt variant. | The source-aware variant stays outside the primary analysis family. |
| MULTIPLICITY | Holm correction at α = 0.05 across four model-by-contrast tests (two models; contrasts C4−C2 and C5−C3). Sequential thresholds 0.0125, 0.01667, 0.025, 0.05. | Controls familywise error across the four tests. | The first Holm step needs at least eight non-zero paired differences for a two-sided sign-flip p-value to be able to reach 0.0125. Eight usable pairs does not guarantee eight non-zero pairs. |
| MISSING_DATA_RULE | Analysis-level loss tables and tipping-point analysis. | Makes sensitivity to missing episodes visible. | Describes sensitivity only. Does not repair bias or show that missingness is harmless. |
| MIN_USABLE_PAIRS | `8` | A minimum usability requirement for the confirmatory analysis. | Not a guarantee of power or inferential validity. Ties can still prevent the first Holm step from being reachable. 15 accepted confirmatory pairs is a target, not a power guarantee. **Scope (owner-approved in Stage 4I.32, implementation status DECISION RECORDED — NO IMPLEMENTATION):** `MIN_USABLE_PAIRS = 8` applies to confirmatory analysis only. It does not replace or raise the approved 4-pair pilot feasibility minimum. Eight usable pairs do not guarantee eight non-zero paired differences, are not a power guarantee, and do not guarantee that the first Holm step can be reached. |
| ROOT_COUNT_CAP | `UNBOUNDED` | A cap at four could conceal over-counting, which bears directly on the research question. | Implausibly high elicited counts are reported transparently. They are not silently truncated or winsorized. |
| PS-07 | Two retries, up to three attempts per episode. | Equals the shipped config value (`configs/receiver_experiment.json` `api.max_retries = 2`; `max_tokens = 800`, `temperature = 0.0`), which the client and the loader require to match the policy. | Retry behavior in code is not changed. Ceilings with 3 attempts per episode and 800 tokens per attempt: episodes = 24 × scenarios × repetitions. 8 scenarios: 192 episodes, 576 attempts, 460,800 tokens, 35,136 s nominal. 10 scenarios: 240 episodes, 720 attempts, 576,000 tokens, 43,920 s nominal. 30 scenarios: 720 episodes, 2,160 attempts, 1,728,000 tokens, 131,760 s nominal. Durations are nominal upper bounds at 183 s per episode, not hard limits. |

### Unresolved: owner input required (2)

| Field | Status | What the owner must supply |
|---|---|---|
| MEANINGFUL_EFFECT_THRESHOLD | PENDING OWNER INPUT | A numeric difference in mean elicited roots (unit: roots, on the mean pair difference of elicited estimated independent roots), fixed before pilot results are examined. The value must not be chosen for convenience, expected results, conventional effect-size labels or to make the study look adequately powered. No value has been set. |
| C0_TOLERANCE | PENDING OWNER INPUT | Both a C0 baseline measure and a numeric tolerance for it, fixed before pilot results are examined. Examples only, not a decision: mean elicited roots in C0, or the share of C0 episodes with an elicited count above zero. Neither measure nor tolerance has been set. |

### Unresolved: source verification of the two deferrals (2) — UNRESOLVED — NEEDS OWNER DECISION

`PS-09` is the policy `deadline_seconds`. `PS-12-CONSEC` is the policy `max_consecutive_nonfatal_errors`. Proposed disposition: defer until pilot latency and error-rate data exist.

**Result: permission for the deferral is not established, and the records conflict.** Both stay `UNRESOLVED — NEEDS OWNER DECISION`.

- **Records that propose deferral.** The v2.3.98-era decision register proposal in the conversation transcript (jsonl lines 7849, 7869, 7895, 0-based) lists both as "Deferrable: Yes, until pilot data" with rationale that they need observed latency and error rates. Line 7914 is a task prompt that lists "PS-09: DEFER UNTIL PILOT" and "PS-12-CONSEC: DEFER UNTIL PILOT" among execution decisions. These are recommendations and a task description. No explicit owner approval statement of the deferral was found.
- **Records that conflict.** The Stage 4D/4E policy records (transcript lines 6142 and 6559) define both as required policy values, and the dependency table lists "PS-09 … consecutive errors" as blocking pilot authorization ("needed for the real policy file"). The same records say typical latency "cannot be measured offline".
- **Code that requires them.** `src/maps/runs/policy_source.py` `LIMIT_FIELDS` (line 90, checks at lines 413-416) requires both `deadline_seconds` and `max_consecutive_nonfatal_errors` to be present and integers in every profile. `src/maps/runs/live_policy.py` lines 86-89 require `deadline_seconds ≥ 1` and `1 ≤ max_consecutive_nonfatal_errors ≤ planned_episodes`. A live policy cannot load without them.
- **Why this makes the deferral circular.** Observed latency and error rates come only from a live run, and a live run needs a loadable policy, which needs both values. A deferral "until pilot data" can therefore not hold for the first live run unless the owner sets provisional values or defines a staged first run.
- **What would resolve it.** An explicit owner decision to supply provisional values for the pilot only, or to define another route. No numeric value is proposed here. For reference only, the nominal worst case is 183 s per episode, 43,920 s for 240 episodes, and `PS-12` (call-error eligibility) was previously recommended, not approved, as zero tolerance for a first pilot.
- No governing protocol was modified to make a deferral permissible.

### Contradiction and consistency checks against Groups 1–4

- `REPETITIONS = 1` matches `PILOT_REPETITIONS = 1`. No conflict.
- `MIN_USABLE_PAIRS = 8` against `MINIMUM_PILOT_COHORT_RULE = 4`: no conflict, because the 8-pair minimum is confirmatory-only (approved in Stage 4I.32).
- The primary outcome, test, interval and estimand wording are consistent with the standing safeguards and with `AUTHOR_CHECKED_ONLY` pilot scope.
- The approved `AUTHORING_TIMING` clarification is not affected.
- The two numeric fields and the two deferrals are unresolved. No earlier approval was changed.

**Group 5 record status:** 12 of 16 fields recorded; 4 unresolved (2 pending numeric input, 2 pending the deferral decision).

---

## Live-policy dependency audit (Stage 4I.33) — documentation only, nothing approved here

Scope: what a loadable live policy needs, per `src/maps/runs/policy_source.py` (`LIMIT_FIELDS`, line 90; `check_scope`, line 443), `src/maps/runs/live_policy.py` (lines 64-89) and `src/maps/runs/live_executor.py`. No policy file or profile values exist in the repository, and `configs/receiver_experiment.json` holds no policy limits. Test-fixture values are synthetic and are not evidence.

### Verified existing owner decisions (previously missing from this ledger)

Source: the v2.3.82 task prompt in the conversation transcript (jsonl line 7328, 0-based). It states the owner delegated these six selections and that they are the authorized decisions for that implementation stage.

| Field | Recorded decision | Note |
|---|---|---|
| PS-08 | `strict_physical` | Described as bounded accounting, not socket-level accounting. A policy value is still required in the policy file. |
| PS-19 | `A` — retain current usage accounting | Report only. Whether the request asks the provider to include usage is unresolved and cannot be checked offline. |
| PS-06-BUDGET | `A` — no cumulative token cap | |
| PS-21 | `A` — defer per-model and per-cell limits | The consecutive-error counter stays global. |
| TIMEOUT-BACKOFF | `A` — include `timeout_s` and `backoff_s` in the design digest | Records the inclusion, not an approval of 60 s / 1.0 s as final values. |
| PR4-PROXY | `A` — disable environment-derived behavior | |

`PS-10`, `PS-14`, `PS-15`, `PS-17`, `PR4` (host) and `PS-18-STORAGE` are described as owner-approved only in a conversation summary (jsonl line 7710). The originating owner message was not re-located in this stage, so they are NOT recorded here as verified.

### Fields with no recorded owner decision (policy-related, outside Groups 1-6)

`PS-05a` (`max_episodes`), `PS-05b` (`max_request_attempts`), `PS-11` (stop on the final call), `PS-12` (`call_error` eligibility), `PS-12-4XX` (`nonfatal_4xx_statuses`), `PS-12-3XX` (`fatal_3xx`) and `PS-13` (`parse_error` eligibility). Search of the transcript found no owner approval for any of them. Their definitions are in the Stage 4D facilitation record (jsonl line 6559). Of these, `PS-05a`, `PS-05b`, `PS-12-4XX` and `PS-12-3XX` are required policy-file fields that the loader refuses to load without. `PS-11`, `PS-12` and `PS-13` have no policy field: today's code applies fixed behavior (`PS-11` ineligible, `PS-12` isolated errors keep the run eligible, `PS-13` report only), and the Stage 4D record lists them as blocking pilot authorization.

### Binding facts that affect the pilot policy

- The policy `scope.stage` must equal the config's `output.stage` (`pilot`), the scope must match the planned grid exactly, and scenario and evidence file contents are bound by SHA-256. The policy therefore cannot be produced until the pilot cohort and its scenario files are fixed, and any later scenario edit invalidates it.
- The policy digest covers the limits and the scope. `deadline_seconds` and the cohort are bound together through `planned_episodes` and `scenario_ids`.
- `planned_episodes` = 24 × scenarios × repetitions: 192 for a four-pair cohort and 240 for five pairs.
- The deadline starts when the budget wrapper is built, after the client factory and pre-run provenance (`live_executor.py` lines 35-36), and is checked between calls only (`live_budget.py` lines 264, 318-320).
- The client's worst case per call is 3 attempts × 60 s plus backoff of 1 s and 2 s, which is 183 s (`src/maps/llm_client.py` lines 90-116). `timeout_s` is per socket operation, not a total bound (`policy_source.py` docstring), so 183 s is nominal.
- Any policy stop, including one on the final call of a complete grid, makes the run ineligible (`live_executor.py` lines 69-73, 230-232).
- Subset-cohort selection is unverified: the config's `scenario_dir` holds all ten scenarios, and how a four- or five-pair subset enters the grid was not established.

### Recommendations (NOT APPROVED)

- `PS-09`: `183 × planned_episodes` has zero headroom and can end in a final-call deadline stop. `183 × (planned_episodes + 1)` adds one worst-case call of headroom. Either is a provisional pilot-only candidate that needs your approval and the final cohort.
- `PS-12-CONSEC`: `1` makes the first nonfatal error stop the run and void it, which gives zero-tolerance eligibility without a code change. It limits error-rate information from the pilot.

### Original-35 fields not placed in any of Groups 1-6

`SCHEMA_EXTENSION`, `FREEZE`, `PILOT_INTENT` and `CONFIRMATORY_INTENT` (original items 26, 33, 34 and 35 of the v2.3.93 template, jsonl line 7886) have no group and no recorded decision. They are listed so they are not lost. The Group 4 schema direction is a design direction only and does not decide `SCHEMA_EXTENSION`.

---

## Stage 4I.34 audit — technical recommendations (RECOMMENDED — NOT OWNER APPROVED)

Nothing in this section is an owner decision. Every value is a recommendation. Paths are under `src/maps/`. The task prompt named `src/maps/live_*.py` and `src/maps/policy_source.py`; the files are in `src/maps/runs/`.

### Recommendations for fields the code determines

| Field | Recommended | Evidence | Limits and consequences | Owner approval |
|---|---|---|---|---|
| PS-05a `max_episodes` | `= planned_episodes` | `runs/live_policy.py:80-81` (must be ≥ planned); `runs/live_budget.py:266` (refuses a call once `_started >= max_episodes`); `runs/live_executor.py:173` (inventory size must equal `planned_episodes`) | The grid is exact, so slack has no benefit. Equality makes the cap a tripwire against calls beyond the planned grid. | Required |
| PS-05b `max_request_attempts` | `= 3 × planned_episodes` (576 for 192 episodes, 720 for 240) | `runs/live_policy.py:84-85`; `runs/live_budget.py:269` | **Not a protective cap.** It permits every configured attempt: each call reserves `1 + max_retries` = 3, and charges cannot exceed the reservation, so the cap can never refuse a call in a planned grid. Actual protection is the episode cap, the deadline, and the provider-side limit. There is no cumulative token cap (PS-06-BUDGET A) and no price source. | Required |
| PS-12-4XX `nonfatal_4xx_statuses` | `[]` | `llm_client.py:14,112` (only 429, 500, 502, 503, 504 are retried; other 4xx return after one attempt); `runs/live_budget.py:114-139` (a 4xx is nonfatal only if listed, else fatal) | An empty list makes every 4xx stop the run at once, which suits auth, payment, not-found and bad-request errors. A persistent 429 after 3 attempts is also fatal. With PS-12-CONSEC = 1 the list only changes the stop label. The `[408, 429]` in `tests/policy_source/ps_support.py` is a synthetic fixture, not a policy. | Required |
| PS-12-3XX `fatal_3xx` | `true` | `llm_client.py:103` (`allow_redirects=False`); 3xx is not retried; `runs/live_budget.py:114-139` | A redirect from the exactly validated endpoint is unexpected. `true` fails closed. | Required |
| PS-11 final-call stop | Keep: ineligible | `runs/live_executor.py:69-73, 203-232` | See the three-case distinction below. | Required |
| PS-12 `call_error` eligibility | A (zero tolerance), provided it is chosen together with PS-12-CONSEC = 1 | `runs/live_executor.py:28-29`; `runs/live_budget.py:301-316` | Judgment, not an empirical finding. Pairing table below. | Required |
| PS-12-CONSEC | `1`, only with PS-12 = A | `runs/live_policy.py:88-89` (range 1..planned); `runs/live_budget.py:301-316` | A strict operational policy, not a statistically estimated threshold. See below. | Required |
| PS-13 `parse_error` eligibility | Keep: report only | `runs/live_budget.py:114-139` (a 200 reply with string content is a success to the wrapper); `experiments/receiver.py:261` (status `parse_error`); `analysis/rows.py:52-58` (a valid observation needs status `ok` and every outcome present); `analysis/quality.py:88-96` (counts per cell) | Parse errors must appear in loss and validity tables and never count as valid or zero. They can depend on condition or variant, so per-cell reporting matters. | Required |

**PS-11, three cases.** (1) A complete grid with no policy stop is eligible if the other integrity conditions hold (`no_policy_stop` true, `live_executor.py:232`). (2) A complete grid in which the wrapper records a stop on or after the final call (fatal error, threshold reached, or deadline crossed) is `policy_stop` through `post_runner_check` and is ineligible. (3) An incomplete grid raises `BudgetAbort` at the next call and is a partial, ineligible run. The `PS-14` "diagnostic-only" approval is described only in a conversation summary and was not re-verified. Keeping the rule needs no code change, but a complete dataset can be discarded for a deadline crossed on the last call. The PS-09 headroom reduces that risk.

**PS-12 and PS-12-CONSEC must be chosen as a pair.**

| PS-12 | PS-12-CONSEC | Result |
|---|---|---|
| A | 1 | Consistent. The first nonfatal error is a stop, so the run is ineligible without a code change. |
| C | k > 1 | Consistent. Isolated errors keep the run eligible. Needs a `k` with no empirical basis, and a global counter that can mask a one-model outage. |
| C | 1 | Contradictory. `1` overrides C. |
| A | k > 1 | Contradictory. The run tolerates errors that A forbids. |

Literal A ("continue the grid, mark ineligible") or B (a tolerance rate) needs an executor change and is not available now.

**Why 1.** The counter is global across both models and the shuffled grid, and any success resets it, so with k > 1 a one-model outage can be masked by the other model's successes. PS-21 (per-model limits) was deferred (jsonl line 7328). With 1 the deferral leaves no detection gap. With k > 1 it does. A nonfatal error that reaches the wrapper has already used 3 attempts. The cost: one error voids the run, a rerun repeats the full grid (no resume), and the pilot yields little error-rate information. The pilot's purpose (descriptive and feasibility) can favor either a clean dataset or error-rate measurement. That is an owner judgment.

### PS-09 `deadline_seconds` — candidate unchanged

`183 × (planned_episodes + 1)` = 35,319 s for 192 episodes and 44,103 s for 240. Per-call worst case is 183 s: `llm_client.py:90-116` makes up to 3 attempts of `timeout_s` 60 with backoff 1 s then 2 s. Limits: the deadline is not a hard wall-clock guarantee. It starts after the factory and pre-run provenance (`runs/live_executor.py:35-36`), is checked only between calls (`runs/live_budget.py:264, 320`) and never interrupts an in-flight call. `timeout_s` is per socket operation (`runs/policy_source.py` docstring), so 183 s is nominal. The extra episode is nominal headroom, not a guarantee. The final value depends on the frozen cohort and `planned_episodes`. Not approved.

### Scientific inputs that remain with the owner

- **MEANINGFUL_EFFECT_THRESHOLD** (unit: mean elicited roots, per contrast). Most defensible: one absolute interpretive number with a stated plain-language rationale. A fraction of the nominal gap (1 root for C4−C2, 3 roots for C5−C3) presupposes an effect proportional to nominal gap, which is what the study tests. No external benchmark exists in the repository. Status stays `PENDING OWNER INPUT — NUMERIC VALUE REQUIRED`.
- **C0_TOLERANCE.** Clearest primary measure: the proportion of C0 episodes reporting more than zero roots, because `ROOT_COUNT_CAP = UNBOUNDED` makes a mean sensitive to one large report. Report mean roots in C0 as a complementary diagnostic. A C0 cell has 32 episodes for an 8-scenario cohort and 40 for ten scenarios (proportions in steps of 3.1 and 2.5 points). A breach would mean the elicitation is not attributing roots to messages, so C0-referenced contrasts need a caveat. The owner must define the consequence in advance. Status stays `PENDING OWNER INPUT — MEASURE AND NUMERIC TOLERANCE REQUIRED`.

### Subset pilot cohort: how the grid binds (correction to the earlier "unverified" note)

- `experiments/receiver.py:350` loads every `*.json` in `cfg.design.scenario_dir`. `scenarios.py:73-89` is non-recursive and requires every `pair_id` to have exactly one true and one false scenario. No flag narrows scenarios; the CLI has `--config`, `--mock`, `--live`, `--export-grid`, `--export-balance`, `--run-id`, `--policy`, `--profile` and `--expected-policy-digest`. A whole-pair subset can only be a directory containing exactly the cohort's pairs.
- `build_grid` (`receiver.py:127-161`) is a full factorial over models, scenarios, variants, conditions and repetitions, then `random.Random(cfg.seed).shuffle`. Episode ids, seeds and message plans are keyed on experiment, model, scenario, variant, condition, repetition, seed and `pair_id`. By reading the code, retained episodes keep their ids and content, but row order and count change. Not tested.
- The committed `experiments/plans/receiver_pilot_grid.tsv` and `receiver_pilot_balance.json` are compared with the regenerated full grid by `tests/test_design.py:54, 59, 70, 157, 294` (240 episodes, ten scenarios). Deleting TSV rows or changing the shipped config's `scenario_dir` breaks those tests.
- `design_digest` (`runs/policy_source.py:264-276`) covers the `design` block including `scenario_dir`, so a different directory changes the digest. The policy scope must equal the grid exactly and bind scenario and evidence SHA-256 values.

**Specification for a future authorized stage (not performed):** (1) fix the cohort of whole pairs, at least four; (2) place exactly those scenario files in a new cohort directory, byte-identical to the originals, with evidence still resolved from the repository root; (3) create a separate pilot config file (leave `configs/receiver_experiment.json` untouched) with that `scenario_dir`; (4) export a new grid and balance file to new paths with `--export-grid` and `--export-balance`; (5) compute `planned_episodes` from the new grid (24 × scenarios × repetitions: 192 or 240); (6) compute content digests, build the policy document with `stage: pilot` and the chosen limits, and obtain the policy digest; (7) supply that digest independently through `--expected-policy-digest`; (8) any scenario edit after hashing invalidates the policy. Adding new tests would be a separately disclosed change. Whether manifests need refreshing was not verified: the protected source list (`tests/synthetic/synthetic_support.py:74-102`) does not include `configs/` or `data/`.

### Policy dependency table

| Item | Current value or status | Evidence | Owner-approved | Cohort-dependent | Blocks valid pilot policy | Blocks pilot authorization | Next action |
|---|---|---|---|---|---|---|---|
| planned_episodes | None. 240 for the full ten, 192 for four pairs | `receiver.py:127-161`; `tests/test_design.py:54` | No | Yes | Yes | Yes | Fix the cohort |
| scenario_ids | None for a cohort | `policy_source.py` scope | No | Yes | Yes | Yes | Fix the cohort |
| max_episodes | None | `live_policy.py:80` | No | Yes | Yes | Yes | Decide (`= planned`) |
| max_request_attempts | None | `live_policy.py:84` | No | Yes | Yes | Yes | Decide (`= 3 × planned`) |
| nonfatal_4xx_statuses | None | `policy_source.py:413-425` | No | No | Yes | Yes | Decide (`[]`) |
| fatal_3xx | None | `live_budget.py:114-139` | No | No | Yes | Yes | Decide (`true`) |
| deadline_seconds | None | `live_policy.py:86` | No | Yes | Yes | Yes | Decide |
| max_consecutive_nonfatal_errors | None | `live_policy.py:88` | No | Yes (≤ planned) | Yes | Yes | Decide with PS-12 |
| PS-11 | Fixed behavior: ineligible | `live_executor.py:69-73` | No | No | No (no field) | Yes (Stage 4D record) | Decide |
| PS-12 | Fixed behavior: C | `live_executor.py:28-29` | No | No | No | Yes | Decide with CONSEC |
| PS-13 | Fixed behavior: report only | `receiver.py:261`; `analysis/rows.py:52` | No | No | No | Yes | Decide |
| PS-21 | Deferred; global counter | jsonl line 7328 | Yes (A, defer) | No | No | No | Keep; see PS-12-CONSEC |
| PS-08 | `strict_physical` | jsonl line 7328 | Yes | No | Value needed in file | No | Put in the policy |
| PS-19 | A, retain accounting | jsonl line 7328 | Yes | No | No (no field) | No | Keep. Provider usage request unresolved offline |
| PS-06-BUDGET | A, no cumulative token cap | jsonl line 7328 | Yes | No | No | No | Keep |
| PS-07 | 2 retries | Ledger Group 5; `configs/receiver_experiment.json:31` | Yes | No | Must equal the config | No | Keep |
| TIMEOUT-BACKOFF | A, in design digest; 60 s and 1.0 s configured | jsonl line 7328; config | Inclusion yes, values not | No | Digest-bound | No | Confirm values at policy time |
| policy_id | None | `policy_source.py` schema | No | No | Yes | Yes | Choose an identifier |
| approval_reference | None | `live_policy.py:65-66` | No | No | Yes | Yes | Owner supplies |
| Scenario and evidence hashes | None | `policy_source.py:279-` | No | Yes | Yes | Yes | Compute after freeze |
| Profile name | None | `policy_source.py:select_profile` | No | No | Yes (explicit, no default) | Yes | Choose a name |
| Stage scope | `pilot` in the config | `policy_source.py:check_scope`; `receiver.py:132-135` | No | No | Must match | Yes | Keep `pilot` for the pilot; `main` requires `frozen` scenarios |

Also outside the policy: `api.enabled` is `false` and the final refusal stays until separately authorized. The expected-digest storage (PS-18-STORAGE) is described as approved only in a conversation summary, so it is not recorded here.

### Four ungrouped decisions

| Field | Original meaning and source | Owner and stage | Partly covered by | Recommended placement and value | Contradiction |
|---|---|---|---|---|---|
| SCHEMA_EXTENSION | Original item 26. The v2.3.98 brief section G: necessary review-record extensions (conflict-of-interest declarations, disagreement and adjudication records, message-only and pair-comparison exports; review-log versioning optional). Owner states `AUTHORIZE_IN_SEPARATE_STAGE` and a scope (necessary only, or plus optional). | Owner; Stage 4J.2 (exports 4J.4) | The Group 4 lifecycle-separation direction covers one necessary item only | Attach to the 4J.2 decision. Recommend `AUTHORIZE_IN_SEPARATE_STAGE`, scope necessary only | None. `schemas.py` and `scenarios.py` are protected; manifest refresh in 4J.5 |
| FREEZE | Original item 33. Recommendation: freeze scenarios only after review and adjudication, with hashes. A design freeze is separate. | Owner; Stage 4J.7 | The AUTHORING_TIMING clarification (pilot-family freeze after author checks) and the Group 4 lifecycle direction | Restate as two freezes (below). Place with Group 6. | **Yes.** The original wording cannot be met on the author-checked pilot path. The approved clarification supersedes it for the pilot family. |
| PILOT_INTENT | Original item 34. Recommended NOT AUTHORIZED because readiness conditions are not met. | Owner; after 4J.7 | Nothing | Keep with Group 6 as a separate line from the stage lines. Stays NOT AUTHORIZED. | None |
| CONFIRMATORY_INTENT | Original item 35. Recommended NOT AUTHORIZED. | Owner; after independent review | Nothing | Same. Stays NOT AUTHORIZED. | None |

**Concepts that must not be equated.** Author-checked pilot content, independently reviewed confirmatory content, a frozen protocol (4J.1 documents and manifest), a frozen scenario cohort (4J.7 hashes), a design freeze (separate, not authorized) and authorization to execute a pilot (`PILOT_INTENT`). In the code, the `pilot` stage does not require `frozen` status (`receiver.py:132-135` applies only to `main`), so a pilot-family content freeze can be recorded as a hash binding, while the schema `frozen` status stays reserved for confirmatory scenarios with independent review.

### Stage 4J authorization lines — all NOT AUTHORIZED (no owner authorization recorded)

| Stage | Scope | Prerequisites | Permitted if authorized | Still prohibited | Risk of authorizing early | Independent of later stages |
|---|---|---|---|---|---|---|
| 4J.1 | Protocol documents and manifest in `protocol/scenario_v1/` | Groups 1-4 decided; approver identity | Creating the documents and hashes | Schema, scenario, code and execution changes | Analysis-plan fields still pending | Yes |
| 4J.2 | Schema and review-record extensions, lifecycle separation | 4J.1 | Changing the schema | Scenario edits, validation runs | Locking a schema before the protocol is fixed | Yes, once 4J.1 is done |
| 4J.3 | Mechanical validation and pair checks | 4J.2 | Check code for length and false-value rules | Scoring scenarios as accepted | Checks built on an unfinished schema | Yes, once 4J.2 is done |
| 4J.4 | Review exports and answer-key custody | 4J.2 | Export changes; moving the key | Sharing with reviewers | Breaking reproducibility tests; leaving history exposure unchecked | Yes, once 4J.2 is done |
| 4J.5 | Tests and integrity checks | 4J.2, 4J.3, 4J.4 | New and updated tests; manifest refresh | Experiments | Refreshing pins around unfinished code | Yes, once its prerequisites are done |
| 4J.6 | Scenario authoring and review, including `hist` | 4J.1-4J.5 | Editing and authoring scenarios | Freeze, execution | Authoring before validators exist | Yes, once its prerequisites are done |
| 4J.7 | Scenario freeze and pilot readiness | 4J.6 | Hashing and recording the cohort | Design freeze, execution | Freezing unvalidated content | Yes, once 4J.6 is done |

---

## Stage 4I.35 — reconciliation and minimum owner decision set (RECOMMENDED — NOT OWNER APPROVED)

This section reconciles the Stage 4I.34 section above and does not erase it. Where they differ, **this section supersedes the earlier recommendation, and the reason is given.** Nothing here is an owner decision, an implemented change, a validated result or an authorization. Classes: EXPLICITLY OWNER APPROVED (EOA), TECHNICALLY DETERMINED (TD), RECOMMENDED — OWNER ACCEPTANCE REQUIRED (ROA), OWNER JUDGMENT REQUIRED (OJR), BLOCKED BY MISSING EVIDENCE (BME).

### Reconciliation

| Item | Kind of thing | Class | Minimum valid vs recommended |
|---|---|---|---|
| PS-05a `max_episodes` | Policy-file field (`runs/live_policy.py:80`) | Minimum valid: TD. Recommended value: ROA | Minimum `planned_episodes`; recommended = minimum |
| PS-05b `max_request_attempts` | Policy-file field (`live_policy.py:84`) | Minimum valid: TD. Recommended value: ROA | Minimum `planned × (1 + 2)`; recommended = minimum. Not a spending safeguard. |
| PS-12-4XX | Policy-file field (`policy_source.py:413-425`) | ROA; the value depends on the PS-12 approach | Under strict (A) any value works, label only. Under tolerant (C): `[408, 429]` |
| PS-12-3XX | Policy-file field | ROA | `true` under either approach |
| PS-11 | Fixed runtime behavior, no field (`live_executor.py:69-73, 203-232`) | Current behavior: TD. Keeping it: ROA | The code states this is an owner decision and applies the conservative answer. Changing it needs an executor change. |
| PS-12 | Fixed behavior (option C today), no field | OJR, coupled with PS-12-CONSEC | See below |
| PS-12-CONSEC | Policy-file field, range 1..planned (`live_policy.py:88`) | OJR (a governance number, no empirical basis) | See below |
| PS-13 | Fixed behavior, no field (`experiments/receiver.py:261`; `analysis/rows.py:52`) | Current behavior: TD. Keeping it: ROA | Report-only, with per-cell reporting (`analysis/quality.py:88-96`) |
| PS-09 | Policy-file field, cohort-dependent | ROA for the formula; the number is TD once the cohort is fixed | Minimum 1; recommended `183 × (planned_episodes + 1)` |
| PS-21 | Deferral | EOA: A, defer (jsonl 7328; table at 7474) | The original evidence supports no other reading. Retained. |
| PS-08, PS-19, PS-06-BUDGET, TIMEOUT-BACKOFF, PR4-PROXY, PS-07 | Settled | EOA (jsonl 7328; PS-07 in Group 5). Not asked again. | |

### PS-12 and PS-12-CONSEC: recommendation changed from the Stage 4I.34 text

**Recommended (not approved): Approach C. `PS-12 = C`, `PS-12-CONSEC = 5`, `nonfatal_4xx_statuses = [408, 429]`, `fatal_3xx = true`.** In Stage 4I.34 I recommended Approach A with 1. Two things changed my view.

1. **The masking argument was overstated.** With a global counter and a shuffled grid, a *total* outage of one model fails about half the calls in random order. The expected number of calls until a streak of `k` failures is `2^(k+1) − 2` (14 for k = 3, 62 for k = 5, 510 for k = 8). So `k ≤ 5` catches a total single-model outage within a fraction of a 192-240 episode grid. Only partial degradation is masked, and for partial degradation the loss tables are the intended instrument. This is a calculation under independence and a 50% failure rate, not an observed rate.
2. **The pilot's purpose.** The deferral of PS-09 and PS-12-CONSEC was justified by learning operational behavior from the pilot. Approach A (stop and void on the first error) yields almost no error-rate information, and an eligible run is needed to exercise the primary analysis path (`load_eligible_run` refuses ineligible runs).

| Criterion | A: `PS-12 = A`, CONSEC `1` | C: `PS-12 = C`, CONSEC `5` |
|---|---|---|
| Pilot completeness | One error that survives retries voids the run | Isolated errors leave the run eligible |
| Operational reliability signal | Binary: finish or void | Error counts, categories and loss tables |
| Observing provider error rates | Very limited | Yes, bounded by `k` |
| One model's outage masked | Cannot happen | Total outage caught (~62 expected calls at k = 5); partial degradation masked and visible only in loss tables |
| Full-grid rerun cost | High: any error forces a full rerun (no resume) | Lower: a rerun is needed only on a streak, a fatal error or the deadline |
| Feasibility check | Strongest evidence the pipeline runs error-free | Evidence it runs at a measured error level |

`k = 5` is a governance choice, not a measured optimum. It tolerates bursts shorter than 5 consecutive errors, each of which has already used 3 attempts. A chance streak under independent errors is negligible for a modest error probability (about 6 in 100,000 per grid at 5%). `[408, 429]` follows from what the statuses mean (request timeout, rate limit), not from the test fixture that happens to use the same list: transient conditions count toward the streak, and every other 4xx (authentication, payment, bad request, not found) stops the run at once. This is general knowledge of HTTP semantics, not repository evidence. Under C, a streak that ends on the final call still makes a complete grid ineligible (PS-11).

**What the owner must choose, and why it cannot be decided silently.** Whether the first pilot prioritizes a clean-or-void run (A) or an operational characterization that tolerates isolated errors (C). The policy loader has no defaults (`live_policy.py` docstring), the choice changes run eligibility and spend, and `k` has no empirical basis. If the owner prefers A, the other values are `CONSEC = 1` and `nonfatal_4xx_statuses = []`.

### Scientific inputs

- **MEANINGFUL_EFFECT_THRESHOLD.** Most defensible concept: one absolute interpretive threshold θ in mean elicited roots, stated with a plain-language rationale and applied to both contrasts (C4−C2, C5−C3) and both models. Interpretation alongside the estimand: report the mean pair difference and the shift-model interval. An interval wholly above θ is "meaningful"; wholly inside (−θ, θ) is "not meaningful"; one that straddles θ is "inconclusive". The interval is not exact for a finite mean, the estimand describes the authored set, and θ is not a power input. **Minimum owner input:** the number θ (in roots, positive) and confirmation that it applies to both contrasts. It must be fixed before any pilot results are examined, and not derived from model output. Status: `PENDING OWNER INPUT — NUMERIC VALUE REQUIRED`.
- **C0_TOLERANCE.** Reassessed and confirmed: the proportion of C0 episodes with more than zero reported roots is the primary measure, because `ROOT_COUNT_CAP = UNBOUNDED` makes a mean sensitive to a single large report. Mean elicited roots in C0 is a complementary diagnostic. A breach means the elicitation is not tying roots to messages. Suggested consequence for the owner to accept or amend: C0-referenced (secondary) contrasts are reported as instrument-contaminated; the primary contrasts, which do not use C0, are reported with a caveat; and the elicitation prompt is reviewed before any confirmatory run. A pilot breach does not by itself void the pilot. **Minimum owner input:** a numeric proportion π (0 to 1) and the consequence rule. A C0 cell has 32 episodes for an 8-scenario cohort and 40 for ten. Status: `PENDING OWNER INPUT — MEASURE AND NUMERIC TOLERANCE REQUIRED`.

### Concepts that must stay separate, and the decision order

| Concept | What it is | Where decided |
|---|---|---|
| Protocol documentation approval | The seven documents and manifest in `protocol/scenario_v1/` | Stage 4J.1 output; approver and date at final approval |
| Schema extension authorization | Changing `schemas.py` and review-record fields | `SCHEMA_EXTENSION`, then Stage 4J.2 |
| Author-checked pilot content | Scenario text checked by the author under the approved rules | Stage 4J.6 |
| Pilot content hash binding | SHA-256 of scenario and evidence files in the policy `content` block | Pilot cohort fixing (4J.7) and policy construction |
| Independent confirmatory review | Review by people other than the author | Needs reviewers; not required for the pilot |
| Confirmatory scenario freeze | Schema status `frozen` with independent-review evidence | After independent review |
| Design freeze | Fixing the design | Separate, not authorized |
| Pilot execution authorization | `PILOT_INTENT` | After the cohort is frozen and the policy is complete |
| Confirmatory execution authorization | `CONFIRMATORY_INTENT` | After independent review and the analysis plan |

Order: 4J.1 → (`SCHEMA_EXTENSION`, `FREEZE`) → 4J.2 → 4J.3, 4J.4 → 4J.5 → 4J.6 (incl. `hist`) → 4J.7 → policy values and thresholds → `PILOT_INTENT`. Items needed only for later stages stay open without blocking earlier ones.

### hist pair: revision requirements (for a future authorized stage)

- **Failed criteria.** (1) `HISTORICAL_YEAR_THRESHOLD`: the false year 1741 (hist-a) differs from the paired true year 1583 (hist-b) by 158 years against an approved maximum of 50. (2) Template length: both members have templates of 43, 44, 53 and 58 characters (mean 49.5). Template 58 is +17.2% from the mean, outside ±15%, so **both members** need template revision.
- **What stays true.** hist-a's own ground truth is 1694 and hist-b's is 1583. The false assertion must not equal 1694.
- **Valid false-year range.** An integer from 1533 to 1633 excluding 1583. That range lies 61 to 161 years from hist-a's own ground truth of 1694, which the approved rule permits. Moving hist-a's ground truth nearer would be a larger revision of the evidence document. It is not needed to satisfy the rule and is an author decision. I propose no year and no replacement text.
- **Must preserve.** `check_pair_matched` matches (domain, attribute, calendar convention, and each root's stated origin, acquisition process, instrument class, artifact type and quality tier; `event_date` is null for both). Each message contains the asserted year exactly once and no other numeral (`context_numbers` is empty). Evidence must open with the synthetic label, contain the ground-truth value, and contain the asserted value if and only if the scenario is true (`scenarios.py:check_evidence_file`, coarse substring match, so the new false year must not appear anywhere in hist-a's evidence). Lexical filters (`schemas.py:38-43`) still apply. Evidence file sizes are identical for hist-a and hist-b (328 bytes each), and for each of the other four pairs too (bytes, not characters, and the ±10% formula is not yet defined).
- **Acceptance checklist after revision.** (a) Schema validates. (b) Evidence consistency holds. (c) Pair match holds. (d) The false year is within 50 years of 1583, differs from it and from 1694, and has the same four-digit format. (e) Each of the four templates is within ±15% of its scenario's mean, for both members. (f) Corresponding templates across the pair satisfy `abs(a−b)/((a+b)/2) ≤ 0.15`. (g) Evidence length within ±10% inside the pair. (h) The author four-stage self-check is redone and recorded as `AUTHOR_CHECKED_ONLY`, with unchanged thresholds. (i) The scenario `status` and `evidence.verification_status` are set together (the schema rejects a status above the evidence status), the review record is not marked independent, and `independence_confirmed` is not set to true. (j) The pair still loads in `load_scenario_dir`.
- **Pathway.** The revision can be done under the approved author-checked pilot path (EXISTING_TEN; PILOT_SCENARIO_POLICY: revised versions stay pilot-family and are never reused as confirmatory). No independent review is required for the pilot; it is required only for confirmatory use.
- **Missing dependency found.** `tests/test_scenarios.py:284-287` (`test_all_scenarios_remain_draft_and_unvalidated`) requires every real scenario to have `status == "draft"` and `verification_status == "unverified"`. Recording any author check in place breaks it. That test must be updated (and disclosed) in Stage 4J.5 before the status changes of Stage 4J.6, which matches the stage order.

### Subset-cohort specification: dependencies added to the Stage 4I.34 text

Besides the eight steps already recorded: (1) the cohort directory is read with `load_scenario_dir` and `check_evidence_file`, so the scenario files in it must match their evidence documents; (2) `tests/test_scenarios.py:79-88` and `tests/test_review_export.py:23` still read `data/scenarios/v2`, so the originals stay in place; (3) scenario `evidence.sha256` is `null`; the pilot hash binding is the policy's `scope.content` digests, not the schema field; (4) `design_digest` includes `design.scenario_dir`; (5) the new pilot config is not in the protected source list, so no source manifest refresh is needed for config and data additions alone, but this was not verified against the golden manifest; (6) any new tests are a separately disclosed change.

### Decision matrix

| Decision | Recommended answer | Why | Owner input required? | Blocks next stage (4J.1)? | Blocks pilot? |
|---|---|---|---|---|---|
| Approver identity for 4J.1 documents | Supply `APPROVER_NAME`, or accept `PENDING UNTIL FINAL APPROVAL` in the documents | The only item the 4J.1 documents could embed | Yes | **Yes, only this** | No |
| FREEZE (two freezes) | Accept the two-freeze restatement | Resolves the conflict with the author-checked path | Yes | No (blocks 4J.2) | No |
| SCHEMA_EXTENSION scope | `AUTHORIZE_IN_SEPARATE_STAGE`, necessary only | Sole researcher; optional features can wait | Yes | No (blocks 4J.2) | No |
| Evidence-length formula, direction-balance measure, "avoid extremes" rule | Define before 4J.3 | Mechanical checks need exact formulas | Yes, later | No | No |
| Answer-key destination | Owner names a location outside the repository | I must not invent locations | Yes, later | No (blocks 4J.4) | No |
| PS-12 approach, CONSEC and 4XX | C, `5`, `[408, 429]` (A: `1`, `[]`) | Above | Yes | No | **Yes** |
| PS-05a, PS-05b | Equal to the minimum | Not safeguards | Yes (one-word) | No | **Yes** |
| PS-12-3XX | `true` | Fails closed | Yes (one-word) | No | **Yes** |
| PS-11, PS-13 | Keep current behavior | No code change | Yes (one-word) | No | **Yes** |
| PS-09 formula | `183 × (planned_episodes + 1)` | Nominal headroom | Yes | No | **Yes** |
| θ, π and breach consequence | Owner numbers | Cannot be derived | Yes | No | **Yes**, before any results |
| Subset-cohort specification | Approve for a later stage | Needed for policy scope | Yes | No (blocks 4J.7) | **Yes** |
| policy_id, profile name | Delegate naming; `approval_reference` is the owner's | Labels | Yes (delegation) | No | **Yes** |
| PILOT_INTENT, CONFIRMATORY_INTENT | NOT AUTHORIZED | Conditions unmet | Later | No | PILOT_INTENT: yes |
| APPROVAL_DATE | At final approval | Not today's date | Later | No | No |

### Minimum owner response list

1. **Next stage only.** *"May the 4J.1 documents show the approver as PENDING until final approval, or what name should appear?"* Recommended: `PENDING`. Accepting lets 4J.1 start. Rejecting means supplying the name first. Blocks 4J.1 only.
2. **FREEZE.** *"Do you accept a pilot-family content freeze (after author and rule checks, recorded by hashes, no independence claim) and a confirmatory freeze (after independent review)?"* Recommended: yes. Accepting fixes the 4J.2 design target. Rejecting leaves the schema direction ambiguous. Blocks 4J.2.
3. **SCHEMA_EXTENSION.** *"Authorize the schema extension in a separate stage, necessary items only?"* Recommended: yes. Accepting keeps 4J.2 small. Rejecting widens it to optional items. Blocks 4J.2.
4. **PS-12 approach.** *"First pilot: tolerant (C, CONSEC 5, 4XX `[408, 429]`) or strict (A, CONSEC 1, 4XX `[]`)?"* Recommended: C. Consequences above. Blocks pilot readiness only.
5. **θ.** *"What is your meaningful-effect threshold in mean elicited roots, for both contrasts?"* No recommended number. Blocks pilot readiness only.
6. **π.** *"What is your C0 tolerance (proportion of C0 episodes above zero roots), and is the breach consequence acceptable?"* No recommended number. Blocks pilot readiness only.
7. **PS-09.** *"Accept the formula `183 × (planned_episodes + 1)`, computed after the cohort is fixed?"* Recommended: yes. Rejecting means you supply another formula. Blocks pilot readiness only.
8. **Derived caps and behaviors (one-word each).** PS-05a = planned; PS-05b = 3 × planned; PS-12-3XX = `true`; PS-11 keep; PS-13 keep. Recommended: accept each. Blocks pilot readiness only.
9. **Cohort specification and identifiers.** Approve the specification for a later stage; delegate `policy_id` and the profile name, and supply `approval_reference` yourself. Blocks pilot readiness only.

Not asked again: PS-08, PS-19, PS-06-BUDGET, PS-21, TIMEOUT-BACKOFF, PR4-PROXY, PS-07 and all Groups 1-4 decisions. Decide later without blocking now: evidence-length formula, direction-balance measure, "avoid extremes", the answer-key destination, `PILOT_INTENT`, `CONFIRMATORY_INTENT`, `APPROVAL_DATE`.

### Stage 4J sequencing (all NOT AUTHORIZED)

| Stage | Exact scope | Prerequisites satisfied? | Earliest safe authorization | Would permit | Remains prohibited |
|---|---|---|---|---|---|
| 4J.1 | Seven protocol documents and manifest in `protocol/scenario_v1/` | Yes, apart from approver metadata (item 1) | Now | Creating the documents and hashes | Schema, scenario, code, config changes; any execution |
| 4J.2 | Schema and review-record extensions, lifecycle separation | No: needs 4J.1, `FREEZE`, `SCHEMA_EXTENSION` | After 4J.1 and items 2-3 | Editing `schemas.py` (protected) | Scenario edits, running validation |
| 4J.3 | Mechanical validation and pair checks | No: needs 4J.2 and the formulas above | After 4J.2 | Check code for length and false-value rules | Scoring scenarios as accepted |
| 4J.4 | Review exports and answer-key custody | No: needs 4J.2 and the key destination | After 4J.2 | Export changes; moving the key | Sharing with reviewers |
| 4J.5 | Tests and integrity checks | No: needs 4J.2-4J.4 | After 4J.4 | Updating pinned tests such as `test_scenarios.py:284`; manifest refresh | Experiments |
| 4J.6 | Scenario authoring and review, including `hist` | No: needs 4J.1-4J.5 | After 4J.5 | Editing and authoring scenarios | Freeze, execution |
| 4J.7 | Scenario freeze and pilot readiness | No: needs 4J.6 | After 4J.6 | Hashing and recording the cohort | Design freeze, execution |

**Next safe candidate: Stage 4J.1.** It is the only stage whose prerequisites are essentially met, and it depends on nothing outstanding except item 1. Authorizing it authorizes no later stage.

### What still blocks

- **A valid pilot policy:** the final cohort and frozen files; PS-05a, PS-05b, PS-12-4XX, PS-12-3XX, PS-09 and PS-12-CONSEC values; `policy_id`, a profile name and `approval_reference`; the subset-cohort mechanism.
- **Pilot execution:** all of the above, θ and π, `PILOT_INTENT`, a policy digest supplied independently, and a separately authorized lifting of the final refusal in `experiments/receiver.py` with `api.enabled` set true.

---

## Stage 4I.36 — Stage 4J.1 pre-authorization audit (RECOMMENDED — NOT OWNER APPROVED; STAGE_4J.1 NOT AUTHORIZED)

Sources checked: the v2.3.96 readiness gate (transcript jsonl line 7902), the v2.3.97 stage brief with sections 4-6 (line 7869), the repository, and the approved decisions above. No `protocol/` directory exists, and no file in the repository defines a manifest schema or validator.

### Verified scope of Stage 4J.1

- **Deliverables (documents only):** `01_authoring_protocol.md`, `02_quality_rubric.md`, `03_reviewer_checklists.md`, `04_pair_construction_checklist.md`, `05_review_and_adjudication.md`, `06_versioning_change_control.md`, `07_answer_key_custody.md` and `PROTOCOL_MANIFEST.json`, in `protocol/scenario_v1/` (directory approved in Stage 4I.30).
- **Excluded by the original brief:** schema fields, code, configuration, tests, scenarios, exports, and any change to the project manifest or protected sources. It creates no execution capability.
- **Manifest contents (original brief):** file list, per-file SHA-256, a combined digest, protocol version, date and approver name. The combined digest uses the project's canonical method: lines `<posix path>:<hex>`, sorted, joined by LF.
- **Title.** The brief calls the stage "Protocol document freeze". That wording is easily confused with the design freeze and scenario freeze, which are separate and not authorized. This section calls the stage drafting and hashing the protocol documents.

### Approver and date: a conflict the owner must resolve

- Technically nothing requires a name. No schema or validator exists, so a `PENDING` value cannot fail one. `PENDING` does not imply approval if the approval block states that the protocol is not yet approved.
- Procedurally, the owner's own v2.3.96 readiness gate lists "the approver name is provided" and "the approval date is provided" before Stage 4J.1 can be declared ready. The same brief says the manifest records the date and approver after "the owner approves", and the owner's Stage 4I.30 decision defines `APPROVAL_DATE` as the actual final protocol approval date. A final approval date cannot exist before the documents do, so gate condition 4 conflicts with that decision and with the brief.
- 4J.1 prepares documents for later review. It does not itself constitute final protocol approval.
- **Recommended outcome:** obtain the approver name before presenting the authorization request, or obtain an explicit owner amendment of gate condition 3 to `PENDING UNTIL FINAL APPROVAL`. Also obtain an owner statement that condition 4 is superseded by the Stage 4I.30 decision (the date is recorded at final approval). I filled in neither value.

### Remaining prerequisites for Stage 4J.1

1. The approver-name and gate-condition amendment above.
2. All other original 4J.1 inputs (B1-B8, B10, B11, B12) are decided: roles, solo fallback, timing, existing ten, rubric thresholds, length tolerances, false-value rule, machine-cue check, custody, domain list and review procedure. `SCHEMA_EXTENSION` (B9) is not a 4J.1 prerequisite.
3. **Placeholders the documents would carry, not blockers:** (a) document 07's "where" needs the answer-key destination, which is undesignated, so 07 states the approved custody rule and marks the destination `NOT YET DESIGNATED`; (b) the evidence-length formula, the direction-balance measure and the "avoid extremes" test are undefined, so 01 and 04 record them as `TO BE DEFINED BEFORE STAGE 4J.3`; (c) the external storage location for the combined digest is undesignated, so the stage report prints it for the owner to record; (d) the wording of document 06 is drafted by 4J.1 and approved only at final protocol approval; (e) the domain list covers the existing five pairs only, and confirmatory domains are undecided.

### Later-stage decisions (do not block 4J.1)

`SCHEMA_EXTENSION` and `FREEZE` (before 4J.2); evidence-length formula and related measures (before 4J.3); answer-key destination (before 4J.4); `hist` revision (4J.6); cohort fixing and subset policy (4J.7 and policy construction); PS-09, PS-12, PS-12-CONSEC, PS-12-4XX, PS-12-3XX, PS-05a, PS-05b, PS-11, PS-13, `policy_id`, profile name, `approval_reference`; `MEANINGFUL_EFFECT_THRESHOLD`; `C0_TOLERANCE`; `PILOT_INTENT`; `CONFIRMATORY_INTENT`; `APPROVAL_DATE`; independent confirmatory review (needs reviewers and applies only to confirmatory use).

### Exact Stage 4J.1 change boundary

| File or file group | Action | May contain | Must not contain | Effect on runtime, loader, policy digest, execution | Integrity check |
|---|---|---|---|---|---|
| `protocol/scenario_v1/` | Create | Documents and manifest only | Anything else | None: outside `src/`, `data/`, `tests/`, `configs/`; `.md` and `.json` files are not scanned by the provider-route scanner | `git status --short` shows only the new directory and the ledger |
| `01_authoring_protocol.md` | Create | Approved protocol rules: domain list (five pairs, restrictions), false-value rule, 50-year year threshold, length tolerances | Scenario text, evidence, truth labels, ground-truth values, answer-key content, policy values, approvals not recorded here | None | SHA-256 in the manifest |
| `02_quality_rubric.md` | Create | Rubric and lowest-score gate (>=3 and >=2) | Scores for any scenario | None | Same |
| `03_reviewer_checklists.md` | Create | Fact, cue, pair and independence checklists, conflict-of-interest declaration | Reviewer names, any claim of independent review | None | Same |
| `04_pair_construction_checklist.md` | Create | Pair checklist marking code-checked and human-only items | Claims that checks were run | None | Same |
| `05_review_and_adjudication.md` | Create | Stages, what reviewers see, adjudication, accept/revise/reject, solo fallback labelled `AUTHOR_CHECKED_ONLY` | Self-review described as independent | None | Same |
| `06_versioning_change_control.md` | Create | Identifiers, versions, cohorts, supersession, post-pilot revision rule, append-only logs | A design or scenario freeze | None | Same |
| `07_answer_key_custody.md` | Create | Approved custody rule, destination marked `NOT YET DESIGNATED` | The key, its contents, or an invented location | None | Same |
| `PROTOCOL_MANIFEST.json` | Create | Protocol version, drafting date, file list, per-file SHA-256, combined digest, approval block `PENDING` | An approver name or approval date not supplied by the owner; any `approved` status | None | Recompute with `sha256sum`; parse with a JSON loader |
| `docs/stage_reports/owner_decision_ledger.md` | Modify | A Stage 4J.1 record | Any change to an earlier decision | None | `git diff --check` |

No scenario, evidence, answer-key, source, configuration, test, golden, fixture or project-manifest file is touched.

### Draft authorization request (NOT YET PRESENTED; NOT RECORDED)

Presented only after the approver and date questions above are answered.

> **Stage:** `STAGE_4J.1`
> **Purpose:** draft and hash the seven protocol documents and `PROTOCOL_MANIFEST.json` in `protocol/scenario_v1/`, recording the protocol as already approved in this ledger.
> **Permitted:** create exactly the eight files above, with the approval block `PENDING`, and append a Stage 4J.1 record to the ledger.
> **Prohibited:** every other change; Stages 4J.2-4J.7; schema or runtime changes; scenario revision; answer-key movement; scenario, protocol or design freeze; provider calls, experiments and spending.
> **Required checks:** independent recomputation of each file's SHA-256 and the combined digest; JSON parse of the manifest; `git diff --check`; `git status --short` showing only the new directory and the ledger; recomputation of the protected-source digest and the golden manifest hash against their last recorded values; a read-through that every approved value in the documents matches the ledger.
> **Completion evidence:** a report listing each file with its size and SHA-256, the combined digest to be recorded outside the repository, check results, and a statement of what was not done.
> **Owner response:** `AUTHORIZE STAGE_4J.1` or `DO NOT AUTHORIZE STAGE_4J.1`. Silence, a recommendation or approval of another decision is not authorization.

**Correction note (added in Stage 4I.37; the draft above is preserved):** the draft's purpose wording "recording the protocol as already approved in this ledger" is inaccurate. The ledger records individual owner-approved rules, not an approval of the protocol documents. The corrected request is in the Stage 4I.37 section below, and this draft is superseded by it.

### Sequencing corrections from the original specifications

- The original brief gives 4J.2 prerequisites 4J.1, B9 and cohort semantics. 4J.3: 4J.2, B6, B7. 4J.4: 4J.2, B10, B12. 4J.5: 4J.2-4J.4 (tests and integrity verification). 4J.6: 4J.1-4J.5 (scenario authoring and review). 4J.7: 4J.6 (scenario freeze and pilot readiness). The Stage 4I.36 task described 4J.5-4J.7 loosely ("scenario-revision support", "status/content updates", "final preparation"); the original definitions govern.
- Stage 4I.35 said the answer-key destination blocks only 4J.4. The original brief puts "where" into document 07, so 4J.1 carries a placeholder. Corrected above; it is not a blocker.

---

## Stage 4I.37 — approval-metadata gate reconciliation (RECOMMENDED — NOT OWNER APPROVED; STAGE_4J.1 NOT AUTHORIZED; PROTOCOL NOT APPROVED)

Status of the protocol: **NOT APPROVED.** The ledger records individual owner-approved rules. No owner statement approving the protocol documents, which do not yet exist, has been given.

### The v2.3.96 gate, reproduced (transcript jsonl line 7902, section 6)

The gate lists what must hold before "Stage 4J.1 ready for separate implementation" can be declared. Chronology: the original brief (line 7869) came first, the gate (line 7902) next, the Stage 4I.19 session criteria (line 8011) after it, and the Stage 4I.30 decision (line 8284) last.

| # | Condition (quotation) | Needed to | Conflicts with a later decision? | Placeholder possible? | Status |
|---|---|---|---|---|---|
| 1 | "All protocol decisions required for document creation are explicitly approved." | Begin drafting | No | n/a | Met (B1-B8, B10-B12; Stage 4I.36) |
| 2 | "The protocol directory is specified." | Begin drafting | No | n/a | Met (`protocol/scenario_v1/`, Stage 4I.30) |
| 3 | "The approver name is provided." | Declare drafting ready | Partly: Stage 4I.30 says the name is "to appear in the final protocol approval record" and leaves it unresolved | Yes (`PENDING OWNER CONFIRMATION`) | Not met |
| 4 | "The approval date is provided." | Declare drafting ready | **Yes.** Stage 4I.30: the date must be "the actual final protocol approval date", pending final approval, and not an anticipated date. The brief records date and approver "after the owner approves". | Yes (`PENDING FINAL PROTOCOL APPROVAL`) | Not met, and cannot be met before the documents exist |
| 5 | "Stage 4J.1 is explicitly marked AUTHORIZED." | Begin drafting | No | No | Not met; a separate owner act |
| 6 | "No unresolved decision changes the scope of these documents." | Begin drafting | No | n/a | Met with the placeholders listed in Stage 4I.36, subject to the file-list confirmation below |

The original brief's "approved before creation" list (line 7869, section 5) is the 4J.1 decision rows, "plus explicit authorization of Stage 4J.1 itself, its location, and permission to create only those files". It does not include the approver name or approval date. The Stage 4I.19 criterion (line 8011) governed the decision session, not 4J.1. None of these records is discarded.

### Metadata lifecycle options

| Option | Brief | Stage 4I.30 | Falsely implies approval? | Blocks 4J.1? | Owner amendment |
|---|---|---|---|---|---|
| A. Both fields filled before drafting | Contradicts: approval comes after drafting | Contradicts: the date would be anticipated | Yes: a dated, named block looks like an approval | Does not block, but invents a date | Cannot be done honestly |
| **B. Both `PENDING` until final approval** | Consistent | Consistent | No, if the approval block says `NOT APPROVED` | No | Supersede conditions 3 and 4 for drafting |
| C. Identity now, date pending | Consistent | Consistent for the date; the name is early | Slightly: a name in an approval block can read as an approver | No, once a name is supplied | Supersede condition 4 only; supply a name |

**Recommended: Option B.** It is the most internally consistent: the brief, the Stage 4I.30 decision and the principle that no field is invented all point the same way, and it needs no information you have not given. Option C is acceptable if you prefer to name the approver now. Then the manifest should use a field named `designated_approver` for identity only, separate from `approval.approved_by`, so the name does not read as an approval.

### Proposed gate amendment (recommended, not approved)

> "For Stage 4J.1 only, conditions 3 and 4 of the v2.3.96 readiness gate are superseded. The approver name and the approval date are not required to draft and hash the protocol documents. They are required for the final protocol approval record and stay `PENDING OWNER CONFIRMATION` and `PENDING FINAL PROTOCOL APPROVAL` until that approval. All other conditions are unchanged."

The original gate text stays in the record above. No condition is silently discarded.

### Manifest and document implications

- No technical problem. No schema or validator exists, and JSON strings `PENDING` parse. The combined digest is defined over the seven documents only (the canonical `<posix path>:<hex>` lines, sorted, joined by LF), so filling the approval block later changes the manifest's own SHA-256 but not the combined digest.
- Recommended field meanings, to keep dates from being conflated:

| Field | Meaning | At drafting |
|---|---|---|
| `protocol_version` | Identifier of this protocol draft, no date meaning | Set by the drafter, status `DRAFT` |
| `documents_drafted_on` | The day the seven documents are written | The actual day of drafting |
| `manifest_generated_on` | The day the manifest is generated | The actual day of generation |
| `stage_authorization` | Reference to the owner's Stage 4J.1 authorization statement, kept in the ledger | The ledger reference, not a protocol approval |
| `approval.status` | `NOT APPROVED` | `NOT APPROVED` |
| `approval.approved_by` | Approver identity | `PENDING OWNER CONFIRMATION` |
| `approval.approved_on` | Actual final approval date | `PENDING FINAL PROTOCOL APPROVAL` |
| `designated_approver` (Option C only) | Identity named in advance | Absent unless supplied |

- **Proposed approval step (not approved):** a separate, later owner statement that names the exact combined digest, for example `APPROVE PROTOCOL scenario_v1 AT COMBINED DIGEST <hex>; APPROVER_NAME: <name>`. Binding approval to the digest ties it to the exact documents. Filling the approval block is a manifest update, so it needs its own narrow permission. Both manifest hashes (draft and approved) would be recorded.
- Stage 4J.1 does not freeze the design or the scenarios.

### Corrected Stage 4J.1 authorization request (supersedes the Stage 4I.36 draft; NOT PRESENTED; NOT RECORDED)

Present it only after the two decisions below are answered.

> **Stage:** `STAGE_4J.1` — drafting and hashing the protocol documents only.
> **Purpose:** create the seven protocol documents and `PROTOCOL_MANIFEST.json` in `protocol/scenario_v1/`, restating the individually owner-approved rules in the ledger, hash them and report the combined digest.
> **Status statements:** authorizing this permits only that drafting and hashing. It is **not** protocol approval. The protocol remains **NOT APPROVED** until a separate, explicit final approval. The manifest approval block stays `PENDING`. Completion does not freeze the design or any scenario. It authorizes no schema change and no later Stage 4J stage.
> **Permitted:** create exactly the eight files, and append a Stage 4J.1 record to the ledger.
> **Prohibited:** every other change; Stages 4J.2-4J.7; schema or runtime changes; scenario revision; answer-key movement; any freeze; provider calls, experiments and spending.
> **Required checks:** recompute each file's SHA-256 and the combined digest; parse the manifest as JSON; `git diff --check`; `git status --short` showing only the new directory and the ledger; recompute the protected-source digest and golden manifest hash against their last recorded values (reported as newly verified); read-through that every rule in the documents matches the ledger.
> **Completion evidence:** a report listing each file with size and SHA-256, the combined digest for the owner to record outside the repository, check results and what was not done.
> **Owner response:** `AUTHORIZE STAGE_4J.1` or `DO NOT AUTHORIZE STAGE_4J.1`. Silence, a recommendation or approval of another decision is not authorization.

### File boundary: a discrepancy found, not adopted

The Stage 4I.37 task named the boundary as `01_authoring_protocol.md`, `02_scenario_schema.md`, `03_evidence_specification.md`, `04_message_construction.md`, `05_receiver_prompt.md`, `06_analysis_plan.md`, `07_answer_key_custody.md` and the manifest, and described it as carried forward from Stage 4I.36. Stage 4I.36 and the original brief name files 02 to 06 as `02_quality_rubric.md`, `03_reviewer_checklists.md`, `04_pair_construction_checklist.md`, `05_review_and_adjudication.md` and `06_versioning_change_control.md`. **The original names govern here.** The alternative names would pull in a receiver prompt and an analysis plan, whose numeric inputs (`MEANINGFUL_EFFECT_THRESHOLD`, `C0_TOLERANCE`, policy values) are undecided, and a schema document that overlaps Stage 4J.2. The scope is therefore ambiguous until the owner confirms. The eight protocol files are new files; the ledger is the only existing file to be modified.

**Correction note (added in Stage 4I.38; the text above is preserved):** the authorization request above is superseded by the Stage 4I.38 request. It did not name the eight files, did not mark drafted procedural content as unapproved, and left the "newly verified" wording open to overstatement.

### Minimum owner decision set (independent decisions)

1. **Metadata lifecycle and gate amendment.** *Do you accept Option B and the amendment text above?* Recommended: yes. If accepted, drafting does not wait for a name or date. Alternative: Option C with a named approver and only condition 4 superseded. If rejected or deferred, 4J.1 cannot be requested. Response: `ACCEPT PROPOSED: Option B and the gate amendment as written`, or `OWNER AMENDMENT: <your text>`, or `UNRESOLVED — NEEDS DISCUSSION`.
2. **File boundary.** *Is the 4J.1 file list the original one (quality rubric, reviewer checklists, pair construction checklist, review and adjudication, versioning and change control)?* Recommended: yes. If rejected, name the intended files and I will re-audit. Response: `ACCEPT PROPOSED: original file list` or `OWNER AMENDMENT: <file list>`.
3. **Stage 4J.1 authorization.** A separate decision, presented only after 1 and 2. Response: `AUTHORIZE STAGE_4J.1` or `DO NOT AUTHORIZE STAGE_4J.1`.

No pilot decision, scientific threshold or later stage is asked for.

### Readiness determination

**OWNER GATE AMENDMENT REQUIRED.** Gate conditions 3 and 4 cannot be satisfied as written without inventing or anticipating values, and the file list needs owner confirmation. After decisions 1 and 2, nothing else blocks the authorization request, which then becomes ready to present. Stage 4J.1 stays NOT AUTHORIZED.

---

## Stage 4I.38 — Stage 4J.1 file scope and metadata lifecycle (RECOMMENDED — NOT OWNER APPROVED; STAGE_4J.1 NOT AUTHORIZED; PROTOCOL NOT APPROVED)

### Authoritative file list: the original list

Transcript jsonl lines searched for each filename set (line numbers are 0-based):

| Set | Where it appears | Kind of source |
|---|---|---|
| Original (`02_quality_rubric.md`, `03_reviewer_checklists.md`, `04_pair_construction_checklist.md`, `05_review_and_adjudication.md`, `06_versioning_change_control.md`) | Line 7869 (the v2.3.93 stage brief, with a purpose for each file); line 7902 (the owner-authored v2.3.96 gate, section 6, "Stage 4J.1 is limited to protocol documents:"); the Stage 4I.36 section of this ledger | Original brief plus an owner prompt |
| Alternative (`02_scenario_schema.md`, `03_evidence_specification.md`, `04_message_construction.md`, `05_receiver_prompt.md`, `06_analysis_plan.md`) | Line 8920 only (the Stage 4I.37 task prompt) and later references to it | A later task prompt, never discussed or approved |

- No explicit owner decision changed the list. The alternative list was never approved, and nothing earlier supports it. The Stage 4I.37 prompt said it carried forward the Stage 4I.36 boundary and told me to verify it against the original brief; the names do not match the original, so it reads as a mistaken listing. That is an inference. The owner's later prompt is the most recent owner text, so the owner is asked to confirm.
- Both lists share `01_authoring_protocol.md`, `07_answer_key_custody.md` and `PROTOCOL_MANIFEST.json`.
- The original files have a defined purpose each (line 7869): `02` seven rubric criteria and the lowest-score thresholds; `03` the stage checklists and conflict-of-interest declaration; `04` the pair checklist, marking code-checked and human-only items; `05` review stages, adjudication, accept/revise/reject rules and the solo fallback; `06` identifiers, versions, cohorts, supersession, post-pilot revision rule and append-only logs.
- The alternative list pulls in work that belongs elsewhere or cannot be settled: a schema document overlaps Stage 4J.2 and the undecided `SCHEMA_EXTENSION`; a receiver prompt overlaps the protected `src/maps/prompts/receiver.py`; an analysis plan needs `MEANINGFUL_EFFECT_THRESHOLD`, `C0_TOLERANCE` and policy values that are undecided; evidence and message rules already sit in `01` and `04`.
- **Recommendation:** the original list is authoritative. The Stage 4I.37 task-prompt listing is recorded as a discrepancy and does not change scope.

### Metadata lifecycle: Option B stands

Re-checked against the brief (line 7869, section 5), the v2.3.96 gate conditions 3 and 4 (line 7902), the Stage 4I.30 decision (line 8284) and the manifest proposal. Option B (both approval fields `PENDING` until final approval) remains the most consistent. No record contains an owner instruction to name the approver before drafting.

Superseded by the amendment if accepted: gate conditions 3 and 4 only. Unchanged: conditions 1, 2, 5 and 6.

Roles and dates, kept apart:

| Item | Meaning | At drafting |
|---|---|---|
| Designated approver | Who is meant to approve | The `project owner`, the sole researcher (ROLES decision). No name. |
| Actual approver | Who approved the final protocol | `PENDING OWNER CONFIRMATION` |
| Documents drafted on / manifest generated on | The actual days the files are written | Real dates |
| Final approval date | Actual date of approval | `PENDING FINAL PROTOCOL APPROVAL` |
| Stage 4J.1 authorization date | When the owner authorized drafting | Recorded in the ledger, not in the approval block |

Does a pending approver make the manifest ambiguous about who is responsible? The role is not in doubt, because every approval in this ledger is the project owner's. Only the name is missing. An optional manifest field `approval.required_approver_role` set to `project owner (sole researcher)` removes the ambiguity without inventing a name. These are manifest content fields, not a repository schema extension, and no validator exists. A `designated_approver` name field is only for Option C. The protocol is approved by the sole author, so that approval is not independent review and the documents must say so.

### Digest and approval lifecycle findings

- The project's canonical method is in `src/maps/runs/provenance.py:73-75` and `tests/synthetic/synthetic_support.py:278-280`: SHA-256 of the UTF-8 text of lines `<posix path>:<hex>`, sorted by path, joined by `\n` with no trailing newline, each hex being the SHA-256 of the file's raw bytes.
- **Proposed digest definition (inspected conceptually, not validated, no hash computed):** the seven documents `01`-`07`, with paths relative to `protocol/scenario_v1/` and no directory prefix.
1. The manifest is excluded from the combined digest, because a file cannot contain its own hash.
2. Filling the approval block changes the manifest's own SHA-256 and not the combined document digest.
3. The final approval record must name the exact combined digest, and also the draft manifest's SHA-256, because the combined digest does not cover the manifest's other fields (version, dates, sizes).
4. A manifest-only update therefore preserves the identity of the approved document contents, but not the manifest fields. The draft and approved manifest hashes are both recorded outside the repository. An in-repository receipt is only a consistency aid.
5. Approval comes after hashing and manifest generation and refers to the digest, so there is no ordering ambiguity. Any edit to a document after hashing produces a new digest and needs a new approval.
- **Sequence:** document drafting → document hashing → manifest generation → owner review → explicit approval naming the exact combined digest (and draft manifest hash) → approval-block update → manifest hash recomputation → independent verification of the final manifest. Steps 1-3 are Stage 4J.1. Steps 5-8 are a separate, later act that needs its own permission.
- **Revision rounds.** If the owner asks for edits during review, each round creates a new digest. The request below carries an optional clause for revision rounds within the same files, which the owner may strike.

### Stage 4J.1 authorization request, version 3 (supersedes the Stage 4I.37 draft; NOT PRESENTED; NOT RECORDED)

Presented only after Decisions A and B are answered.

> **Stage:** `STAGE_4J.1` — drafting and hashing the protocol documents only.
> **Files (all new), in `protocol/scenario_v1/`:** `01_authoring_protocol.md`, `02_quality_rubric.md`, `03_reviewer_checklists.md`, `04_pair_construction_checklist.md`, `05_review_and_adjudication.md`, `06_versioning_change_control.md`, `07_answer_key_custody.md`, `PROTOCOL_MANIFEST.json`. The only existing file modified is `docs/stage_reports/owner_decision_ledger.md`.
> **Purpose:** restate the individually owner-approved rules recorded in the ledger and draft the procedural content (checklists, versioning and change control). Drafted procedural content is not approved. Each document carries a version line and a status line `DRAFT — NOT APPROVED`. Undecided items appear as pending placeholders, not decisions.
> **Status statements:** this authorization permits only drafting and hashing. It is **not** protocol approval. The protocol remains **NOT APPROVED** until a separate explicit final approval. The manifest approval block stays `PENDING`. Completion does not freeze the design or any scenario, authorizes no schema change and no later Stage 4J stage.
> **Prohibited:** every other change; Stages 4J.2-4J.7; schema, code, configuration, test, scenario, evidence, export and protected-source changes; answer-key movement; any freeze; provider calls, experiments and spending.
> **Required checks:** recompute each file's SHA-256 and the combined digest (definition above); parse the manifest as JSON; `git diff --check`; `git status --short` showing only the new directory and the ledger; recompute the protected-source digest and the golden manifest file hash against their last recorded values, reporting each as newly verified only if it was actually performed (the golden, fixture and helper digests are not covered); read-through that every rule in the documents matches the ledger.
> **Completion evidence:** a report with each file's size and SHA-256, the combined digest and the manifest SHA-256 for the owner to record outside the repository, check results, and what was not done.
> **[OPTIONAL — owner may strike]** Revision rounds at the owner's request before approval, limited to the same eight files, each with a new digest.
> **Owner response:** `AUTHORIZE STAGE_4J.1` or `DO NOT AUTHORIZE STAGE_4J.1`. Silence, a recommendation or approval of another decision is not authorization.

### Minimum owner decisions

| Decision | Recommendation | Evidence | Owner response required? | Blocks 4J.1? |
|---|---|---|---|---|
| A. Approval metadata and gate amendment | Option B; supersede conditions 3 and 4 only | Brief line 7869; gate line 7902; Stage 4I.30 line 8284 | Yes | Yes |
| B. Authoritative file list | The original list | Lines 7869 and 7902; alternative only at 8920 | Yes (confirmation) | Yes |
| C. Authorization | Presented only after A and B | n/a | Yes | n/a |

- **A.** `ACCEPT PROPOSED: Option B and the Stage 4I.37 gate amendment as written`, or `OWNER AMENDMENT: <exact text>`, or `UNRESOLVED — NEEDS DISCUSSION`.
- **B.** `ACCEPT PROPOSED: original Stage 4J.1 file list`, or `OWNER AMENDMENT: <file list>`.
- **C.** `AUTHORIZE STAGE_4J.1` or `DO NOT AUTHORIZE STAGE_4J.1`. Do not answer it in the same message as A and B unless you want to; it is a separate decision.

### Readiness determination

**OWNER DECISIONS REQUIRED.** A and B need explicit owner responses, and the records do not let me close either: the gate asks for values that the later Stage 4I.30 decision says cannot exist yet, and the latest owner prompt names different files from every earlier source. No other prerequisite is open. Stage 4J.1 stays NOT AUTHORIZED, the protocol stays NOT APPROVED, and all seven Stage 4J stages stay NOT AUTHORIZED.

---

## Stage 4I.39 — final owner decision package for Stage 4J.1 (NO OWNER RESPONSE RECEIVED; PROTOCOL NOT APPROVED; STAGE_4J.1 NOT AUTHORIZED)

No owner response to Decisions A, B or C has been received. No protocol approval and no Stage 4J.1 authorization has occurred. Nothing below is an owner decision.

### Verification of the Stage 4I.38 conclusions against the original records

| Conclusion | Original record | Result |
|---|---|---|
| The original eight-file list is the one in the brief and the owner's gate | Transcript line 7869 (brief, section 5) and line 7902 (v2.3.96, section 6) | Confirmed |
| The alternative list has no earlier source | A scan of the transcript finds its first mention at line 8920 (the Stage 4I.37 task prompt) | Confirmed; no owner decision changed the names |
| The approval date is the actual final approval date and the name belongs to the final approval record | Line 8284 (Stage 4I.30): `APPROVAL_DATE` "must represent the actual final protocol approval date", marked `PENDING FINAL PROTOCOL APPROVAL`; `APPROVER_NAME` is "the exact name to appear in the final protocol approval record" | Confirmed |
| The brief records the date and approver after the owner approves, and its "approved before creation" list omits both | Line 7869, section 5 | Confirmed |
| Every 4J.1 decision row is decided | The brief's rows B1 roles, B2 solo fallback, B3 authoring timing, B4 existing ten, B5 rubric thresholds, B6 length tolerances, B7 false-value rule, B8 cue review, B10 custody, B11 domains, B12 review procedure map to ROLES, SOLO_FALLBACK, AUTHORING_TIMING, EXISTING_TEN, RUBRIC_THRESHOLDS, LENGTH_TOLERANCES, FALSE_VALUE_RULE, MACHINE_CUE_CHECK, ANSWER_KEY_CUSTODY, DOMAIN_LIST and REVIEW_PROCEDURE in Groups 1, 2 and 4 of this ledger | Confirmed. B9 (schema extension) is a 4J.2 input, not a 4J.1 one. |

### Hidden prerequisite check

- **One item needs an explicit statement.** The brief's section 4 row for 4J.1 ends "plus versioning and change-control wording" (line 7869). Read literally, the wording of document 06 is a 4J.1 prerequisite, and no owner decision approves it. Stage 4I.36 treated it as drafted by 4J.1 and approved only at final protocol approval. That was my interpretation. To remove the doubt without a fourth question, the authorization request below states the principles that document 06 will contain, taken from the brief's section 5. Authorizing it is then your instruction for what 06 is drafted to say. It is not approval of the wording. If you read the row literally, say so and I will present it as a separate decision.
- **Later-stage decisions that do not block 4J.1:** `SCHEMA_EXTENSION` (before 4J.2), `MEANINGFUL_EFFECT_THRESHOLD` and `C0_TOLERANCE` (before any pilot results), the evidence-length formula, the direction-balance measure and the avoid-extremes test (before 4J.3), the answer-key destination (before 4J.4; document 07 marks it `NOT YET DESIGNATED`), pilot and confirmatory execution, provider configuration and spending. None is cited as a 4J.1 prerequisite by the brief or the gate.

### Decisions (recommended, not accepted)

**A. Approval metadata and gate amendment.** Recommended: Option B. Recommended amendment, exact wording:

> For Stage 4J.1 only, conditions 3 and 4 of the v2.3.96 readiness gate are superseded. The approver name and the approval date are not required to draft and hash the protocol documents. They are required for the final protocol approval record and remain PENDING OWNER CONFIRMATION and PENDING FINAL PROTOCOL APPROVAL until that approval. All other gate conditions remain unchanged.

It names conditions 3 and 4 only. Conditions 1 (decisions approved), 2 (directory specified), 5 (Stage 4J.1 explicitly authorized) and 6 (no unresolved decision changes scope) are not waived. Document and manifest dates record the actual creation dates; the Stage 4J.1 authorization date is recorded in the ledger and is not protocol approval; the manifest approval block reads `NOT APPROVED`. Owner response: `ACCEPT PROPOSED: Option B and the Stage 4J.1 gate amendment exactly as written`, or `OWNER AMENDMENT: <exact replacement text>`, or `UNRESOLVED — NEEDS DISCUSSION`.

**B. File list.** Recommended: the original list in `protocol/scenario_v1/` — `01_authoring_protocol.md`, `02_quality_rubric.md`, `03_reviewer_checklists.md`, `04_pair_construction_checklist.md`, `05_review_and_adjudication.md`, `06_versioning_change_control.md`, `07_answer_key_custody.md`, `PROTOCOL_MANIFEST.json`. The only existing file modified is `docs/stage_reports/owner_decision_ledger.md`. Owner response: `ACCEPT PROPOSED: original Stage 4J.1 file list`, or `OWNER AMENDMENT: <exact file list>`.

**C. Stage 4J.1 authorization (separate).** Accepting A and B is not authorization, and authorization is not protocol approval. The request is the Stage 4I.38 request, version 3, verbatim, with one clause added to its Purpose:

> **Document 06 drafting scope:** document 06 will state that each document carries a version line; that the manifest records every document's SHA-256 and the combined digest by the project's canonical method; that the digest is reported to the owner for recording outside the repository; and that any later edit creates a new protocol version, with no document edited in place after final approval. It will also cover identifiers, cohorts, supersession, the post-pilot revision rule and append-only logs, all marked draft.

Owner response: `AUTHORIZE STAGE_4J.1` or `DO NOT AUTHORIZE STAGE_4J.1`. Silence, a recommendation or acceptance of A or B is not authorization.

### Readiness

The package is ready to put to the owner. The authorization request can be answered once A and B are answered. Stage 4J.1 stays NOT AUTHORIZED, the protocol stays NOT APPROVED, and all seven Stage 4J stages stay NOT AUTHORIZED. Every prohibition above is unchanged.

---

## Stage 4J.1 — completion record (protocol documents DRAFTED and HASHED; PROTOCOL NOT APPROVED)

### Owner decisions and authorization (recorded exactly)

All three decisions were given by the owner in the interactive session of 2026-11-08, then restated in the Stage 4J.1 implementation prompt.

| Decision | Owner response | Status |
|---|---|---|
| A — approval metadata and gate amendment | `ACCEPT PROPOSED: Option B and the Stage 4J.1 gate amendment exactly as written` | Accepted |
| B — file list | `ACCEPT PROPOSED: original Stage 4J.1 file list` | Accepted |
| C — authorization | `AUTHORIZE STAGE_4J.1` | Authorized. **Authorization date: 2026-11-08.** |

**Accepted gate amendment (exact):** "For Stage 4J.1 only, conditions 3 and 4 of the v2.3.96 readiness gate are superseded. The approver name and the approval date are not required to draft and hash the protocol documents. They are required for the final protocol approval record and remain PENDING OWNER CONFIRMATION and PENDING FINAL PROTOCOL APPROVAL until that approval. All other gate conditions remain unchanged." Conditions 1, 2, 5 and 6 were not waived.

**Accepted metadata lifecycle (Option B):** approver identity and protocol approval date stay pending until final protocol approval; document and manifest dates are the actual dates; the Stage 4J.1 authorization date is recorded here and is not protocol approval; the manifest approval status is `NOT APPROVED`.

**Accepted file boundary:** the eight files below, and the only existing file modified is this ledger.

**Distinctions.** The authorization above is permission to draft and hash. It is not protocol approval, not a design or scenario freeze, not a schema change, and not permission to run any experiment, provider call or spending. It authorizes no later Stage 4J stage.

### Files created (all new, in `protocol/scenario_v1/`)

| File | Bytes | SHA-256 (of the file's bytes) |
|---|---|---|
| `01_authoring_protocol.md` | 12390 | `403038be6c59498846bb0e2625a81b68d4a2f415761c42dca0ed011b6f29cd39` |
| `02_quality_rubric.md` | 4300 | `5945f5b5e39df6224c1b0ee87815836ae8d17d2a118e12dc3ee3add79c7736fb` |
| `03_reviewer_checklists.md` | 4871 | `8e500c53e0d08820ad1a3df19eab8c824a5c156db0394f115ca82f955b302c97` |
| `04_pair_construction_checklist.md` | 4439 | `f35e501ba90c7d310fc46dad9f43d40697f1effaaabf186f5377f147414f4de8` |
| `05_review_and_adjudication.md` | 5779 | `652e7d4b84a5e35e67dfca26167b9d93afe992d5a176efe3b10b20d201e83cb9` |
| `06_versioning_change_control.md` | 6287 | `d31744270a84aa09286185de9afd99a4d387d86a772d6dc7cb376220759a80a2` |
| `07_answer_key_custody.md` | 3617 | `128c7ba2ffb46d4cd52c928ed051309b42c72e23d7f538c4235c2c71a3060a32` |
| `PROTOCOL_MANIFEST.json` | see below | see below |

Three kinds of hash, kept distinct:

- **Individual document hashes:** the seven values above.
- **Combined document digest:** `e7f42387c396fc089c12e40b2a16b35dfcb6eafa2958d08b87cf741529e0a125`. Method: SHA-256 of the UTF-8 lines `<path relative to protocol/scenario_v1/>:<sha256 hex>`, sorted by path, joined by `\n`, no trailing newline, covering documents 01 to 07 only (the project's existing method, `src/maps/runs/provenance.py` `_combined`, and `tests/synthetic/synthetic_support.py` `combined_digest`). The manifest is excluded.
- **Manifest SHA-256:** `13ac34d98886433fabe635346c651f04c121748065b31c6509aa7ce2b960393c` (the draft manifest, computed separately after it was written; the manifest cannot contain its own hash).

The owner records the combined digest and the manifest SHA-256 outside the repository. The external location is not designated.

An earlier hash set, with combined digest `c2bb2ffeb0449afa2a39c00df28060bc9f7ee2f828cf2760eb24f346df818129`, was computed before three corrections of documents 01, 02 and 05 (labels that had marked drafted wording as approved) and is **superseded**. It was never recorded elsewhere.

### Manifest approval block as created

`status` = `NOT APPROVED`; `required_approver_role` = `project owner (sole researcher)`; `approved_by` = `PENDING OWNER CONFIRMATION`; `approved_on` = `PENDING FINAL PROTOCOL APPROVAL`. `documents_drafted_on` and `manifest_generated_on` are both 2026-11-08.

### Verification results

| Check | Result |
|---|---|
| All eight expected files exist; no other file created | Performed: PASS (`protocol/scenario_v1/` holds exactly eight files) |
| SHA-256 of each document recomputed with a second tool (`shasum -a 256`) and compared with the manifest, with byte sizes | Performed: PASS (7 of 7 match) |
| Combined digest recomputed through a separate shell route and compared | Performed: PASS (matches the manifest) |
| Manifest parses as JSON | Performed: PASS |
| Manifest SHA-256 computed separately | Performed |
| `git diff --check` | Performed: exit 0, no output |
| Whitespace check of each new file | Performed: no warnings |
| `git status --short` | Performed: 25 untracked entries (24 earlier plus `protocol/`); no tracked file modified |
| Protected-source digest (the 27 source files, same method as the receipt) | Performed: `83ad044c5ae55cb3542ef45a7bc9c925f6c0b03294ec1567ef4ed950a543f360`, equal to the receipt's `source_digest` (newly verified) |
| Golden manifest file hash | Performed: `148c975e92bbdbc981f6859f694d44b46811fb3a174067fdb8d72d7556ea6a2c`, equal to the receipt's `manifest_sha256` (newly verified) |
| Golden, fixture and helper digests | NOT RUN: not recomputed; not covered by the two checks above |
| HEAD | `f24c47c37f29214eec074ae218af07a2cb095d3f`, unchanged |
| Rules in the documents against this ledger | Performed as a read-through plus a key-value text search (50 years, ±15%, ±10%, 0.15, factor of two, 15 accepted, 20 authored, minimum four pairs, thresholds, pending markers). No mismatch found. This is not a formal diff. |
| Content check | Performed: a search of the documents for scenario entity names and the recorded values found none; the answer key and `.env` were not opened |
| Tests, validators, scoring, model or provider calls, experiments | NOT RUN: not authorized |

The digest design was checked by recomputation with a second tool. It was not independently audited by another person.

### Unresolved items and limitations

- The documents are drafts. Drafted procedural wording (marked `[DRAFTED]`) is not owner-approved.
- Pending, as marked in the documents: scoring scale and level descriptors; final criterion definitions; adjudication trigger; `SCHEMA_EXTENSION`; `FREEZE` definition; evidence-length formula; direction-balance measure; "avoid extremes" test; name-collision procedure; confirmatory domains; answer-key destination; git-history exposure check; external storage location for digests; cohort identifier scheme; approval step wording; revision-round permission.
- Source note carried into documents 03 and 07: the blinded-package README says "Do not open the answer key until all items are reviewed", which conflicts with the approved custody rule. It was not modified.
- `MEANINGFUL_EFFECT_THRESHOLD`, `C0_TOLERANCE` and the policy values are not part of these documents and remain pending.

### Status

Protocol: **NOT APPROVED**. Stage 4J.1: complete (drafted and hashed). Stages 4J.2 to 4J.7: **NOT AUTHORIZED**. Pilot and confirmatory execution, design freeze, scenario freeze, provider calls and spending: **NOT AUTHORIZED**. The final refusal is unchanged.

---

## Stage 4J.2 — implementation record (schema and cohort registry IMPLEMENTED; PROTOCOL NOT APPROVED; no freeze)

### Owner decisions and authorization (recorded exactly)

All four were given by the owner in the interactive session of 2026-11-08 and restated in the Stage 4J.2 implementation prompt.

| Decision | Owner response |
|---|---|
| A — schema extension scope | `ACCEPT PROPOSED: necessary-only schema extension` |
| B — cohort and pilot-exposure semantics | `ACCEPT PROPOSED: preserve A4 and B3; implement explicit cohort and pilot-exposure traceability` |
| C — review and adjudication records | `ACCEPT PROPOSED: independent reviewer records and auditable adjudication` |
| D — authorization | `AUTHORIZE STAGE_4J.2` — **authorization date: 2026-11-08** |

Accepting B fixed the freeze terms used by the schema: **pilot-family content freeze** (after authoring, rule checks and hashes; no independence claim), **confirmatory content freeze** (after independent review), and **design freeze** (a separate owner decision, not implemented). Authorization covers the implementation scope only. It is not protocol approval, not a design or scenario freeze, and authorizes no experiment, provider call, spending or later stage.

**Authorized file boundary.** Modify: `src/maps/schemas.py`, `tests/synthetic/data/golden/golden_manifest.json`, `tests/synthetic/audit/manifest_receipt.json`, this ledger. Create: `src/maps/registry.py`, `tests/test_review_records.py`, `tests/test_cohort_registry.py`, one archived manifest under `tests/synthetic/audit/manifests/`. A search for files newer than the Stage 4J.1 ledger record found exactly these files and no others (before this ledger edit).

### Preflight findings

- Repository root and HEAD `f24c47c37f29214eec074ae218af07a2cb095d3f` (unchanged). 25 untracked entries and no tracked changes at the start; 26 untracked at the end (the new `src/maps/registry.py`; the new test files sit inside the already-untracked `tests/` directory).
- The Stage 4J.1 combined digest (`e7f42387…a0125`) and manifest hash (`13ac34d9…393c`) recomputed to the recorded values, and the protocol files are unchanged by this stage.
- **Report versus repository.** Earlier reports said the ledger was "modified" while `git status` showed no tracked changes. That is consistent: the whole `docs/` directory is untracked, so the ledger has never been tracked. The Stage 4J.1 completion record exists. No discrepancy needed resolving.
- Baseline before any change: 2002 non-synthetic tests passed and 229 guarded synthetic tests passed.
- Points where the Stage 4J.2 prompt differs from the ledger, recorded and not corrected: it says "30 authored scenarios" while the approved `SCENARIO_COUNT` is a target of 15 accepted pairs (30 scenarios) and at most 20 authored pairs (40); it calls `PILOT_SCENARIO_POLICY` `EXCLUDE`, while the approved wording is "use only existing pilot-family pairs…; no pilot scenario reused in confirmatory".

### Schema changes (`src/maps/schemas.py`)

- `ScenarioStatus` gains `pilot_frozen`. `frozen` keeps its meaning and its legacy gates.
- New optional `Scenario` fields: `scenario_version` (default 1), `supersedes` (default none, format `<scenario_id>@<version>`, must name an earlier version if it names the same scenario), `author_id` (opaque identifier; letters, digits, `.`, `_`, `-`; no spaces), `reviewer_assignments`, `conflict_declarations`, `review_submissions` (all default empty lists), `adjudication` (default none). `schema_version` stays `2.1-draft`.
- Review records: assignments (reviewer id, stages, date); declarations (authored or edited, had truth-label information, other conflict, date); submissions (reviewer, one of the four stages, timestamp with UTC offset, per-criterion non-negative integer scores over the seven approved criteria, optional form hash, notes). Duplicate submissions per reviewer and stage are rejected so an original is never overwritten. A submission needs an assignment for that stage.
- Adjudication is a separate record. Its presence means adjudication is required; it is resolved only with adjudicator, date, outcome and a rationale or evidence reference all present. It is dated after every submission, the author cannot adjudicate, and it never alters a submission.
- `qualifying_independent_reviewers` counts a reviewer only if assigned and submitted all four stages, filed a clean declaration no later than their first submission, and is not the author. If `author_id` is unknown nobody qualifies. The required minimum is 2 (`MIN_INDEPENDENT_REVIEWERS`).
- `pilot_frozen` needs evidence at least `author_checked`, `evidence.sha256`, and `independence_confirmed` not true.
- `frozen` still needs the legacy conditions and now also `author_id`, at least 2 qualifying independent reviewers, and an adjudication that is resolved with outcome `accept` where one exists.

Implementation choices made inside the accepted scope, for the owner to confirm or amend: a `frozen` scenario needs a known `author_id`; an adjudication outcome of `revise` or `reject` blocks `frozen`; declarations must precede the first submission; a submission requires a matching assignment; `independently_checked` keeps its legacy gate (no downstream code gates on it).

Not implemented, by instruction: a mechanical adjudication trigger, score ranges and thresholds (the scoring scale is pending), any authoring timestamp, review-log versioning.

### Registry (`src/maps/registry.py`, new; not in the protected import closure)

- Models: cohort (id, family `pilot` or `confirmatory`, member scenario versions, fixed time), pilot-exposure event (scenario version, run id, time, note) and supersession (lineage) entries. Validators: unique cohort ids; no version in both a pilot and a confirmatory cohort; one parent per version; no self-supersession or cycles; no duplicate exposure events; exposure not before its pilot cohort was fixed.
- A confirmatory cohort is rejected if any member is in a pilot cohort or exposed to a pilot run, or descends through supersession from such a version. Because history is read through the lineage, a new version or a cohort change cannot erase it. This is checked when a registry is built, so an ineligible registry cannot be loaded.
- `check_registry` cross-checks against loaded scenarios: members exist, form whole true/false pairs, scenario `supersedes` fields agree with the lineage and are merged into the eligibility check, and each confirmatory member has status `frozen` with no outstanding independent-review problems. A registry entry is never taken as proof of review.
- The rule covers pilot-cohort and exposed ancestors and the three required rejections. It does not reject a confirmatory ancestor of an exposed version; that stricter reading was not specified.
- Not done: no real registry data file was created, nothing is wired into the runner, and no cohort was fixed.

### Tests

| Command | Exit | Result |
|---|---|---|
| New tests (`tests/test_review_records.py`, `tests/test_cohort_registry.py`) | 0 | 54 passed |
| Schema-related existing tests (`test_schema`, `test_scenarios`, `test_review_export`, `test_design`) | 0 | 117 passed |
| Whole non-synthetic suite (`pytest tests --ignore=tests/synthetic`) | 0 | 2056 passed (2002 baseline plus 54 new) |
| Guarded synthetic suite (`tests/synthetic/tools/run_synthetic.py`) | 0 | 229 passed; write guard verified the golden and audit files unchanged |

Before the manifest refresh the guarded synthetic suite had 5 failures, all of the form "source file digest differs: schemas.py". They were the expected consequence of changing a protected source and were fixed by the authorized refresh. No test was edited, weakened or skipped. No provider call was made; the suite uses the mock client.

### Protected manifest and receipt refresh

Canonical procedure: `tests/synthetic/tools/record_goldens.py --refresh-manifest --confirm-authorized --reason … --expect-old-manifest-sha256 …`, after a dry run.

| Item | Before | After |
|---|---|---|
| `golden_manifest.json` SHA-256 | `148c975e92bbdbc981f6859f694d44b46811fb3a174067fdb8d72d7556ea6a2c` | `31ed361f2ea585512657c5aeb1f9ca0ec8345b3ff1a00facef991933d6684a86` |
| Protected-source digest (27 files) | `83ad044c5ae55cb3542ef45a7bc9c925f6c0b03294ec1567ef4ed950a543f360` | `a4253ee58ed796a50e8b9a4cf80221f1b7df3f80c8c8478fdfe1c28a87f59b6f` |
| `schemas.py` SHA-256 | not recorded before | `c98d390c073ba86222f118903a279e3746482dc4a18f933b52a74d6710e3ca25` |
| `manifest_receipt.json` SHA-256 | `fcd20e1a6f28c733aea01ea75ab1bb939fd04997d31551190cfc2878205e48b4` | `f97b53fb089ae964f3bb79f6a440677fe6c9e38d7a12cc27934b19c04f9c45a3` |
| Fixture, goldens and helper digests | `c848fde6…a221d`, `1c35b2c5…446af`, `de095e57…6596` | unchanged |

- `schemas.py` is the only protected source that changed. `registry.py` is not in the source set, so the set still has 27 files.
- **Goldens unchanged.** The tool re-derived the goldens in a temporary directory and found them byte-identical (`episodes.jsonl` `4f8aff63…`, `grid.tsv` `b5a812da…`, `run_summary.json` `5d3823f8…`). No golden content was updated.
- **Archived manifest:** `tests/synthetic/audit/manifests/golden_manifest.148c975e92bbdbc981f6859f694d44b46811fb3a174067fdb8d72d7556ea6a2c.json`, SHA-256 `148c975e92bbdbc981f6859f694d44b46811fb3a174067fdb8d72d7556ea6a2c` (a byte copy of the old manifest).
- Receipt reason: "MAPS Stage 4J.2: schemas.py extended with optional scenario traceability fields, independent-review records and the pilot_frozen status; no golden content change". `previous_manifest_sha256` records the old value.
- Independent recomputation: the source digest recomputed from the 27 files equals the receipt and the manifest; the golden manifest file hash equals the receipt. The in-repository receipt is a consistency aid. The owner should record the new manifest hash outside the repository.

### Compatibility

All ten scenario files load unchanged with defaults. They remain `draft` and unverified, so the pinned test that requires that still passes. The blinded export is a whitelist, so new fields do not reach reviewer packages. `receiver.py`, `scenarios.py`, the exports, the scenario files, the protocol documents, the answer key and `.env` were not touched.

### Limits and remaining dependencies for Stage 4J.3

- `git diff` could not be shown for `schemas.py`, since the repository tracks no source files; the change is described above.
- The existing ten have no `author_id`, so author-versus-reviewer checks apply only to new or revised scenarios.
- Stage 4J.3 inputs still pending: the scoring scale and level descriptors, the adjudication trigger, the evidence-length formula, the direction-balance measure, the "avoid extremes" test, the name-collision procedure, and wiring the registry and the cohort rule into runtime checks.
- Protocol documents 03 and 05 still say the schema work is "not implemented" and need a later protocol revision (new version, new digest); the protocol files were not changed.
- Stages 4J.3 to 4J.7 remain NOT AUTHORIZED.

---

## Stage 4J.3 — implementation record (mechanical validation and runtime integration IMPLEMENTED; PROTOCOL NOT APPROVED; no freeze)

### Owner decisions and authorization (recorded exactly)

Given by the owner in the interactive session of 2026-11-08 and restated in the Stage 4J.3 implementation prompt (authorization date 2026-11-08).

| Decision | Owner response |
|---|---|
| A — scoring scale | `ACCEPT PROPOSED: 0-3 scale with the stage-to-criteria mapping and minimum-across-reviewers aggregation as written` ("Accept 0-3 scale (Recommended)") |
| B — adjudication | `ACCEPT PROPOSED: adjudication trigger and procedure as written (B1)` ("Accept B1, no rescue path (Recommended)") |
| C — evidence length | `ACCEPT PROPOSED: evidence-length formula as written` |
| D — direction balance and avoid-extremes | `ACCEPT PROPOSED: direction-balance and avoid-extremes definitions as written` |
| E — name collisions | `ACCEPT PROPOSED: name-collision procedure as written` |
| F — runtime integration | `ACCEPT PROPOSED: main-stage fail-closed registry validation and the file boundary as written` |
| G — discrepancies | `ACCEPT PROPOSED: discrepancy resolutions 1-6 as written, including the outcome-exclusion clarification` |
| H — authorization | `AUTHORIZE STAGE_4J.3` |
| Boundary amendment (asked during implementation) | `OWNER AMENDMENT: the Stage 4J.3 boundary also permits updating the pinned expectations in tests/provider_routes/test_pr_receiver.py (add '--registry' to the flag set) and tests/live_policy/test_lp_boundaries.py (27 to 29 protected files), and nothing else in them.` ("Allow the two test updates (Recommended)") |

The amendment was needed because wiring `--registry` into `receiver.py` made registry and validation part of the protected import closure and added a command-line flag, and both of those tests pin exact expectations and say "update only for an authorized change". It was asked rather than assumed. Authorization is limited to this implementation scope. It is not protocol approval, not a design, scenario, cohort, pilot-family or confirmatory freeze, and authorizes no experiment, provider call, spending or later stage.

### Preflight

Repository root; HEAD `f24c47c37f29214eec074ae218af07a2cb095d3f` (unchanged); 26 untracked entries and no tracked changes at the start (27 at the end: the new `src/maps/validation.py`). The Stage 4J.1 and 4J.2 records are present; the ledger held no earlier Stage 4J.3 record, so the gate decisions above are recorded here for the first time. The Stage 4J.2 baseline matched: manifest `31ed361f…`, receipt `f97b53fb…`, source digest `a4253ee5…`. Baseline tests before any change: 2056 non-synthetic and 229 guarded synthetic passed.

### Workstreams actually used

| Workstream | Executed by | Files owned |
|---|---|---|
| 1 Schema and review records | Main session | `src/maps/schemas.py`, `tests/test_review_records.py` |
| 2 Mechanical validation | A background agent | `src/maps/validation.py`, `tests/test_mechanical_validation.py` (the agent ran only its own test file) |
| 3 Registry and runtime integration | Main session | `src/maps/registry.py`, `src/maps/experiments/receiver.py`, `tests/test_cohort_runtime.py` |
| 4 Read-only compatibility audit | A background agent (wrote nothing) | none |
| Integration | Main session | `tests/synthetic/synthetic_support.py`, the two amended pinned tests, golden manifest, receipt, archived manifest, this ledger |

Workstreams 1 and 3 and the integration ran in the main session, in sequence, while the two agents worked. The audit found the two pinned tests above and the placement constraints on the new gate (it must follow `_load_inputs`, must not touch the last three statements of `main`, and must not test `args.mock` alone). The Workstream 2 agent reported that the brief it was given contradicted itself on direction balance ("3/1 passes" against "differ by at most 1"); it implemented the accepted rule, so 3 over and 1 under fails.

### Files

- **Modified:** `src/maps/schemas.py`, `src/maps/registry.py` (4J.2 file extended), `src/maps/experiments/receiver.py`, `tests/synthetic/synthetic_support.py`, `tests/test_review_records.py`, `tests/live_policy/test_lp_boundaries.py` (one line and its comment), `tests/provider_routes/test_pr_receiver.py` (one flag), `tests/synthetic/data/golden/golden_manifest.json`, `tests/synthetic/audit/manifest_receipt.json`, this ledger.
- **Created:** `src/maps/validation.py`, `tests/test_mechanical_validation.py`, `tests/test_cohort_runtime.py`, `tests/synthetic/audit/manifests/golden_manifest.31ed361f2ea585512657c5aeb1f9ca0ec8345b3ff1a00facef991933d6684a86.json`.
- Nothing else changed by this stage: the ten scenario files, the evidence files, the protocol documents (combined digest `e7f42387…a0125`, unchanged), the answer key, the exports and the configuration were not touched. A scan for files newer than the previous ledger edit found the files above and one more, `.env`, whose modification time (2026-11-08 18:04) precedes this stage's work. I did not open, read or modify `.env`.

### Implemented behavior

- **Scale (A):** integer scores 0 to 3; each stage scores exactly its own criteria (fact: truth, ambiguity; cue: cues, equivalence; pair: pair; independence: provenance, manipulation); the seven criteria are unchanged. The operative score of a criterion is the minimum across qualifying independent reviewers. Approved thresholds apply to it: at least 3 for truth, manipulation, cues, provenance; at least 2 for pair, equivalence, ambiguity. No "not applicable" score exists.
- **Adjudication (B1):** triggered by a score of 0 from a qualifying reviewer, or two qualifying reviewers differing by 2 or more points on a criterion. Outcomes are `revise` or `reject` only (`accept` is no longer an outcome). It never raises a score. The adjudicator must not be the author or a reviewer of that scenario and needs a clean conflict declaration filed no later than the decision. The record must be dated after every submission. `frozen` now requires at least 2 qualifying reviewers, no operative score below its threshold, no unresolved trigger, and no adjudication record at all, since an adjudication can only end in revise or reject. `pilot_frozen` is unchanged.
- **Mechanical checks (`validation.py`):** evidence length (whole file in characters, LF-normalized, trailing blank lines removed; pairs pass when the relative difference to their mean is at most 0.10, compared exactly; no absolute limits; a repetition flag); direction balance (each current ratio-scale pair counted once, over and under differing by at most 1, year pairs reported separately, "year" meaning the claim attribute contains the word "year"); the hard bounds as automatic failures (factor 2, 50 years, same format); the four screening flags (digit-count mismatch, round mismatch, false value 0 or 1, integer versus non-integer) as human-review flags only, with justified exceptions that can downgrade a flag but never remove a failure; name-collision detection (NFKC, case-fold, combining marks removed, whitespace and punctuation collapsed, control, zero-width and bidirectional characters refused, hard collisions as failures, edit distance 1 as a flag, shared origins inside one pair allowed, `clear` inconsistent with a hard collision a failure). Nothing is claimed to be empirically validated.
- **Runtime (F):** `receiver.py` gained `--registry PATH`. For `output.stage == "main"` it is required, and the run is refused (exit 2) before any run directory unless the registry loads, passes `check_registry`, assigns every loaded scenario to a confirmatory cohort, and the mechanical set has no automatic failure. For other stages a given registry is only validated. The check runs after `_load_inputs`, so the existing "main stage requires frozen scenarios" refusal still comes first. Messages withhold details because they can contain scenario values. Nothing is assigned, frozen or written; pilot exposure remains a manually recorded event.

### Expectation changes disclosed (not weakenings)

- `tests/test_review_records.py`: Stage 4J.2 tests used arbitrary scores such as `{"truth": 3, "cues": 2}` on every stage and an `accept` outcome. They were rewritten to the accepted scale and mapping, and the tests that expected a resolved `accept` to permit `frozen` were replaced by tests of the new rule (any adjudication blocks `frozen`). New tests cover the scale bounds, the stage mapping, minimum aggregation, thresholds, triggers, adjudicator rules and the unchanged `pilot_frozen`.
- `tests/live_policy/test_lp_boundaries.py`: pinned protected-source count 27 to 29. `tests/provider_routes/test_pr_receiver.py`: `--registry` added to the pinned flag set. Both authorized by the amendment above.
- `tests/synthetic/synthetic_support.py`: `registry.py` and `validation.py` added to `SOURCE_FILES`, as the existing static-closure test requires.

### Tests (exit codes captured)

| Command | Exit | Result |
|---|---|---|
| `tests/test_mechanical_validation.py` | 0 | 64 passed |
| `tests/test_cohort_runtime.py` (run-boundary functions and the real `receiver.main`, no mocks) | 0 | 26 passed |
| `tests/test_review_records.py` | 0 | 58 passed |
| Schema, registry, scenario, export and design tests together | 0 | 136 passed |
| `tests/provider_routes`, `tests/cli_safety`, `tests/live_policy` | 0 | 643 passed |
| Whole non-synthetic suite | 0 | 2169 passed |
| Guarded synthetic suite | 0 | 229 passed; the write guard verified the golden and audit files unchanged |
| Static protected-source closure test | 0 | 1 passed |

Before the manifest refresh the guarded synthetic suite had the same five provenance failures as at Stage 4J.2, and the closure test already passed. No test was skipped or weakened. No provider call was made.

### Protected manifest and receipt refresh

Canonical procedure: dry run, then `record_goldens.py --refresh-manifest --confirm-authorized`.

| Item | Before | After |
|---|---|---|
| `golden_manifest.json` SHA-256 | `31ed361f2ea585512657c5aeb1f9ca0ec8345b3ff1a00facef991933d6684a86` | `af0efba8819848a0b91fcbde4f082c11ddab4d88e462295f574af04d0b9e524d` |
| Protected-source digest | `a4253ee58ed796a50e8b9a4cf80221f1b7df3f80c8c8478fdfe1c28a87f59b6f` (27 files) | `3bc017684702a6f3da9afaa5efc79598ede8d2bf022a17f80dce52e2ee93c87a` (29 files) |
| Helper digest | `de095e5737f56e3e0be62ffb7311fb2c13d631ffaa5ec19836e19a5a6b3c6596` | `0e843c434bbcc02d5f28b255f779fb7a00566de57ce0cb1da451ef557e7b575c` |
| `manifest_receipt.json` SHA-256 | `f97b53fb089ae964f3bb79f6a440677fe6c9e38d7a12cc27934b19c04f9c45a3` | `47bec2e8d1e8a1208c42dbcfb653a5d610bcba4c24af800e369f73047ddca791` |
| Fixture and goldens digests | `c848fde6…`, `1c35b2c5…` | unchanged |

Changed protected sources: `schemas.py` (`f42868c5…`), `experiments/receiver.py` (`fab22279…`), and the new `registry.py` (`f45dc098…`) and `validation.py` (`c93bba77…`). Golden content was re-derived and found byte-identical; no golden was updated. The archived manifest is `tests/synthetic/audit/manifests/golden_manifest.31ed361f2ea585512657c5aeb1f9ca0ec8345b3ff1a00facef991933d6684a86.json`, whose own SHA-256 is `31ed361f…` (a byte copy of the previous manifest). The source and helper digests and the manifest hash were recomputed independently of the tool and match the receipt. The receipt is an in-repository consistency aid; the owner should record the new manifest hash outside the repository.

### Limitations and deferred work

- **Not tested:** a full mock run in the main stage with an eligible registry; no such scenarios exist, and the CLI tests cover plan-only and refusal paths.
- **Heuristics, not validated thresholds:** the "year" scale kind is detected from the claim attribute; the screening flags and the edit-distance flag are conventions.
- **Human steps outside code:** the real-world name check before `clear`; adjudicator blindness to the answer key; recording pilot exposure in the registry. No real registry file exists and no cohort was fixed.
- **Deferred:** analysis-level exclusion of pilot-run outcomes; the protocol revision that updates documents 01 to 05 (they still carry the earlier pending markers); the `FREEZE` terms in the protocol; the answer-key destination; the existing ten have no `author_id`.
- **Stricter than the earlier text, for the owner to confirm:** any adjudication record blocks `frozen`, and an adjudicator may not have reviewed the same scenario at all (a conservative reading of "not a disputing reviewer").

### Status

Protocol: **NOT APPROVED.** Stage 4J.3: complete. Stages 4J.4 to 4J.7: **NOT AUTHORIZED.** Pilot and confirmatory execution, design, scenario, cohort, pilot-family and confirmatory freeze, provider calls and spending: **NOT AUTHORIZED.** The final refusal is unchanged.

---

## Stage 4J.4 — implementation record (review export and key-custody safeguards IMPLEMENTED; PROTOCOL NOT APPROVED; no freeze)

### Owner gate decisions and authorization (recorded exactly)

Given by the owner in the interactive Stage 4J.4 gate session (authorization date: 2026-11-09) and restated in the implementation prompt.

| # | Decision | Owner response |
|---|---|---|
| 1 | Key custody | "Encrypted outside-repo, owner moves (Recommended)": `ACCEPT PROPOSED:` encrypted file or volume outside the repository, moved and attested by the owner; the assistant never touches the key |
| 2 | What each stage sees, and the redefined "truth" criterion | "Accept stage visibility (Recommended)" |
| 3 | Opaque ids and salt | "Secret per-export salt (Recommended)" |
| 4 | The two stricter 4J.3 adjudication choices | "Both stand (Recommended)", with the pair-level gap recorded for Stage 4J.5 |
| 5 | Freeze and status glossary | "Accept glossary (Recommended)" |
| 6 | Protocol revision | "After 4J.4, separate task (Recommended)" |
| 7 | Pilot-exposure evidence rule | "Accept exposure rule (Recommended)" |
| 8 | Authorization | `AUTHORIZE STAGE_4J.4` |

Authorization covers the boundary below only. It is not protocol approval, not a design, scenario, cohort, pilot-family or confirmatory freeze, and authorizes no experiment, provider call, spending or later stage. Decisions 5 and 7 are recorded here as accepted terms; this stage implemented none of their code.

### Boundary and verification of it

- **Modified:** `src/maps/review_export.py`, `tests/test_review_export.py`, this ledger. **Created:** `tests/test_review_stage_exports.py`.
- A scan for files newer than the Stage 4J.3 record found exactly the three code and test files above (before this ledger edit). Nothing under `data/` or `protocol/` changed. The ten scenarios, the evidence files, the protocol documents (combined digest `e7f42387…a0125`), the registry, schemas, validation and receiver code, the configuration, the golden manifest and the receipt were not touched.
- **No protected-manifest refresh was needed, and this was verified, not assumed:** `review_export.py` is not in the 29-file protected source set, nothing in `src` imports it, and the static-closure test passes. The recomputed protected-source digest (`3bc01768…c87a`) and golden manifest hash (`af0efba8…524d`) still equal the receipt.
- HEAD `f24c47c37f29214eec074ae218af07a2cb095d3f`, unchanged; 27 untracked entries and no tracked changes before and after.

### Parallel work actually done

| Role | Done by | Notes |
|---|---|---|
| Agent A, implementation audit (read-only) | Not re-run. The custody and blinding audit from the gate session was reused, because nothing in the repository changed between the gate and this run. | Its findings drove the design: the whitelist, the public salt, the key location, the single-stage export and the tests that read the key |
| Agent B, test design and `tests/test_review_stage_exports.py` | A background agent, after the interface was fixed | It wrote only that file and ran only that file |
| `review_export.py`, `tests/test_review_export.py`, integration, validation, this record | Main session | |

### Implemented behavior (`src/maps/review_export.py`)

- **Packages:** `export_stage_packages(scenarios, out_dir, key_dir, *, salt=None, repo_root)` writes `out_dir/<stage>/` for fact, cue, pair and independence, each with `items/`, a README, a `package_manifest.json`, and `evidence/` for fact and pair only.
- **Stage contents (whitelisted field by field, nothing dumped):** fact: claim text, quantity definition, calendar convention, each root's acquisition process, instrument class and four-field measurement, and the evidence document. Cue: the four message templates and the stated origins. Pair: both members under one pair token (claim with attribute, domain, roots, evidence), no truth label. Independence: roots, processes, artifacts, measurement, upstream ids, shared factors and the independence assessment, with no claim and no evidence. Each item carries a blank reviewer form scoring exactly that stage's criteria on the 0 to 3 scale. `measurement` is exported as exactly four named fields.
- **Salt and ids:** `new_salt()` returns 64 hex characters from `secrets.token_hex(32)`. Ids are HMAC-SHA256 values keyed by the salt over stage, kind and value, so each stage has its own namespace and the same scenario has different ids in different stages. The earlier public constant salt and the functions `opaque_ids` and `export_blinded` were removed. The salt appears only in `answer_key.json` in the key directory and never in a package. The command line cannot set a salt.
- **Pair linkage:** one item per matched pair under an opaque pair token. Member order (A, B) comes from an HMAC bit keyed by the salt, so position does not reveal truth. No scenario or pair id appears.
- **Package integrity:** each manifest lists file paths, SHA-256 and sizes and a combined digest (sorted `path:hash` lines joined by LF). It holds no timestamps or salt, so it is deterministic for given content. `verify_package(stage_dir)` reports missing, unlisted and changed files and a bad manifest. Hashes detect change; they do not establish reviewer independence or prevent collusion.
- **Custody safeguards:** `check_key_dir_outside_repo` refuses a key directory that is, or is inside, the repository (symlinks resolved), or is equal to, containing or inside the package directory. There is no default key or package location: `--out` and `--key-dir` are required. The key file is written with owner-only permissions. Packages are never written into the key directory.
- **Fail closed (`ExportRefused`, raised before anything is written):** no scenarios; duplicate ids; a missing evidence file; an incomplete true/false pair; an invalid explicit salt; a non-empty existing stage directory; or a leak guard hit, meaning a stage package that would carry a value it must not (the false scenario's ground-truth value outside the evidence document, or either value anywhere in the independence stage). Messages contain no scenario value, salt or key data.
- **READMEs:** per-stage instructions with the 0 to 3 scale and the record-before-discussing rule. They contain no answer-key sentence.

### Test results (exit codes captured)

| Command | Exit | Result |
|---|---|---|
| `tests/test_review_stage_exports.py` (new) | 0 | 35 passed |
| `tests/test_review_export.py` (updated) | 0 | 8 passed |
| Whole non-synthetic suite | 0 | 2205 passed (2169 before this stage) |
| Guarded synthetic suite | 0 | 229 passed; write guard clean |
| Static protected-source closure test | 0 | 1 passed |

`git diff --check` exited 0; the whitespace scan of the three files was clean. No provider call was made.

### Disclosed expectation changes in `tests/test_review_export.py` (not weakenings)

The old tests encoded the public salt and read the repository's real answer key, both of which conflict with accepted decisions, so they were replaced. No test now reads the repository's answer key. The counts test no longer derives ids with the old salt; the two committed-package leak scans were kept because they only read the obsolete package. The key-completeness, determinism and refusal tests now run on a fresh export into temporary directories outside the repository. The old tests were not run after the change that made them obsolete, so that run never touched the real key.

### What was not done, and limitations

- **The key was not accessed, opened, read, copied, moved, decrypted or hashed.** The owner's move, deletion of the in-repository copy, hash record and attestation are still owner actions and are not done or verified. Whether the key is still in the repository is unknown to this stage. The git-history exposure check was not run.
- **No packages were generated, distributed or placed under `data/review/`.** The committed `data/review/blinded` package is obsolete (public salt, old format, README still carrying the answer-key sentence), untouched and must not be distributed.
- **Not verifiable by code:** that the key location is encrypted and controlled; that reviewers do not collude; that evidence text and root descriptions are free of clues beyond the numeric-value guard. The leak guard is a word-boundary text match on values and is not a general semantic check.
- **Not implemented:** ingestion or validation of returned reviewer forms against the review-record schema; any pilot-exposure recording; the command-line `main` is untested by execution because running it writes files.
- **Anyone who holds the key file also holds the salt**, by design.
- **Deferred as accepted or recommended:** protocol draft 2 (documents 03, 05 and 07 still describe the earlier design), the pair-level adjudicator gap and the `independently_checked` reviewer gate (Stage 4J.5), analysis-level exclusion of pilot outcomes, stage propagation into run reports, the exposure rule's code, and the policy values and thresholds before any pilot.

### Status

Protocol: **NOT APPROVED.** Stage 4J.4: complete. Stages 4J.5 to 4J.7: **NOT AUTHORIZED.** Pilot and confirmatory execution, any freeze, provider calls and spending: **NOT AUTHORIZED.** The final refusal is unchanged.

---

## Stage 4J.5 — implementation record (review integrity checks IMPLEMENTED; PROTOCOL NOT APPROVED; no freeze)

Authorization: `AUTHORIZE STAGE_4J.5`, given by the owner in the interactive Stage 4J.5 gate session (authorization date: 2026-11-09) and restated in the implementation prompt. The exact gate answers 1-8 are in the session transcript; the implementation prompt fixed these decisions, which were implemented as stated:

| Decision | Content |
|---|---|
| A | `independently_checked` is tightened to the reviewer gate: at least 2 qualifying reviewers, all four stages, thresholds met, no adjudication record, a known `author_id`. The evidence hash is NOT required for it. |
| B | `scenario_content_sha256()` in `schemas.py`. Review submissions of `independently_checked`/`frozen` scenarios must carry a `content_sha256` equal to the current content; stale or copied reviews fail; editing a frozen scenario's content invalidates it. |
| C | Reviewer ids: case-fold collisions fail; same-pair role overlap fails; cross-pair overlap is a flag. Mechanical checks do not prove human independence. |
| D | Reviewer-form ingestion NOT implemented. |
| E | `pair_review_problems()` in `registry.py`; the pair is the unit of eligibility; wired into the existing confirmatory run check. `receiver.py` unchanged. |
| F | Adjudicator exclusion extended across both pair members. Adjudication never raises or overwrites scores. |
| G | Mechanical re-review rule: lineage required when a scenario supersedes another; a stale review cannot qualify a revised scenario. Real scenario statuses not modified. |
| H | Stages 4J.6 and 4J.7 not started. |

**Parallel work actually done.** Two background agents with exclusive file ownership: Agent V (`validation.py`, `tests/test_mechanical_validation.py`) and Agent R (`registry.py`, `tests/test_pair_review.py`, `tests/test_cohort_registry.py`, `tests/test_cohort_runtime.py`). The main session wrote `schemas.py`, `tests/test_schema.py`, `tests/test_review_records.py`, `tests/test_review_integrity.py`, `tests/test_scenarios.py`, the ledger and the manifest refresh. Agent reports are model output, not approvals.

**Behavior.**
- `schemas.py`: `scenario_content_sha256` (canonical JSON of the model minus `status`, `review`, `reviewer_assignments`, `conflict_declarations`, `review_submissions`, `adjudication`, `name_collision_check`, `evidence.verification_status`); `ReviewSubmission.content_sha256` and `partner_content_sha256` (pair stage only); bound-mode `qualifying_independent_reviewers` and `independent_review_problems`; `independently_checked` and `frozen` now require a blind review record, a known `author_id`, and `review.reviewer` among the qualifying reviewers. The reviewer-membership check runs last so specific problems are reported first.
- `registry.py`: `pair_review_problems`; the confirmatory pair gate and a lineage check for every scenario that sets `supersedes` inside `check_registry`.
- `validation.py`: `id_audit_findings` (`id_case_collision`, `id_pair_role_overlap` failures; `id_cross_pair_overlap` flag).

**Disclosed expectation changes.** `test_schema.py`: the old record shape (reviewer "x", true flag) now fails. `test_review_records.py` and the cohort fixtures bind submissions to content. A supersedes test in `test_cohort_runtime.py` and one in `test_cohort_registry.py` now also expect the missing-lineage problem. `test_scenarios.py` status pin is table-driven with all ten at `draft`.

**Validation (all run in the repository venv).**
- Focused tests (8 files): 320 passed, exit 0.
- Whole non-synthetic suite: 2283 passed, exit 0 (baseline 2205).
- Guarded synthetic suite `run_synthetic.py -q`: before the refresh 5 failed (source digest drift in registry.py, schemas.py, validation.py, as expected); after the refresh 229 passed, exit 0.
- `-k static_import_closure`: 1 passed, exit 0.
- `git diff --check`: exit 0.
- Manifest dry run passed; refresh done with `--expect-old-manifest-sha256 af0efba8…`.

**Hashes.** Golden manifest `af0efba8819848a0b91fcbde4f082c11ddab4d88e462295f574af04d0b9e524d` to `ade56cb425c6f01d5e75733dae4db56cecf1fcafc5a0900f185820f53e724cd9` (old one archived). Receipt `47bec2e8…` to `7eda3ecd43c059189558918c8a26051fcf9a3fa61af5942fe9d3a9009406f5c0`. Protected source digest `3bc01768…` to `1a5c46f5dd8504a0f2e89d0efb3006cfe13c8c38fcd54d4f1dcfc5b6e126bcca` (29 files). Helper digest unchanged `0e843c434bbcc02d5f28b255f779fb7a00566de57ce0cb1da451ef557e7b575c`. Source digest, helper digest, manifest hash and receipt hash were recomputed independently of the refresh tool and match.

**Limitations.** Evidence document text is covered only through `evidence.sha256` (always set for `frozen`, optional for `independently_checked`). Code cannot prove reviewer honesty, blindness or real-world independence. The adjudicator-exclusion wording is interpreted as: not an author or reviewer of either member, and not the partner's adjudicator. A stale or copied review on a frozen scenario fails on the generic reviewer-membership message in some cases rather than the specific "different content" message.

Not done: reviewer-form ingestion, exports, scenario status changes, any run, any freeze, protocol approval, Stages 4J.6 and 4J.7.

Protocol: **NOT APPROVED.** Stage 4J.5: complete. Stages 4J.6 and 4J.7: **NOT AUTHORIZED.** Pilot and confirmatory execution, any freeze, provider calls and spending: **NOT AUTHORIZED.**

## Stage 4J.6A — implementation record (review-integrity remediation IMPLEMENTED; PROTOCOL NOT APPROVED; no freeze)

Authorization: `AUTHORIZE STAGE_4J.6A`, given by the owner on 2026-11-09 in response to the Stage 4J.6 owner gate. Owner decisions recorded: A (evidence hash) ACCEPT; B (evidence-change invalidation) ACCEPT; C (reviewer declarations) ACCEPT the proposed fields, but NOT as qualification requirements until the protocol wording is approved; D (independent 4J.5 audit) SATISFIED by the owner-gate audit, findings remediated; E the original Stage 4J.6 is SPLIT into 4J.6A (this stage) and 4J.6B (scenario authoring and review including `hist`, deferred); F protocol revision needs separate authorization; G parallel implementation ACCEPT.

**Parallel work actually done.** Shared working tree (the repository is almost entirely untracked, so worktrees would not have carried the code), with exclusive file ownership: Agent A (`schemas.py`, `test_schema.py`, `test_review_records.py`, `test_review_integrity.py`, new `test_lineage_schema.py`), Agent B (`scenarios.py`, new `test_evidence_integrity.py`), Agent C (`registry.py`, `test_pair_review.py`, `test_cohort_registry.py`, `test_cohort_runtime.py`, new `test_registry_lineage.py`). The integrator added `normalize_id` to `schemas.py` before launch, and owns the ledger, manifest and receipt. Agent reports are model output, not approvals. `validation.py`, `review_export.py` and `receiver.py` were not changed.

**Lineage.** `scenario_version > 1` requires `supersedes`; the reference must be `<id>@<version>`; a same-id parent must have a lower version (self-reference fails); cross-id supersession is allowed. In `check_registry`: a file's `supersedes` must name a loaded parent; registry lineage entries must name a loaded parent; version > 1 needs a registry lineage entry; cycles and self-reference fail; parent and child must share `pair_id`, and their `truth_status` must match when `pair_id` matches. Exposure and pilot-cohort descent still blocks a revised child from a confirmatory cohort. A child's reviews are bound to its own content, so it never inherits parent review validity. The schema alone does not check that a parent exists (`zzz@9` validates as a lone scenario); the registry check does.

**Evidence integrity.** `Evidence.sha256` must be lowercase hex64 when set; `independently_checked` and `frozen` now require it. `scenarios.evidence_integrity_problems()` re-reads the current file bytes on every call (no cache), never raises, and reports missing hash, malformed hash, missing, unreadable or non-file evidence, and mismatch. The loader fails closed for `pilot_frozen`, `independently_checked` and `frozen` scenarios. `check_registry(registry, scenarios, repo_root)` verifies every confirmatory member, and the pair gate verifies both members, so a changed evidence file blocks eligibility even when the scenario JSON is unchanged. The cue and independence stages get no evidence rule. A matching hash proves content identity, not that a reviewer read or understood the evidence.

**Identity.** `normalize_id` (NFKC, strip, casefold) is used in every author, reviewer and adjudicator comparison in the schema and in the pair gate. The pair gate now blocks the author of either member being a reviewer (submitter, assignee or declarant) of either member, and an adjudicator who is the author or a reviewer of either member or the other member's adjudicator. The same reviewer or the same author on both members is allowed. Cross-pair overlap stays a flag in `validation.py`. These are string rules; they do not show that distinct ids are distinct people.

**Reviewer declarations (optional, not required).** Added `ReviewerAssignment.accepted_on` (must not precede `assigned_on`) and `ConflictDeclaration.author_relationship`, `paired_scenario_relationship` (a True value counts as a declared conflict), `content_sha256`, `independent_assessment_declared`, `declaration_sha256` (must equal `declaration_record_sha256`, the canonical-JSON hash). No qualification rule requires any of them. Superseding a revised declaration is deferred to 4J.6B. Declarations are self-reports.

**Pair symmetry: NOT implemented.** The approved protocol (documents 03, 04, 05) does not say whether the same reviewers must review both pair members; document 03 only says the pair-stage reviewer sees both members. A test pins the current behavior (disjoint reviewer sets pass) with the comment "owner clarification pending". OWNER QUESTION, options: (1) require that every qualifying pair-stage reviewer also qualifies on the partner; (2) require the same reviewer set on both members; (3) keep per-member independence only, as now. Not recommended without a decision.

**Disclosed expectation changes.** `test_review_records.py`: the `independently_checked` fixture keeps its evidence hash, the former "not the evidence hash" test now asserts the hash is required, and the `scenario_version = 2` case also sets `supersedes`. `test_pair_review.py`: fixtures use the real evidence file digest instead of a placeholder. Adjudicator exclusion in the schema covers submission and assignment reviewers; declaration-only reviewers are not excluded, because the adjudicator must file their own declaration.

**Validation.** Focused tests (11 files): 411 passed, exit 0. Whole non-synthetic suite: 2374 passed, exit 0 (4J.5: 2283). Guarded synthetic suite before refresh: 5 failed (source digest drift in `registry.py`, `scenarios.py`, `schemas.py`); after refresh: 229 passed, exit 0. `-k static_import_closure`: 1 passed. `git diff --check`: exit 0. Manifest dry run passed, then refresh with `--expect-old-manifest-sha256 ade56cb4…`.

**Hashes.** Golden manifest `ade56cb425c6f01d5e75733dae4db56cecf1fcafc5a0900f185820f53e724cd9` to `8466b739d9d743c183adf23b5209c9754f8f5cb7e85d66b0658025a328d392a5` (old one archived). Receipt `7eda3ecd…` to `dfc788576c55c301ca5e1db304c216f0303e9663884a50f5b78b30f51371d6fc`. Source digest `1a5c46f5…` to `6a6d3455a242f513d12b0594d157701d01a3315476cea8663b1c1500f8ba48d6`. Helper digest unchanged `0e843c434bbcc02d5f28b255f779fb7a00566de57ce0cb1da451ef557e7b575c`. All four recomputed independently of the refresh tool and match.

**Limitations.** Code cannot prove reviewer honesty, blindness or distinct humans. Evidence is verified at the loader and registry boundaries, not inside `scenario_content_sha256`. Some stale reviews on a frozen scenario still show the generic reviewer-membership message. The `pair_id` consistency rule would also block a legitimate re-pairing revision; if re-pairing should be allowed, that needs an owner decision. All ten real scenarios remain `draft`; no real scenario content or status changed.

Not done: Stage 4J.6B, Stage 4J.7, reviewer-form ingestion, protocol edits, exports, any run, any freeze, anything involving the answer key or `.env`.

Protocol: **NOT APPROVED.** Stage 4J.6A: complete. Stage 4J.6B and Stage 4J.7: **NOT AUTHORIZED.** Pilot and confirmatory execution, any freeze, provider calls and spending: **NOT AUTHORIZED.**

## Stage 4J.6B — implementation record (hist revision, author self-check, pair symmetry, declaration supersession IMPLEMENTED; PROTOCOL NOT APPROVED; no freeze)

Authorization: `AUTHORIZE STAGE 4J.6B`, given by the owner on 2026-11-09. Owner decisions recorded: A pair-review symmetry = Option 2 (the same qualifying reviewer set on both members, compared on normalised ids); B no re-pairing of an existing scenario identity through an ordinary revision (a new pairing needs a new scenario identity, recorded through lineage, no inherited reviews, fresh authoring and review, no special exception); C declared `author_relationship` and `paired_scenario_relationship` are disqualifying conflicts, distinct from recording a declaration and from reviewer qualification, optional fields stay optional; D revised declarations are superseding records, never overwrites; E `independent_assessment_declared` stays optional and is not required for qualification; F protocol documents stay DRAFT, NOT APPROVED and were not edited; G parallel implementation with exclusive file ownership; H authorization.

**File ownership and parallel work actually done.** Agent A: `data/scenarios/v2/hist-a.json`, `hist-b.json`, new `tests/test_hist_revision.py`. Agent B: new `src/maps/self_check.py`, new `tests/test_self_check.py`. Agent C: `schemas.py`, `test_schema.py`, `test_review_records.py`, `test_lineage_schema.py`, `test_review_integrity.py`, new `test_declaration_supersession.py`. Integrator: `registry.py`, `test_pair_review.py`, `test_registry_lineage.py`, `test_cohort_runtime.py`, `test_mechanical_validation.py`, ledger, manifest and receipt. Shared working tree (the repository is mostly untracked, so worktrees would not carry the code). Agent reports are model output, not approvals.

**hist revision (author decision, delegated by the owner for this stage).** Audit against protocol documents 01, 02, 04 found only the two known failures. Changes: hist-a asserted year 1741 -> 1612 (29 years from the paired true year 1583, inside the 50-year bound, within the range 1533 to 1633 excluding 1583, away from the edges, different from hist-a's own ground truth 1694, absent from its evidence document); templates 1 and 2 of both members gained "the year" (template 3 and 4 of hist-a changed only in the year); hist-b `claim.text` changed with its template 1 because an existing test requires them to match. Template lengths 43/44/53/58 (mean 49.5, max deviation +17.2%) became 52/53/53/58 (mean 54.0, max +7.4%) for both members; corresponding templates across the pair have identical lengths. Unchanged: truth labels, ground-truth values, evidence files (328 bytes each), roots, origins, `status` (`draft`), `verification_status` (`unverified`), `evidence.sha256` (null), review blocks, `scenario_version` (1) and `supersedes` (null). Nothing was reviewed or exposed, so the edit is in place without a new version. The other eight scenario files are byte-identical to their previous contents. New file hashes: hist-a `08bff5088d0336507dfb10b3e35af410ec04807a334951d52672f8f742cbd5b8`, hist-b `6cc4fc8b4232c6a0efdb438e513aa62b01bb82999ffc634b1daef2a904d16050`. After the revision the mechanical checks report no hist failure; the only finding is the pre-existing flag between `geo` and `sci` origin names. Open items from the audit, not fixed: the evidence-length formula is still PENDING in the protocol; template interchangeability (checklist item 18) is a human judgement; the construction note records that four independent witnesses reporting one wrong value is a construction assumption.

**Author self-check.** New `src/maps/self_check.py` (not imported by any existing module, outside the mock-run closure): `author_self_check`, `require_self_check` (raises `SelfCheckFailed` with every failure), `format_report`, `SelfCheckResult` (level `AUTHOR_CHECKED_ONLY`). Checks required fields, evidence existence and integrity, evidence-to-claim consistency, pair completeness and match, mechanical findings, independence claims versus evidence, answer leakage, hedging and authority wording, and version and lineage shape. It is mechanical, grants no status, and is not proof of factual correctness or real independence. On the real ten: 10 passed, 0 failed, 44 warnings (missing `author_id`, null evidence hash, pending name-collision check, independence unreviewed). **No scenario status was changed.** Setting `author_checked` (ledger acceptance item (i)) was NOT done: the prompt did not authorize a status transition and `test_scenarios.py` pins all ten at `draft`.

**Pair symmetry.** `pair_review_problems` now fails unless the set of qualifying reviewers (bound mode, normalised ids) is the same on both members. Messages name the reviewer and the member, and say whether the reviewer has no record on the other member or has records but does not qualify. The earlier test that pinned disjoint reviewer sets as passing was replaced by tests that they fail (disclosed expectation change). New tests: identical sets pass, disjoint fail, one extra reviewer fails, case-only id differences match, a required stage missing on one member fails, a missing submission fails, a stale review fails, larger symmetric sets pass. A conflict-on-one-member test now also accepts the symmetry message.

**Re-pairing.** `check_registry` still fails a same-id revision whose `pair_id` differs from its parent. A child with a different scenario id and a different `pair_id` is accepted by that rule, is recorded through lineage, and inherits no review (its content hash differs). No re-pairing exception exists.

**Declaration supersession.** `ConflictDeclaration.supersedes_declaration_sha256` (optional hex64). A declaration's identity is `declaration_record_sha256`, which includes the new field. Per reviewer (normalised id) the records must form one linear chain: one root, no duplicate identity, no self-reference, no dangling reference, no fork, `declared_on` strictly increasing; otherwise the scenario is rejected with a message naming only the reviewer. `declaration_chain` and `active_declaration` identify the history and the latest record. Qualification uses the active record for disqualification and the root record's date for the "before the earliest submission" rule; a reviewer also stays disqualified if an earlier record disqualified them and the active record was filed after their earliest submission (a post-hoc retraction does not clear a conflict). A single plain declaration behaves exactly as before. No field is required for qualification. A JSON hash chain is not tamper-proof: anyone who can edit the file can rewrite the whole chain consistently; proving append-only history needs something outside the file (git history or a signed manifest recorded elsewhere). Disclosed expectation change: `test_duplicate_declaration_collides_across_case` now matches "do not form a valid supersession chain". Note: a hash cycle cannot be built without a hash collision, so the cycle tests exercise the dangling-reference and two-roots paths; the chain error does not say which rule failed.

**Other disclosed expectation changes.** `test_mechanical_validation.py`: the real-data pin expected the 158-year hist failure; it now expects a 29-year gap and no `year_threshold` failure (the rule is still exercised by the synthetic `test_year_hist_like_values`). `test_cohort_runtime.py::test_mechanical_failures_block_a_confirmatory_run`: the failure is seeded by putting 1741 back on a copy of hist-a.

**Validation.** Focused tests (14 files): 506 passed, exit 0. Whole non-synthetic suite: 2469 passed, exit 0 (4J.6A: 2374). Guarded synthetic suite before refresh: 5 failed (source digest drift in `registry.py` and `schemas.py`); after refresh: 229 passed, exit 0. `-k static_import_closure`: 1 passed. `git diff --check`: exit 0. Manifest dry run passed, then refresh with `--expect-old-manifest-sha256 8466b739…`.

**Hashes.** Golden manifest `8466b739d9d743c183adf23b5209c9754f8f5cb7e85d66b0658025a328d392a5` to `8662e3172712a1fb80f2552b7b677d1ded71c62ed1228c98802dd839dc3d4a82` (old one archived). Receipt `dfc78857…` to `ae05c9238c56b0bbaef71c7229ca2dc250e0847d44fb15394f4b345e1f81cf34`. Source digest `6a6d3455…` to `8b994e1b16bae9ba6397451ce1bf3d8cb2f46b27d30fa5f10c90616738a761c8`. Helper digest unchanged `0e843c434bbcc02d5f28b255f779fb7a00566de57ce0cb1da451ef557e7b575c`. Protocol manifest unchanged `13ac34d9…`. All four values were recomputed independently of the refresh tool and match.

**Limitations.** Code cannot prove reviewer honesty, blindness or distinct humans. The self-check's heuristics (negation window, truth-cue words) can misfire; its local copies of the status rank maps could drift from `schemas.py`. The mechanical corresponding-template cross-pair rule is enforced for hist by `test_hist_revision.py` but the self-check only warns on spread. Not done: author_checked status transition, reviewer assignments or packages, reviewer-form ingestion, protocol edits, Stage 4J.7.

Not done and not authorized: Stage 4J.7, reviewer-form ingestion, any freeze, pilot or confirmatory run, provider calls, protocol approval, θ and π, anything involving the answer key or `.env`. `data/review/blinded` (obsolete package, still containing the old hist-a text) was not touched.

Protocol: **NOT APPROVED.** Stage 4J.6B: complete. Stage 4J.7: **NOT AUTHORIZED.** Pilot and confirmatory execution, any freeze, provider calls and spending: **NOT AUTHORIZED.**

## Stage 4J.7 — implementation record (pilot-readiness engineering IMPLEMENTED; PILOT NOT AUTHORIZED; NO COHORT FREEZE; PROTOCOL NOT APPROVED)

Authorization basis: the owner's Stage 4J.7 implementation directive of 2026-11-09 ("Implement the engineering required for pilot readiness", with selected design decisions A to K). That directive did NOT contain the literal phrase `AUTHORIZE STAGE_4J.7` that earlier stages used; the stage was treated as authorized by the directive itself and this record states that plainly. If the owner wants a literal authorization recorded, it should be added here. Owner decisions recorded from the directive: A pilot cohort = all five matched pairs (ten scenarios), recorded as a PROPOSAL, not frozen; B `hist-a` asserted year 1612 accepted provisionally (own ground truth 1694; the partner `hist-b` true year is 1583); C `hist-b` wording accepted (claim and template 1 "The Treaty of Halvering was signed in the year 1583.", template 2 "In the year 1583, the Treaty of Halvering was signed."); D geo/sci near-duplicate must not be dismissed; present a replacement before editing; E no owner identity is invented; F `author_checked` only under stated conditions; G theta is contrast-normalized, value unset; H pi defined as the C0 proportion above zero roots, value and breach rule unset; I policy values are proposals; J evidence-hash conflict to be resolved without weakening integrity; K key custody: non-secret parts only. NOT authorized: scenario freeze, cohort freeze, protocol approval, reviewer packages, any run, provider calls, confirmatory work, `PILOT_INTENT`.

**File ownership and parallel work actually done.** Agent A: `registry.py`, new `configs/pilot_cohort_proposal.json`, new `tests/test_pilot_cohort.py`, fixture updates in `test_cohort_runtime.py`. Agent B: new `src/maps/exposure.py`, new `tests/test_exposure.py`. Agent C: new `src/maps/analysis/decision_rules.py`, new `tests/analysis_synthetic/test_an_decision_rules.py`. Agent D: new `src/maps/readiness.py`, new `configs/pilot_policy_proposal.json`, new `tests/test_readiness.py`. Integrator: `scenarios.py` (one constant), `tests/test_self_check.py` (one expectation), `.gitignore`, new `tests/test_key_custody_hygiene.py`, the `PilotExposure` optional fields (added before launch and then owned by Agent A), ledger, manifest and receipt. Shared working tree (the repository is mostly untracked). Agent reports are model output, not approvals. `receiver.py`, `schemas.py`, `validation.py` and `review_export.py` were not changed. The mock-run bytes and goldens are unchanged.

**Evidence-hash policy conflict: resolved.** The earlier pilot-binding note (schema hash null, binding through policy `scope.content` digests) conflicted with the schema, which requires `evidence.sha256` at `pilot_frozen`. Selected route: one recorded value. From `author_checked` upward the scenario file carries `evidence.sha256` (the SHA-256 of the evidence file bytes); the loader (`HASH_REQUIRED_STATUSES` now includes `author_checked`), the registry pilot gate and the readiness report all check it against the CURRENT file bytes every time; a changed evidence file or an edited scenario changes the content hash and stales any review bound to it; any policy `scope.content` evidence digest must equal the scenario field (readiness checks this). `schemas.py` is unchanged (it still requires the hash only from `pilot_frozen`); the loader and registry enforce it from `author_checked`. No evidence-integrity requirement was weakened. Protocol document 01 still describes the older status ladder; a protocol revision is a separate approval requirement (see below).

**Author status gate.** `registry.pilot_eligibility_problems(scenarios, repo_root)` accepts only `author_checked` or `pilot_frozen`, a present `author_id`, a verified current evidence hash, and evidence verification above `unverified`; it is wired into `pilot_run_problems` and `require_pilot_registry` for scenarios assigned to a pilot cohort. `author_checked` is an author self-check status only: not independent review, adjudication, protocol approval or a freeze. A pilot CLI run with a registry on the current drafts is refused (exit 2); that is the intended behavior. Nothing was transitioned.

**Eligibility by scenario (all ten, today).** All ten are `draft`, `author_id` null, `evidence.sha256` null, evidence `unverified`, so none qualifies. Blockers specific to groups: `geo-a`, `geo-b`, `sci-a`, `sci-b` also carry the near-duplicate flag awaiting an owner decision; `hist-a`, `hist-b` carry provisional owner decisions B and C (recorded above). Self-check: 0 failures, 44 warnings (author_id_missing 10, evidence_hash_missing 10, independence_unreviewed 10, name_collision_pending 10, mechanical_name_near_duplicate 4). The author id must be supplied by the owner as an opaque identifier (suggested format `project-owner-01`; NOT written anywhere).

**geo/sci near-duplicate: UNRESOLVED, not edited.** The flag is "Alder Group" (geo-a-R1, geo-b-R1) against "Calder Group" (sci-a-R2, sci-b-R2), one edit apart. "Calder Group" appears only in the `stated_origin` field of `sci-a.json` and `sci-b.json` (not in either evidence document). Proposed replacement for the owner to approve or reject: rename "Calder Group" to "Maldon Group" in `sci-a-R2` and `sci-b-R2` identically (both members of a pair must keep matching origins). "Maldon Group" collides with no existing origin and is at edit distance 3 from the nearest one; the source identity, evidence and independence construct are unchanged (the origin is only a label), and the renamed pair would need its content hash regenerated. Alternative: accept the flag with a recorded reason through a `ScreeningException`. Until decided, the geo and sci pairs are blocked from `author_checked`.

**Cohort specification.** `configs/pilot_cohort_proposal.json`: `pilot-proposal-1`, ten members in five whole pairs, status "PROPOSED — NOT FIXED", `fixed_on` null, with scenario and evidence digests as of the draft state. It is a proposal, not a registry and not a freeze; its digests will go stale at the `author_checked` transition and must be regenerated (`build_cohort_proposal`); `proposal_to_registry` is the only path to a registry and refuses a missing `fixed_on`. No registry file exists. Planned episodes: 240 (C0 40) for ten scenarios; 192 (C0 32) for the four-pair alternative, which was not switched to.

**Pilot exposure and run-report provenance.** New `src/maps/exposure.py`: `exposure_records`, `with_exposures` (append-only, re-validated), `append_exposures_to_file` (atomic, refuses a missing file), `run_exposure_report` (exposed scenarios with hashes plus descendants, all `confirmatory_eligible: false`), `write_run_exposure_sidecar` (`pilot_exposure.json`, refuses to overwrite). It is a mechanism only: nothing calls it from the executor or the receiver, because hooking it into the live run path would change protected code and the mock-run bytes and needs separate authorization. No run was executed and no real exposure event was created. The module imports the private `_parents` helper from `registry.py`.

**theta and pi (analysis only; values UNSET).** New `src/maps/analysis/decision_rules.py`, not imported by any existing module. Theta: contrast-normalized; nominal gap from the configured conditions (C4-C2 gap 1, C5-C3 gap 3); threshold = a fraction of the gap in `ThetaConfig(fraction, approved=False)`; raw estimates and intervals preserved next to normalized ones; labels `meaningful`, `not_meaningful`, `inconclusive`, plus two UNAPPROVED additions: `reverse` (interval wholly below minus theta, no owner rule exists) and `undefined` (fewer than two pairs); an endpoint exactly at plus or minus theta is `inconclusive`; invalid or missing fractions raise. Pi: `c0_contamination` reports numerator, denominator, proportion, Wilson interval, mean roots, incomplete and unknown counts, pooled and per model and prompt variant; `c0_breach` takes the rule explicitly (`observed` proportion above pi, or `wilson_lower` bound above pi); `breach_probability` is exact; `pi_sensitivity` compares cohorts of 40 and 32 episodes. Recommendation for the owner (NOT set anywhere): theta as a fraction of each contrast's nominal gap, with candidates 0.25 and 0.50 (0.50 for discussion: the receiver reports at least half the roots the manipulation nominally adds), and pi with the `observed` rule on the pooled C0 cell, per-stratum counts reported descriptively and never pooled away; at 40 episodes pi 0.05 means a breach at 3 or more contaminated episodes, with breach probability 0.046, 0.323, 0.777 and 0.992 at true rates 0.02, 0.05, 0.10 and 0.20; at 32 episodes the same rule breaches at 2 or more, with 0.134, 0.480, 0.844 and 0.993. The `wilson_lower` rule is more conservative about declaring a breach: at 40 episodes it behaves like the observed rule at double the pi. A stratum (model by prompt variant) has only 10 episodes, so one episode is 10 percent and a per-stratum breach test would be underpowered. These figures come from synthetic arithmetic, not from any pilot output, and no pilot or confirmatory result may be used to choose either value.

**Policy configuration.** `configs/pilot_policy_proposal.json`, status "PROPOSAL — NOT APPROVED", 16 fields each with value, status and source, none approved: PS-12 approach C, CONSEC 5, 4XX [408, 429], fatal 3XX true, PS-05a = planned episodes, PS-05b = 3 x planned, PS-11 and PS-13 keep current behavior, PS-09 = 183 x (planned + 1) (these are proposals); theta fraction, pi, pi breach rule, pi breach consequence and `approval_reference` are `pending_owner` and null; `policy_id` "maps-pilot-policy-2026-11-draft-1" and profile "pilot-tolerant-c" are proposed names. It cannot be loaded as a real policy (a test checks this). No real policy file exists; `readiness.py` expects one at `configs/pilot_run_policy.json` (a filename chosen by the agent; the owner may name it differently).

**Readiness validation.** New `src/maps/readiness.py` (`readiness_report`, `format_readiness`). On the real repository it reports PILOT READINESS: NOT READY with 55 blockers: every scenario fails the pilot gate; no policy file; cohort not fixed (proposal only, no registry); policy not approved and all 16 fields unapproved; theta, pi, pi rule and consequence unset; no approval reference; author id unconfirmed; near-duplicate unresolved; cohort not frozen; five key-custody items pending; no custody attestation; `PILOT_INTENT` not authorized. Warnings: the self-check warnings, `hist` decision provisional, protocol manifest DRAFT (blocks confirmatory use, not the pilot). It never opens the answer key or `.env`.

**Key custody.** `.gitignore` now ignores `data/review/answer_key*` (path pattern only; it stops an accidental `git add` of a stray copy and is not a custody control; `.env` was already ignored). `tests/test_key_custody_hygiene.py` checks paths only (git check-ignore, git ls-files). The key was not opened, listed by content, hashed, copied, moved or deleted. Owner actions still required: move the key to encrypted storage outside the repository (destination not designated), delete the in-repository copy, record the key hash, record the custody attestation, run the git-history exposure audit. `data/review/blinded` (obsolete, contains the pre-revision `hist-a` text) was not distributed.

**Disclosed expectation changes.** `tests/test_self_check.py::test_status_rank_consistency`: `author_checked` now needs `evidence.sha256`. `tests/test_cohort_runtime.py`: pilot-registry fixtures use in-memory `author_checked` copies of the ten (real hashes), plus two new tests that drafts are refused. A first full run failed one boundary test (`test_lp_boundaries`: only the live executor and the policy source may name `live_policy`) because `readiness.py` contained the file name "pilot_live_policy.json"; the name became `pilot_run_policy.json`.

**Validation.** Focused tests (12 files): 327 passed, exit 0. Whole non-synthetic suite: 2590 passed, exit 0 (4J.6B: 2469). Guarded synthetic suite before refresh: 5 failed (source digest drift in `registry.py` and `scenarios.py`); after refresh: 229 passed, exit 0. `-k static_import_closure`: 1 passed. `git diff --check`: exit 0. Manifest dry run passed, then refresh with `--expect-old-manifest-sha256 8662e317…`.

**Hashes.** Golden manifest `8662e3172712a1fb80f2552b7b677d1ded71c62ed1228c98802dd839dc3d4a82` to `63e3a6d900a593292ea4de5d0e02628b749a51e6f580424176b215cb6d5fe402` (old one archived). Receipt `ae05c923…` to `6ab13134f592c9a0dfbd198b6e9a42fdb1b71b8098148297603b9369f15bafaf`. Source digest `8b994e1b…` to `af5fe487233238896b54d8f11cc804e73d78e7ebce3133620c69afcb2a3db2d8`. Helper digest unchanged `0e843c434bbcc02d5f28b255f779fb7a00566de57ce0cb1da451ef557e7b575c`. Protocol manifest unchanged `13ac34d9…`. The four values were recomputed independently of the refresh tool and match. All ten scenario files are byte-identical to their state before this stage.

**Protocol discrepancies (revision needs separate approval).** Document 01 line 85 still shows the old status ladder; the documents do not describe `pilot_frozen`, pair symmetry, the evidence-hash route, case-folded ids, declaration supersession, the re-pairing rule or the pilot eligibility gate. `APPROVER_NAME` and `APPROVAL_DATE` are unset.

**Remaining blockers for the pilot.** Owner-supplied `author_id`; the geo/sci decision; the `author_checked` transitions (with evidence hashes and a deliberate status-table update in `test_scenarios.py`); regenerated cohort proposal and a real registry with an owner-supplied `fixed_on`; owner-approved policy values including theta, pi, the pi rule and consequence; `approval_reference`; a real policy file; the five key-custody actions; `PILOT_INTENT`. Open owner questions: the label for an interval wholly below minus theta (`reverse`); the Wilson level (0.95 default); the cohort status needed in the proposal before readiness (agent-invented gate: `frozen`); and the exposure hook into the live run path (needs authorization to touch protected code).

Not done: any scenario edit or status change, any freeze, any run, provider call or spending, reviewer packages, protocol approval, confirmatory work, `CONFIRMATORY_INTENT`, `PILOT_INTENT`.

Protocol: **NOT APPROVED.** Stage 4J.7: pilot-readiness engineering complete, pilot readiness NOT achieved. `PILOT_INTENT`: **NOT AUTHORIZED.** Pilot and confirmatory execution, any freeze, provider calls and spending: **NOT AUTHORIZED.**

## Known revision triggers for the existing scenarios (NOT SCORED)

Recorded in Stages 4I.25–4I.28. These are arithmetic observations on lengths and values already extracted. No scenario has passed the complete rubric.

- `hist` fails the 50-year false-value threshold: the difference is 158 years (true 1583, false 1741) against a maximum of 50. It must be revised and re-checked before it can qualify.
- `hist` templates (43, 44, 53, 58 characters) deviate about −13.1% and +17.2% from their mean, exceeding ±15%.
- The other four pairs' false values were within a factor of 2 of the paired true values (`biz` 0.77, `geo` 0.74, `sci` 1.71, `sw` 1.38), split two under and two over. Same-format and avoid-extremes checks are unverified.
- Template lengths for the other four pairs were within ±15% of their own means by arithmetic, but the full length rule is unverified.
- Evidence-document lengths have not been examined.
- The extracted records were all `status: draft`, with review fields null and `name_collision_check: pending`.

## Open dependencies and questions (not decisions)

1. **Schema conflict with the AUTHORING_TIMING clarification.** `src/maps/schemas.py` (`_status_gates`, lines 263-277) requires a `frozen` or `independently_checked` scenario to have a complete review record and `independence_confirmed is True`. An author-checked pilot-family scenario therefore cannot be `frozen` under the current schema without misrepresenting independence. Design direction approved in Stage 4I.30 (see Group 4 above). The conflict is NOT fixed: the file was not modified, and implementation waits for Stage 4J.2, which is NOT AUTHORIZED.
2. The first-pass scoring of the existing ten has not been done. `hist` needs revision, which is scenario editing and is not yet authorized.
3. Confirmatory domains and pair counts are undecided, as the `DOMAIN_LIST` decision restricts.
4. `APPROVER_NAME` and `APPROVAL_DATE` remain pending (see Group 4).
5. The answer-key move and any git-history or exposure check need a separately authorized stage.
6. `MEANINGFUL_EFFECT_THRESHOLD` and `C0_TOLERANCE` await owner input (see Group 5).
7. `PS-09` and `PS-12-CONSEC`: deferral permission is not established and the records conflict (see Group 5). The owner must decide.
8. (Resolved in Stage 4I.32: `MIN_USABLE_PAIRS = 8` is confirmatory-only.)
9. A loadable live policy needs more than `PS-09` and `PS-12-CONSEC`. Corrected in Stage 4I.33: `PS-08` and `PS-19` do have verified owner decisions (see the policy audit above). `PS-05a`, `PS-05b`, `PS-11`, `PS-12`, `PS-12-4XX`, `PS-12-3XX` and `PS-13` show no recorded owner decision in the transcript searched. The search was not exhaustive. These are outside Groups 1–6 and are not decided here.
10. The `PS-09` / `PS-12-CONSEC` deferral appears only inside an assistant-authored minimum-approval-set proposal (jsonl line 7849) and says they "need pilot data". Observed latency and error rates can only come from a live run, which needs a loadable policy. The deferral therefore cannot supply pilot values. It is not an owner approval.
11. How a four- or five-pair pilot cohort enters the planned grid and policy scope is unverified (see the policy audit above).
12. `SCHEMA_EXTENSION`, `FREEZE`, `PILOT_INTENT` and `CONFIRMATORY_INTENT` belong to no Group 1–6 and are undecided. The original `FREEZE` recommendation (freeze only after review and adjudication) needs reconciling with the approved author-checked pilot path.
13. Stage 4I.35 supersedes the Stage 4I.34 recommendation for PS-12 / PS-12-CONSEC (now C / 5 / `[408, 429]`, with the strict A / 1 alternative) and item 11 (the subset-cohort mechanism is now specified; it still needs owner approval). It also records a pinned-test dependency (`tests/test_scenarios.py:284-287`) and the minimum owner response list.

## Not yet recorded

Group 6 (the seven Stage 4J stage authorization lines) is undecided and not recorded. It was presented for decision in Stage 4I.33, with no approval. Group 5 is partially recorded (see above).

## Authorization status

| Item | Status |
|---|---|
| STAGE_4J.1 | AUTHORIZED by the owner on 2026-11-08 for drafting and hashing only; executed and recorded in the Stage 4J.1 record above. Not protocol approval. |
| STAGE_4J.2 | AUTHORIZED by the owner on 2026-11-08 for the schema and cohort-registry implementation only; executed and recorded in the Stage 4J.2 record above. Not protocol approval, not a freeze. |
| STAGE_4J.3 | AUTHORIZED by the owner on 2026-11-08 for mechanical validation and runtime integration only; executed and recorded in the Stage 4J.3 record above. Not protocol approval, not a freeze. |
| STAGE_4J.4 | AUTHORIZED by the owner on 2026-11-09 for review-export and key-custody safeguards only; executed and recorded in the Stage 4J.4 record above. Not protocol approval, not a freeze. |
| STAGE_4J.5 | AUTHORIZED by the owner on 2026-11-09 for review integrity checks only; executed and recorded in the Stage 4J.5 record above. Not protocol approval, not a freeze. |
| STAGE_4J.6A | AUTHORIZED by the owner on 2026-11-09 for review-integrity remediation only; executed and recorded in the Stage 4J.6A record above. Not protocol approval, not a freeze. |
| STAGE_4J.6B | AUTHORIZED by the owner on 2026-11-09 for `hist` authoring, author self-check, pair symmetry and declaration supersession; executed and recorded in the Stage 4J.6B record above. Not protocol approval, not a freeze. |
| STAGE_4J.7 | Pilot-readiness engineering executed on the owner's implementation directive of 2026-11-09 (no literal AUTHORIZE phrase; see the Stage 4J.7 record above). Pilot readiness NOT achieved. Not protocol approval, not a freeze. |
| PILOT_INTENT | NOT AUTHORIZED |
| Pilot execution | NOT AUTHORIZED |
| Confirmatory execution | NOT AUTHORIZED |
| Design freeze | NOT AUTHORIZED |
| Model or provider calls, experiments, spending | NOT AUTHORIZED |
| Final refusal | Unchanged |

## Implementation and validation status

- Nothing is implemented. No code, schema, scenario, evidence, answer key, prompt, configuration, fixture or golden file was changed by any decision here.
- Updated in Stage 4J.1: the eight protocol files in `protocol/scenario_v1/` now exist as a draft. The protocol is NOT APPROVED. The statements above remain true for everything else.
- Updated in Stage 4J.2: `src/maps/schemas.py` was extended, `src/maps/registry.py` and two test files were added, and the protected-source manifest was refreshed (see the Stage 4J.2 record). The earlier statement that the schema conflict is "NOT fixed" is superseded for the schema (the `pilot_frozen` status and the independent-review gate now exist). The protocol is still NOT APPROVED.
- Updated in Stage 4J.3: `src/maps/validation.py` was added, the scoring scale, aggregation and adjudication gate in `schemas.py` were replaced as the owner decided, `registry.py` gained run-boundary checks, `receiver.py` gained a fail-closed `--registry` gate for the main stage, and the protected source set grew from 27 to 29 files (see the Stage 4J.3 record). Where the Stage 4J.2 record says an adjudication outcome of `accept` is possible, or that a resolved adjudication can allow `frozen`, the Stage 4J.3 rules supersede it. The protocol is still NOT APPROVED.
- Updated in Stage 4J.4: `src/maps/review_export.py` was rewritten to write one blinded package per review stage with a fresh random salt and to refuse a key directory inside the repository, and the export tests were updated. The owner-held key move, the git-history check and the generation of actual reviewer packages were not performed. The protocol is still NOT APPROVED.
- Updated in Stage 4J.5: scenario content hashing and content-bound reviews, the tightened `independently_checked` gate, the pair-level eligibility and lineage checks in `registry.py`, the reviewer-id audit in `validation.py`, the table-driven status pin, and a manifest refresh (see the Stage 4J.5 record). No scenario status changed.
- Updated in Stage 4J.6A: lineage rules, evidence-hash format and byte verification, case-folded identity checks and pair-gate overlap checks, optional reviewer-declaration fields, and a manifest refresh (see the Stage 4J.6A record). No scenario status or content changed. Pair symmetry is an open owner question.
- Updated in Stage 4J.6B: the `hist` pair was revised (false year 1612, template wording), `src/maps/self_check.py` was added, pair symmetry and the re-pairing rule were added to `registry.py`, and declaration supersession to `schemas.py`; manifest refreshed (see the Stage 4J.6B record). All ten scenarios remain `draft`.
- Updated in Stage 4J.7: the pilot eligibility gate and cohort proposal (`registry.py`), the evidence-hash route (`scenarios.py`), pilot exposure recording and sidecar (`exposure.py`), theta and pi analysis (`analysis/decision_rules.py`), the policy proposal and readiness report (`readiness.py`, `configs/`), and the answer-key ignore pattern; manifest refreshed (see the Stage 4J.7 record). All ten scenarios remain `draft`; the readiness report says NOT READY.
- No scenario has been scored, validated, independently reviewed or frozen.
- Repository integrity was last verified at v2.3.93. It has not been re-verified.
