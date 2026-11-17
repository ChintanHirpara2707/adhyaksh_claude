# Model results

All figures come from the latest training run. Dataset: synthetic and UNREVIEWED; see docs/DATA_CARD.md. The held-out split shares template families with the training split, so the in-distribution score is optimistic. The code-mixed file uses different wording and is the harder, more honest figure.

| Model | Active | Val macro-F1 | Test accuracy | Test macro-F1 | Code-mixed macro-F1 | tau | Size KB | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | no | 0.912 | 0.932 | 0.921 | 0.607 | 0.45 | 2262 | 3.45 | 10.27 |
| TF-IDF + Logistic Regression | no | 0.931 | 0.941 | 0.911 | 0.640 | 0.3 | 2710 | 5.32 | 6.54 |
| TF-IDF + Logistic Regression | no | 0.868 | 0.927 | 0.910 | 0.928 | 0.5 | 3195 | 2.93 | 6.27 |
| TF-IDF + Logistic Regression | no | 0.932 | 0.934 | 0.901 | 0.909 | 0.3 | 2930 | 2.89 | 4.01 |
| TF-IDF + Logistic Regression | no | 0.922 | 0.932 | 0.891 | 0.901 | 0.35 | 3968 | 3.15 | 4.69 |
| TF-IDF + Logistic Regression | no | 0.922 | 0.932 | 0.891 | 0.901 | 0.35 | 3968 | 2.84 | 3.29 |
| TF-IDF + Logistic Regression | no | 0.935 | 0.954 | 0.934 | 0.901 | 0.3 | 4581 | 8.58 | 18.92 |
| TF-IDF + Logistic Regression | no | 0.935 | 0.954 | 0.934 | 0.901 | 0.3 | 4581 | 2.95 | 4.44 |
| TF-IDF + Logistic Regression | no | 0.960 | 0.959 | 0.942 | 0.904 | 0.3 | 6223 | 2.97 | 4.76 |
| TF-IDF + Logistic Regression | no | 0.913 | 0.953 | 0.933 | 0.895 | 0.3 | 6442 | 2.91 | 4.30 |
| TF-IDF + Logistic Regression | no | 0.913 | 0.953 | 0.933 | 0.895 | 0.3 | 6442 | 2.87 | 4.85 |
| TF-IDF + PyTorch MLP | no | 0.947 | 0.939 | 0.902 | 0.640 | 0.4 | 12863 | 4.71 | 6.65 |
| TF-IDF + PyTorch MLP | no | 0.875 | 0.929 | 0.899 | 0.901 | 0.65 | 15161 | 4.81 | 6.68 |
| TF-IDF + PyTorch MLP | no | 0.939 | 0.929 | 0.902 | 0.904 | 0.3 | 13900 | 3.78 | 5.88 |
| TF-IDF + PyTorch MLP | no | 0.911 | 0.930 | 0.889 | 0.914 | 0.55 | 16987 | 5.27 | 8.40 |
| TF-IDF + PyTorch MLP | no | 0.911 | 0.930 | 0.889 | 0.914 | 0.55 | 16987 | 6.85 | 20.36 |
| TF-IDF + PyTorch MLP | no | 0.936 | 0.958 | 0.940 | 0.912 | 0.5 | 17871 | 6.61 | 10.82 |
| TF-IDF + PyTorch MLP | no | 0.936 | 0.958 | 0.940 | 0.912 | 0.5 | 17871 | 5.53 | 8.33 |
| TF-IDF + PyTorch MLP | no | 0.958 | 0.964 | 0.952 | 0.915 | 0.3 | 20117 | 4.80 | 6.67 |
| TF-IDF + PyTorch MLP | no | 0.917 | 0.963 | 0.946 | 0.926 | 0.5 | 20333 | 4.42 | 6.20 |
| TF-IDF + PyTorch MLP | no | 0.917 | 0.963 | 0.946 | 0.926 | 0.5 | 20333 | 5.83 | 8.02 |
| TF-IDF + calibrated linear SVM | no | 0.912 | 0.916 | 0.904 | 0.611 | 0.55 | 6333 | 20.58 | 32.49 |
| TF-IDF + calibrated linear SVM | no | 0.936 | 0.950 | 0.926 | 0.640 | 0.45 | 7583 | 14.66 | 17.90 |
| TF-IDF + calibrated linear SVM | no | 0.885 | 0.937 | 0.909 | 0.919 | 0.65 | 8937 | 15.01 | 17.72 |
| TF-IDF + calibrated linear SVM | no | 0.935 | 0.942 | 0.917 | 0.923 | 0.35 | 8198 | 13.05 | 17.80 |
| TF-IDF + calibrated linear SVM | no | 0.937 | 0.930 | 0.886 | 0.900 | 0.4 | 11174 | 15.25 | 18.11 |
| TF-IDF + calibrated linear SVM | no | 0.937 | 0.930 | 0.886 | 0.900 | 0.4 | 11174 | 13.83 | 19.82 |
| TF-IDF + calibrated linear SVM | no | 0.932 | 0.958 | 0.938 | 0.896 | 0.35 | 12972 | 17.15 | 25.87 |
| TF-IDF + calibrated linear SVM | no | 0.932 | 0.958 | 0.938 | 0.896 | 0.35 | 12972 | 16.22 | 20.14 |
| TF-IDF + calibrated linear SVM | no | 0.954 | 0.969 | 0.956 | 0.886 | 0.3 | 17796 | 17.71 | 21.91 |
| TF-IDF + calibrated linear SVM | no | 0.925 | 0.952 | 0.932 | 0.864 | 0.45 | 18442 | 18.73 | 22.48 |
| TF-IDF + calibrated linear SVM | yes | 0.925 | 0.952 | 0.932 | 0.864 | 0.45 | 18442 | 19.91 | 38.58 |

Per-language test macro-F1:

| Model | en | hi | gu | hinglish | gujlish |
|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | 0.810 | 0.744 | 0.862 | 0.893 | 0.644 |
| TF-IDF + Logistic Regression | 0.836 | 0.719 | 0.729 | 0.833 | 0.713 |
| TF-IDF + Logistic Regression | 0.837 | 0.863 | 0.713 | 0.819 | 0.871 |
| TF-IDF + Logistic Regression | 0.824 | 0.711 | 0.746 | 0.847 | 0.836 |
| TF-IDF + Logistic Regression | 0.867 | 0.823 | 0.716 | 0.804 | 0.906 |
| TF-IDF + Logistic Regression | 0.867 | 0.823 | 0.716 | 0.804 | 0.906 |
| TF-IDF + Logistic Regression | 0.914 | 0.804 | 0.867 | 0.933 | 0.870 |
| TF-IDF + Logistic Regression | 0.914 | 0.804 | 0.867 | 0.933 | 0.870 |
| TF-IDF + Logistic Regression | 0.838 | 0.800 | 0.851 | 0.904 | 0.896 |
| TF-IDF + Logistic Regression | 0.892 | 0.784 | 0.830 | 0.904 | 0.819 |
| TF-IDF + Logistic Regression | 0.892 | 0.784 | 0.830 | 0.904 | 0.819 |
| TF-IDF + PyTorch MLP | 0.836 | 0.697 | 0.729 | 0.833 | 0.713 |
| TF-IDF + PyTorch MLP | 0.832 | 0.824 | 0.713 | 0.819 | 0.877 |
| TF-IDF + PyTorch MLP | 0.808 | 0.744 | 0.730 | 0.884 | 0.836 |
| TF-IDF + PyTorch MLP | 0.857 | 0.844 | 0.717 | 0.807 | 0.906 |
| TF-IDF + PyTorch MLP | 0.857 | 0.844 | 0.717 | 0.807 | 0.906 |
| TF-IDF + PyTorch MLP | 0.910 | 0.826 | 0.860 | 0.933 | 0.897 |
| TF-IDF + PyTorch MLP | 0.910 | 0.826 | 0.860 | 0.933 | 0.897 |
| TF-IDF + PyTorch MLP | 0.862 | 0.857 | 0.850 | 0.913 | 0.896 |
| TF-IDF + PyTorch MLP | 0.890 | 0.826 | 0.837 | 0.949 | 0.819 |
| TF-IDF + PyTorch MLP | 0.890 | 0.826 | 0.837 | 0.949 | 0.819 |
| TF-IDF + calibrated linear SVM | 0.773 | 0.724 | 0.862 | 0.893 | 0.649 |
| TF-IDF + calibrated linear SVM | 0.836 | 0.761 | 0.729 | 0.849 | 0.757 |
| TF-IDF + calibrated linear SVM | 0.831 | 0.874 | 0.713 | 0.823 | 0.869 |
| TF-IDF + calibrated linear SVM | 0.817 | 0.714 | 0.748 | 0.939 | 0.836 |
| TF-IDF + calibrated linear SVM | 0.860 | 0.823 | 0.711 | 0.807 | 0.906 |
| TF-IDF + calibrated linear SVM | 0.860 | 0.823 | 0.711 | 0.807 | 0.906 |
| TF-IDF + calibrated linear SVM | 0.923 | 0.803 | 0.860 | 0.924 | 0.897 |
| TF-IDF + calibrated linear SVM | 0.923 | 0.803 | 0.860 | 0.924 | 0.897 |
| TF-IDF + calibrated linear SVM | 0.868 | 0.828 | 0.901 | 0.921 | 0.886 |
| TF-IDF + calibrated linear SVM | 0.883 | 0.786 | 0.830 | 0.904 | 0.819 |
| TF-IDF + calibrated linear SVM | 0.883 | 0.786 | 0.830 | 0.904 | 0.819 |

Dataset hash: 29e0e312d0593d60. Target macro-F1 0.85: best test macro-F1 is 0.956 (reached).

## Dataset balance

```
rows: 4141
by intent: app_close=165, app_open=198, bot_identity=41, clipboard_read=77, clipboard_write=52, doc_question=70, file_create=144, file_delete=142, file_read=148, file_search=142, file_update=70, folder_create=53, get_identity=86, greet=48, help=92, knowledge_question=252, memory_recall=124, memory_save=144, ocr_read=103, office_create=70, out_of_scope=157, pc_performance=205, process_kill=100, process_list=101, reminder_cancel=78, reminder_list=72, reminder_set=98, screenshot=52, set_identity=70, source_delete=110, source_list=103, source_summary=104, special_folder_open=50, system_status=86, time_date=55, unknown=40, vision_detect=197, voice_control=202, web_open=40
by language: en=1145, hinglish=777, gujlish=749, gu=737, hi=733
reviewed: false=4141
```
