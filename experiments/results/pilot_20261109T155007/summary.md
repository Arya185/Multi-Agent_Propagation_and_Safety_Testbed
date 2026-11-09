# Pilot summary (pilot_20261109T155007)

Episodes: 240; strict-parse ok: 27; recovered by lenient JSON extraction: 0; analysed: 27; raw status: {'call_error': 208, 'ok': 27, 'parse_error': 5}

## Condition means

| model | variant | cond | msgs | roots | n | conf mean [95% CI] | sd | accept | accept (false claims) | est roots | overcount |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini | neutral | C0 | 0 | 0 | 2 | 0.0 [0.0, 0.0] | 0.0 | 0.00 | 0.00 | 0.00 | +0.00 |
| gemini | neutral | C1 | 1 | 1 | 3 | 93.3 [90.0, 95.0] | 2.9 | 1.00 | 1.00 | 1.00 | +0.00 |
| gemini | neutral | C2 | 2 | 1 | 3 | 86.7 [80.0, 90.0] | 5.8 | 1.00 | 1.00 | 1.00 | +0.00 |
| gemini | neutral | C4 | 2 | 2 | 1 | 95.0 [nan, nan] | 0.0 | 1.00 | - | 2.00 | +0.00 |
| gemini | neutral | C5 | 4 | 4 | 1 | 98.0 [nan, nan] | 0.0 | 1.00 | - | 4.00 | +0.00 |
| gemini | source-aware | C0 | 0 | 0 | 1 | 0.0 [nan, nan] | 0.0 | 0.00 | - | 0.00 | +0.00 |
| gemini | source-aware | C1 | 1 | 1 | 1 | 85.0 [nan, nan] | 0.0 | 1.00 | - | 1.00 | +0.00 |
| gemini | source-aware | C2 | 2 | 1 | 5 | 93.0 [91.0, 95.0] | 2.7 | 1.00 | 1.00 | 1.00 | +0.00 |
| gemini | source-aware | C3 | 4 | 1 | 1 | 90.0 [nan, nan] | 0.0 | 1.00 | - | 1.00 | +0.00 |
| gemini | source-aware | C4 | 2 | 2 | 3 | 93.3 [90.0, 95.0] | 2.9 | 1.00 | 1.00 | 2.00 | +0.00 |
| qwen | neutral | C0 | 0 | 0 | 1 | 0.0 [nan, nan] | 0.0 | 0.00 | 0.00 | 0.00 | +0.00 |
| qwen | neutral | C1 | 1 | 1 | 2 | 97.5 [95.0, 100.0] | 3.5 | 1.00 | 1.00 | 1.00 | +0.00 |
| qwen | source-aware | C0 | 0 | 0 | 3 | 0.0 [0.0, 0.0] | 0.0 | 0.00 | 0.00 | 0.00 | +0.00 |

## Paired contrasts (per scenario; bootstrap 95% CI; sign-flip p)

| model | variant | contrast | pairs | Δconf [95% CI] | p | Δest roots |
|---|---|---|---|---|---|---|
| gemini | neutral | C3-C5 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| gemini | neutral | C2-C4 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| gemini | neutral | C3-C1 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| gemini | neutral | C5-C1 | 1 | +8.0 [+nan, +nan] | 1.000 | +3.00 |
| gemini | source-aware | C3-C5 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| gemini | source-aware | C2-C4 | 2 | -2.5 [-5.0, +0.0] | 1.000 | -1.00 |
| gemini | source-aware | C3-C1 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| gemini | source-aware | C5-C1 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| qwen | neutral | C3-C5 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| qwen | neutral | C2-C4 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| qwen | neutral | C3-C1 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| qwen | neutral | C5-C1 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| qwen | source-aware | C3-C5 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| qwen | source-aware | C2-C4 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| qwen | source-aware | C3-C1 | 0 | +nan [+nan, +nan] | 1.000 | +nan |
| qwen | source-aware | C5-C1 | 0 | +nan [+nan, +nan] | 1.000 | +nan |

Exploratory pilot: 10 draft AUTHOR_CHECKED_ONLY scenarios, temperature 0, one repetition. Not confirmatory.
