from __future__ import annotations

from typing import Any

from .reference_payloads import build_inquiry
from .summaries import summarize_inquiry


def build_request(
    pas_request: dict[str, Any],
    *,
    no_match: bool = False,
) -> dict[str, Any]:
    return build_inquiry(pas_request, no_match=no_match)


def interpret_response(body: dict[str, Any]) -> dict[str, Any]:
    return summarize_inquiry(body)
