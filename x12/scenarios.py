from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, replace
from datetime import date, datetime

from hl7_demo.models import CoverageProfile, Patient
from identity.models import IdentityQuery, MatchResult
from payer.materialize import materialize_payer_state
from payer.models import (
    BenefitPlan,
    EligibilityResponse,
    EnrollmentRecord,
    MemberRecord,
)
from payer.system import PayerSystem
from reality.models import CoverageTruth, PersonTruth

from .eligibility_270 import Parsed270, build_270_from_clinical, parse_270_to_inquiry
from .eligibility_271 import Parsed271, build_271_transaction, parse_271
from .envelope import EnvelopeConfig, wrap_interchange
from .models import EligibilityExchange, X12Party


SCENARIO_LABELS = {
    "clean_active": "Clean Active Eligibility",
    "identity_divergence": "Identity Divergence — Payer Name Differs",
}


@dataclass(frozen=True)
class EligibilityScenario:
    key: str
    label: str
    description: str
    clinical_patient: Patient
    clinical_coverage: CoverageProfile
    payer_member: MemberRecord
    payer_enrollment: EnrollmentRecord
    payer_plan: BenefitPlan
    payer_system: PayerSystem
    requester: X12Party
    payer_party: X12Party


@dataclass(frozen=True)
class EligibilityScenarioResult:
    scenario_key: str
    scenario_label: str
    run_at: datetime
    service_date: str
    clinical_patient: Patient
    clinical_coverage: CoverageProfile
    payer_member: MemberRecord
    payer_enrollment: EnrollmentRecord
    payer_plan: BenefitPlan
    match_result: MatchResult
    eligibility_response: EligibilityResponse
    parsed_270: Parsed270
    parsed_271: Parsed271
    x270: str
    x271: str

    @property
    def timestamp(self) -> str:
        return self.run_at.strftime("%Y%m%d_%H%M%S")

    @property
    def x270_filename(self) -> str:
        return f"medilacra_270_{self.timestamp}.x12"

    @property
    def x271_filename(self) -> str:
        return f"medilacra_271_{self.timestamp}.x12"

    @property
    def summary_filename(self) -> str:
        return f"exchange_summary_{self.timestamp}.json"

    @property
    def zip_filename(self) -> str:
        return f"medilacra_x12_exchange_{self.timestamp}.zip"

    def summary_dict(self) -> dict:
        clinical_last = self.clinical_patient.patient_name.split("^", 1)[0]
        return {
            "scenario": self.scenario_key,
            "scenario_label": self.scenario_label,
            "run_datetime": self.run_at.isoformat(),
            "service_date": self.service_date,
            "trace_id": self.parsed_270.trace_id,
            "member_match": self.match_result.outcome.value,
            "eligibility_outcome": self.eligibility_response.outcome.value,
            "matched_fields": list(self.match_result.matched_fields),
            "conflicting_fields": list(self.match_result.conflicting_fields),
            "clinical_identity": {
                "patient_id": self.clinical_patient.patient_id,
                "first_name": self.parsed_270.inquiry.first_name,
                "last_name": clinical_last,
                "member_id": self.clinical_coverage.member_id,
            },
            "payer_identity": {
                "member_record_id": self.payer_member.member_record_id,
                "first_name": self.payer_member.first_name,
                "last_name": self.payer_member.last_name,
                "member_id": self.payer_member.member_id,
            },
            "payer": {
                "payer_id": self.payer_member.payer_id,
                "plan_id": self.payer_plan.plan_id,
                "plan_name": self.payer_plan.plan_name,
                "group_number": self.payer_enrollment.group_number,
                "coverage_start": self.payer_enrollment.effective_start,
                "coverage_end": self.payer_enrollment.effective_end,
            },
            "files": {
                "x12_270": self.x270_filename,
                "x12_271": self.x271_filename,
            },
        }


def _clinical_patient() -> Patient:
    return Patient(
        patient_id="RAD1054994",
        patient_name="KELLEY^DEVIN",
        date_of_birth="19490116",
        sex="M",
        gender="",
        race="Asian",
        ethnicity="Hispanic or Latino",
        marital_status="M",
        language="en",
        employer="CVS Health Corporation",
        ssn="000-00-0000",
        address="100 Synthetic Way",
        phone="5550100000",
        email="devin.kelley@example.test",
        zip_code="00000",
        city="Synthetic City",
        state="MA",
    )


def _clinical_coverage(patient_id: str) -> CoverageProfile:
    return CoverageProfile(
        coverage_profile_id="COV-CLINICAL-001",
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


def _payer_materialization(
    clinical_patient: Patient,
    clinical_coverage: CoverageProfile,
) -> tuple[MemberRecord, EnrollmentRecord, BenefitPlan]:
    person_truth = PersonTruth(
        truth_person_id="PERSON-001",
        first_name="DEVIN",
        last_name="KELLEY",
        date_of_birth="1949-01-16",
        administrative_sex="M",
    )
    coverage_truth = CoverageTruth(
        truth_coverage_id="COVERAGE-001",
        truth_person_id=person_truth.truth_person_id,
        payer_id=clinical_coverage.payer_id,
        employer_id=clinical_coverage.employer_id,
        plan_id=clinical_coverage.plan_id,
        group_number=clinical_coverage.group_number,
        member_id=clinical_coverage.member_id,
        effective_start=clinical_coverage.effective_start,
        effective_end=clinical_coverage.effective_end,
    )

    member, enrollment, plan, _oracle_link = materialize_payer_state(
        person_truth,
        coverage_truth,
        plan_name=clinical_coverage.plan_name,
        plan_type=clinical_coverage.plan_type,
        clinical_patient_id=clinical_patient.patient_id,
        clinical_coverage_profile_id=clinical_coverage.coverage_profile_id,
    )

    return member, enrollment, plan


def build_scenario(key: str) -> EligibilityScenario:
    if key not in SCENARIO_LABELS:
        raise KeyError(f"Unknown X12 eligibility scenario: {key}")

    patient = _clinical_patient()
    coverage = _clinical_coverage(patient.patient_id)
    patient.coverage_profile = coverage

    member, enrollment, plan = _payer_materialization(
        patient,
        coverage,
    )

    if key == "identity_divergence":
        member = replace(
            member,
            last_name="KELLY",
        )

    payer_system = PayerSystem(
        coverage.payer_id,
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )

    requester = X12Party(
        identifier="MEDILACRA01",
        name="MEDILACRA CLINIC",
        identifier_qualifier="SV",
    )
    payer_party = X12Party(
        identifier=coverage.payer_id,
        name=coverage.payer_name.upper(),
        identifier_qualifier="PI",
    )

    description = (
        "Clinical and payer identities agree."
        if key == "clean_active"
        else (
            "Clinical last name is KELLEY while the payer holds KELLY. "
            "The payer still resolves the exact member ID."
        )
    )

    return EligibilityScenario(
        key=key,
        label=SCENARIO_LABELS[key],
        description=description,
        clinical_patient=patient,
        clinical_coverage=coverage,
        payer_member=member,
        payer_enrollment=enrollment,
        payer_plan=plan,
        payer_system=payer_system,
        requester=requester,
        payer_party=payer_party,
    )


def list_scenarios() -> tuple[tuple[str, str], ...]:
    return tuple(SCENARIO_LABELS.items())


def _controls_for_run(run_at: datetime) -> tuple[str, str, str, str]:
    raw = run_at.strftime("%Y%m%d%H%M%S")
    request_transaction = raw[-6:]
    response_transaction = f"{(int(request_transaction) + 1) % 1_000_000:06d}"

    request_interchange = raw[-9:]
    response_interchange = f"{(int(request_interchange) + 1) % 1_000_000_000:09d}"

    return (
        request_transaction,
        response_transaction,
        request_interchange,
        response_interchange,
    )


def run_scenario(
    key: str,
    *,
    service_date: str | date,
    run_at: datetime | None = None,
) -> EligibilityScenarioResult:
    scenario = build_scenario(key)
    run_at = run_at or datetime.now()
    service_date_value = (
        service_date.isoformat()
        if isinstance(service_date, date)
        else str(service_date)
    )

    (
        request_control,
        response_control,
        request_interchange,
        response_interchange,
    ) = _controls_for_run(run_at)

    compact_stamp = run_at.strftime("%Y%m%d%H%M%S")
    exchange = EligibilityExchange(
        trace_id=f"TRACE-270-{compact_stamp}",
        originating_company_id="MEDILACRA-CLINIC",
        reference_id=f"ELIG-REQ-{compact_stamp}",
        request_control_number=request_control,
        response_control_number=response_control,
        transaction_date=run_at.strftime("%Y%m%d"),
        request_time=run_at.strftime("%H%M%S"),
        response_time=run_at.strftime("%H%M%S"),
    )

    x270_transaction = build_270_from_clinical(
        scenario.clinical_patient,
        scenario.clinical_coverage,
        requester=scenario.requester,
        service_date=service_date_value,
        exchange=exchange,
    )

    x270 = wrap_interchange(
        x270_transaction,
        config=EnvelopeConfig(
            sender_id="MEDILACRA",
            receiver_id=scenario.clinical_coverage.payer_id,
            interchange_control_number=request_interchange,
            group_control_number="1",
            interchange_date=run_at.strftime("%y%m%d"),
            interchange_time=run_at.strftime("%H%M"),
            group_date=run_at.strftime("%Y%m%d"),
            group_time=run_at.strftime("%H%M%S"),
        ),
    )

    parsed_270 = parse_270_to_inquiry(x270)

    identity_query = IdentityQuery(
        member_id=parsed_270.inquiry.member_id,
        first_name=parsed_270.inquiry.first_name,
        last_name=parsed_270.inquiry.last_name,
        date_of_birth=parsed_270.inquiry.date_of_birth,
        administrative_sex=parsed_270.inquiry.administrative_sex,
    )
    match_result = scenario.payer_system.resolve_member(identity_query)
    response = scenario.payer_system.evaluate_eligibility(parsed_270.inquiry)

    x271_transaction = build_271_transaction(
        response,
        member=scenario.payer_member,
        plan=scenario.payer_plan,
        payer=scenario.payer_party,
        request=parsed_270,
        response_control_number=response_control,
        transaction_date=run_at.strftime("%Y%m%d"),
        transaction_time=run_at.strftime("%H%M%S"),
    )

    x271 = wrap_interchange(
        x271_transaction,
        config=EnvelopeConfig(
            sender_id=scenario.clinical_coverage.payer_id,
            receiver_id="MEDILACRA",
            interchange_control_number=response_interchange,
            group_control_number="2",
            interchange_date=run_at.strftime("%y%m%d"),
            interchange_time=run_at.strftime("%H%M"),
            group_date=run_at.strftime("%Y%m%d"),
            group_time=run_at.strftime("%H%M%S"),
        ),
    )

    parsed_271 = parse_271(x271)

    return EligibilityScenarioResult(
        scenario_key=scenario.key,
        scenario_label=scenario.label,
        run_at=run_at,
        service_date=service_date_value,
        clinical_patient=scenario.clinical_patient,
        clinical_coverage=scenario.clinical_coverage,
        payer_member=scenario.payer_member,
        payer_enrollment=scenario.payer_enrollment,
        payer_plan=scenario.payer_plan,
        match_result=match_result,
        eligibility_response=response,
        parsed_270=parsed_270,
        parsed_271=parsed_271,
        x270=x270,
        x271=x271,
    )


def build_exchange_zip(result: EligibilityScenarioResult) -> bytes:
    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            result.x270_filename,
            result.x270,
        )
        archive.writestr(
            result.x271_filename,
            result.x271,
        )
        archive.writestr(
            result.summary_filename,
            json.dumps(
                result.summary_dict(),
                indent=2,
                sort_keys=True,
            ),
        )

    return buffer.getvalue()
