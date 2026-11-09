# Pilot summary (pilot_20261109T160009_mock_dedup)

Episodes: 240; strict-parse ok: 194; recovered by lenient JSON extraction: 46; analysed: 240; raw status: {'ok': 194, 'parse_error': 46}

## Condition means

| model | variant | cond | msgs | roots | n | conf mean [95% CI] | sd | accept | accept (false claims) | est roots | overcount |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini | neutral | C0 | 0 | 0 | 10 | 50.0 [50.0, 50.0] | 0.0 | 0.00 | 0.00 | 0.00 | +0.00 |
| gemini | neutral | C1 | 1 | 1 | 10 | 62.5 [60.5, 64.6] | 3.4 | 1.00 | 1.00 | 1.00 | +0.00 |
| gemini | neutral | C2 | 2 | 1 | 10 | 62.5 [60.5, 64.4] | 3.4 | 1.00 | 1.00 | 1.00 | +0.00 |
| gemini | neutral | C3 | 4 | 1 | 10 | 62.1 [60.4, 63.9] | 2.9 | 1.00 | 1.00 | 1.00 | +0.00 |
| gemini | neutral | C4 | 2 | 2 | 10 | 74.3 [72.3, 76.2] | 3.4 | 1.00 | 1.00 | 2.00 | +0.00 |
| gemini | neutral | C5 | 4 | 4 | 10 | 94.8 [94.6, 95.0] | 0.4 | 1.00 | 1.00 | 4.00 | +0.00 |
| gemini | source-aware | C0 | 0 | 0 | 10 | 50.0 [50.0, 50.0] | 0.0 | 0.00 | 0.00 | 0.00 | +0.00 |
| gemini | source-aware | C1 | 1 | 1 | 10 | 63.2 [61.4, 65.0] | 3.1 | 1.00 | 1.00 | 1.00 | +0.00 |
| gemini | source-aware | C2 | 2 | 1 | 10 | 61.3 [60.1, 62.5] | 2.0 | 1.00 | 1.00 | 1.00 | +0.00 |
| gemini | source-aware | C3 | 4 | 1 | 10 | 62.4 [60.9, 64.0] | 2.7 | 1.00 | 1.00 | 1.00 | +0.00 |
| gemini | source-aware | C4 | 2 | 2 | 10 | 73.5 [71.7, 75.3] | 3.2 | 1.00 | 1.00 | 2.00 | +0.00 |
| gemini | source-aware | C5 | 4 | 4 | 10 | 94.6 [94.0, 95.0] | 0.8 | 1.00 | 1.00 | 4.00 | +0.00 |
| qwen | neutral | C0 | 0 | 0 | 10 | 50.0 [50.0, 50.0] | 0.0 | 0.00 | 0.00 | 0.00 | +0.00 |
| qwen | neutral | C1 | 1 | 1 | 10 | 61.3 [59.2, 63.4] | 3.5 | 1.00 | 1.00 | 1.00 | +0.00 |
| qwen | neutral | C2 | 2 | 1 | 10 | 61.4 [59.9, 62.9] | 2.6 | 1.00 | 1.00 | 1.00 | +0.00 |
| qwen | neutral | C3 | 4 | 1 | 10 | 60.8 [59.4, 62.5] | 2.7 | 1.00 | 1.00 | 1.00 | +0.00 |
| qwen | neutral | C4 | 2 | 2 | 10 | 74.3 [72.6, 76.2] | 3.2 | 1.00 | 1.00 | 2.00 | +0.00 |
| qwen | neutral | C5 | 4 | 4 | 10 | 95.0 [95.0, 95.0] | 0.0 | 1.00 | 1.00 | 4.00 | +0.00 |
| qwen | source-aware | C0 | 0 | 0 | 10 | 50.0 [50.0, 50.0] | 0.0 | 0.00 | 0.00 | 0.00 | +0.00 |
| qwen | source-aware | C1 | 1 | 1 | 10 | 62.1 [60.4, 63.6] | 2.7 | 1.00 | 1.00 | 1.00 | +0.00 |
| qwen | source-aware | C2 | 2 | 1 | 10 | 62.2 [60.1, 64.2] | 3.4 | 1.00 | 1.00 | 1.00 | +0.00 |
| qwen | source-aware | C3 | 4 | 1 | 10 | 61.7 [60.0, 63.5] | 2.9 | 1.00 | 1.00 | 1.00 | +0.00 |
| qwen | source-aware | C4 | 2 | 2 | 10 | 73.9 [72.0, 75.8] | 3.4 | 1.00 | 1.00 | 2.00 | +0.00 |
| qwen | source-aware | C5 | 4 | 4 | 10 | 94.5 [94.0, 95.0] | 0.8 | 1.00 | 1.00 | 4.00 | +0.00 |

## Paired contrasts (per scenario; bootstrap 95% CI; sign-flip p)

| model | variant | contrast | pairs | Δconf [95% CI] | p | Δest roots |
|---|---|---|---|---|---|---|
| gemini | neutral | C3-C5 | 10 | -32.7 [-34.4, -31.0] | 0.002 | -3.00 |
| gemini | neutral | C2-C4 | 10 | -11.8 [-15.0, -8.7] | 0.002 | -1.00 |
| gemini | neutral | C3-C1 | 10 | -0.4 [-1.8, +1.2] | 0.691 | +0.00 |
| gemini | neutral | C5-C1 | 10 | +32.3 [+30.2, +34.2] | 0.002 | +3.00 |
| gemini | source-aware | C3-C5 | 10 | -32.2 [-33.8, -30.8] | 0.002 | -3.00 |
| gemini | source-aware | C2-C4 | 10 | -12.2 [-14.5, -10.1] | 0.002 | -1.00 |
| gemini | source-aware | C3-C1 | 10 | -0.8 [-4.0, +2.0] | 0.659 | +0.00 |
| gemini | source-aware | C5-C1 | 10 | +31.4 [+29.4, +33.2] | 0.002 | +3.00 |
| qwen | neutral | C3-C5 | 10 | -34.2 [-35.6, -32.5] | 0.002 | -3.00 |
| qwen | neutral | C2-C4 | 10 | -12.9 [-15.5, -9.9] | 0.002 | -1.00 |
| qwen | neutral | C3-C1 | 10 | -0.5 [-2.7, +1.4] | 0.734 | +0.00 |
| qwen | neutral | C5-C1 | 10 | +33.7 [+31.6, +35.8] | 0.002 | +3.00 |
| qwen | source-aware | C3-C5 | 10 | -32.8 [-34.3, -31.2] | 0.002 | -3.00 |
| qwen | source-aware | C2-C4 | 10 | -11.7 [-14.8, -9.0] | 0.002 | -1.00 |
| qwen | source-aware | C3-C1 | 10 | -0.4 [-2.7, +2.0] | 0.798 | +0.00 |
| qwen | source-aware | C5-C1 | 10 | +32.4 [+31.0, +34.1] | 0.002 | +3.00 |

Exploratory pilot: 10 draft AUTHOR_CHECKED_ONLY scenarios, temperature 0, one repetition. Not confirmatory.
