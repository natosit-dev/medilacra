import json
import logging

from utils.log_utils import JSONFormatter


def test_json_formatter_includes_context_fields():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.funcName = "test_json_formatter_includes_context_fields"
    record.context = {"component": "unit-test"}

    formatter = JSONFormatter()
    payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["component"] == "unit-test"
    assert "timestamp" in payload