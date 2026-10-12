from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


LOCAL_ID_SYSTEM = "http://medilacra.example/fhir/mrn"


@dataclass(frozen=True)
class MutationResult:
    payload: dict[str, Any]
    path: str | None = None
    note: str | None = None


def _resources(bundle: dict[str, Any], resource_type: str) -> list[dict[str, Any]]:
    return [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if isinstance(entry.get("resource"), dict)
        and entry["resource"].get("resourceType") == resource_type
    ]


def apply_mutation(name: str, payload: dict[str, Any]) -> MutationResult:
    value = copy.deepcopy(payload)

    if name == "unknown_payer":
        coverage = value["prefetch"]["coverage"]
        changed = False
        for org in coverage.get("contained", []):
            if org.get("resourceType") == "Organization":
                for identifier in org.get("identifier", []):
                    if identifier.get("value"):
                        identifier["value"] = "99999"
                        changed = True
        for payor in coverage.get("payor", []):
            identifier = payor.get("identifier")
            if isinstance(identifier, dict) and identifier.get("value"):
                identifier["value"] = "99999"
                changed = True
        if not changed:
            raise ValueError("unknown_payer mutation found no payer identifier")
        return MutationResult(value)

    if name == "missing_coverage_unknown_member":
        value["parameter"] = [
            parameter
            for parameter in value.get("parameter", [])
            if parameter.get("name") != "coverage"
        ]
        for parameter in value.get("parameter", []):
            resource = parameter.get("resource")
            if parameter.get("name") == "referenced" and isinstance(resource, dict):
                resource["id"] = "MEDILACRA-UNKNOWN"
        return MutationResult(value)

    if name == "bad_patient_linkage":
        patients = _resources(value, "Patient")
        if len(patients) != 1:
            raise ValueError("bad_patient_linkage expects one Patient")
        patients[0]["identifier"] = [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                            "code": "MR",
                        }
                    ]
                },
                "system": LOCAL_ID_SYSTEM,
                "value": "MEDILACRA-LOCAL-ONLY",
            }
        ]
        return MutationResult(value)

    if name == "remove_coverage_beneficiary":
        coverages = _resources(value, "Coverage")
        if len(coverages) != 1:
            raise ValueError("remove_coverage_beneficiary expects one Coverage")
        coverages[0].pop("beneficiary", None)
        return MutationResult(value)

    if name == "identifier_only_claim_patient":
        claims = _resources(value, "Claim")
        if len(claims) != 1:
            raise ValueError("identifier_only_claim_patient expects one Claim")
        claims[0]["patient"] = {
            "type": "Patient",
            "identifier": {
                "system": "http://example.org/MIN",
                "value": "12345678901",
            },
        }
        return MutationResult(value)

    if name == "bad_questionnaire_version":
        qparams = [
            parameter
            for parameter in value.get("parameter", [])
            if parameter.get("name") == "questionnaire"
        ]
        if len(qparams) != 1:
            raise ValueError("bad_questionnaire_version expects one questionnaire parameter")
        qparams[0]["valueCanonical"] = qparams[0]["valueCanonical"].split("|")[0] + "|9.9.9"
        return MutationResult(value)

    if name == "hook_service_mismatch":
        value["hook"] = "order-dispatch"
        return MutationResult(
            value,
            path="/cds-services/shn-order-sign",
            note="order-dispatch body sent to the advertised order-sign service",
        )

    if name == "order_dispatch":
        value["hook"] = "order-dispatch"
        return MutationResult(
            value,
            path="/cds-services/shn-order-dispatch",
            note="order-dispatch is not advertised by the provider test endpoint",
        )

    if name == "no_match_inquiry":
        return MutationResult(value)

    if name in {"reuse_correlation_id", "expired_token"}:
        return MutationResult(value)

    raise KeyError(f"unknown SHN negative-test mutation: {name}")
