# NLU evaluation (polarity, slots, negation)

Latest run: 2026-11-19 18:00 (1b factorised heads). Offline path, every tool mocked. Cases: tests/eval/nlu_cases.csv. A polarity pair passes only when both of its commands pass.

| Suite | Passed | Rate |
|---|---|---|
| polarity | 25/25 pairs | 100.0% |
| slots | 30/30 cases | 100.0% |
| negation | 20/20 cases | 100.0% |

Per language (individual commands):

| Language | Passed |
|---|---|
| en | 49/49 |
| gu | 13/13 |
| gujlish | 9/9 |
| hi | 13/13 |
| hinglish | 16/16 |

## Failures (0)

None.
