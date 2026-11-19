# NLU evaluation (polarity, slots, negation)

Latest run: 2026-11-19 19:50 (2b-1 volume and brightness). Offline path, every tool mocked. Cases: tests/eval/nlu_cases.csv. A polarity pair passes only when both of its commands pass.

| Suite | Passed | Rate |
|---|---|---|
| polarity | 35/35 pairs | 100.0% |
| slots | 34/34 cases | 100.0% |
| negation | 23/23 cases | 100.0% |

Per language (individual commands):

| Language | Passed |
|---|---|
| en | 56/56 |
| gu | 18/18 |
| gujlish | 13/13 |
| hi | 18/18 |
| hinglish | 22/22 |

## Failures (0)

None.
