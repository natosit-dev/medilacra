"""Minimal synthetic X12 projection for Claims (837P/835) and ePA (278).

These test fixtures demonstrate common envelopes and semantic correspondence;
they have NOT been certified against the complete licensed X12 TR3 guides.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from x12.envelope import EnvelopeConfig, wrap_interchange
from .models import ClaimSubmission, ClaimDecision, AuthorizationRequest, AuthorizationDecision, PayerSubject, PayerContact, usd


def _safe(value: object) -> str:
    text = str(value).strip().upper()
    if not text or any(ch in text for ch in "*~:^>|\r\n"):
        raise ValueError(f"unsafe or empty X12 element: {text!r}")
    return text


def _name(value: str) -> tuple[str, str]:
    raw = str(value).strip()
    if "^" in raw:
        last, first = raw.split("^", 1)
    elif "," in raw:
        last, first = raw.split(",", 1)
    else:
        raise ValueError("clinical patient name must be LAST, FIRST or LAST^FIRST")
    return _safe(last), _safe(first)


def _ctrl(exchange_id: str, variant: int) -> str:
    # 9-digit (8-digit stable base + variant), no wall-clock collision assumptions.
    base = int(hashlib.sha256(exchange_id.encode()).hexdigest()[:12], 16) % 100_000_000
    return f"{base:08d}{variant}"


def _segment(*items: object) -> str:
    # Composite fields (e.g. HC:CPT, 11:B:1) contain ':' legitimately.
    # Keep field separators and segment terminators out of source values.
    values = list(items)
    while values and values[-1] is None:
        values.pop()
    fields = []
    for value in values:
        part = "" if value is None else str(value).strip().upper()
        if any(char in part for char in "*~|\\r\\n"):
            raise ValueError(f"unsafe X12 field: {part!r}")
        fields.append(part)
    return "*".join(fields) + "~"


def _transaction(segments: list[str], control: str) -> str:
    if not segments or not segments[0].startswith("ST*"):
        raise ValueError("ST is required")
    segments.append(_segment("SE", len(segments) + 1, control))
    return "".join(segments)


def _wrap(txn: str, *, source: str, target: str, control: str,
          functional: str, version: str, run_at: datetime) -> str:
    return wrap_interchange(
        txn,
        config=EnvelopeConfig(
            sender_id=_safe(source)[:15],
            receiver_id=_safe(target)[:15],
            interchange_control_number=control,
            group_control_number=control,
            interchange_date=run_at.strftime("%y%m%d"),
            interchange_time=run_at.strftime("%H%M"),
            group_date=run_at.strftime("%Y%m%d"),
            group_time=run_at.strftime("%H%M%S"),
        ),
        functional_id=functional, version=version,
    )


def _diag(value: str) -> str:
    """ICD-10 codes in X12 omit decimal separators."""
    return _safe(value).replace(".", "")


def build_837p(claim: ClaimSubmission, run_at: datetime) -> str:
    control = _ctrl(claim.exchange_id, 1)
    last, first = _name(claim.patient_name)
    p_last, p_first = _name(claim.provider_name)
    d = run_at.strftime("%Y%m%d")
    t = run_at.strftime("%H%M")
    s = [
        _segment("ST", "837", control, "005010X222A1"),
        _segment("BHT", "0019", "00", claim.exchange_id, d, t, "CH"),
        _segment("NM1", "41", "2", "MEDILACRA TEST", "", "", "", "", "46", "MEDILACRA01"),
        _segment("PER", "IC", "TEST CONTACT", "TE", "5550100000"),
        _segment("NM1", "40", "2", claim.payer_name, "", "", "", "", "46", claim.payer_id),
        _segment("HL", "1", "", "20", "1"),
        _segment("NM1", "85", "1", p_last, p_first, "", "", "", "XX", claim.provider_npi),
        _segment("N3", "1 SYNTHETIC STREET"),
        _segment("N4", "LOWELL", "MA", "01852"),
        _segment("REF", "EI", "999999999"),
        _segment("HL", "2", "1", "22", "0"),
        _segment("SBR", "P", "18", "", "", "", "", "", "", "CI"),
        _segment("NM1", "IL", "1", last, first, "", "", "", "MI", claim.member_id),
        _segment("N3", "100 SYNTHETIC WAY"),
        _segment("N4", "LOWELL", "MA", "01852"),
        _segment("DMG", "D8", claim.birth_date.replace("-", ""), claim.sex),
        _segment("NM1", "PR", "2", claim.payer_name, "", "", "", "", "PI", claim.payer_id),
        _segment("CLM", claim.claim_id, usd(claim.charge_cents), "", "", "11:B:1", "Y", "A", "Y", "Y"),
        _segment("HI", f"ABK:{_diag(claim.line.diagnosis_code)}"),
        _segment("NM1", "82", "1", p_last, p_first, "", "", "", "XX", claim.provider_npi),
        _segment("LX", claim.line.sequence),
        _segment("SV1", f"HC:{_safe(claim.line.procedure_code)}",
                 usd(claim.charge_cents), "UN", claim.line.units, "", "", "1"),
        _segment("DTP", "472", "D8", claim.service_date.replace("-", "")),
    ]
    return _wrap(_transaction(s, control), source="MEDILACRA", target=claim.payer_id,
                 control=control, functional="HC", version="005010X222A1", run_at=run_at)


def build_835(claim: ClaimSubmission, decision: ClaimDecision, run_at: datetime,
              payer_subject: PayerSubject, payer_contact: PayerContact) -> str:
    if claim.claim_id != decision.claim_id or claim.exchange_id != decision.exchange_id:
        raise ValueError("claim response exchange mismatch")
    control = _ctrl(claim.exchange_id, 2)
    if payer_subject.member_id != claim.member_id or payer_subject.payer_id != claim.payer_id:
        raise ValueError("payer identity does not match claim routing identifiers")
    if payer_contact.payer_id != claim.payer_id:
        raise ValueError("payer contact does not match claim payer")
    last, first = _safe(payer_subject.last_name), _safe(payer_subject.first_name)
    d = run_at.strftime("%Y%m%d")
    s = [
        _segment("ST", "835", control, "005010X221A1"),
        _segment("BPR", "I", usd(decision.paid_cents), "C", "CHK",
                 "", "", "", "", "", "", "", "", "", "", "", d),
        _segment("TRN", "1", f"PAY{control}", "999999999"),
        _segment("DTM", "405", d),
        _segment("N1", "PR", claim.payer_name),
        # IRIS HIPAA_5010:835 requires payer 1000A address/contact segments
        # before the 1000B payee N1 loop begins.
        _segment("N3", payer_contact.address_line1),
        _segment("N4", payer_contact.city, payer_contact.state, payer_contact.postal_code),
        _segment("PER", "CX", payer_contact.contact_name, "TE", payer_contact.contact_phone),
        _segment("N1", "PE", claim.provider_name, "XX", claim.provider_npi),
        _segment("LX", "1"),
        _segment("CLP", claim.claim_id, "1" if decision.status == "paid" else "4",
                 usd(decision.charged_cents), usd(decision.paid_cents),
                 usd(decision.patient_cents), "CI", claim.claim_id),
        _segment("NM1", "QC", "1", last, first, "", "", "", "MI", payer_subject.member_id),
        _segment("SVC", f"HC:{_safe(claim.line.procedure_code)}",
                 usd(claim.charge_cents), usd(decision.paid_cents)),
        _segment("DTM", "472", claim.service_date.replace("-", "")),
    ]
    if decision.adjusted_cents:
        s.append(_segment("CAS", "CO", "45" if decision.status == "paid" else "96",
                          usd(decision.adjusted_cents)))
    if decision.allowed_cents:
        s.append(_segment("AMT", "B6", usd(decision.allowed_cents)))
    return _wrap(_transaction(s, control), source=claim.payer_id, target="MEDILACRA",
                 control=control, functional="HP", version="005010X221A1", run_at=run_at)


def build_278(
    request: AuthorizationRequest, run_at: datetime,
    decision: AuthorizationDecision | None = None,
    payer_subject: PayerSubject | None = None,
) -> str:
    if decision and (request.request_id != decision.request_id or
                     request.exchange_id != decision.exchange_id):
        raise ValueError("authorization response exchange mismatch")
    is_response = decision is not None
    if is_response and payer_subject is None:
        raise ValueError("payer response requires payer-local identity")
    if is_response and (payer_subject.member_id != request.member_id or
                        payer_subject.payer_id != request.payer_id):
        raise ValueError("payer identity does not match authorization routing identifiers")
    control = _ctrl(request.exchange_id, 4 if is_response else 3)
    last, first = (
        (_safe(payer_subject.last_name), _safe(payer_subject.first_name))
        if is_response else _name(request.patient_name)
    )
    p_last, p_first = _name(request.provider_name)
    d = run_at.strftime("%Y%m%d")
    t = run_at.strftime("%H%M")
    s = [
        _segment("ST", "278", control, "005010X217"),
        _segment("BHT", "0007", "11" if is_response else "13",
                 request.request_id, d, t,
                 "19" if is_response and decision.status == "pended"
                 else ("18" if is_response else None)),
        _segment("HL", "1", "", "20", "1"),
        _segment("NM1", "PR", "2", request.payer_name, "", "", "", "", "PI", request.payer_id),
        _segment("HL", "2", "1", "21", "1"),
        _segment("NM1", "1P", "1", p_last, p_first, "", "", "", "XX", request.provider_npi),
        _segment("HL", "3", "2", "22", "1"),
        _segment("NM1", "IL", "1", last, first, "", "", "", "MI",
                 payer_subject.member_id if is_response else request.member_id),
        _segment("DMG", "D8", request.birth_date.replace("-", ""), request.sex),
        _segment("HL", "4", "3", "EV", "0"),
        _segment("TRN", "2" if is_response else "1", request.request_id, "999999999"),
        _segment("UM", "SC", "I", "3", "11:B", "", "", "", "", "Y"),
    ]
    if is_response:
        s.append(_segment(
            "HCR",
            {"approved": "A1", "denied": "A3", "pended": "A4"}[decision.status],
            decision.authorization_number,
        ))
    s.extend([
        _segment("HI", f"BF:{_diag(request.diagnosis_code)}:D8:{request.service_date.replace('-', '')}"),
        _segment("HSD", "VS", request.quantity),
        _segment("NM1", "SJ", "1", p_last, p_first, "", "", "", "XX", request.provider_npi),
    ])
    return _wrap(
        _transaction(s, control),
        source=request.payer_id if is_response else "MEDILACRA",
        target="MEDILACRA" if is_response else request.payer_id,
        control=control, functional="HI", version="005010X217", run_at=run_at,
    )


def validate_envelope(text: str, expected_type: str) -> None:
    """Lightweight self-check, not a licensed TR3/profile conformance validator."""
    from x12.parser import tokenize_x12
    segments = tokenize_x12(text)
    tags = [x.tag for x in segments]
    if tags[:2] != ["ISA", "GS"] or tags[-2:] != ["GE", "IEA"]:
        raise ValueError("missing X12 interchange envelope")
    st = next((i for i, x in enumerate(segments) if x.tag == "ST"), None)
    se = next((i for i, x in enumerate(segments) if x.tag == "SE"), None)
    if st is None or se is None or st >= se:
        raise ValueError("missing ST/SE")
    if segments[st].element(1) != expected_type:
        raise ValueError("unexpected X12 transaction set")
    if segments[st].element(2) != segments[se].element(2):
        raise ValueError("transaction control mismatch")
    if int(segments[se].element(1)) != se - st + 1:
        raise ValueError("SE segment count mismatch")
    if segments[0].element(13) != segments[-1].element(2):
        raise ValueError("interchange control mismatch")
    if segments[1].element(6) != segments[-2].element(2):
        raise ValueError("functional group control mismatch")
