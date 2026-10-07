from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from eligibility.generation import (
    EligibilityRunContext,
    build_eligibility_inquiry_from_clinical,
)
from fhir.eligibility_generation import generate_fhir_eligibility_artifacts
from hl7_demo.models import CoverageProfile, Patient
from payer.materialize import materialize_payer_from_clinical
from payer.system import PayerSystem
from x12.eligibility_270 import parse_270_to_inquiry
from x12.eligibility_271 import parse_271
from x12.generation import (
    X12RunContext,
    generate_x12_eligibility_artifacts,
)


RUN_AT = datetime(2026, 10, 7, 18, 29, 0)


def _patient():
    return Patient(
        patient_id="RAD1054994",
        patient_name="KELLEY, DEVIN",
        date_of_birth="1949-01-16",
        sex="M",
        gender="Man",
        race="Other",
        ethnicity="Not Hispanic or Latino",
        marital_status="Single",
        language="English",
        employer="CVS Health Corporation",
        ssn="000-00-0000",
        address="100 Synthetic Way",
        phone="555-0100",
        email="devin.kelley@example.invalid",
        zip_code="01852",
        city="Lowell",
        state="MA",
    )


def _coverage():
    return CoverageProfile(
        coverage_profile_id="COV-EQUIV-001",
        patient_id="RAD1054994",
        employer_id="CVS",
        employer_name="CVS Health Corporation",
        payer_id="KAISER",
        payer_name="Kaiser Permanente",
        plan_id="STANDARD_PPO",
        plan_name="Standard PPO",
        plan_type="PPO",
        worker_profile="DEFAULT_FULL_TIME_EMPLOYEE",
        subscriber_relationship="SELF",
        member_id="MEM-01374522",
        group_number="GRP-CVS-398915",
        policy_number="POL-27411793",
        effective_start="2026-01-01",
        effective_end="2026-12-31",
        employer_provenance="researched",
        payer_provenance="researched",
        employer_payer_provenance="synthetic",
        plan_provenance="synthetic",
        assignment_seed="42",
    )


def _find(bundle, resource_type, predicate=None):
    resources = [
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == resource_type
    ]
    if predicate is not None:
        resources = [
            resource
            for resource in resources
            if predicate(resource)
        ]
    assert len(resources) == 1
    return resources[0]


def _resolve(bundle, reference):
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if f"{resource['resourceType']}/{resource['id']}" == reference:
            return resource
    raise AssertionError(reference)


def _class_value(coverage, code):
    for item in coverage.get("class", []):
        if any(
            coding.get("code") == code
            for coding in item["type"].get("coding", [])
        ):
            return item["value"]
    return None


def test_x12_and_fhir_are_sibling_projections_of_same_semantic_exchange():
    patient = _patient()
    coverage = _coverage()
    encounter = SimpleNamespace(
        encounter_id="ENC-EQUIV-001",
        admit_datetime="2026-10-03 13:45:00",
    )

    member, enrollment, plan = materialize_payer_from_clinical(
        patient,
        coverage,
    )
    payer = PayerSystem(
        coverage.payer_id,
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )

    semantic_context = EligibilityRunContext(RUN_AT)
    identity = semantic_context.next_exchange()
    inquiry = build_eligibility_inquiry_from_clinical(
        patient,
        coverage,
        encounter,
    )
    response = payer.evaluate_eligibility(inquiry)

    x12 = generate_x12_eligibility_artifacts(
        inquiry=inquiry,
        response=response,
        exchange_identity=identity,
        encounter_id=encounter.encounter_id,
        coverage_profile=coverage,
        payer_member=member,
        payer_plan=plan,
        run_context=X12RunContext(RUN_AT),
    )
    fhir = generate_fhir_eligibility_artifacts(
        patient=patient,
        coverage_profile=coverage,
        inquiry=inquiry,
        response=response,
        exchange_identity=identity,
        run_at=RUN_AT,
        payer_member=member,
        payer_enrollment=enrollment,
        payer_plan=plan,
        encounter_id=encounter.encounter_id,
    )

    parsed_270 = parse_270_to_inquiry(x12.x270)
    parsed_271 = parse_271(x12.x271)

    request = _find(
        fhir.request_bundle,
        "CoverageEligibilityRequest",
    )
    request_coverage = _resolve(
        fhir.request_bundle,
        request["insurance"][0]["coverage"]["reference"],
    )
    request_payer = _resolve(
        fhir.request_bundle,
        request["insurer"]["reference"],
    )

    assert parsed_270.trace_id == identity.trace_id
    assert request["identifier"][0]["value"] == identity.exchange_id

    assert parsed_270.inquiry.member_id == request_coverage["subscriberId"]
    assert parsed_270.inquiry.service_date == request["servicedDate"]
    assert parsed_270.inquiry.payer_id == request_payer["identifier"][0]["value"]
    assert (
        coverage.group_number
        == _class_value(request_coverage, "group")
    )

    response_resource = _find(
        fhir.response_bundle,
        "CoverageEligibilityResponse",
    )
    payer_patient = _resolve(
        fhir.response_bundle,
        response_resource["patient"]["reference"],
    )
    payer_coverage = _resolve(
        fhir.response_bundle,
        response_resource["insurance"][0]["coverage"]["reference"],
    )

    assert parsed_271.trace_id == identity.trace_id
    assert response_resource["identifier"][0]["value"] == identity.exchange_id
    assert response_resource["insurance"][0]["inforce"] is True

    assert parsed_271.subscriber_member_id == payer_coverage["subscriberId"]
    assert parsed_271.subscriber_first_name == payer_patient["name"][0]["given"][0]
    assert parsed_271.subscriber_last_name == payer_patient["name"][0]["family"]
    assert parsed_271.coverage_start == payer_coverage["period"]["start"]
    assert parsed_271.coverage_end == payer_coverage["period"]["end"]
    assert parsed_271.group_number == _class_value(payer_coverage, "group")
    assert parsed_271.plan_name == plan.plan_name


def test_semantic_inquiry_exists_without_x12_projection():
    patient = _patient()
    coverage = _coverage()
    encounter = SimpleNamespace(
        encounter_id="ENC-NOX12-001",
        admit_datetime="2026-10-03 13:45:00",
    )

    inquiry = build_eligibility_inquiry_from_clinical(
        patient,
        coverage,
        encounter,
    )

    assert inquiry.member_id == coverage.member_id
    assert inquiry.payer_id == coverage.payer_id
    assert inquiry.service_date == "2026-10-03"
    assert inquiry.first_name == "DEVIN"
    assert inquiry.last_name == "KELLEY"
