# NLU evaluation (polarity, slots, negation)

Latest run: 2026-11-19 20:30 (2b-3 windows). Offline path, every tool mocked. Cases: tests/eval/nlu_cases.csv. A polarity pair passes only when both of its commands pass.

| Suite | Passed | Rate |
|---|---|---|
| polarity | 38/38 pairs | 100.0% |
| slots | 41/41 cases | 100.0% |
| negation | 27/27 cases | 100.0% |

Per language (individual commands):

| Language | Passed |
|---|---|
| en | 62/62 |
| gu | 21/21 |
| gujlish | 15/15 |
| hi | 20/20 |
| hinglish | 26/26 |

## Failures (0)

None.
