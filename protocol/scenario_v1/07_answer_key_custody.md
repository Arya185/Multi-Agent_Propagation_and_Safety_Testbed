# 07 — Answer Key Custody

| Field | Value |
|---|---|
| Protocol version | scenario_v1 (draft 1) |
| Document | 07_answer_key_custody.md |
| Document version | 1 (draft) |
| Status | **DRAFT — NOT APPROVED** |
| Drafted on | 2026-11-08 |
| Source of decisions | `docs/stage_reports/owner_decision_ledger.md` (Group 4 `ANSWER_KEY_CUSTODY`) |

Legend: `[APPROVED]` owner-approved as recorded in the ledger; `[DRAFTED]` newly drafted in Stage 4J.1 and not owner-approved; `[PENDING]` undecided. This document is a draft and not protocol approval. It does not contain the answer key, any truth label or any scenario content.

## 1. Custody rule `[APPROVED]`

- The project owner is the sole answer-key custodian.
- External reviewers may receive only the blinded review package at `data/review/blinded`. They must not receive the answer key, truth labels or other unblinded materials.
- Before any external reviewer is engaged, the answer key is moved outside the shared repository.
- `.gitignore` alone is not sufficient protection if the key has previously been committed or otherwise exposed.
- The answer key must not be included in shared repository snapshots, reviewer packages or public artifacts.
- The move and any history or security checks are deferred to a separately authorized stage.

## 2. Current state (facts recorded in the ledger)

- The key file is in the repository tree, in a directory separate from the blinded package (`data/review/answer_key/`). Directory separation is not custody.
- `git status` lists `data/` as untracked, so the key is not in the current index.
- Whether the key appears in earlier git history, or has been shared, has **not** been checked.
- The owner is unblinded by authorship. The sole researcher cannot act as a blind reviewer.
- Stage 4J.1 did not open, move, copy or read the key.

## 3. Destination and hash record

| Item | Status |
|---|---|
| Destination of the key | `NOT YET DESIGNATED` `[PENDING]` The owner designates it. It is decided before Stage 4J.4. No location is invented here. |
| Recording the key's hash | `[DRAFTED]` After the move, the owner records the key's SHA-256 outside the repository so a later change can be detected. The hash is not computed in Stage 4J.1. |
| Who may open the key | `[DRAFTED]` The custodian only. Reviewers never. |
| When the key may be opened | `[DRAFTED]` By the custodian only, and for review purposes only after the relevant reviewers' scores are recorded. |
| Exposure check of git history | `[PENDING]` Separately authorized stage |

## 4. Rules for reviewer materials `[DRAFTED]`

Not owner-approved.

- A reviewer package contains scenario records and evidence copies under opaque identifiers, with no truth label, pair identifier, internal identifier or construction note.
- A package is built only from the blinded export, never by copying repository directories.
- Any file shared with a reviewer is listed beforehand and checked for the absence of the key and truth labels.
- Source note: the existing blinded README ends "Do not open the answer key until all items are reviewed". Under the approved rule external reviewers receive no key, so that sentence needs reconciling when exports are revised (Stage 4J.4). The README is not modified by Stage 4J.1.

## 5. Pending items

| Item | Status | Decided in |
|---|---|---|
| Key destination | `NOT YET DESIGNATED` | Before Stage 4J.4 |
| Git-history exposure check | `[PENDING]` | A separately authorized stage |
| Hash record of the key after the move | `[PENDING]` | After the move |
| Reviewer-package listing procedure | `[PENDING]` | Stage 4J.4 |
