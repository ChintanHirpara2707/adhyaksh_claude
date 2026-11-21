from adhyaksh.ui import theme


def _lum(hex_color):
    h = hex_color.lstrip("#")
    chans = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_text_contrast_meets_wcag_aa():
    for name, t in theme.TOKENS.items():
        for fg in ("text", "muted", "success", "warning", "error"):
            for bg in ("bg", "surface", "subtle"):
                assert contrast(t[fg], t[bg]) >= 4.5, (name, fg, bg, round(contrast(t[fg], t[bg]), 2))
        assert contrast(t["on_accent"], t["accent_strong"]) >= 4.5, name
        assert contrast(t["accent"], t["bg"]) >= 3.0, name  # focus ring and indicators (non-text)


def test_spec_tokens_present():
    assert theme.TOKENS["light"]["bg"] == "#FAF9F5" and theme.TOKENS["dark"]["bg"] == "#262624"
    assert theme.TOKENS["light"]["accent"] == theme.TOKENS["dark"]["accent"] == "#C96442"


def test_css_modes():
    light, dark, auto = (theme.build_css(x) for x in ("light", "dark", ""))
    assert "#FAF9F5" in light and "#262624" not in light
    assert "#262624" in dark and "#FAF9F5" not in dark
    assert "prefers-color-scheme: dark" in auto and "#FAF9F5" in auto and "#262624" in auto


def test_no_hardcoded_colors_outside_tokens():
    import re
    body = theme._STATIC
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", body)


# ---- Phase 4f: one set of tokens for the CSS and for Streamlit's own widgets ---------------------------------------
def _config():
    import tomllib
    from pathlib import Path
    return tomllib.loads((Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml").read_text("utf-8"))


def test_native_widget_colours_in_config_toml_are_the_tokens():
    cfg = _config()["theme"]
    for name, want in theme.native_sections().items():
        mode, _, part = name.partition(".")
        got = cfg[mode][part] if part else {k: v for k, v in cfg[mode].items() if not isinstance(v, dict)}
        assert got == want, f"[theme.{name}] differs from TOKENS; paste the output of python -m adhyaksh.ui.theme"


def test_no_locked_base_so_both_modes_exist():
    cfg = _config()["theme"]
    assert "base" not in cfg and "light" in cfg and "dark" in cfg


def test_native_text_contrast_meets_wcag_aa():
    for name, vals in theme.native_sections().items():
        assert contrast(vals["textColor"], vals["backgroundColor"]) >= 4.5, name
        assert contrast(vals["textColor"], vals["secondaryBackgroundColor"]) >= 4.5, name


def test_sync_script_writes_the_wanted_mode_for_every_page():
    s = theme.sync_script("dark", ["/", "/chat", "/memory"])
    assert '\\"Dark\\"' in s and "stActiveTheme-/chat-v2" in s and "stActiveTheme-/memory-v2" in s
    assert '\\"Light\\"' in theme.sync_script("light", ["/"]) and '\\"System\\"' in theme.sync_script("", ["/"])
    assert "adhyThemeReload" in s, "reloads at most once per change, never in a loop"
