"""CLI-driven, semantics-first Claims/ePA MVP tests.

Self-tests are intentionally distinct from licensed X12 TR3/HL7 PAS certification.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from claims_epa.generation import demo_case, demo_sources, generate, write_artifacts
from claims_epa.models import (
    AuthorizationDecision, ClaimDecision, build_case, cents,
)
from claims_epa.x12_projection import validate_envelope
from claims_epa.fhir_projection import validate_bundle
from payer.models import EnrollmentStatus


RUN_AT = datetime(2026, 10, 7, 23, 0, 0)


def _find(bundle, resource_type):
    matches = [
        entry["resource"] for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == resource_type
    ]
    assert len(matches) == 1, (resource_type, len(matches))
    return matches[0]


def _resolve(bundle, reference):
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if f"{resource['resourceType']}/{resource['id']}" == reference:
            return resource
    raise AssertionError(reference)


def test_semantic_case_uses_existing_clinical_and_payer_primitives():
    patient, coverage, encounter, txn, obs, member, enrollment = demo_sources(43)
    case = demo_case(run_at=RUN_AT)
    assert case.claim.patient_id == patient.patient_id
    assert case.claim.member_id == coverage.member_id
    assert case.claim.service_date == encounter.admit_datetime[:10]
    assert case.claim.line.charge_cents == cents(txn.transaction_amount)
    assert case.claim.line.procedure_code == obs.cpt_code
    assert case.claim.line.diagnosis_code == obs.icd_code
    assert case.authorization.service_date > case.claim.service_date
    assert case.authorization.service_date > RUN_AT.date().isoformat()
    assert case.claim.service_date < RUN_AT.date().isoformat()
    assert member.member_record_id == enrollment.member_record_id
    assert case.claim_decision.paid_cents == 34000
    assert case.claim_decision.adjusted_cents == 8500
    assert case.authorization_decision.authorization_number is not None


def test_sibling_x12_and_fhir_share_request_response_facts():
    case = demo_case(run_at=RUN_AT)
    output = generate(case, RUN_AT)
    for msg, kind in (
        (output.x837p, "837"), (output.x835, "835"),
        (output.x278_request, "278"), (output.x278_response, "278"),
    ):
        validate_envelope(msg, kind)
    assert "GS*HC*" in output.x837p
    assert "005010X222A1" in output.x837p
    assert "GS*HP*" in output.x835
    assert "005010X221A1" in output.x835
    assert "GS*HI*" in output.x278_request
    assert "005010X217" in output.x278_response
    assert "CLM*CLM-20261007230000-00001*425.00" in output.x837p
    assert "CLP*CLM-20261007230000-00001*1*425.00*340.00" in output.x835
    assert "HCR*A1*CERT-20261007230000-00001" in output.x278_response
    assert "SV1*HC:72148*425.00*UN*1" in output.x837p

    for bundle in (
        output.claim_request, output.claim_response,
        output.authorization_request, output.authorization_response,
    ):
        validate_bundle(bundle)
    claim = _find(output.claim_request, "Claim")
    claim_response = _find(output.claim_response, "ClaimResponse")
    pa = _find(output.authorization_request, "Claim")
    pa_response = _find(output.authorization_response, "ClaimResponse")
    assert claim["use"] == claim_response["use"] == "claim"
    assert pa["use"] == pa_response["use"] == "preauthorization"
    assert claim["identifier"][0]["value"] == case.claim.exchange_id
    assert pa["identifier"][0]["value"] == case.authorization.exchange_id
    assert claim["item"][0]["productOrService"]["coding"][0]["code"] == case.claim.line.procedure_code
    assert pa["item"][0]["productOrService"]["coding"][0]["code"] == case.authorization.procedure_code
    assert claim["total"]["value"] == 425.00
    assert claim_response["payment"]["amount"]["value"] == 340.00
    assert pa_response["preAuthRef"] == case.authorization_decision.authorization_number
    assert _resolve(output.claim_request, claim["patient"]["reference"])["name"][0]["family"] == "KELLEY"
    assert _resolve(output.claim_response, claim_response["patient"]["reference"])["identifier"][0]["value"] == case.claim.member_id


@pytest.mark.parametrize("status,hcr,outcome", [
    ("approved", "HCR*A1*", "complete"),
    ("pended", "HCR*A4", "queued"),
    ("denied", "HCR*A3", "complete"),
])
def test_authorization_states(status, hcr, outcome):
    case = demo_case(run_at=RUN_AT, authorization_status=status)
    output = generate(case, RUN_AT)
    assert hcr in output.x278_response
    response = _find(output.authorization_response, "ClaimResponse")
    assert response["outcome"] == outcome
    assert response["disposition"] == status
    assert ("preAuthRef" in response) == (status == "approved")
    assert case.authorization_decision.authorization_number is None if status != "approved" else True


def test_denied_claim_reconciles_and_has_no_payment():
    case = demo_case(run_at=RUN_AT, claim_status="denied")
    output = generate(case, RUN_AT)
    assert case.claim_decision.paid_cents == 0
    assert case.claim_decision.adjusted_cents == case.claim.charge_cents
    assert "CLP*CLM-20261007230000-00001*4*425.00*0.00" in output.x835
    response = _find(output.claim_response, "ClaimResponse")
    assert response["payment"]["amount"]["value"] == 0.0


def test_inactive_payer_enrollment_overrides_requested_approval():
    patient, coverage, encounter, txn, obs, member, enrollment = demo_sources()
    enrollment = replace(enrollment, status=EnrollmentStatus.INACTIVE)
    case = build_case(
        patient=patient, coverage=coverage, encounter=encounter,
        transaction=txn, observation=obs, run_at=RUN_AT,
        payer_member=member, payer_enrollment=enrollment,
    )
    assert case.claim_decision.status == "denied"
    assert case.authorization_decision.status == "denied"
    assert "HCR*A3" in generate(case, RUN_AT).x278_response


def test_invalid_semantic_data_fails_before_projection():
    with pytest.raises(ValueError, match="reconcile"):
        ClaimDecision("exchange", "claim", "paid", 10000, 5000, 6000, 0, 0)
    with pytest.raises(ValueError, match="authorization"):
        AuthorizationDecision("ex", "req", "approved", None, None)
    with pytest.raises(ValueError, match="cannot have certification"):
        AuthorizationDecision("ex", "req", "denied", "AUTH001", None)
    with pytest.raises(ValueError):
        cents(-1)
    with pytest.raises(ValueError):
        cents("NaN")


def test_rejects_cross_institution_and_clinical_id_mismatch():
    p, cov, enc, txn, obs, member, enrollment = demo_sources()
    with pytest.raises(ValueError, match="clinical patient/encounter"):
        build_case(
            patient=p, coverage=cov, encounter=replace(enc, patient_id="OTHER"),
            transaction=txn, observation=obs, run_at=RUN_AT,
            payer_member=member, payer_enrollment=enrollment,
        )
    with pytest.raises(ValueError, match="observation/encounter"):
        build_case(
            patient=p, coverage=cov, encounter=enc, transaction=txn,
            observation=replace(obs, encounter_id="OTHER"), run_at=RUN_AT,
            payer_member=member, payer_enrollment=enrollment,
        )


def test_determinism_controls_and_no_aliasing():
    first = generate(demo_case(seed=43, run_at=RUN_AT), RUN_AT)
    second = generate(demo_case(seed=43, run_at=RUN_AT), RUN_AT)
    third = generate(demo_case(seed=44, run_at=RUN_AT, ordinal=2), RUN_AT)
    assert first == second
    assert first.semantic.claim.exchange_id != third.semantic.claim.exchange_id
    assert first.claim_request != third.claim_request
    from x12.parser import tokenize_x12
    controls = [
        next(seg for seg in tokenize_x12(msg) if seg.tag == "ST").element(2)
        for msg in (first.x837p, first.x835, first.x278_request, first.x278_response)
    ]
    assert len(set(controls)) == 4


def test_100_synthetic_cases_have_unique_controls_and_exchanges():
    from x12.parser import tokenize_x12
    controls = set()
    exchanges = set()
    for i in range(100):
        case = demo_case(seed=43 + i, run_at=RUN_AT, ordinal=i+1)
        output = generate(case, RUN_AT)
        for msg in (output.x837p, output.x835, output.x278_request, output.x278_response):
            st = next(seg for seg in tokenize_x12(msg) if seg.tag == "ST")
            assert st.element(2) not in controls
            controls.add(st.element(2))
        exchanges.add(case.claim.exchange_id)
        exchanges.add(case.authorization.exchange_id)
    assert len(controls) == 400
    assert len(exchanges) == 200


def test_files_and_cli(tmp_path):
    out = generate(demo_case(run_at=RUN_AT), RUN_AT)
    paths = write_artifacts(out, tmp_path / "single")
    assert len(paths) == 10
    for path in paths.values():
        assert Path(path).exists()
    manifest = json.loads(Path(paths["MANIFEST"]).read_text())
    assert "NOT X12" in manifest["label"]
    assert manifest["claim_exchange_id"] == out.semantic.claim.exchange_id

    cmd = [
        sys.executable, "-m", "claims_epa", "--at", RUN_AT.isoformat(),
        "--seed", "43", "--count", "2", "--out", str(tmp_path / "cli"),
        "--authorization-status", "pended",
    ]
    run = subprocess.run(cmd, check=True, text=True, capture_output=True)
    summary = json.loads(run.stdout)
    assert summary["count"] == 2
    for case in summary["cases"]:
        path = Path(case["path"])
        assert path.exists()
        assert (path / "278_response.x12").exists()
        assert (path / "epa_response.fhir.json").exists()
    assert {case["authorization_status"] for case in summary["cases"]} == {"pended"}


def test_payer_authoring_preserves_identity_divergence():
    p, coverage, encounter, txn, obs, member, enrollment = demo_sources()
    # Payer-local demographic divergence is not silently overwritten by the
    # request's clinical Patient name.
    payer_member = replace(member, last_name="PAYERONLY")
    case = build_case(
        patient=p, coverage=coverage, encounter=encounter,
        transaction=txn, observation=obs, run_at=RUN_AT,
        payer_member=payer_member, payer_enrollment=enrollment,
    )
    result = generate(case, RUN_AT)
    assert "NM1*IL*1*KELLEY*DEVIN" in result.x837p
    assert "NM1*QC*1*PAYERONLY*DEVIN" in result.x835
    assert "NM1*IL*1*KELLEY*DEVIN" in result.x278_request
    assert "NM1*IL*1*PAYERONLY*DEVIN" in result.x278_response
    payer_patient = _resolve(
        result.claim_response,
        _find(result.claim_response, "ClaimResponse")["patient"]["reference"],
    )
    assert payer_patient["name"][0]["family"] == "PAYERONLY"


def test_tampered_payer_routing_identity_fails_closed():
    case = demo_case(run_at=RUN_AT)
    modified = replace(
        case, payer_subject=replace(case.payer_subject, member_id="WRONG"),
    )
    with pytest.raises(ValueError, match="payer"):
        generate(modified, RUN_AT)


def test_claim_paid_but_future_authorization_denied_after_coverage_expires():
    p, cov, enc, txn, obs, member, enrollment = demo_sources()
    # Existing service occurred before termination; proposed repeat service
    # occurs after termination. These are two different institutional decisions.
    enrollment = replace(enrollment, effective_end="2026-10-15")
    case = build_case(
        patient=p, coverage=cov, encounter=enc,
        transaction=txn, observation=obs, run_at=RUN_AT,
        payer_member=member, payer_enrollment=enrollment,
    )
    assert case.claim.service_date == "2026-10-03"
    assert case.authorization.service_date == "2026-10-21"
    assert case.claim_decision.status == "paid"
    assert case.authorization_decision.status == "denied"
    artifacts = generate(case, RUN_AT)
    assert "HCR*A3" in artifacts.x278_response
    assert _find(artifacts.authorization_response, "ClaimResponse")["disposition"] == "denied"
