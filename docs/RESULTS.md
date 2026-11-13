# Model results

All figures come from the latest training run. Dataset: synthetic and UNREVIEWED; see docs/DATA_CARD.md. The held-out split shares template families with the training split, so the in-distribution score is optimistic. The code-mixed file uses different wording and is the harder, more honest figure.

| Model | Active | Val macro-F1 | Test accuracy | Test macro-F1 | Code-mixed macro-F1 | tau | Size KB | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | no | 0.912 | 0.932 | 0.921 | 0.607 | 0.45 | 2262 | 3.45 | 10.27 |
| TF-IDF + Logistic Regression | no | 0.931 | 0.941 | 0.911 | 0.640 | 0.3 | 2710 | 5.32 | 6.54 |
| TF-IDF + PyTorch MLP | yes | 0.947 | 0.939 | 0.902 | 0.640 | 0.4 | 12863 | 4.71 | 6.65 |
| TF-IDF + calibrated linear SVM | no | 0.912 | 0.916 | 0.904 | 0.611 | 0.55 | 6333 | 20.58 | 32.49 |
| TF-IDF + calibrated linear SVM | no | 0.936 | 0.950 | 0.926 | 0.640 | 0.45 | 7583 | 14.66 | 17.90 |

Per-language test macro-F1:

| Model | en | hi | gu | hinglish | gujlish |
|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | 0.810 | 0.744 | 0.862 | 0.893 | 0.644 |
| TF-IDF + Logistic Regression | 0.836 | 0.719 | 0.729 | 0.833 | 0.713 |
| TF-IDF + PyTorch MLP | 0.836 | 0.697 | 0.729 | 0.833 | 0.713 |
| TF-IDF + calibrated linear SVM | 0.773 | 0.724 | 0.862 | 0.893 | 0.649 |
| TF-IDF + calibrated linear SVM | 0.836 | 0.761 | 0.729 | 0.849 | 0.757 |

Dataset hash: 29e0e312d0593d60. Target macro-F1 0.85: best test macro-F1 is 0.926 (reached).

## Dataset balance

```
rows: 2386
by intent: app_close=165, app_open=198, bot_identity=41, doc_question=70, file_create=130, file_delete=142, file_read=148, file_search=142, file_update=70, folder_create=43, get_identity=70, greet=48, help=79, knowledge_question=152, memory_recall=124, memory_save=144, office_create=70, out_of_scope=157, screenshot=52, set_identity=70, special_folder_open=50, system_status=86, time_date=55, unknown=40, web_open=40
by language: en=674, hinglish=455, gujlish=429, hi=417, gu=411
reviewed: false=2386
```
