"""Dual X12/FHIR Claims/ePA scenario and file generation.

This is a synthetic interoperability test fixture, not a clearinghouse client.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from hl7_demo.models import Patient, Encounter, Transaction, Observation, CoverageProfile
from payer.materialize import materialize_payer_from_clinical

from .models import SemanticCase, build_case
from .x12_projection import build_837p, build_835, build_278, validate_envelope
from .fhir_projection import build_claim_fhir, build_authorization_fhir, validate_bundle


@dataclass(frozen=True)
class DualArtifacts:
    semantic: SemanticCase
    x837p: str
    x835: str
    x278_request: str
    x278_response: str
    claim_request: dict[str, Any]
    claim_response: dict[str, Any]
    authorization_request: dict[str, Any]
    authorization_response: dict[str, Any]


def generate(case: SemanticCase, run_at: datetime) -> DualArtifacts:
    """Project one already-materialized semantic case. No decisions made here."""
    claim_request, claim_response = build_claim_fhir(
        case.claim, case.claim_decision, run_at, case.payer_subject,
    )
    auth_request, auth_response = build_authorization_fhir(
        case.authorization, case.authorization_decision, run_at,
        case.payer_subject,
    )
    output = DualArtifacts(
        semantic=case,
        x837p=build_837p(case.claim, run_at),
        x835=build_835(case.claim, case.claim_decision, run_at,
                       case.payer_subject),
        x278_request=build_278(case.authorization, run_at),
        x278_response=build_278(case.authorization, run_at,
                                 case.authorization_decision, case.payer_subject),
        claim_request=claim_request, claim_response=claim_response,
        authorization_request=auth_request, authorization_response=auth_response,
    )
    for message, type_id in (
        (output.x837p, "837"), (output.x835, "835"),
        (output.x278_request, "278"), (output.x278_response, "278"),
    ):
        validate_envelope(message, type_id)
    for bundle in (
        output.claim_request, output.claim_response,
        output.authorization_request, output.authorization_response,
    ):
        validate_bundle(bundle)
    return output


def demo_sources(seed: int = 43):
    """Explicit test-only case using MediLacra's EXISTING clinical dataclasses.

    Codes/amounts here are deliberately declared fixture data. None is inferred
    by an X12/FHIR serializer.
    """
    if seed < 0 or seed > 999999:
        raise ValueError("demo seed outside 0..999999")
    pid = f"TEST{seed:06d}"
    eid = f"ENC{seed:06d}"
    member = f"MEM{seed:06d}"
    patient = Patient(
        patient_id=pid, patient_name="KELLEY, DEVIN",
        date_of_birth="1980-02-17", sex="M", gender="Man",
        race="Other", ethnicity="Not Hispanic or Latino",
        marital_status="Single", language="English",
        employer="SYNTHETIC EMPLOYER", ssn="000-00-0000",
        address="100 Synthetic Way", phone="555-0100",
        email="synthetic@example.invalid", zip_code="01852",
        city="Lowell", state="MA",
    )
    coverage = CoverageProfile(
        coverage_profile_id=f"COV{seed:06d}", patient_id=pid,
        employer_id="SYNTHETIC", employer_name="SYNTHETIC EMPLOYER",
        payer_id="TESTPAYER", payer_name="TEST PAYER",
        plan_id="TESTPPO", plan_name="TEST PPO", plan_type="PPO",
        worker_profile="DEFAULT_FULL_TIME_EMPLOYEE",
        subscriber_relationship="SELF", member_id=member,
        group_number="TESTGROUP", policy_number=f"POL{seed:06d}",
        effective_start="2026-01-01", effective_end="2026-12-31",
        employer_provenance="synthetic", payer_provenance="synthetic",
        employer_payer_provenance="synthetic", plan_provenance="synthetic",
        assignment_seed=str(seed),
    )
    encounter = Encounter(
        encounter_id=eid, patient_id=pid, visit_number=f"V{seed:06d}",
        account_number=f"A{seed:06d}", patient_class="OUTPATIENT",
        assigned_patient_location="RAD1",
        admit_datetime="2026-10-03 09:00:00",
        discharge_datetime="2026-10-03 11:00:00",
        hospital_service="RAD", admit_source="Physician Referral",
        discharge_disposition="Home",
        ordering_provider_id="PR1", ordering_provider_name="SMITH, ALEX",
        attending_provider_id="PR1", attending_provider_name="SMITH, ALEX",
        attending_provider_taxonomy="2085R0202X",
        attending_provider_specialty="Diagnostic Radiology",
        mid_level_provider_id="ML1", mid_level_provider_name="SMITH, ALEX",
        referring_provider_id="PR1", referring_provider_name="SMITH, ALEX",
        placer_order_number=f"O{seed:06d}", filler_order_number=f"F{seed:06d}",
        place_of_service_code="11", place_of_service_description="Office",
    )
    txn = Transaction(
        transaction_id=f"TX{seed:06d}", encounter_id=eid,
        transaction_date="2026-10-03 10:00:00", transaction_amount=425.00,
        unit_cost=425.00, transaction_quantity=1, fee_schedule="TEST",
        insurance_plan_id=coverage.plan_id, insurance_plan_name=coverage.plan_name,
        member_id=member, group_number=coverage.group_number, plan_type="PPO",
        subscriber_relationship="SELF", authorization_number="",
        billing_provider_id="PR1", billing_provider_name="SMITH, ALEX",
        billing_provider_npi="1234567893", guarantor_name=patient.patient_name,
        guarantor_relationship="SELF",
    )
    obs = Observation(
        encounter_id=eid, observation_id=f"OBS{seed:06d}",
        cpt_code="72148", cpt_description="MRI lumbar spine without contrast",
        procedure_description="MRI lumbar spine", icd_code="M54.50",
        icd_description="Low back pain, unspecified",
        diagnosis_type="Primary", diagnosis_rank=1,
        placer_order_number=encounter.placer_order_number,
        filler_order_number=encounter.filler_order_number,
        observation_text="Synthetic test only", observation_sub_id="1",
        result_status="F", completed_time="2026-10-03 10:15:00",
        performing_provider_id="PR1", performing_provider_name="SMITH, ALEX",
    )
    payer_member, payer_enrollment, _plan = materialize_payer_from_clinical(patient, coverage)
    return patient, coverage, encounter, txn, obs, payer_member, payer_enrollment


def demo_case(
    seed: int = 43, *, run_at: datetime,
    authorization_status: str = "approved", claim_status: str = "paid",
    ordinal: int = 1,
) -> SemanticCase:
    p, cov, enc, txn, obs, payer_member, payer_enrollment = demo_sources(seed)
    return build_case(
        patient=p, coverage=cov, encounter=enc, transaction=txn,
        observation=obs, payer_member=payer_member,
        payer_enrollment=payer_enrollment, run_at=run_at, ordinal=ordinal,
        authorization_status=authorization_status, claim_status=claim_status,
    )


def write_artifacts(output: DualArtifacts, out_dir: str | Path) -> dict[str, str]:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    values = {
        "X12_837P": ("837P.x12", output.x837p),
        "X12_835": ("835.x12", output.x835),
        "X12_278_REQUEST": ("278_request.x12", output.x278_request),
        "X12_278_RESPONSE": ("278_response.x12", output.x278_response),
        "FHIR_CLAIM_REQUEST": ("claim_request.fhir.json", output.claim_request),
        "FHIR_CLAIM_RESPONSE": ("claim_response.fhir.json", output.claim_response),
        "FHIR_EPA_REQUEST": ("epa_request.fhir.json", output.authorization_request),
        "FHIR_EPA_RESPONSE": ("epa_response.fhir.json", output.authorization_response),
        "SEMANTIC_CASE": ("semantic_reality.json", asdict(output.semantic)),
    }
    paths = {}
    for key, (filename, payload) in values.items():
        full = path / filename
        if isinstance(payload, str):
            full.write_text(payload, encoding="utf-8")
        else:
            full.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths[key] = str(full)
    (path / "manifest.json").write_text(
        json.dumps({
            "label": "SYNTHETIC TEST ONLY; NOT X12 TR3 / PAS IG CERTIFIED",
            "claim_exchange_id": output.semantic.claim.exchange_id,
            "epa_exchange_id": output.semantic.authorization.exchange_id,
            "claim_status": output.semantic.claim_decision.status,
            "authorization_status": output.semantic.authorization_decision.status,
            "files": {key: Path(value).name for key, value in paths.items()},
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    paths["MANIFEST"] = str(path / "manifest.json")
    return paths
