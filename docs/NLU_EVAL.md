# NLU evaluation (polarity, slots, negation)

Latest run: 2026-11-19 19:20 (2a verification and recovery). Offline path, every tool mocked. Cases: tests/eval/nlu_cases.csv. A polarity pair passes only when both of its commands pass.

| Suite | Passed | Rate |
|---|---|---|
| polarity | 30/30 pairs | 100.0% |
| slots | 30/30 cases | 100.0% |
| negation | 20/20 cases | 100.0% |

Per language (individual commands):

| Language | Passed |
|---|---|
| en | 51/51 |
| gu | 15/15 |
| gujlish | 11/11 |
| hi | 15/15 |
| hinglish | 18/18 |

## Failures (0)

None.
