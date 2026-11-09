# 06 — Versioning and Change Control

| Field | Value |
|---|---|
| Protocol version | scenario_v1 (draft 1) |
| Document | 06_versioning_change_control.md |
| Document version | 1 (draft) |
| Status | **DRAFT — NOT APPROVED** |
| Drafted on | 2026-11-08 |
| Source of decisions | `docs/stage_reports/owner_decision_ledger.md` (Stage 4I.37 to 4I.39 records and the Stage 4J.1 authorization) |

Legend: `[APPROVED]` owner-approved as recorded in the ledger; `[CODE]` the project's existing implementation; `[DRAFTED]` newly drafted in Stage 4J.1 and not owner-approved; `[PENDING]` undecided. **Everything in sections 2 to 7 is `[DRAFTED]` procedural wording within the drafting scope the owner authorized. It is not protocol approval.**

## 1. What Stage 4J.1 is and is not `[APPROVED]`

- Stage 4J.1 authorization (owner, 2026-11-08) permits drafting and hashing the protocol documents and manifest only.
- It is **not** protocol approval. The protocol is **NOT APPROVED** until a separate explicit final approval.
- It is not a design freeze or a scenario freeze, authorizes no schema change and no later Stage 4J stage, and permits no experiment, provider call or spending.
- The approver name and approval date are `PENDING OWNER CONFIRMATION` and `PENDING FINAL PROTOCOL APPROVAL` (the accepted gate amendment for Stage 4J.1).

## 2. Identifiers `[DRAFTED]`

- **Protocol:** `scenario_v1`, with a draft counter in the protocol version (the first is `scenario_v1-draft-1`).
- **Document:** its filename in `protocol/scenario_v1/` (`01_…` to `07_…`), plus a document version number shown in its header.
- **Scenario and pair:** the existing `scenario_id` and `pair_id`.
- **Cohort:** a named set of whole pairs fixed and recorded before any execution (document 01, section 3). A cohort identifier is not assigned yet. `[PENDING]`

## 3. Document versions `[DRAFTED]`

- Every document carries a version line in its header. Draft 1 of each is version 1.
- A document's version changes only when its content changes. A change to any document creates a new **protocol** version and a new combined digest.

## 4. Hashes and the combined digest

`[CODE]` The project's existing combined-digest method (`src/maps/runs/provenance.py`, function `_combined`, and its test helper `combined_digest` in `tests/synthetic/synthetic_support.py`): SHA-256 over the UTF-8 text of lines `<posix path>:<hex>`, sorted by path, joined by `\n` with no trailing newline, where each `<hex>` is the SHA-256 of the file's raw bytes.

`[DRAFTED]` Application to this protocol:

- Files covered: documents `01` to `07` only.
- Paths: relative to `protocol/scenario_v1/`, with no directory prefix.
- The manifest `PROTOCOL_MANIFEST.json` is **excluded** from the combined digest, because a file cannot contain its own hash.
- Three different values are kept distinct everywhere: each document's own SHA-256, the combined document digest, and the manifest's own SHA-256.
- The manifest records each document's SHA-256 and byte size and the combined digest. The manifest's own SHA-256 is computed after the manifest is written and is reported separately (it cannot be inside the manifest).
- A digest shows content equals a value. It does not authenticate who wrote it and is not owner approval.

## 5. Recording the digest outside the repository `[DRAFTED]`

The Stage 4J.1 report prints the combined digest and the manifest SHA-256 for the owner to record **outside** the repository tree. An in-repository copy is only a consistency aid. The external storage location is not designated. `[PENDING]`

## 6. Approval lifecycle `[DRAFTED]`

Proposed, not owner-approved:

1. Document drafting.
2. Document hashing.
3. Manifest generation (approval block `NOT APPROVED`, approver and date pending).
4. Owner review.
5. A separate owner statement approving the **exact combined digest** (and the draft manifest's SHA-256), for example `APPROVE PROTOCOL scenario_v1 AT COMBINED DIGEST <hex>; APPROVER_NAME: <name>`.
6. Update of the manifest approval block with the actual approver and the actual approval date (a manifest-only change; it needs its own permission).
7. Recompute the manifest's SHA-256 and record both manifest hashes (draft and approved) outside the repository.
8. Independent verification of the final manifest.

Steps 1 to 3 are Stage 4J.1. Steps 4 to 8 are not authorized by Stage 4J.1. Because the combined digest covers the seven documents only, step 6 changes the manifest's SHA-256 but not the combined digest. The digest does not cover the manifest's other fields (version, dates, sizes), which is why step 5 also names the draft manifest's SHA-256.

**Date fields** are kept apart: documents drafted on, manifest generated on, protocol approval date (pending) and Stage 4J.1 authorization date (recorded in the ledger, not an approval date).

## 7. Change control and supersession `[DRAFTED]`

- No document is edited in place after final protocol approval. Any later edit creates a new protocol version with its own combined digest.
- Before final approval, owner-requested revisions are allowed only if the owner's authorization covers revision rounds (Stage 4J.1 as authorized does not unless the owner says so). Each revision produces a new digest, and earlier digests stay in the log.
- A new protocol version **supersedes** the earlier one. The earlier version is kept, labelled superseded, with the date and the reason.
- Post-pilot revision rule: a scenario revised after the pilot stays in the pilot family and is excluded from confirmatory inference (approved, document 01). A change to a protocol rule after the pilot creates a new protocol version, and the reason is recorded.
- **Append-only logs.** Decision, review and change logs are append-only. Corrections are new entries that refer to the entry they correct.
- A change to a protected source file or a test is outside this protocol and follows the repository's own integrity and disclosure procedure (a separate, authorized stage).

## 8. Pending items

| Item | Status |
|---|---|
| Cohort identifier scheme | `[PENDING]` |
| External storage location for digests | `[PENDING]` owner designates |
| Approval step wording (section 6) | `[PENDING]` owner approval |
| Revision-round permission | `[PENDING]` owner |
