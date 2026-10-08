"""Direct FHIR R4 4.0.1 sibling projections for synthetic Claims and ePA.

Not a PAS implementation-guide certification; resource-level MVP only.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from .models import (
    SemanticCase, ClaimSubmission, ClaimDecision,
    AuthorizationRequest, AuthorizationDecision, usd,
)

FHIR_VERSION = "4.0.1"
SYS_CPT = "http://www.ama-assn.org/go/cpt"
SYS_ICD10 = "http://hl7.org/fhir/sid/icd-10-cm"
SYS_ADJ = "http://terminology.hl7.org/CodeSystem/adjudication"
SYS_CLAIM_TYPE = "http://terminology.hl7.org/CodeSystem/claim-type"


def _id(prefix: str, *values: object) -> str:
    digest = hashlib.sha256("|".join(map(str, values)).encode()).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _ref(resource: dict[str, Any]) -> dict[str, str]:
    return {"reference": f"{resource['resourceType']}/{resource['id']}"}


def _patient(*, source: str, id_value: str, name: str, dob: str, sex: str,
             member_id: str) -> dict[str, Any]:
    raw = str(name).replace("^", ",")
    if "," not in raw:
        raise ValueError("patient name requires LAST, FIRST")
    last, first = [v.strip() for v in raw.split(",", 1)]
    if not last or not first:
        raise ValueError("incomplete patient name")
    return {
        "resourceType": "Patient",
        "id": _id("pat", source, id_value),
        "identifier": [{"system": "urn:medilacra:member-id", "value": member_id}],
        "name": [{"family": last, "given": [first]}],
        "birthDate": dob,
        "gender": {"M": "male", "F": "female", "O": "other", "U": "unknown"}.get(sex.upper(), "unknown"),
    }


def _organization(kind: str, identifier: str, name: str) -> dict[str, Any]:
    return {
        "resourceType": "Organization",
        "id": _id("org", kind, identifier),
        "identifier": [{"system": f"urn:medilacra:{kind}", "value": identifier}],
        "name": name,
    }


def _coverage(person: dict[str, Any], payer: dict[str, Any], member_id: str,
              exchange_id: str, source: str) -> dict[str, Any]:
    return {
        "resourceType": "Coverage",
        "id": _id("cov", source, exchange_id),
        "status": "active",
        "subscriberId": member_id,
        "beneficiary": _ref(person),
        "payor": [_ref(payer)],
    }


def _code(system: str, code: str) -> dict[str, Any]:
    return {"coding": [{"system": system, "code": code}]}


def _money(cents: int) -> dict[str, Any]:
    return {"value": float(usd(cents)), "currency": "USD"}


def _bundle(kind: str, exchange_id: str, resources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "id": _id("bundle", kind, exchange_id),
        "type": "collection",
        "entry": [{"resource": resource} for resource in resources],
    }


def _shared_context(
    *, member_id: str, patient_id: str, name: str, dob: str, sex: str,
    payer_id: str, payer_name: str, provider_npi: str, provider_name: str,
    exchange_id: str,
) -> dict[str, dict[str, Any]]:
    payer = _organization("payer", payer_id, payer_name)
    provider = _organization("provider-npi", provider_npi, provider_name)
    clinical_patient = _patient(
        source="clinical", id_value=patient_id, name=name,
        dob=dob, sex=sex, member_id=member_id,
    )
    payer_patient = _patient(
        source="payer", id_value=f"{payer_id}:{member_id}", name=name,
        dob=dob, sex=sex, member_id=member_id,
    )
    clinical_coverage = _coverage(clinical_patient, payer, member_id, exchange_id, "clinical")
    payer_coverage = _coverage(payer_patient, payer, member_id, exchange_id, "payer")
    return locals()


def _base_claim(
    *, exchange_id: str, request_id: str, use: str, ctx: dict[str, dict],
    procedure: str, diagnosis: str, date: str, units: int, run_at: datetime,
    amount_cents: int | None,
) -> dict[str, Any]:
    claim: dict[str, Any] = {
        "resourceType": "Claim",
        "id": _id("claim", exchange_id),
        "identifier": [{"system": "urn:medilacra:exchange", "value": exchange_id},
                       {"system": "urn:medilacra:request", "value": request_id}],
        "status": "active",
        "type": _code(SYS_CLAIM_TYPE, "professional"),
        "use": use,
        "patient": _ref(ctx["clinical_patient"]),
        "created": run_at.isoformat(),
        "insurer": _ref(ctx["payer"]),
        "provider": _ref(ctx["provider"]),
        "priority": _code("http://terminology.hl7.org/CodeSystem/processpriority", "normal"),
        "insurance": [{"sequence": 1, "focal": True, "coverage": _ref(ctx["clinical_coverage"])}],
        "diagnosis": [{"sequence": 1, "diagnosisCodeableConcept": _code(SYS_ICD10, diagnosis)}],
        "item": [{
            "sequence": 1,
            "productOrService": _code(SYS_CPT, procedure),
            "servicedDate": date,
            "quantity": {"value": units},
            "diagnosisSequence": [1],
        }],
    }
    if amount_cents is not None:
        claim["item"][0]["net"] = _money(amount_cents)
        claim["total"] = _money(amount_cents)
    return claim


def _base_response(
    *, exchange_id: str, use: str, ctx: dict[str, dict],
    request: dict[str, Any], run_at: datetime,
    outcome: str, disposition: str,
) -> dict[str, Any]:
    return {
        "resourceType": "ClaimResponse",
        "id": _id("cr", exchange_id),
        "identifier": [{"system": "urn:medilacra:exchange", "value": exchange_id}],
        "status": "active", "type": _code(SYS_CLAIM_TYPE, "professional"),
        "use": use,
        "patient": _ref(ctx["payer_patient"]),
        "created": run_at.isoformat(),
        "insurer": _ref(ctx["payer"]),
        "request": _ref(request),
        "outcome": outcome,
        "disposition": disposition,
    }


def _project(
    *, claim: dict[str, Any], response: dict[str, Any],
    ctx: dict[str, dict], exchange_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        _bundle("request", exchange_id, [
            claim, ctx["clinical_patient"], ctx["clinical_coverage"],
            ctx["payer"], ctx["provider"],
        ]),
        _bundle("response", exchange_id, [
            response, claim, ctx["clinical_patient"], ctx["clinical_coverage"],
            ctx["payer_patient"], ctx["payer_coverage"], ctx["payer"], ctx["provider"],
        ]),
    )


def build_claim_fhir(
    request: ClaimSubmission, decision: ClaimDecision, run_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if request.claim_id != decision.claim_id or request.exchange_id != decision.exchange_id:
        raise ValueError("claim/decision correlation mismatch")
    ctx = _shared_context(
        member_id=request.member_id, patient_id=request.patient_id,
        name=request.patient_name, dob=request.birth_date, sex=request.sex,
        payer_id=request.payer_id, payer_name=request.payer_name,
        provider_npi=request.provider_npi, provider_name=request.provider_name,
        exchange_id=request.exchange_id,
    )
    claim = _base_claim(
        exchange_id=request.exchange_id, request_id=request.claim_id,
        use="claim", ctx=ctx, procedure=request.line.procedure_code,
        diagnosis=request.line.diagnosis_code, date=request.service_date,
        units=request.line.units, amount_cents=request.charge_cents,
        run_at=run_at,
    )
    response = _base_response(
        exchange_id=request.exchange_id, use="claim", ctx=ctx,
        request=claim, run_at=run_at,
        outcome="complete", disposition=decision.status,
    )
    response["item"] = [{
        "itemSequence": request.line.sequence,
        "adjudication": [
            {"category": _code(SYS_ADJ, "submitted"), "amount": _money(decision.charged_cents)},
            {"category": _code(SYS_ADJ, "eligible"), "amount": _money(decision.allowed_cents)},
            {"category": _code(SYS_ADJ, "benefit"), "amount": _money(decision.paid_cents)},
        ],
    }]
    response["total"] = [
        {"category": _code(SYS_ADJ, "benefit"), "amount": _money(decision.paid_cents)}
    ]
    response["payment"] = {"amount": _money(decision.paid_cents)}
    return _project(claim=claim, response=response, ctx=ctx, exchange_id=request.exchange_id)


def build_authorization_fhir(
    request: AuthorizationRequest, decision: AuthorizationDecision, run_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if request.request_id != decision.request_id or request.exchange_id != decision.exchange_id:
        raise ValueError("authorization request/decision correlation mismatch")
    ctx = _shared_context(
        member_id=request.member_id, patient_id=request.patient_id,
        name=request.patient_name, dob=request.birth_date, sex=request.sex,
        payer_id=request.payer_id, payer_name=request.payer_name,
        provider_npi=request.provider_npi, provider_name=request.provider_name,
        exchange_id=request.exchange_id,
    )
    claim = _base_claim(
        exchange_id=request.exchange_id, request_id=request.request_id,
        use="preauthorization", ctx=ctx, procedure=request.procedure_code,
        diagnosis=request.diagnosis_code, date=request.service_date,
        units=request.quantity, amount_cents=None, run_at=run_at,
    )
    response = _base_response(
        exchange_id=request.exchange_id, use="preauthorization",
        ctx=ctx, request=claim, run_at=run_at,
        outcome="queued" if decision.status == "pended" else "complete",
        disposition=decision.status,
    )
    if decision.authorization_number:
        response["preAuthRef"] = decision.authorization_number
    if decision.reason:
        response["processNote"] = [{"number": 1, "text": decision.reason}]
    return _project(claim=claim, response=response, ctx=ctx, exchange_id=request.exchange_id)


def validate_bundle(bundle: dict[str, Any]) -> None:
    """Self-contained relative-reference check, not an IG conformance validator."""
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "collection":
        raise ValueError("expected FHIR collection Bundle")
    objects = [entry["resource"] for entry in bundle["entry"]]
    ids = [f"{r['resourceType']}/{r['id']}" for r in objects]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate resource identity")
    def inspect(node):
        if isinstance(node, dict):
            if "reference" in node and "/" in node["reference"]:
                if node["reference"] not in ids:
                    raise ValueError(f"missing Bundle reference: {node['reference']}")
            for value in node.values():
                inspect(value)
        elif isinstance(node, list):
            for value in node:
                inspect(value)
    for resource in objects:
        inspect(resource)
