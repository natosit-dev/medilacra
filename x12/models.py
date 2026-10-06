from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class X12Party:
    """Exchange-layer organization identity used in 270/271."""

    identifier: str
    name: str
    identifier_qualifier: str


@dataclass(frozen=True)
class EligibilityExchange:
    """
    Request/response correlation state.

    This belongs to the inter-institutional exchange layer, not clinical or
    payer reality.
    """

    trace_id: str
    originating_company_id: str
    reference_id: str
    request_control_number: str
    response_control_number: str
    transaction_date: str
    request_time: str
    response_time: str
