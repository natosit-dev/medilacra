from datetime import datetime

from templating.jinja_setup import build_env, hl7_escape, render, ts_fmt


def test_hl7_escape_handles_special_characters():
    assert hl7_escape("A|B^C&~\\") == "A\\F\\B\\S\\C\\T\\\\R\\\\E\\"


def test_ts_fmt_supports_datetime_and_string():
    ts = datetime(2024, 1, 1, 12, 0, 0)
    assert ts_fmt(ts) == "20240101120000"
    assert ts_fmt("20240101120000") == "20240101120000"


def test_render_applies_filters_and_trailing_newline(tmp_path):
    template_path = tmp_path / "templates"
    template_path.mkdir()
    template_file = template_path / "message.hl7"
    template_file.write_text("PID|{{ patient_id|hl7_escape }}", encoding="utf-8")

    env = build_env(template_path)
    output = render(env, "message.hl7", {"patient_id": "PAT|1"})

    assert output == "PID|PAT\\F\\1\n"
    assert "hl7_escape" in env.filters
    assert "ts" in env.filters