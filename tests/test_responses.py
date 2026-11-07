from adhyaksh import responses as r


def test_reference_replies_exact():
    assert r.t("identity_saved", name="Chintan") == "Welcome, Chintan. Your profile has been saved."
    assert r.t("identity_query", name="Chintan") == "Your name is Chintan."
    assert r.t("memory_saved", fact="my car is Audi") == "Saved to memory: my car is Audi."
    assert r.t("memory_exists", fact="x") == "This is already stored: x."
    assert r.t("unknown") == "I could not match that request. Please rephrase it."
    assert r.t("file_created", path="C:/w/a.txt") == "File created: C:/w/a.txt."
    assert r.t("confirm_delete", file="report.txt") == (
        "Delete report.txt? This moves it to the Recycle Bin. Confirm or cancel.")
    assert r.t("error", reason="file not found") == "The action could not be completed. Reason: file not found."


def test_no_exclamation_marks_in_any_variant():
    for key, variants in r.TEMPLATES.items():
        for lang, text in variants.items():
            assert "!" not in text, (key, lang)


def test_every_template_has_english_and_formats():
    for key, variants in r.TEMPLATES.items():
        assert "en" in variants, key
        for lang, text in variants.items():
            import string
            fields = {f for _, f, _, _ in string.Formatter().parse(text) if f}
            text.format(**{f: 1 for f in fields})


def test_language_fallback_to_english():
    assert r.t("cancelled", "hi") == r.t("cancelled", "en")
    assert r.t("identity_query", "hi", name="Amit") != r.t("identity_query", "en", name="Amit")
