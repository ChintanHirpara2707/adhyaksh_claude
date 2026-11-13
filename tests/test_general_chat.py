"""General-assistant answers: local model, consented cloud/Wikipedia, and no-consent fallbacks."""
import os

from adhyaksh import config
from adhyaksh.llm import base as llm
from adhyaksh.nlu import registry
from tests.test_routing_fixes import _STATE, _boot


def test_general_questions_use_model_wiki_or_link(monkeypatch):
    from adhyaksh.chat import context, engine
    from adhyaksh.llm import wiki
    from adhyaksh.result import Result
    _boot()
    registry.set_active(_STATE["model_id"])
    for var in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        os.environ.pop(var, None)
    cid = context.new_conversation()
    q = "why is the sky blue"
    # No consent, no model: search link only, nothing leaves the machine.
    monkeypatch.setattr(wiki, "lookup", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sent without consent")))
    assert "google.com/search" in engine.handle_message(q, cid).data["reply"]
    # Consent but no model: Wikipedia fallback.
    config.set_value("cloud_consent", "true")
    monkeypatch.setattr(wiki, "lookup", lambda text, lang="en", **k: "Rayleigh scattering. (Source: Wikipedia)")
    assert "Rayleigh" in engine.handle_message(q, cid).data["reply"]
    # Local model needs no consent and receives the history-aware prompt.
    config.set_value("cloud_consent", "false")
    config.set_value("llm_provider", "ollama")
    seen = {}

    def fake(prompt, timeout=8.0, max_tokens=400):
        seen["prompt"] = prompt
        return Result.success("Because of scattering.")
    monkeypatch.setattr(llm, "ask", fake)
    r = engine.handle_message("explain how a transistor works", cid).data
    assert r["reply"] == "Because of scattering." and "ADHYAKSH" in seen["prompt"]
    # Tool-like requests the app cannot do are not handed to the model.
    assert "I cannot do that yet" in engine.handle_message("shut down my laptop", cid).data["reply"]
