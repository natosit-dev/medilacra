from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any


BASELINE_DIR = Path(__file__).resolve().parents[1] / "shn_live_baseline_00301"
PAYER_SYSTEM = "urn:oid:2.16.840.1.113883.6.300"
HCPCS_SYSTEM = "http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets"

SERVICE_DISPLAYS = {
    "G0151": "Services performed by a qualified physical therapist in the home health setting",
    "L8000": "Breast prosthesis, mastectomy bra",
    "E1390": "Oxygen concentrator",
}


def _load(name: str) -> dict[str, Any]:
    return json.loads((BASELINE_DIR / name).read_text(encoding="utf-8"))


def service(code: str, display: str | None = None) -> dict[str, str]:
    return {
        "system": HCPCS_SYSTEM,
        "code": code,
        "display": display or SERVICE_DISPLAYS.get(code, code),
    }


def build_crd(
    *,
    route: str,
    service_def: dict[str, str],
    member_id: str = "MBR-COVERED",
    hook: str = "order-sign",
) -> dict[str, Any]:
    payload = copy.deepcopy(_load("crd-00301.json"))
    payload["hook"] = hook
    payload["hookInstance"] = str(uuid.uuid4())
    payload["context"]["patientId"] = member_id
    payload["prefetch"]["patient"]["id"] = member_id

    order = payload["context"]["draftOrders"]["entry"][0]["resource"]
    order["subject"] = {"reference": f"Patient/{member_id}"}
    order["code"] = {"coding": [copy.deepcopy(service_def)]}

    coverage = payload["prefetch"]["coverage"]
    coverage["beneficiary"] = {"reference": f"Patient/{member_id}"}
    coverage["contained"][0]["identifier"][0] = {
        "system": PAYER_SYSTEM,
        "value": route,
    }
    return payload


def build_dtr(
    *,
    route: str,
    questionnaire: str,
    member_id: str = "MBR-COVERED",
) -> dict[str, Any]:
    payload = copy.deepcopy(_load("dtr-00301.json"))
    coverage = next(p["resource"] for p in payload["parameter"] if p["name"] == "coverage")
    coverage["beneficiary"] = {"reference": f"Patient/{member_id}"}
    coverage["contained"][0]["identifier"][0] = {
        "system": PAYER_SYSTEM,
        "value": route,
    }
    patient = next(p["resource"] for p in payload["parameter"] if p["name"] == "referenced")
    patient["id"] = member_id
    qparam = next(p for p in payload["parameter"] if p["name"] == "questionnaire")
    qparam["valueCanonical"] = questionnaire
    return payload


def build_dtr_relaunch(
    *,
    route: str,
    trace_number: str,
    member_id: str = "MBR-COVERED",
) -> dict[str, Any]:
    payload = build_dtr(
        route=route,
        questionnaire="http://example.invalid/not-sent",
        member_id=member_id,
    )
    coverage = next(p for p in payload["parameter"] if p["name"] == "coverage")
    payload["parameter"] = [
        coverage,
        {"name": "context", "valueString": trace_number},
    ]
    return payload


def _resources(bundle: dict[str, Any], resource_type: str) -> list[dict[str, Any]]:
    return [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if isinstance(entry.get("resource"), dict)
        and entry["resource"].get("resourceType") == resource_type
    ]


def build_pas(
    *,
    route: str,
    service_def: dict[str, str],
    tag: str,
) -> dict[str, Any]:
    bundle = copy.deepcopy(_load("pas-00301.json"))
    bundle["identifier"]["value"] = f"{tag}-{uuid.uuid4()}"

    claims = _resources(bundle, "Claim")
    coverages = _resources(bundle, "Coverage")
    service_requests = _resources(bundle, "ServiceRequest")
    if len(claims) != 1 or len(coverages) != 1 or len(service_requests) != 1:
        raise ValueError("reference PAS baseline has unexpected resource cardinality")

    claim = claims[0]
    claim["identifier"][0]["value"] = f"{tag}-claim-{uuid.uuid4()}"
    claim["item"][0]["productOrService"] = {"coding": [copy.deepcopy(service_def)]}

    coverages[0]["payor"][0]["identifier"] = {
        "system": PAYER_SYSTEM,
        "value": route,
    }
    service_requests[0]["code"] = {"coding": [copy.deepcopy(service_def)]}
    return bundle


def build_inquiry(
    pas_bundle: dict[str, Any],
    *,
    no_match: bool = False,
) -> dict[str, Any]:
    bundle = copy.deepcopy(pas_bundle)
    bundle.setdefault("meta", {})["profile"] = [
        "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-inquiry-request-bundle"
    ]
    claims = _resources(bundle, "Claim")
    patients = _resources(bundle, "Patient")
    if len(claims) != 1 or len(patients) != 1:
        raise ValueError("inquiry source PAS bundle has unexpected Claim/Patient cardinality")
    claims[0].setdefault("meta", {})["profile"] = [
        "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-claim-inquiry"
    ]
    if no_match:
        member_identifiers = []
        for identifier in patients[0].get("identifier", []):
            codings = identifier.get("type", {}).get("coding", [])
            if any(coding.get("code") == "MB" for coding in codings):
                member_identifiers.append(identifier)
        if not member_identifiers:
            raise ValueError("reference Patient has no typed MB identifier")
        for identifier in member_identifiers:
            identifier["value"] = f"NO-MATCH-{uuid.uuid4()}"
    return bundle


def communication_trace(pas_response: dict[str, Any]) -> str:
    communications = _resources(pas_response, "CommunicationRequest")
    if len(communications) != 1:
        raise ValueError(
            f"expected exactly one CommunicationRequest, got {len(communications)}"
        )
    identifiers = [
        identifier.get("value")
        for identifier in communications[0].get("identifier", [])
        if identifier.get("value")
    ]
    if not identifiers:
        raise ValueError("CommunicationRequest has no trace identifier")
    return identifiers[0]
