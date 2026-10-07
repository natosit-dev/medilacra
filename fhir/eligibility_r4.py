from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from payer.models import (
    BenefitPlan,
    EligibilityOutcome,
    EligibilityResponse,
    EnrollmentRecord,
    EnrollmentStatus,
    MemberRecord,
)


FHIR_VERSION = "4.0.1"
FHIR_RELEASE = "R4"
ELIGIBILITY_IDENTIFIER_SYSTEM = "urn:medilacra:eligibility-exchange"


def deterministic_resource_id(prefix: str, *parts: object) -> str:
    material = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _reference(resource: dict[str, Any]) -> dict[str, str]:
    return {
        "reference": (
            f"{resource['resourceType']}/{resource['id']}"
        )
    }


def _bundle_entry(resource: dict[str, Any]) -> dict[str, Any]:
    return {"resource": resource}


def _split_name(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if "^" in raw:
        last_name, first_name = [
            part.strip()
            for part in raw.split("^", 1)
        ]
    elif "," in raw:
        last_name, first_name = [
            part.strip()
            for part in raw.split(",", 1)
        ]
    else:
        raise ValueError(
            "Patient name must contain LAST, FIRST or LAST^FIRST"
        )

    if not first_name or not last_name:
        raise ValueError("Patient name requires first and last name")

    return first_name, last_name


def _iso_date(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
        return raw[:10]

    compact = raw.replace("-", "")
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"

    raise ValueError(f"Expected YYYY-MM-DD or YYYYMMDD date, got {value!r}")


def _fhir_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.astimezone()
    return value.isoformat(timespec="seconds")


def _gender(value: str) -> str:
    normalized = str(value or "").strip().upper()
    return {
        "M": "male",
        "F": "female",
        "O": "other",
        "U": "unknown",
    }.get(normalized, "unknown")


def _self_relationship() -> dict[str, Any]:
    return {
        "coding": [
            {
                "system": (
                    "http://terminology.hl7.org/CodeSystem/"
                    "subscriber-relationship"
                ),
                "code": "self",
                "display": "Self",
            }
        ]
    }


def _coverage_classes(
    *,
    group_number: str | None,
    plan_id: str | None,
    plan_name: str | None,
) -> list[dict[str, Any]]:
    classes: list[dict[str, Any]] = []

    if group_number:
        classes.append(
            {
                "type": {
                    "coding": [
                        {
                            "system": (
                                "http://terminology.hl7.org/"
                                "CodeSystem/coverage-class"
                            ),
                            "code": "group",
                        }
                    ]
                },
                "value": str(group_number),
            }
        )

    if plan_id:
        plan_class: dict[str, Any] = {
            "type": {
                "coding": [
                    {
                        "system": (
                            "http://terminology.hl7.org/"
                            "CodeSystem/coverage-class"
                        ),
                        "code": "plan",
                    }
                ]
            },
            "value": str(plan_id),
        }
        if plan_name:
            plan_class["name"] = str(plan_name)
        classes.append(plan_class)

    return classes


def build_clinical_patient(patient) -> dict[str, Any]:
    first_name, last_name = _split_name(patient.patient_name)

    resource: dict[str, Any] = {
        "resourceType": "Patient",
        "id": deterministic_resource_id(
            "pat",
            "clinical",
            patient.patient_id,
        ),
        "identifier": [
            {
                "system": "urn:medilacra:clinical-patient-id",
                "value": str(patient.patient_id),
            }
        ],
        "name": [
            {
                "family": last_name,
                "given": [first_name],
            }
        ],
        "gender": _gender(patient.sex),
        "birthDate": _iso_date(patient.date_of_birth),
    }

    address: dict[str, Any] = {}
    if getattr(patient, "address", ""):
        address["line"] = [str(patient.address)]
    if getattr(patient, "city", ""):
        address["city"] = str(patient.city)
    if getattr(patient, "state", ""):
        address["state"] = str(patient.state)
    if getattr(patient, "zip_code", ""):
        address["postalCode"] = str(patient.zip_code)
    if address:
        resource["address"] = [address]

    if getattr(patient, "phone", ""):
        resource["telecom"] = [
            {
                "system": "phone",
                "value": str(patient.phone),
            }
        ]

    return resource


def build_payer_patient(member: MemberRecord) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": deterministic_resource_id(
            "pmem",
            member.payer_id,
            member.member_record_id,
        ),
        "identifier": [
            {
                "system": (
                    f"urn:medilacra:payer-member:{member.payer_id}"
                ),
                "value": member.member_id,
            }
        ],
        "name": [
            {
                "family": member.last_name,
                "given": [member.first_name],
            }
        ],
        "gender": _gender(member.administrative_sex),
        "birthDate": _iso_date(member.date_of_birth),
    }


def build_organization(
    *,
    role: str,
    source_id: str,
    name: str,
) -> dict[str, Any]:
    return {
        "resourceType": "Organization",
        "id": deterministic_resource_id(
            "org",
            role,
            source_id,
        ),
        "identifier": [
            {
                "system": f"urn:medilacra:{role}",
                "value": str(source_id),
            }
        ],
        "name": str(name),
    }


def build_clinical_coverage(
    coverage_profile,
    *,
    patient: dict[str, Any],
    payer: dict[str, Any],
    employer: dict[str, Any] | None,
) -> dict[str, Any]:
    coverage: dict[str, Any] = {
        "resourceType": "Coverage",
        "id": deterministic_resource_id(
            "cov",
            "clinical",
            coverage_profile.coverage_profile_id,
        ),
        "identifier": [
            {
                "system": "urn:medilacra:clinical-coverage-profile",
                "value": str(
                    coverage_profile.coverage_profile_id
                ),
            }
        ],
        "status": "active",
        "subscriber": _reference(patient),
        "subscriberId": str(coverage_profile.member_id),
        "beneficiary": _reference(patient),
        "relationship": _self_relationship(),
        "period": {
            "start": _iso_date(
                coverage_profile.effective_start
            ),
            "end": _iso_date(
                coverage_profile.effective_end
            ),
        },
        "payor": [_reference(payer)],
    }

    if employer is not None:
        coverage["policyHolder"] = _reference(employer)

    if coverage_profile.plan_type:
        coverage["type"] = {
            "text": str(coverage_profile.plan_type)
        }

    classes = _coverage_classes(
        group_number=coverage_profile.group_number,
        plan_id=coverage_profile.plan_id,
        plan_name=coverage_profile.plan_name,
    )
    if classes:
        coverage["class"] = classes

    return coverage


def build_payer_coverage(
    *,
    member: MemberRecord,
    enrollment: EnrollmentRecord,
    plan: BenefitPlan,
    patient: dict[str, Any],
    payer: dict[str, Any],
) -> dict[str, Any]:
    if enrollment.status != EnrollmentStatus.ACTIVE:
        raise NotImplementedError(
            "FHIR R4 eligibility MVP only projects ACTIVE enrollment"
        )

    coverage: dict[str, Any] = {
        "resourceType": "Coverage",
        "id": deterministic_resource_id(
            "pcov",
            enrollment.payer_id,
            enrollment.enrollment_id,
        ),
        "identifier": [
            {
                "system": (
                    "urn:medilacra:payer-enrollment:"
                    f"{enrollment.payer_id}"
                ),
                "value": enrollment.enrollment_id,
            }
        ],
        "status": "active",
        "subscriber": _reference(patient),
        "subscriberId": member.member_id,
        "beneficiary": _reference(patient),
        "relationship": _self_relationship(),
        "period": {
            "start": _iso_date(enrollment.effective_start),
            "end": _iso_date(enrollment.effective_end),
        },
        "payor": [_reference(payer)],
        "type": {"text": plan.plan_type},
    }

    classes = _coverage_classes(
        group_number=enrollment.group_number,
        plan_id=plan.plan_id,
        plan_name=plan.plan_name,
    )
    if classes:
        coverage["class"] = classes

    return coverage


def build_coverage_eligibility_request(
    *,
    inquiry,
    exchange_identity,
    run_at: datetime,
    patient: dict[str, Any],
    coverage: dict[str, Any],
    requester: dict[str, Any],
    payer: dict[str, Any],
) -> dict[str, Any]:
    return {
        "resourceType": "CoverageEligibilityRequest",
        "id": deterministic_resource_id(
            "cerq",
            exchange_identity.exchange_id,
        ),
        "identifier": [
            {
                "system": ELIGIBILITY_IDENTIFIER_SYSTEM,
                "value": exchange_identity.exchange_id,
            }
        ],
        "status": "active",
        "purpose": ["validation", "benefits"],
        "patient": _reference(patient),
        "servicedDate": _iso_date(inquiry.service_date),
        "created": _fhir_datetime(run_at),
        "provider": _reference(requester),
        "insurer": _reference(payer),
        "insurance": [
            {
                "focal": True,
                "coverage": _reference(coverage),
            }
        ],
    }


def build_coverage_eligibility_response(
    *,
    response: EligibilityResponse,
    inquiry,
    exchange_identity,
    run_at: datetime,
    patient: dict[str, Any],
    coverage: dict[str, Any],
    requester: dict[str, Any],
    payer: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    if response.outcome != EligibilityOutcome.ACTIVE:
        raise NotImplementedError(
            "FHIR R4 eligibility MVP only projects ACTIVE responses"
        )

    insurance: dict[str, Any] = {
        "coverage": _reference(coverage),
        "inforce": True,
    }

    if response.coverage_start or response.coverage_end:
        period: dict[str, str] = {}
        if response.coverage_start:
            period["start"] = _iso_date(
                response.coverage_start
            )
        if response.coverage_end:
            period["end"] = _iso_date(
                response.coverage_end
            )
        insurance["benefitPeriod"] = period

    return {
        "resourceType": "CoverageEligibilityResponse",
        "id": deterministic_resource_id(
            "cers",
            exchange_identity.exchange_id,
        ),
        "identifier": [
            {
                "system": ELIGIBILITY_IDENTIFIER_SYSTEM,
                "value": exchange_identity.exchange_id,
            }
        ],
        "status": "active",
        "purpose": ["validation", "benefits"],
        "patient": _reference(patient),
        "servicedDate": _iso_date(inquiry.service_date),
        "created": _fhir_datetime(run_at),
        "requestor": _reference(requester),
        "request": _reference(request),
        "outcome": "complete",
        "insurer": _reference(payer),
        "insurance": [insurance],
    }


def build_request_bundle(
    *,
    request: dict[str, Any],
    clinical_patient: dict[str, Any],
    clinical_coverage: dict[str, Any],
    requester: dict[str, Any],
    payer: dict[str, Any],
    employer: dict[str, Any] | None,
    exchange_identity,
) -> dict[str, Any]:
    resources = [
        request,
        clinical_patient,
        clinical_coverage,
        requester,
        payer,
    ]
    if employer is not None:
        resources.append(employer)

    return {
        "resourceType": "Bundle",
        "id": deterministic_resource_id(
            "bundle",
            "request",
            exchange_identity.exchange_id,
        ),
        "type": "collection",
        "entry": [
            _bundle_entry(resource)
            for resource in resources
        ],
    }


def build_response_bundle(
    *,
    response_resource: dict[str, Any],
    request: dict[str, Any],
    clinical_patient: dict[str, Any],
    clinical_coverage: dict[str, Any],
    payer_patient: dict[str, Any],
    payer_coverage: dict[str, Any],
    requester: dict[str, Any],
    payer: dict[str, Any],
    employer: dict[str, Any] | None,
    exchange_identity,
) -> dict[str, Any]:
    resources = [
        response_resource,
        request,
        clinical_patient,
        clinical_coverage,
        payer_patient,
        payer_coverage,
        requester,
        payer,
    ]
    if employer is not None:
        resources.append(employer)

    return {
        "resourceType": "Bundle",
        "id": deterministic_resource_id(
            "bundle",
            "response",
            exchange_identity.exchange_id,
        ),
        "type": "collection",
        "entry": [
            _bundle_entry(resource)
            for resource in resources
        ],
    }
