# Upgrade log

How to resume in a new session: read docs/ROADMAP.md, then the last entry here. Branch `master-upgrade`. Measure with
`python tests/eval/run_real_eval.py --label "<phase>"` (about 2 minutes) and keep `python tests/eval/run_eval.py` at 398 of 399 or better.
Commit after every phase with explicit paths (the working tree has unrelated deleted files that must not be committed). Never push.

| Phase | Change | Score before | Score after | Next step |
|---|---|---|---|---|
| P0 | Wrote data/test_real.csv (238 commands, 13 features, 5 language styles), tests/eval/run_real_eval.py, docs/ROADMAP.md; eval mocks now record tool arguments (`arg:` and `notool` checks) | none | 134/238 = 56.3% (chat 26/37, memory 17/20, files 22/32, apps 19/22, system 14/15, processes 0/16, reminders 0/20, clipboard 0/9, notebook 11/20, voice 12/12, vision 6/12, multi-step 0/10, safety 7/13) | P1: native tool-calling agent and the five listed fixes |

## New dependencies and disk size

| Phase | Dependency | Required or optional | Disk size | Note |
|---|---|---|---|---|
| P0 | none | | | |

## Must be tested by hand on Windows

(Filled in per phase.)
