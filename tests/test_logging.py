from adhyaksh import logging_setup as ls


def test_redacts_secret_shapes():
    for secret in ("gsk_" + "a1b2c3d4e5f6g7h8", "AIza" + "x" * 30, "sk-" + "A" * 24, "api_key=abc123"):
        out = ls.redact(f"calling provider with {secret} now")
        assert secret not in out and "[REDACTED]" in out


def test_plain_text_untouched():
    assert ls.redact("opened notes.txt") == "opened notes.txt"
