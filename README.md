# MAPS
## Multi-Agent Propagation and Safety Testbed

### Research Title
Provenance Laundering in Multi-Agent LLM Networks:
Testing Repetition, Independent Corroboration, and Belief Formation.

### Research Question
Do multi-agent LLM systems mistake repeated messages from a
single information origin for independent corroboration, and
can preserving source lineage reduce resulting errors in
belief formation?

### Initial Experimental Scope
1. Receiver double-counting experiment.
2. Provenance fidelity across LLM relays.
3. Diamond network communication experiment.
4. Belief and confidence measurement.
5. Statistical analysis and reproducible reporting.

### Technology
- Python 3.12
- OpenRouter API
- NetworkX
- NumPy / Pandas / SciPy
- Matplotlib
- Pytest

### Research Integrity
No empirical results will be fabricated.
Pilot and main experiment results will be stored separately.
All model identifiers, prompts, configurations, and API
usage will be logged.
# Multi-Agent_Propagation_and_Safety_Testbed

### Exploratory pilot (Swarm Alignment Hackathon, Nov 2026)
`scripts/pilot_live.py` runs the receiver-v2 grid (`configs/receiver_experiment.json`,
240 episodes: 10 scenarios x 6 conditions x 2 prompt variants x 2 models) against
OpenRouter, reusing the repo's grid builder, prompts and strict parser. It bypasses the
staged live executor, which ends in a deliberate refusal. Output goes to
`experiments/results/pilot_<timestamp>/` (calls, episodes, summary, figure).

    .venv/bin/python scripts/pilot_live.py --mock              # offline dry run
    .venv/bin/python scripts/pilot_live.py --confirm-spend     # live, spends credits

Results are an exploratory pilot on draft, author-checked-only scenarios. They are not
confirmatory.

Synthetic validation (known-behaviour receivers, no API calls):

    .venv/bin/python scripts/pilot_live.py --mock --mock-kind counter
    .venv/bin/python scripts/pilot_live.py --mock --mock-kind dedup
    .venv/bin/python scripts/make_paper_figure.py

Committed outputs: `experiments/validation/` (synthetic) and
`experiments/results/pilot_20261109T155007/` (credit-limited partial pilot, 27/240 episodes).
The report is submitted separately as a PDF. All code was written during the sprint (first commit 6 Nov 2026).
