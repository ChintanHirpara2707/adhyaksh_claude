# Model results

All figures come from the latest training run. Dataset: synthetic and UNREVIEWED; see docs/DATA_CARD.md. The held-out split shares template families with the training split, so the in-distribution score is optimistic. The code-mixed file uses different wording and is the harder, more honest figure.

| Model | Active | Val macro-F1 | Test accuracy | Test macro-F1 | Code-mixed macro-F1 | tau | Size KB | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | no | 0.934 | 0.962 | 0.952 | 0.874 | 0.3 | 1346 | 2.86 | 3.31 |
| TF-IDF + Logistic Regression | no | 0.912 | 0.932 | 0.921 | 0.607 | 0.45 | 2262 | 2.92 | 5.01 |
| TF-IDF + Logistic Regression | yes | 0.912 | 0.932 | 0.921 | 0.607 | 0.45 | 2262 | 2.86 | 3.30 |
| TF-IDF + PyTorch MLP | no | 0.930 | 0.956 | 0.944 | 0.863 | 0.3 | 8533 | 3.54 | 5.32 |
| TF-IDF + PyTorch MLP | no | 0.909 | 0.924 | 0.912 | 0.615 | 0.55 | 10743 | 5.33 | 7.32 |
| TF-IDF + PyTorch MLP | no | 0.909 | 0.924 | 0.912 | 0.615 | 0.55 | 10743 | 3.64 | 6.14 |
| TF-IDF + calibrated linear SVM | no | 0.957 | 0.962 | 0.951 | 0.828 | 0.3 | 3679 | 10.83 | 13.20 |
| TF-IDF + calibrated linear SVM | no | 0.912 | 0.916 | 0.904 | 0.611 | 0.55 | 6333 | 18.06 | 24.57 |
| TF-IDF + calibrated linear SVM | no | 0.912 | 0.916 | 0.904 | 0.611 | 0.55 | 6333 | 13.02 | 15.79 |

Per-language test macro-F1:

| Model | en | hi | gu | hinglish | gujlish |
|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | 0.870 | 0.906 | 0.880 | 0.970 | 0.833 |
| TF-IDF + Logistic Regression | 0.810 | 0.744 | 0.862 | 0.893 | 0.644 |
| TF-IDF + Logistic Regression | 0.810 | 0.744 | 0.862 | 0.893 | 0.644 |
| TF-IDF + PyTorch MLP | 0.870 | 0.879 | 0.880 | 0.970 | 0.833 |
| TF-IDF + PyTorch MLP | 0.820 | 0.724 | 0.862 | 0.853 | 0.690 |
| TF-IDF + PyTorch MLP | 0.820 | 0.724 | 0.862 | 0.853 | 0.690 |
| TF-IDF + calibrated linear SVM | 0.870 | 0.914 | 0.880 | 0.970 | 0.833 |
| TF-IDF + calibrated linear SVM | 0.773 | 0.724 | 0.862 | 0.893 | 0.649 |
| TF-IDF + calibrated linear SVM | 0.773 | 0.724 | 0.862 | 0.893 | 0.649 |

Dataset hash: 11f6453cb6c17c85. Target macro-F1 0.85: best test macro-F1 is 0.952 (reached).

## Dataset balance

```
rows: 1668
by intent: app_close=70, app_open=103, bot_identity=41, doc_question=70, file_create=73, file_delete=70, file_read=70, file_search=70, file_update=70, folder_create=43, get_identity=70, greet=48, help=70, knowledge_question=80, memory_recall=70, memory_save=70, office_create=70, out_of_scope=157, screenshot=40, set_identity=70, special_folder_open=50, system_status=70, time_date=43, unknown=40, web_open=40
by language: en=417, hi=325, gu=319, hinglish=312, gujlish=295
reviewed: false=1668
```
