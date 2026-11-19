"""Phase 1b: factorised check. Action and target heads cross-check the flat intent model; a confident
disagreement is never dispatched to the nearest intent."""
from adhyaksh.chat import context, engine
from adhyaksh.nlu import factorized as fz
from adhyaksh.nlu import registry
from adhyaksh.result import Result
from tests.helpers import fresh_env


def test_every_intent_has_its_own_action_target_pair():
    assert len(set(fz.FACTORS.values())) == len(fz.FACTORS)
    assert all(fz.COMPOSE[pair] == intent for intent, pair in fz.FACTORS.items())
    assert fz.labels_for(["app_close", "greet"]) == (["close", fz.NONE], ["app", fz.NONE])


def test_without_trained_heads_the_check_does_nothing():
    fresh_env()
    assert fz.heads_say("open notepad") is None and fz.cross_check("open notepad", "app_open") == (True, "")


def test_confident_disagreement_is_flagged(monkeypatch):
    monkeypatch.setattr(fz, "heads_say", lambda text: ("close", 0.9, "app", 0.95))
    agree, note = fz.cross_check("x", "app_open")
    assert not agree and "app_close" in note
    assert fz.cross_check("x", "app_close") == (True, "")
    assert fz.cross_check("x", "greet") == (True, "")  # not an action intent: nothing to check
    monkeypatch.setattr(fz, "heads_say", lambda text: ("close", 0.4, "app", 0.95))
    assert fz.cross_check("x", "app_open")[0]  # an unsure head never vetoes


def test_heads_train_and_report(tmp_path):
    import pandas as pd
    fresh_env()
    rows = [("open notepad", "app_open"), ("launch chrome", "app_open"), ("start paint", "app_open"),
            ("close notepad", "app_close"), ("quit chrome", "app_close"), ("exit paint", "app_close"),
            ("hello", "greet"), ("hi there", "greet"), ("good morning", "greet")] * 3
    df = pd.DataFrame(rows, columns=["text", "intent"])
    rep = fz.train(df, df, df, df, out_dir=tmp_path)
    assert set(rep) == {"action", "target"} and rep["action"]["test"] > 0.9
    assert (tmp_path / "factor_action.joblib").exists() and (tmp_path / "factor_report.json").exists()


def test_engine_does_not_run_a_conflicting_classifier_intent(monkeypatch):
    fresh_env()
    monkeypatch.setattr(engine.router, "understand", lambda text: None)  # force the classifier path
    monkeypatch.setattr(engine.router, "split_steps", lambda text: None)
    monkeypatch.setattr(engine.frames, "command", lambda text: None)
    monkeypatch.setattr(engine.frames, "negated_command", lambda text: None)
    monkeypatch.setattr(registry, "predict", lambda text: ("app_open", 0.95, 0.9))
    monkeypatch.setattr(registry, "available", lambda: True)
    monkeypatch.setattr(fz, "heads_say", lambda text: ("close", 0.9, "app", 0.9))
    opened = []
    monkeypatch.setattr(engine.apps, "open_app", lambda app, **k: opened.append(app) or Result.success({"app": app}))
    r = engine.handle_message("blorp the zorp app", context.new_conversation()).data
    assert not opened and r["intent"] != "app_open"
