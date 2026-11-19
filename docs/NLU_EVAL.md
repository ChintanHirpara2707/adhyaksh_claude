# NLU evaluation (polarity, slots, negation)

Latest run: 2026-11-19 20:45 (2b-4 look at my screen). Offline path, every tool mocked. Cases: tests/eval/nlu_cases.csv. A polarity pair passes only when both of its commands pass.

| Suite | Passed | Rate |
|---|---|---|
| polarity | 38/38 pairs | 100.0% |
| slots | 46/46 cases | 100.0% |
| negation | 28/28 cases | 100.0% |

Per language (individual commands):

| Language | Passed |
|---|---|
| en | 64/64 |
| gu | 22/22 |
| gujlish | 16/16 |
| hi | 21/21 |
| hinglish | 27/27 |

## Failures (0)

None.
