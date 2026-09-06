from __future__ import annotations

import argparse
import copy
import io
import json
import random
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from faker import Faker

from hl7_demo.models import Encounter, Patient, Transaction


DTR_QR_CONTEXT = "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/qr-context"
DTR_QR_COVERAGE = "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/qr-coverage"
DTR_INTENDED_USE = "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/intendedUse"
DTR_INFO_ORIGIN = "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/information-origin"
CRD_21_TEMP_CODES = "http://hl7.org/fhir/us/davinci-crd/CodeSystem/temp"

SHN_CONTRACT = "pa.dtr"
SHN_FROM = "2.1"
SHN_TO = "2.2"

CASE_NAMESPACE = uuid.UUID("8b717c70-86d2-4c1f-b1ab-51c8837856a9")


@dataclass(frozen=True)
class SHNMVP0Reality:
    """One coherent synthetic patient reality for the SHN MVP-0 experiment."""

    case_id: str
    seed: int
    patient: Patient
    encounter: Encounter
    transaction: Transaction
    coverage_id: str
    service_request_id: str
    payer_id: str
    therapy_weeks: int
    neuro_deficit: bool
    prior_imaging: bool


def _stable_id(seed: int, label: str) -> str:
    value = uuid.uuid5(CASE_NAMESPACE, f"{seed}:{label}")
    return value.hex[:16]


def _provider_name(fake: Faker) -> str:
    name = fake.name().split()
    return f"{name[-1].upper()}, {name[0].upper()}"


def build_reality(seed: int = 43) -> SHNMVP0Reality:
    """Build a deterministic synthetic reality using MediLacra's entity models.

    This fixture deliberately avoids network/reference-data lookups so the
    Connectathon experiment remains runnable offline. IDs and clinical facts
    are deterministic for a seed.
    """
    fake = Faker()
    fake.seed_instance(seed)
    rng = random.Random(seed)

    patient_id = f"ML-{_stable_id(seed, 'patient')}"
    encounter_id = f"ENC-{_stable_id(seed, 'encounter')}"
    visit_number = f"VN-{_stable_id(seed, 'visit')}"
    account_number = f"ACC-{_stable_id(seed, 'account')}"
    coverage_id = f"COV-{_stable_id(seed, 'coverage')}"
    service_request_id = f"SR-{_stable_id(seed, 'service-request')}"
    payer_id = f"PAY-{_stable_id(seed, 'payer')}"

    sex = rng.choice(["M", "F"])
    name_parts = (fake.name_male() if sex == "M" else fake.name_female()).split()
    first, last = name_parts[0], name_parts[-1]
    dob = fake.date_of_birth(minimum_age=35, maximum_age=80)
    patient_name = f"{last.upper()}, {first.upper()}"

    patient = Patient(
        patient_id=patient_id,
        patient_name=patient_name,
        date_of_birth=dob.strftime("%Y-%m-%d"),
        sex=sex,
        gender="Man" if sex == "M" else "Woman",
        race=rng.choice(
            [
                "White",
                "Black or African American",
                "Asian",
                "American Indian or Alaska Native",
                "Other",
            ]
        ),
        ethnicity=rng.choice(["Not Hispanic or Latino", "Hispanic or Latino"]),
        marital_status=rng.choice(["Single", "Married", "Divorced", "Widowed"]),
        language=rng.choice(["English", "Spanish", "Portuguese", "French"]),
        employer=fake.company().upper(),
        ssn=fake.ssn(),
        address=fake.street_address(),
        phone=fake.phone_number().replace("\n", " "),
        email=f"{first.lower()}.{last.lower()}@example.invalid".replace(" ", ""),
        zip_code=fake.postcode()[:5],
        city=fake.city(),
        state=fake.state_abbr(),
    )

    ordering_provider = _provider_name(fake)
    attending_provider = _provider_name(fake)
    encounter = Encounter(
        encounter_id=encounter_id,
        patient_id=patient_id,
        visit_number=visit_number,
        account_number=account_number,
        patient_class="OUTPATIENT",
        assigned_patient_location="RAD_DEPT1",
        admit_datetime="2026-09-05 09:00:00",
        discharge_datetime="2026-09-05 11:00:00",
        hospital_service="RAD",
        admit_source="Physician Referral",
        discharge_disposition="Home",
        ordering_provider_id=f"R-{_stable_id(seed, 'ordering-provider')}",
        ordering_provider_name=ordering_provider,
        attending_provider_id=f"P-{_stable_id(seed, 'attending-provider')}",
        attending_provider_name=attending_provider,
        attending_provider_taxonomy="2085R0202X",
        attending_provider_specialty="Diagnostic Radiology",
        mid_level_provider_id=f"ML-{_stable_id(seed, 'midlevel-provider')}",
        mid_level_provider_name=_provider_name(fake),
        referring_provider_id=f"REF-{_stable_id(seed, 'referring-provider')}",
        referring_provider_name=_provider_name(fake),
        placer_order_number=service_request_id,
        filler_order_number=f"FIL-{_stable_id(seed, 'filler-order')}",
        place_of_service_code="22",
        place_of_service_description="On Campus-Outpatient Hospital",
    )

    plan_name, plan_type = rng.choice(
        [
            ("Blue Cross PPO", "PPO"),
            ("Community Health HMO", "HMO"),
            ("Regional Health EPO", "EPO"),
            ("Medicare", "MEDICARE"),
            ("Medicaid", "MEDICAID"),
        ]
    )
    transaction = Transaction(
        transaction_id=str(uuid.uuid5(CASE_NAMESPACE, f"{seed}:transaction")),
        encounter_id=encounter_id,
        transaction_date="2026-09-05 10:30:00",
        transaction_amount=425.00,
        unit_cost=225.00,
        transaction_quantity=1,
        fee_schedule="TECH",
        insurance_plan_id=coverage_id,
        insurance_plan_name=plan_name,
        member_id=f"MEM-{_stable_id(seed, 'member')}",
        group_number=f"GRP-{_stable_id(seed, 'group')}",
        plan_type=plan_type,
        subscriber_relationship="SELF",
        authorization_number=f"AUTH-{_stable_id(seed, 'auth')}",
        billing_provider_id=f"BILL-{_stable_id(seed, 'billing-provider')}",
        billing_provider_name=attending_provider,
        billing_provider_npi=str(1000000000 + (seed % 899999999)),
        guarantor_name=patient_name,
        guarantor_relationship="SELF",
    )

    return SHNMVP0Reality(
        case_id=f"shn_mvp0_{seed:04d}",
        seed=seed,
        patient=patient,
        encounter=encounter,
        transaction=transaction,
        coverage_id=coverage_id,
        service_request_id=service_request_id,
        payer_id=payer_id,
        therapy_weeks=6 + (seed % 4),
        neuro_deficit=False,
        prior_imaging=True,
    )


def reality_manifest(reality: SHNMVP0Reality) -> dict[str, Any]:
    """Return the truth record PIQITT can later compare against SHN artifacts."""
    patient_ref = f"Patient/{reality.patient.patient_id}"
    coverage_ref = f"Coverage/{reality.coverage_id}"
    order_ref = f"ServiceRequest/{reality.service_request_id}"
    payer_ref = f"Organization/{reality.payer_id}"

    return {
        "experiment": "Medilacra -> SHN -> PIQITT MVP-0",
        "case_id": reality.case_id,
        "seed": reality.seed,
        "entities": {
            "patient": asdict(reality.patient),
            "encounter": asdict(reality.encounter),
            "transaction": asdict(reality.transaction),
        },
        "relationships": [
            {"subject": patient_ref, "predicate": "hasCoverage", "object": coverage_ref},
            {"subject": patient_ref, "predicate": "hasOrder", "object": order_ref},
            {"subject": coverage_ref, "predicate": "payor", "object": payer_ref},
        ],
        "clinical_facts": {
            "conservative_therapy_weeks": reality.therapy_weeks,
            "neuro_deficit": reality.neuro_deficit,
            "prior_imaging": reality.prior_imaging,
        },
    }


def supporting_fhir(reality: SHNMVP0Reality) -> dict[str, dict[str, Any]]:
    """Project the minimal supporting FHIR resources for human/PIQITT inspection."""
    patient_ref = f"Patient/{reality.patient.patient_id}"
    coverage_ref = f"Coverage/{reality.coverage_id}"
    payer_ref = f"Organization/{reality.payer_id}"

    patient = {
        "resourceType": "Patient",
        "id": reality.patient.patient_id,
        "identifier": [
            {
                "system": "urn:medilacra:member-id",
                "value": reality.transaction.member_id,
            }
        ],
        "name": [{"text": reality.patient.patient_name}],
        "birthDate": reality.patient.date_of_birth,
        "gender": "male" if reality.patient.sex == "M" else "female",
    }

    payer = {
        "resourceType": "Organization",
        "id": reality.payer_id,
        "identifier": [
            {
                "system": "urn:medilacra:payer-id",
                "value": reality.transaction.insurance_plan_name,
            }
        ],
        "name": reality.transaction.insurance_plan_name,
    }

    coverage = {
        "resourceType": "Coverage",
        "id": reality.coverage_id,
        "status": "active",
        "beneficiary": {"reference": patient_ref},
        "subscriberId": reality.transaction.member_id,
        "payor": [{"reference": payer_ref}],
        "class": [
            {
                "type": {"coding": [{"system": "urn:medilacra:coverage-class", "code": "group"}]},
                "value": reality.transaction.group_number,
            }
        ],
    }

    service_request = {
        "resourceType": "ServiceRequest",
        "id": reality.service_request_id,
        "status": "active",
        "intent": "order",
        "subject": {"reference": patient_ref},
        "insurance": [{"reference": coverage_ref}],
        "code": {
            "coding": [
                {
                    "system": "http://www.ama-assn.org/go/cpt",
                    "code": "72148",
                    "display": "MRI lumbar spine without contrast",
                }
            ]
        },
    }

    return {
        "patient": patient,
        "payer": payer,
        "coverage": coverage,
        "service_request": service_request,
    }


def _auto_origin_extension() -> dict[str, Any]:
    return {
        "extension": [{"url": "source", "valueCode": "auto"}],
        "url": DTR_INFO_ORIGIN,
    }


def build_dtr_21_questionnaire_response(reality: SHNMVP0Reality) -> dict[str, Any]:
    """Project reality into a DTR 2.1 QuestionnaireResponse accepted by SHN's demo transform."""
    patient_ref = f"Patient/{reality.patient.patient_id}"
    coverage_ref = f"Coverage/{reality.coverage_id}"
    order_ref = f"ServiceRequest/{reality.service_request_id}"

    return {
        "resourceType": "QuestionnaireResponse",
        "id": f"qr-{_stable_id(reality.seed, 'questionnaire-response')}",
        "extension": [
            {
                "url": DTR_QR_CONTEXT,
                "valueReference": {"reference": coverage_ref},
            },
            {
                "url": DTR_QR_CONTEXT,
                "valueReference": {"reference": order_ref},
            },
            {
                "url": DTR_INTENDED_USE,
                "valueCodeableConcept": {
                    "coding": [
                        {
                            "system": CRD_21_TEMP_CODES,
                            "code": "withpa",
                            "display": "Information needed for a prior authorization",
                        }
                    ]
                },
            },
        ],
        "questionnaire": "http://smarthealth.network/fhir/Questionnaire/pa-lumbar-mri|1.0.0",
        "status": "completed",
        "subject": {"reference": patient_ref},
        "authored": "2026-09-05T10:00:00Z",
        "item": [
            {
                "linkId": "clinical-history",
                "item": [
                    {
                        "linkId": "conservative-therapy-weeks",
                        "answer": [
                            {
                                "extension": [_auto_origin_extension()],
                                "valueInteger": reality.therapy_weeks,
                            }
                        ],
                    },
                    {
                        "linkId": "neuro-deficit",
                        "answer": [
                            {
                                "extension": [_auto_origin_extension()],
                                "valueBoolean": reality.neuro_deficit,
                            }
                        ],
                    },
                    {
                        "linkId": "prior-treatment",
                        "item": [
                            {
                                "linkId": "prior-imaging",
                                "answer": [
                                    {
                                        "extension": [_auto_origin_extension()],
                                        "valueBoolean": reality.prior_imaging,
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ],
    }


def build_shn_transform_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap a FHIR payload in SHN's /demo/transform request shape."""
    return {
        "contract": SHN_CONTRACT,
        "from": SHN_FROM,
        "to": SHN_TO,
        "payload": copy.deepcopy(payload),
    }


def expected_invariants(reality: SHNMVP0Reality) -> dict[str, Any]:
    """State meaning that should survive the 2.1 -> 2.2 transformation."""
    return {
        "case_id": reality.case_id,
        "expected_transform": f"{SHN_CONTRACT} {SHN_FROM}->{SHN_TO}",
        "relationships": [
            {
                "name": "QuestionnaireResponse subject",
                "expected_reference": f"Patient/{reality.patient.patient_id}",
                "meaning": "QuestionnaireResponse remains about the same patient",
            },
            {
                "name": "Coverage context",
                "expected_reference": f"Coverage/{reality.coverage_id}",
                "meaning": "Coverage relationship survives even if its DTR extension location changes",
            },
            {
                "name": "Order context",
                "expected_reference": f"ServiceRequest/{reality.service_request_id}",
                "meaning": "QuestionnaireResponse remains linked to the same order",
            },
        ],
        "representation_change": {
            "input": DTR_QR_CONTEXT,
            "output": DTR_QR_COVERAGE,
            "applies_to": f"Coverage/{reality.coverage_id}",
        },
    }


def build_case(seed: int = 43) -> dict[str, Any]:
    reality = build_reality(seed)
    dtr_input = build_dtr_21_questionnaire_response(reality)
    return {
        "reality": reality_manifest(reality),
        "supporting_fhir": supporting_fhir(reality),
        "dtr_input": dtr_input,
        "shn_request": build_shn_transform_request(dtr_input),
        "expected_invariants": expected_invariants(reality),
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def case_zip_bytes(case: dict[str, Any]) -> bytes:
    """Package one case into stable artifacts that can be handed to PIQITT."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("reality.json", _json_bytes(case["reality"]))
        archive.writestr("dtr_2_1.fhir.json", _json_bytes(case["dtr_input"]))
        archive.writestr("shn_transform_request.json", _json_bytes(case["shn_request"]))
        archive.writestr("expected_invariants.json", _json_bytes(case["expected_invariants"]))
        for name, resource in case["supporting_fhir"].items():
            archive.writestr(f"supporting/{name}.fhir.json", _json_bytes(resource))
    return out.getvalue()


def write_case(case: dict[str, Any], output_dir: str | Path) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    (path / "reality.json").write_bytes(_json_bytes(case["reality"]))
    (path / "dtr_2_1.fhir.json").write_bytes(_json_bytes(case["dtr_input"]))
    (path / "shn_transform_request.json").write_bytes(_json_bytes(case["shn_request"]))
    (path / "expected_invariants.json").write_bytes(_json_bytes(case["expected_invariants"]))

    supporting = path / "supporting"
    supporting.mkdir(exist_ok=True)
    for name, resource in case["supporting_fhir"].items():
        (supporting / f"{name}.fhir.json").write_bytes(_json_bytes(resource))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the MediLacra SHN MVP-0 DTR 2.1 case")
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--out", default="connectathon/results/shn_mvp0")
    args = parser.parse_args()

    case = build_case(args.seed)
    out = write_case(case, Path(args.out) / case["reality"]["case_id"])
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
