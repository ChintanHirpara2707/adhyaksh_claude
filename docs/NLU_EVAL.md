# NLU evaluation (polarity, slots, negation)

Latest run: 2026-11-19 16:45 (1c retrain (polarity pairs)). Offline path, every tool mocked. Cases: tests/eval/nlu_cases.csv. A polarity pair passes only when both of its commands pass.

| Suite | Passed | Rate |
|---|---|---|
| polarity | 23/25 pairs | 92.0% |
| slots | 26/30 cases | 86.7% |
| negation | 0/20 cases | 0.0% |

Per language (individual commands):

| Language | Passed |
|---|---|
| en | 35/49 |
| gu | 10/13 |
| gujlish | 7/9 |
| hi | 8/13 |
| hinglish | 12/16 |

## Failures (28)

| Id | Language | Text | Problem |
|---|---|---|---|
| P13a | en | open note pad | expected open_app, called nothing |
| P13b | en | close note pad | expected close_app, called nothing |
| P24a | hi | स्पॉटिफाई खोलो | expected open_app, called nothing |
| P24b | hi | स्पॉटिफाई बंद करो | expected close_app, called nothing |
| S09 | en | create groceries.txt in my work folder | expected create, called nothing |
| S20 | en | go to github.com | argument 'github.com', expected 'https://github.com' |
| S22 | en | end task for notepad.exe | argument 'for', expected 'notepad.exe' |
| S28 | en | search for files named invoice | expected search, called ['voice_command'] |
| N01 | en | don't open notepad | a negated request ran ['open_app'] |
| N02 | en | do not close chrome | a negated request ran ['close_app'] |
| N03 | en | never delete report.txt | a negated request ran ['delete'] |
| N04 | en | please don't launch spotify | a negated request ran ['open_app'] |
| N05 | en | no need to open calculator | a negated request ran ['open_app'] |
| N06 | hi | नोटपैड मत खोलो | a negated request ran ['open_app'] |
| N07 | hi | क्रोम बंद मत करो | a negated request ran ['close_app'] |
| N08 | hi | report.txt मत हटाओ | a negated request ran ['delete'] |
| N09 | gu | નોટપેડ ના ખોલો | a negated request ran ['open_app'] |
| N10 | gu | ક્રોમ બંધ ના કરો | a negated request ran ['close_app'] |
| N11 | gu | report.txt કાઢી ના નાખો | a negated request ran ['delete'] |
| N12 | hinglish | notepad mat kholo | a negated request ran ['open_app'] |
| N13 | hinglish | chrome band mat karo | a negated request ran ['close_app'] |
| N14 | hinglish | notes.txt delete nahi karni hai | a negated request ran ['delete'] |
| N15 | gujlish | notepad na kholo | a negated request ran ['open_app'] |
| N16 | gujlish | chrome bandh na karo | a negated request ran ['close_app'] |
| N17 | en | I don't want to delete notes.txt | a negated request ran ['delete'] |
| N18 | en | don't take a screenshot | a negated request ran ['screenshot'] |
| N19 | hinglish | abhi calculator mat chalu karna | a negated request ran ['open_app'] |
| N20 | en | wait, don't open paint | a negated request ran ['open_app'] |
