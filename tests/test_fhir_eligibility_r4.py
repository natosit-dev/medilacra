from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from eligibility.generation import (
    EligibilityRunContext,
    build_eligibility_inquiry_from_clinical,
)
from fhir.eligibility_generation import (
    generate_fhir_eligibility_artifacts,
    write_fhir_eligibility_artifacts,
)
from hl7_demo.models import CoverageProfile, Patient
from payer.materialize import materialize_payer_from_clinical
from payer.system import PayerSystem


RUN_AT = datetime(2026, 10, 7, 18, 29, 0)


def _patient(name="KELLEY, DEVIN"):
    return Patient(
        patient_id="RAD1054994",
        patient_name=name,
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


def _coverage(patient_id="RAD1054994"):
    return CoverageProfile(
        coverage_profile_id="COV-FHIR-001",
        patient_id=patient_id,
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


def _encounter():
    return SimpleNamespace(
        encounter_id="ENC-FHIR-001",
        admit_datetime="2026-10-03 13:45:00",
    )


def _generate(patient=None):
    patient = patient or _patient()
    coverage = _coverage(patient.patient_id)
    encounter = _encounter()

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

    artifacts = generate_fhir_eligibility_artifacts(
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

    return (
        artifacts,
        coverage,
        member,
        enrollment,
        plan,
        identity,
    )


def _resources(bundle):
    return [entry["resource"] for entry in bundle["entry"]]


def _by_type(bundle, resource_type):
    return [
        resource
        for resource in _resources(bundle)
        if resource["resourceType"] == resource_type
    ]


def _resolve(bundle, reference):
    matches = [
        resource
        for resource in _resources(bundle)
        if f"{resource['resourceType']}/{resource['id']}" == reference
    ]
    assert len(matches) == 1, reference
    return matches[0]


def _class_value(coverage, code):
    for item in coverage.get("class", []):
        codings = item["type"].get("coding", [])
        if any(coding.get("code") == code for coding in codings):
            return item.get("value")
    return None


def test_request_bundle_is_self_contained_r4_collection():
    artifacts, coverage, _member, _enrollment, _plan, identity = _generate()
    bundle = artifacts.request_bundle

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"

    requests = _by_type(bundle, "CoverageEligibilityRequest")
    patients = _by_type(bundle, "Patient")
    coverages = _by_type(bundle, "Coverage")
    organizations = _by_type(bundle, "Organization")

    assert len(requests) == 1
    assert len(patients) == 1
    assert len(coverages) == 1
    assert len(organizations) == 3

    request = requests[0]
    clinical_coverage = coverages[0]

    assert request["status"] == "active"
    assert request["purpose"] == ["validation", "benefits"]
    assert request["servicedDate"] == "2026-10-03"
    assert request["identifier"][0]["value"] == identity.exchange_id

    _resolve(bundle, request["patient"]["reference"])
    _resolve(bundle, request["provider"]["reference"])
    _resolve(bundle, request["insurer"]["reference"])
    _resolve(
        bundle,
        request["insurance"][0]["coverage"]["reference"],
    )

    assert clinical_coverage["subscriberId"] == coverage.member_id
    assert clinical_coverage["period"] == {
        "start": "2026-01-01",
        "end": "2026-12-31",
    }
    assert _class_value(
        clinical_coverage,
        "group",
    ) == coverage.group_number
    assert _class_value(
        clinical_coverage,
        "plan",
    ) == coverage.plan_id
    assert "policyHolder" in clinical_coverage


def test_response_bundle_preserves_clinical_request_and_payer_reality():
    artifacts, coverage, member, enrollment, plan, identity = _generate()
    bundle = artifacts.response_bundle

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"

    responses = _by_type(bundle, "CoverageEligibilityResponse")
    requests = _by_type(bundle, "CoverageEligibilityRequest")
    patients = _by_type(bundle, "Patient")
    coverages = _by_type(bundle, "Coverage")

    assert len(responses) == 1
    assert len(requests) == 1
    assert len(patients) == 2
    assert len(coverages) == 2

    response = responses[0]
    request = requests[0]

    assert response["identifier"][0]["value"] == identity.exchange_id
    assert response["status"] == "active"
    assert response["purpose"] == ["validation", "benefits"]
    assert response["outcome"] == "complete"
    assert response["servicedDate"] == "2026-10-03"

    resolved_request = _resolve(
        bundle,
        response["request"]["reference"],
    )
    assert resolved_request["id"] == request["id"]

    payer_patient = _resolve(
        bundle,
        response["patient"]["reference"],
    )
    assert payer_patient["name"][0]["family"] == member.last_name
    assert payer_patient["name"][0]["given"] == [member.first_name]
    assert payer_patient["identifier"][0]["value"] == member.member_id

    payer_coverage = _resolve(
        bundle,
        response["insurance"][0]["coverage"]["reference"],
    )
    assert payer_coverage["subscriberId"] == member.member_id
    assert payer_coverage["period"] == {
        "start": enrollment.effective_start,
        "end": enrollment.effective_end,
    }
    assert payer_coverage["type"]["text"] == plan.plan_type
    assert _class_value(
        payer_coverage,
        "group",
    ) == enrollment.group_number
    assert _class_value(
        payer_coverage,
        "plan",
    ) == plan.plan_id
    assert "policyHolder" not in payer_coverage

    assert response["insurance"][0]["inforce"] is True
    assert response["insurance"][0]["benefitPeriod"] == {
        "start": enrollment.effective_start,
        "end": enrollment.effective_end,
    }

    request_patient = _resolve(
        bundle,
        request["patient"]["reference"],
    )
    assert request_patient["id"] != payer_patient["id"]

    request_coverage = _resolve(
        bundle,
        request["insurance"][0]["coverage"]["reference"],
    )
    assert request_coverage["id"] != payer_coverage["id"]
    assert request_coverage["subscriberId"] == coverage.member_id
    assert "policyHolder" in request_coverage


def test_payer_fhir_projection_does_not_mutate_with_clinical_patient_after_materialization():
    patient = _patient()
    artifacts, _coverage, member, _enrollment, _plan, _identity = _generate(
        patient
    )

    payer_patient_before = _resolve(
        artifacts.response_bundle,
        _by_type(
            artifacts.response_bundle,
            "CoverageEligibilityResponse",
        )[0]["patient"]["reference"],
    )

    patient.patient_name = "CHANGED, CLINICAL"

    assert payer_patient_before["name"][0]["family"] == member.last_name
    assert payer_patient_before["name"][0]["family"] == "KELLEY"


def test_fhir_writer_uses_timestamped_json_and_ndjson(tmp_path):
    artifacts, *_rest = _generate()

    per_paths = write_fhir_eligibility_artifacts(
        artifacts,
        out_dir=str(tmp_path / "per"),
        run_ts="20261007_182900",
        per_encounter=True,
        safe_encounter="ENC_FHIR_001",
    )

    assert per_paths["FHIR_ELIGIBILITY_REQUEST"].endswith(
        "FHIR_R4_4.0.1_CoverageEligibilityRequest_"
        "ENC_FHIR_001_20261007_182900.json"
    )
    assert per_paths["FHIR_ELIGIBILITY_RESPONSE"].endswith(
        "FHIR_R4_4.0.1_CoverageEligibilityResponse_"
        "ENC_FHIR_001_20261007_182900.json"
    )

    request_json = json.loads(
        Path(
            per_paths["FHIR_ELIGIBILITY_REQUEST"]
        ).read_text(encoding="utf-8")
    )
    assert request_json["resourceType"] == "Bundle"

    bulk_dir = tmp_path / "bulk"
    for _ in range(3):
        write_fhir_eligibility_artifacts(
            artifacts,
            out_dir=str(bulk_dir),
            run_ts="20261007_182900",
            per_encounter=False,
            safe_encounter="ignored",
        )

    request_bulk = (
        bulk_dir
        / (
            "FHIR_R4_4.0.1_CoverageEligibilityRequest_"
            "20261007_182900.ndjson"
        )
    )
    response_bulk = (
        bulk_dir
        / (
            "FHIR_R4_4.0.1_CoverageEligibilityResponse_"
            "20261007_182900.ndjson"
        )
    )

    assert len(
        request_bulk.read_text(encoding="utf-8").splitlines()
    ) == 3
    assert len(
        response_bulk.read_text(encoding="utf-8").splitlines()
    ) == 3


def test_fhir_eligibility_modules_do_not_depend_on_x12():
    for path in (
        Path("fhir/eligibility_r4.py"),
        Path("fhir/eligibility_generation.py"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "from x12" not in source
        assert "import x12" not in source
        assert "parse_270_to_inquiry" not in source
