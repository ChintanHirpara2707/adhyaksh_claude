from pathlib import Path

from adhyaksh.voice import bridge

HTML = (Path(__file__).resolve().parent.parent / "adhyaksh" / "voice" / "component" / "index.html").read_text(encoding="utf-8")


def test_speakable_strips_markup_and_caps_length():
    t = bridge.speakable("**Done.** See `notes.txt` and https://example.com/x\n- item one\n```code```")
    assert "*" not in t and "`" not in t and "http" not in t and "code" not in t.split("link")[-1]
    long = ("This is a sentence. " * 80)
    out = bridge.speakable(long)
    assert len(out) <= bridge.MAX_SPOKEN_CHARS + 40 and out.endswith("The rest is on screen.")


def test_component_has_handsfree_features():
    for needle in ("continuous", "Start hands-free", "wake", "speechSynthesis", "STOP_LISTEN", "stopAll"):
        assert needle in HTML, needle
    # Never listens to its own voice: recognition is paused while speaking.
    assert "speaking = true" in HTML and "rec.stop()" in HTML
