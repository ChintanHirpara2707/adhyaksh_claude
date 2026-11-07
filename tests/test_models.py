import numpy as np

from adhyaksh.nlu import dataset as ds, evaluate, registry, train
from tests.helpers import fresh_env


def test_training_reproducible_and_registry_predicts():
    fresh_env()
    a = train.train_all(42, kinds=["m1_logreg", "m3_svm"], write_report=False)
    assert all(s.status == "ok" for s in a)
    assert registry.available()
    assert registry.predict("hello")[0] == "greet"
    assert registry.predict("mera naam Amit hai")[0] == "set_identity"
    assert registry.predict("create a file named notes.txt")[0] == "file_create"
    first = registry.predict("delete report.txt")
    b = train.train_all(42, kinds=["m1_logreg", "m3_svm"], write_report=False)
    assert [round(s.test_macro_f1, 9) for s in a] == [round(s.test_macro_f1, 9) for s in b]
    assert registry.predict("delete report.txt")[0] == first[0]


def test_best_model_meets_target_and_latency():
    fresh_env()
    res = train.train_all(42, kinds=["m1_logreg", "m3_svm"], write_report=False)
    assert max(s.test_macro_f1 for s in res) >= 0.85
    assert all(s.p95_ms < 300 for s in res)


def test_metrics_and_tau():
    m = evaluate.compute_metrics(["a", "b", "a"], ["a", "b", "b"], ["en", "en", "hi"], ["a", "b"])
    assert 0 < m["accuracy"] < 1 and set(m["per_language"]) == {"en", "hi"} and m["confusion"] == [[1, 1], [0, 1]]
    proba = np.array([[0.9, 0.1], [0.8, 0.2], [0.95, 0.05], [0.1, 0.9], [0.2, 0.8]])
    assert 0.3 <= evaluate.tune_tau(proba, ["a", "a", "a", "b", "b"], ["a", "b"]) <= 0.9
