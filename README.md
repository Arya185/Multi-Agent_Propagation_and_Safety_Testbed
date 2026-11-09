# MAPS: Multi-Agent Propagation and Safety Testbed

**Provenance Laundering in Multi-Agent LLM Networks: Testing Repetition, Independent Corroboration, and Belief Formation**

## Overview

When AI agents pass messages to each other, one claim can reach a receiver many times through different channels. If the receiver treats every copy as separate confirmation, a single wrong or compromised origin can look like independent corroboration. This is *provenance laundering*.

MAPS is a research testbed for studying this. It builds controlled scenarios, shows a receiver LLM messages with stated source labels, and measures how its belief and confidence change. The testbed also covers scenario validation, run-integrity checks and analysis code.

## Research Question

Do multi-agent LLM systems mistake repeated messages from a single information origin for independent corroboration, and can preserving source lineage reduce the resulting errors in belief formation?

## Experimental Design

A receiver judges a claim about a fictional entity after seeing messages that carry stated origins. The six conditions separate **message count** from **origin count**:

| Condition | Messages | Stated origins |
|---|---|---|
| C0 | 0 | 0 (no-evidence baseline) |
| C1 | 1 | 1 |
| C2 | 2 | 1 |
| C3 | 4 | 1 |
| C4 | 2 | 2 |
| C5 | 4 | 4 |

Key contrasts: C3 vs C5 (4 messages, 1 vs 4 origins) and C2 vs C4 (2 messages, 1 vs 2 origins). Each condition runs with a *neutral* and a *source-aware* prompt, on matched true/false scenario pairs. The draft configuration is `configs/receiver_experiment.json` (draft v2.1, 10 scenarios, 2 models).

Source labels are nominal. Distinct labels do not show genuinely independent acquisition. The study tests belief formation under those labels, not sender authentication or evidence verification.

## Project Structure

```
src/maps/
  experiments/   receiver experiment and metrics
  prompts/       receiver prompts and strict output parsing
  analysis/      aggregation, contrasts, effect sizes, decision rules
  runs/          run executor, integrity gate, live-run policy and budget guards
  scenarios.py, schemas.py, readiness.py, ...   scenario loading, validation, readiness checks
configs/         draft experiment, cohort and policy configurations
data/            scenarios (v2), evidence, blinded review exports
protocol/        scenario authoring, review and answer-key custody protocol
scripts/         pilot_live.py (pilot runner), figure and environment scripts
experiments/     synthetic validation outputs and run outputs
tests/           test suites
docs/            environment notes and owner decision ledger
paper/           hackathon report draft
```

## Technology Stack

Python 3.12, OpenRouter API (via `requests`), pydantic, jsonschema, NumPy, pandas, SciPy, statsmodels, NetworkX, Matplotlib, pytest. Dependencies are listed in `requirements.in`, with exact versions in `requirements.lock`.

## Setup and Usage

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt     # not re-run for this README
cp .env.example .env                          # only needed for live runs; add your own OpenRouter key
```

Offline dry run (no API calls, uses a mock client):

```bash
.venv/bin/python scripts/pilot_live.py --mock
```

Synthetic known-behaviour receivers (also no API calls):

```bash
.venv/bin/python scripts/pilot_live.py --mock --mock-kind counter
.venv/bin/python scripts/pilot_live.py --mock --mock-kind dedup
```

`scripts/pilot_live.py --confirm-spend` makes live OpenRouter calls and spends credits. Do not use it unless you intend to. See `docs/ENVIRONMENT.md` for the full environment notes.

## Testing

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q
```

Last full run (local, macOS, Python 3.12.16): **2814 passed, 1 skipped, 4 failed**. The tests make no provider calls. The 4 failures are real and open:

- 2 in `tests/provider_routes/test_pr_repo.py`: `scripts/pilot_live.py` is not in the provider-route allow-list.
- 1 in `tests/test_pilot_cohort.py`: the committed cohort proposal has a status the schema rejects.
- 1 in `tests/test_readiness.py`: `test_real_repo_not_ready`.

## Current Status and Limitations

**Implemented infrastructure:**
- Scenario schema, validation and readiness checks.
- Receiver prompts, strict output parsing and metrics.
- Run executor with integrity and budget guards.
- Analysis code (contrasts, intervals, decision rules).
- A draft ten-scenario set, checked only by its author (`AUTHOR_CHECKED_ONLY`). It is not independently reviewed.

**Experiments actually conducted:**
- Synthetic known-behaviour receivers only. These check that the pipeline can tell a double-counter from a deduplicator. They are calculations on simulated receivers, not findings about real models.
- One exploratory live attempt (`experiments/results/pilot_20261109T155007/`) ran out of credits. Only 27 of 240 episodes parsed, so it supports no conclusions.

**Limitations:**
- The pilot is not ready. No pilot or confirmatory experiment has been completed, and empirical validation remains future work.
- Pilot cohort and policy files in `configs/` are proposals. They are not approved or frozen.
- No power claim is made. Results will depend on the authored scenarios, chosen models, prompts and temperature 0.
- Nominally distinct sources do not establish independent acquisition.
- The 4 failing tests above are unresolved.

## Future Work

- Complete the pilot readiness path, then run the pilot on reviewed scenarios.
- Run separate confirmatory experiments with independently reviewed scenarios.
- Extend to provenance fidelity across LLM relays, diamond-shaped networks, and relays with source labels removed.
