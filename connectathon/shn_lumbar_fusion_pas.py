from __future__ import annotations

import argparse
import copy
import json
import uuid
from pathlib import Path
from typing import Any

from connectathon.shn_lumbar_fusion import (
    ICD10_CM_SYSTEM,
    LUMBAR_FUSION_CPT,
    LUMBAR_FUSION_QUESTIONNAIRE,
    LUMBAR_SPONDYLOLISTHESIS_DISPLAY,
    LUMBAR_SPONDYLOLISTHESIS_ICD10,
    build_lumbar_fusion_reality,
)
from connectathon.shn_medilacra_crd import (
    SHN_PAYER_IDENTIFIER_SYSTEM,
    SHN_ROUTE_00301,
)
from connectathon.shn_mvp0 import CASE_NAMESPACE, supporting_fhir


PAS_SD = "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/"
PROFILE_REQUEST_BUNDLE = f"{PAS_SD}profile-pas-request-bundle"
PROFILE_CLAIM = f"{PAS_SD}profile-claim"
PROFILE_BENEFICIARY = f"{PAS_SD}profile-beneficiary"
PROFILE_SUBSCRIBER = f"{PAS_SD}profile-subscriber"
PROFILE_COVERAGE = f"{PAS_SD}profile-coverage"
PROFILE_INSURER = f"{PAS_SD}profile-insurer"
PROFILE_REQUESTOR = f"{PAS_SD}profile-requestor"
PROFILE_PRACTITIONER = f"{PAS_SD}profile-practitioner"
PROFILE_PRACTITIONER_ROLE = f"{PAS_SD}profile-practitionerrole"
PROFILE_SERVICE_REQUEST = f"{PAS_SD}profile-servicerequest"

EXT_TRANSMISSION_IDENTIFIERS = f"{PAS_SD}extension-TransmissionIdentifiers"
EXT_CARE_TEAM_CLAIM_SCOPE = f"{PAS_SD}extension-careTeamClaimScope"
EXT_SERVICE_ITEM_REQUEST_TYPE = f"{PAS_SD}extension-serviceItemRequestType"
EXT_CERTIFICATION_TYPE = f"{PAS_SD}extension-certificationType"
EXT_REQUESTED_SERVICE = f"{PAS_SD}extension-requestedService"
EXT_DOCUMENT_INFORMATION = f"{PAS_SD}extension-documentInformation"

DTR_QR_COVERAGE = (
    "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/qr-coverage"
)

PAS_TEMP_CODES = "http://hl7.org/fhir/us/davinci-pas/CodeSystem/PASTempCodes"
X12_PWK01_SYSTEM = "https://codesystem.x12.org/005010/755"
X12_REQUEST_TYPE_SYSTEM = "https://codesystem.x12.org/005010/1525"
X12_CERTIFICATION_TYPE_SYSTEM = "https://codesystem.x12.org/005010/1322"
X12_SERVICE_TYPE_SYSTEM = "https://codesystem.x12.org/005010/1365"
X12_RELATIONSHIP_SYSTEM = "https://codesystem.x12.org/005010/1069"
CMS_POS_SYSTEM = (
    "https://www.cms.gov/Medicare/Coding/place-of-service-codes/"
    "Place_of_Service_Code_Set"
)
CLAIM_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/claim-type"
PROCESS_PRIORITY_SYSTEM = "http://terminology.hl7.org/CodeSystem/processpriority"
SUBSCRIBER_RELATIONSHIP_SYSTEM = (
    "http://terminology.hl7.org/CodeSystem/subscriber-relationship"
)
V2_IDENTIFIER_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v2-0203"
US_NPI_SYSTEM = "http://hl7.org/fhir/sid/us-npi"

MEMBER_IDENTIFIER_SYSTEM = "urn:medilacra:member-id"
REQUESTOR_IDENTIFIER_SYSTEM = "urn:medilacra:requestor-id"
PRACTITIONER_IDENTIFIER_SYSTEM = "urn:medilacra:provider-id"
CLAIM_IDENTIFIER_SYSTEM = "urn:medilacra:pas:claim"
TRANSACTION_IDENTIFIER_SYSTEM = "urn:medilacra:pas:transaction"
PAYER_NPI = "1234567893"
PROVIDER_FHIR_BASE = "https://medilacra.example/fhir"


def _stable(seed: int, label: str) -> str:
    return uuid.uuid5(CASE_NAMESPACE, f"{seed}:pas:{label}").hex[:16]


def _reference(resource: dict[str, Any]) -> str:
    return f"{resource['resourceType']}/{resource['id']}"


def _entry(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "fullUrl": f"{PROVIDER_FHIR_BASE}/{resource['resourceType']}/{resource['id']}",
        "resource": resource,
    }


def _name_parts(text: str) -> tuple[str, str]:
    if "," in text:
        family, given = [part.strip() for part in text.split(",", 1)]
        return family, given.split()[0] if given else "SYNTHETIC"
    parts = text.split()
    if not parts:
        return "SYNTHETIC", "PATIENT"
    return parts[-1], parts[0]


def _mb_identifier(member_id: str) -> dict[str, Any]:
    return {
        "type": {
            "coding": [
                {
                    "system": V2_IDENTIFIER_TYPE_SYSTEM,
                    "code": "MB",
                    "display": "Member Number",
                }
            ]
        },
        "system": MEMBER_IDENTIFIER_SYSTEM,
        "value": member_id,
    }


def _qr_coverage_reference(qr: dict[str, Any]) -> str | None:
    values = [
        extension.get("valueReference", {}).get("reference")
        for extension in qr.get("extension", [])
        if extension.get("url") == DTR_QR_COVERAGE
    ]
    values = [value for value in values if value]
    if not values:
        return None
    if len(set(values)) != 1:
        raise ValueError("QuestionnaireResponse carries multiple qr-coverage references")
    return values[0]


def _leaf_answers(qr: dict[str, Any]) -> dict[str, Any]:
    answers: dict[str, Any] = {}

    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            link_id = item.get("linkId")
            values = item.get("answer") or []
            if values:
                if len(values) != 1:
                    raise ValueError(
                        f"QuestionnaireResponse item {link_id!r} has multiple answers"
                    )
                answer = values[0]
                if "valueInteger" in answer:
                    answers[str(link_id)] = answer["valueInteger"]
                elif "valueBoolean" in answer:
                    answers[str(link_id)] = answer["valueBoolean"]
                else:
                    raise ValueError(
                        f"QuestionnaireResponse item {link_id!r} has unsupported answer type"
                    )
            walk(item.get("item") or [])

    walk(qr.get("item") or [])
    return answers


def validate_documented_questionnaire_response(
    qr: dict[str, Any],
    seed: int,
) -> None:
    reality = build_lumbar_fusion_reality(seed)
    expected_patient = f"Patient/{reality.patient.patient_id}"
    expected_coverage = f"Coverage/{reality.coverage_id}"

    if qr.get("resourceType") != "QuestionnaireResponse":
        raise ValueError("documentation is not a QuestionnaireResponse")
    if qr.get("status") != "completed":
        raise ValueError("QuestionnaireResponse must be completed before PAS")
    if qr.get("questionnaire") != LUMBAR_FUSION_QUESTIONNAIRE:
        raise ValueError("QuestionnaireResponse canonical does not match lumbar-fusion DTR")
    if qr.get("subject", {}).get("reference") != expected_patient:
        raise ValueError("QuestionnaireResponse subject does not match MediLacra reality")
    if _qr_coverage_reference(qr) != expected_coverage:
        raise ValueError("QuestionnaireResponse coverage does not match MediLacra reality")

    answers = _leaf_answers(qr)
    if answers.get("1.1") != reality.therapy_weeks:
        raise ValueError("QuestionnaireResponse item 1.1 does not match therapy weeks")
    if (
        answers.get("1.2")
        is not reality.imaging_confirms_instability_or_spondylolisthesis
    ):
        raise ValueError("QuestionnaireResponse item 1.2 does not match imaging finding")


def _build_patient(seed: int) -> dict[str, Any]:
    reality = build_lumbar_fusion_reality(seed)
    family, given = _name_parts(reality.patient.patient_name)
    return {
        "resourceType": "Patient",
        "id": reality.patient.patient_id,
        "meta": {"profile": [PROFILE_BENEFICIARY, PROFILE_SUBSCRIBER]},
        "identifier": [_mb_identifier(reality.transaction.member_id)],
        "name": [{"family": family, "given": [given]}],
        "birthDate": reality.patient.date_of_birth,
        "gender": "male" if reality.patient.sex == "M" else "female",
        "telecom": [{"system": "phone", "value": reality.patient.phone}],
    }


def _build_insurer() -> dict[str, Any]:
    return {
        "resourceType": "Organization",
        "id": "shn-payer-00301",
        "meta": {"profile": [PROFILE_INSURER]},
        "active": True,
        "name": "SHN reference payer route 00301",
        "identifier": [
            {
                "system": SHN_PAYER_IDENTIFIER_SYSTEM,
                "value": SHN_ROUTE_00301,
            },
            {"system": US_NPI_SYSTEM, "value": PAYER_NPI},
        ],
        "type": [{"coding": [{"system": "https://codesystem.x12.org/005010/98", "code": "PR"}]}],
    }


def _build_requestor(seed: int) -> dict[str, Any]:
    reality = build_lumbar_fusion_reality(seed)
    return {
        "resourceType": "Organization",
        "id": f"requestor-{_stable(seed, 'requestor')}",
        "meta": {"profile": [PROFILE_REQUESTOR]},
        "active": True,
        "name": "MediLacra Synthetic Spine Provider",
        "identifier": [
            {
                "system": REQUESTOR_IDENTIFIER_SYSTEM,
                "value": f"MEDILACRA-{seed:04d}",
            },
            {
                "system": US_NPI_SYSTEM,
                "value": reality.transaction.billing_provider_npi,
            },
        ],
        "type": [{"coding": [{"system": "https://codesystem.x12.org/005010/98", "code": "X3"}]}],
    }


def _build_practitioner(seed: int) -> dict[str, Any]:
    reality = build_lumbar_fusion_reality(seed)
    family, given = _name_parts(reality.encounter.attending_provider_name)
    return {
        "resourceType": "Practitioner",
        "id": f"practitioner-{_stable(seed, 'practitioner')}",
        "meta": {"profile": [PROFILE_PRACTITIONER]},
        "identifier": [
            {
                "system": PRACTITIONER_IDENTIFIER_SYSTEM,
                "value": reality.encounter.attending_provider_id,
            }
        ],
        "name": [{"family": family, "given": [given]}],
        "telecom": [{"system": "phone", "value": "555-0100"}],
    }


def _build_practitioner_role(
    seed: int,
    practitioner: dict[str, Any],
    requestor: dict[str, Any],
) -> dict[str, Any]:
    return {
        "resourceType": "PractitionerRole",
        "id": f"practitioner-role-{_stable(seed, 'practitioner-role')}",
        "meta": {"profile": [PROFILE_PRACTITIONER_ROLE]},
        "practitioner": {"reference": _reference(practitioner)},
        "organization": {"reference": _reference(requestor)},
        "telecom": [{"system": "phone", "value": "555-0100"}],
    }


def _build_coverage(
    seed: int,
    patient: dict[str, Any],
    insurer: dict[str, Any],
) -> dict[str, Any]:
    reality = build_lumbar_fusion_reality(seed)
    member = reality.transaction.member_id
    return {
        "resourceType": "Coverage",
        "id": reality.coverage_id,
        "meta": {"profile": [PROFILE_COVERAGE]},
        "status": "active",
        "identifier": [_mb_identifier(member)],
        "subscriber": {"reference": _reference(patient)},
        "subscriberId": member,
        "beneficiary": {"reference": _reference(patient)},
        "relationship": {
            "coding": [
                {
                    "system": SUBSCRIBER_RELATIONSHIP_SYSTEM,
                    "code": "self",
                    "display": "Self",
                },
                {
                    "system": X12_RELATIONSHIP_SYSTEM,
                    "code": "18",
                    "display": "Self",
                },
            ]
        },
        "period": {"start": "2026-09-05"},
        "payor": [
            {
                "reference": _reference(insurer),
                "identifier": {
                    "system": SHN_PAYER_IDENTIFIER_SYSTEM,
                    "value": SHN_ROUTE_00301,
                },
            }
        ],
        "class": [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/coverage-class",
                            "code": "group",
                        }
                    ]
                },
                "value": reality.transaction.group_number,
            },
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/coverage-class",
                            "code": "plan",
                        }
                    ]
                },
                "value": reality.transaction.insurance_plan_name,
            },
        ],
    }


def _build_service_request(
    seed: int,
    patient: dict[str, Any],
    coverage: dict[str, Any],
    practitioner: dict[str, Any],
) -> dict[str, Any]:
    reality = build_lumbar_fusion_reality(seed)
    source = supporting_fhir(reality)["service_request"]
    order = copy.deepcopy(source)
    order["meta"] = {"profile": [PROFILE_SERVICE_REQUEST]}
    order["status"] = "active"
    order["intent"] = "order"
    order["subject"] = {"reference": _reference(patient)}
    order["insurance"] = [{"reference": _reference(coverage)}]
    order["requester"] = {"reference": _reference(practitioner)}
    return order


def _supporting_info(qr: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence": 1,
        "category": {
            "coding": [
                {
                    "system": PAS_TEMP_CODES,
                    "code": "additionalInformation",
                }
            ]
        },
        "valueReference": {"reference": _reference(qr)},
        "extension": [
            {
                "url": EXT_DOCUMENT_INFORMATION,
                "extension": [
                    {
                        "url": "reportTypeCode",
                        "valueCodeableConcept": {
                            "coding": [
                                {
                                    "system": X12_PWK01_SYSTEM,
                                    "code": "OZ",
                                    "display": "Support Data for Claim",
                                }
                            ]
                        },
                    }
                ],
            }
        ],
    }


def _build_claim(
    seed: int,
    patient: dict[str, Any],
    insurer: dict[str, Any],
    requestor: dict[str, Any],
    coverage: dict[str, Any],
    practitioner_role: dict[str, Any],
    order: dict[str, Any],
    qr: dict[str, Any],
) -> dict[str, Any]:
    reality = build_lumbar_fusion_reality(seed)
    diagnosis = {
        "coding": [
            {
                "system": ICD10_CM_SYSTEM,
                "code": LUMBAR_SPONDYLOLISTHESIS_ICD10,
                "display": LUMBAR_SPONDYLOLISTHESIS_DISPLAY,
            }
        ]
    }
    return {
        "resourceType": "Claim",
        "id": f"claim-{_stable(seed, 'claim')}",
        "meta": {"profile": [PROFILE_CLAIM]},
        "extension": [
            {
                "url": EXT_TRANSMISSION_IDENTIFIERS,
                "extension": [
                    {
                        "url": "applicationSenderCode",
                        "valueString": reality.transaction.billing_provider_npi,
                    },
                    {
                        "url": "applicationReceiverCode",
                        "valueString": PAYER_NPI,
                    },
                ],
            }
        ],
        "identifier": [
            {
                "system": CLAIM_IDENTIFIER_SYSTEM,
                "value": str(uuid.uuid5(CASE_NAMESPACE, f"{seed}:pas:claim-identifier")),
            }
        ],
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": CLAIM_TYPE_SYSTEM,
                    "code": "professional",
                    "display": "Professional",
                }
            ]
        },
        "use": "preauthorization",
        "patient": {"reference": _reference(patient)},
        "created": "2026-09-05T10:30:00Z",
        "provider": {"reference": _reference(requestor)},
        "priority": {
            "coding": [
                {
                    "system": PROCESS_PRIORITY_SYSTEM,
                    "code": "normal",
                    "display": "Normal",
                }
            ]
        },
        "insurer": {"reference": _reference(insurer)},
        "insurance": [
            {
                "sequence": 1,
                "focal": True,
                "coverage": {"reference": _reference(coverage)},
            }
        ],
        "careTeam": [
            {
                "sequence": 1,
                "provider": {"reference": _reference(practitioner_role)},
                "extension": [
                    {
                        "url": EXT_CARE_TEAM_CLAIM_SCOPE,
                        "valueBoolean": True,
                    }
                ],
            }
        ],
        "diagnosis": [
            {
                "sequence": 1,
                "diagnosisCodeableConcept": diagnosis,
            }
        ],
        "supportingInfo": [_supporting_info(qr)],
        "item": [
            {
                "sequence": 1,
                "careTeamSequence": [1],
                "diagnosisSequence": [1],
                "category": {
                    "coding": [
                        {
                            "system": X12_SERVICE_TYPE_SYSTEM,
                            "code": "2",
                            "display": "Surgical",
                        }
                    ]
                },
                "extension": [
                    {
                        "url": EXT_SERVICE_ITEM_REQUEST_TYPE,
                        "valueCodeableConcept": {
                            "coding": [
                                {
                                    "system": X12_REQUEST_TYPE_SYSTEM,
                                    "code": "HS",
                                    "display": "Health Services Review",
                                }
                            ]
                        },
                    },
                    {
                        "url": EXT_CERTIFICATION_TYPE,
                        "valueCodeableConcept": {
                            "coding": [
                                {
                                    "system": X12_CERTIFICATION_TYPE_SYSTEM,
                                    "code": "I",
                                    "display": "Initial",
                                }
                            ]
                        },
                    },
                    {
                        "url": EXT_REQUESTED_SERVICE,
                        "valueReference": {"reference": _reference(order)},
                    },
                ],
                "locationCodeableConcept": {
                    "coding": [
                        {
                            "system": CMS_POS_SYSTEM,
                            "code": reality.encounter.place_of_service_code,
                            "display": reality.encounter.place_of_service_description,
                        }
                    ]
                },
                "productOrService": copy.deepcopy(order["code"]),
            }
        ],
    }


def build_documented_pas_bundle(
    seed: int,
    questionnaire_response: dict[str, Any],
) -> dict[str, Any]:
    """Build a self-contained PAS request carrying completed DTR documentation."""
    validate_documented_questionnaire_response(questionnaire_response, seed)
    reality = build_lumbar_fusion_reality(seed)

    patient = _build_patient(seed)
    insurer = _build_insurer()
    requestor = _build_requestor(seed)
    practitioner = _build_practitioner(seed)
    role = _build_practitioner_role(seed, practitioner, requestor)
    coverage = _build_coverage(seed, patient, insurer)
    order = _build_service_request(seed, patient, coverage, practitioner)
    qr = copy.deepcopy(questionnaire_response)
    claim = _build_claim(
        seed,
        patient,
        insurer,
        requestor,
        coverage,
        role,
        order,
        qr,
    )

    bundle = {
        "resourceType": "Bundle",
        "meta": {"profile": [PROFILE_REQUEST_BUNDLE]},
        "identifier": {
            "system": TRANSACTION_IDENTIFIER_SYSTEM,
            "value": str(uuid.uuid5(CASE_NAMESPACE, f"{seed}:pas:transaction")),
        },
        "type": "collection",
        "timestamp": "2026-09-05T10:30:00Z",
        "entry": [
            _entry(claim),
            _entry(patient),
            _entry(practitioner),
            _entry(role),
            _entry(requestor),
            _entry(insurer),
            _entry(coverage),
            _entry(order),
            _entry(qr),
        ],
    }

    # The request must preserve the clinical identity established before PAS.
    serialized = json.dumps(bundle)
    if "MBR-COVERED" in serialized or "G0151" in serialized:
        raise ValueError("reference-fixture identity leaked into MediLacra PAS request")
    if LUMBAR_FUSION_CPT not in serialized:
        raise ValueError("lumbar-fusion service code missing from PAS request")
    if LUMBAR_SPONDYLOLISTHESIS_ICD10 not in serialized:
        raise ValueError("lumbar diagnosis missing from PAS request")
    if reality.patient.patient_id not in serialized or reality.coverage_id not in serialized:
        raise ValueError("MediLacra Patient/Coverage identity missing from PAS request")

    return bundle


def expected_pas_behavior(seed: int) -> dict[str, Any]:
    reality = build_lumbar_fusion_reality(seed)
    return {
        "seed": seed,
        "case_id": reality.case_id,
        "service_code": LUMBAR_FUSION_CPT,
        "diagnosis_code": LUMBAR_SPONDYLOLISTHESIS_ICD10,
        "questionnaire": LUMBAR_FUSION_QUESTIONNAIRE,
        "payer_route": {
            "system": SHN_PAYER_IDENTIFIER_SYSTEM,
            "value": SHN_ROUTE_00301,
        },
        "expected_live_response": {
            "http": 200,
            "claim_response_outcome": "complete",
            "review_action_code": "A1",
            "review_action_display": "Certified in total",
            "communication_request_count": 0,
            "authorization_expected": True,
        },
        "note": (
            "This expectation comes from SHN's documented route-00301 lumbar-fusion "
            "PAS case with completed questionnaire documentation. It is not embedded "
            "into the outbound request."
        ),
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_pas_case(
    bundle: dict[str, Any],
    expected: dict[str, Any],
    output_root: str | Path,
) -> Path:
    root = Path(output_root) / expected["case_id"]
    root.mkdir(parents=True, exist_ok=True)
    (root / "pas_request.json").write_bytes(_json_bytes(bundle))
    (root / "expected_pas_behavior.json").write_bytes(_json_bytes(expected))
    return root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build one documented MediLacra lumbar-fusion PAS request"
    )
    parser.add_argument("--seed", type=int, default=300)
    parser.add_argument("--questionnaire-response", required=True)
    parser.add_argument(
        "--out",
        default="connectathon/results/shn_lumbar_fusion_pas",
    )
    args = parser.parse_args()

    qr = json.loads(Path(args.questionnaire_response).read_text())
    bundle = build_documented_pas_bundle(args.seed, qr)
    expected = expected_pas_behavior(args.seed)
    out = write_pas_case(bundle, expected, args.out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
