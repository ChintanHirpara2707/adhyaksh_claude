# NLU evaluation (polarity, slots, negation)

Latest run: 2026-11-19 20:11 (2b-2 radios and power). Offline path, every tool mocked. Cases: tests/eval/nlu_cases.csv. A polarity pair passes only when both of its commands pass.

| Suite | Passed | Rate |
|---|---|---|
| polarity | 35/35 pairs | 100.0% |
| slots | 38/38 cases | 100.0% |
| negation | 26/26 cases | 100.0% |

Per language (individual commands):

| Language | Passed |
|---|---|
| en | 58/58 |
| gu | 19/19 |
| gujlish | 14/14 |
| hi | 19/19 |
| hinglish | 24/24 |

## Failures (0)

None.
