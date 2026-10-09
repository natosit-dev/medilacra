from dataclasses import replace

import pytest

from hl7_demo.models import CoverageProfile, Patient
from payer.materialize import materialize_payer_state
from payer.models import EligibilityOutcome
from payer.system import PayerSystem
from reality.models import CoverageTruth, PersonTruth
from x12.eligibility_270 import (
    build_270_from_clinical,
    parse_270_to_inquiry,
)
from x12.eligibility_271 import (
    GENERIC_ACTIVE_SERVICE_TYPES,
    build_271_transaction,
    parse_271,
)
from x12.envelope import EnvelopeConfig, wrap_interchange
from x12.models import EligibilityExchange, X12Party
from x12.parser import first_segment, transaction_segments


def _clinical_patient():
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
        ssn="331-20-5428",
        address="224 Stevens Mall",
        phone="869-923-4470",
        email="devin.kelley@fakermail.com",
        zip_code="53002",
        city="Allenton",
        state="WI",
    )


def _clinical_coverage(patient_id="RAD1054994"):
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


def _truth():
    person = PersonTruth(
        truth_person_id="PERSON-001",
        first_name="DEVIN",
        last_name="KELLEY",
        date_of_birth="1949-01-16",
        administrative_sex="M",
    )
    coverage = CoverageTruth(
        truth_coverage_id="COVERAGE-001",
        truth_person_id=person.truth_person_id,
        payer_id="KAISER",
        employer_id="CVS",
        plan_id="STANDARD_PPO",
        group_number="GRP-CVS-398915",
        member_id="MEM-01374522",
        effective_start="2026-01-01",
        effective_end="2026-12-31",
    )
    return person, coverage


def _exchange():
    return EligibilityExchange(
        trace_id="TRACE-270-0001",
        originating_company_id="MEDILACRA-CLINIC",
        reference_id="ELIG-REQ-0001",
        request_control_number="0001",
        response_control_number="0002",
        transaction_date="20261006",
        request_time="0910",
        response_time="0911",
    )


def _requester():
    return X12Party(
        identifier="MEDILACRA01",
        name="MEDILACRA CLINIC",
        identifier_qualifier="SV",
    )


def _payer_party():
    return X12Party(
        identifier="KAISER",
        name="KAISER PERMANENTE",
        identifier_qualifier="PI",
    )


def _payer_state():
    person, coverage = _truth()
    member, enrollment, plan, oracle = materialize_payer_state(
        person,
        coverage,
        plan_name="Standard PPO",
        plan_type="PPO",
        clinical_patient_id="RAD1054994",
        clinical_coverage_profile_id="COV-CLINICAL-001",
    )
    return member, enrollment, plan, oracle


def _build_270():
    return build_270_from_clinical(
        _clinical_patient(),
        _clinical_coverage(),
        requester=_requester(),
        service_date="2026-10-06",
        exchange=_exchange(),
    )


def _evaluate(x270, *, member_override=None):
    parsed = parse_270_to_inquiry(x270)
    member, enrollment, plan, oracle = _payer_state()
    if member_override is not None:
        member = member_override(member)

    system = PayerSystem(
        "KAISER",
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )
    response = system.evaluate_eligibility(parsed.inquiry)
    return parsed, member, plan, response, oracle


def _assert_se_count(transaction):
    segments = transaction_segments(transaction)
    se = first_segment(segments, "SE")
    assert se is not None
    assert int(se.element(1)) == len(segments)
    assert se.element(2) == segments[0].element(2)


def test_scenario_1_clean_active_270_to_271():
    x270 = _build_270()

    assert "ST*270*0001*005010X279A1~" in x270
    assert "NM1*IL*1*KELLEY*DEVIN****MI*MEM-01374522~" in x270
    assert "DTP*291*D8*20261006~" in x270
    assert "EQ*30~" in x270
    _assert_se_count(x270)

    parsed, member, plan, response, _ = _evaluate(x270)

    assert parsed.inquiry.payer_id == "KAISER"
    assert parsed.inquiry.requester_id == "MEDILACRA01"
    assert parsed.inquiry.member_id == "MEM-01374522"
    assert parsed.inquiry.first_name == "DEVIN"
    assert parsed.inquiry.last_name == "KELLEY"
    assert parsed.inquiry.date_of_birth == "1949-01-16"
    assert parsed.inquiry.administrative_sex == "M"
    assert parsed.inquiry.service_date == "2026-10-06"
    assert parsed.inquiry.service_type == "30"
    assert parsed.trace_id == "TRACE-270-0001"

    assert response.outcome == EligibilityOutcome.ACTIVE
    assert response.conflicting_fields == ()

    x271 = build_271_transaction(
        response,
        member=member,
        plan=plan,
        payer=_payer_party(),
        request=parsed,
        response_control_number=_exchange().response_control_number,
        transaction_date=_exchange().transaction_date,
        transaction_time=_exchange().response_time,
    )

    assert "ST*271*0002*005010X279A1~" in x271
    assert "TRN*2*TRACE-270-0001*MEDILACRA-CLINIC~" in x271
    assert "NM1*IL*1*KELLEY*DEVIN****MI*MEM-01374522~" in x271
    assert "DTP*346*D8*20260101~" in x271
    assert "DTP*347*D8*20261231~" in x271
    assert "EB*1**30**Standard PPO~" in x271
    assert "REF*6P*GRP-CVS-398915~" in x271
    _assert_se_count(x271)

    parsed_271 = parse_271(x271)

    assert parsed_271.trace_id == parsed.trace_id
    assert parsed_271.subscriber_member_id == "MEM-01374522"
    assert parsed_271.subscriber_last_name == "KELLEY"
    assert parsed_271.subscriber_first_name == "DEVIN"
    assert parsed_271.subscriber_date_of_birth == "1949-01-16"
    assert parsed_271.coverage_start == "2026-01-01"
    assert parsed_271.coverage_end == "2026-12-31"
    assert parsed_271.plan_name == "Standard PPO"
    assert parsed_271.group_number == "GRP-CVS-398915"
    assert parsed_271.active_service_types == ()  # no payer service facts established


def test_scenario_2_clinical_and_payer_names_diverge_but_member_matches():
    x270 = _build_270()

    assert "NM1*IL*1*KELLEY*DEVIN****MI*MEM-01374522~" in x270

    parsed, member, plan, response, _ = _evaluate(
        x270,
        member_override=lambda record: replace(
            record,
            last_name="KELLY",
        ),
    )

    assert response.outcome == EligibilityOutcome.ACTIVE
    assert "member_id" in response.matched_fields
    assert "date_of_birth" in response.matched_fields
    assert "last_name" in response.conflicting_fields

    x271 = build_271_transaction(
        response,
        member=member,
        plan=plan,
        payer=_payer_party(),
        request=parsed,
        response_control_number=_exchange().response_control_number,
        transaction_date=_exchange().transaction_date,
        transaction_time=_exchange().response_time,
    )

    assert "NM1*IL*1*KELLY*DEVIN****MI*MEM-01374522~" in x271
    assert "NM1*IL*1*KELLEY*DEVIN****MI*MEM-01374522~" not in x271

    parsed_271 = parse_271(x271)
    assert parsed_271.subscriber_last_name == "KELLY"
    assert parsed_271.trace_id == "TRACE-270-0001"


def test_270_can_be_parsed_after_minimal_x12_envelope_is_added():
    x270 = _build_270()
    full = wrap_interchange(
        x270,
        config=EnvelopeConfig(
            sender_id="MEDILACRA",
            receiver_id="KAISER",
            interchange_control_number="1",
            group_control_number="1",
            interchange_date="261006",
            interchange_time="0910",
            group_date="20261006",
            group_time="0910",
        ),
    )

    assert full.startswith("ISA*00*")
    assert "GS*HS*MEDILACRA*KAISER*20261006*0910*1*X*005010X279A1~" in full
    assert full.endswith("IEA*1*000000001~")

    parsed = parse_270_to_inquiry(full)
    assert parsed.inquiry.member_id == "MEM-01374522"
    assert parsed.trace_id == "TRACE-270-0001"


def test_271_generic_active_response_has_plan_and_required_status_service_types():
    x270 = _build_270()
    parsed, member, plan, response, _ = _evaluate(x270)

    x271 = build_271_transaction(
        response,
        member=member,
        plan=plan,
        payer=_payer_party(),
        request=parsed,
        response_control_number="0002",
        transaction_date="20261006",
        transaction_time="0911",
    )

    parsed_271 = parse_271(x271)
    assert parsed_271.plan_name == "Standard PPO"
    assert parsed_271.active_service_types == ()

    # Service benefit claims are available only when supplied by the payer.
    explicit_plan = replace(plan, active_service_types=("1", "33", "MH"))
    x271_with_benefits = build_271_transaction(
        response, member=member, plan=explicit_plan, payer=_payer_party(),
        request=parsed, response_control_number="0003",
        transaction_date="20261006", transaction_time="0911",
    )
    assert parse_271(x271_with_benefits).active_service_types == ("1", "33", "MH")
    assert "EB*1**1>33>MH~" in x271_with_benefits


def test_first_271_builder_refuses_non_active_outcomes_for_now():
    x270 = _build_270()
    parsed, member, plan, response, _ = _evaluate(x270)
    inactive = replace(
        response,
        outcome=EligibilityOutcome.INACTIVE,
    )

    with pytest.raises(NotImplementedError):
        build_271_transaction(
            inactive,
            member=member,
            plan=plan,
            payer=_payer_party(),
            request=parsed,
            response_control_number="0002",
            transaction_date="20261006",
            transaction_time="0911",
        )


def test_x12_boundary_does_not_import_hidden_or_clinical_state_into_271():
    import x12.eligibility_270 as eligibility_270
    import x12.eligibility_271 as eligibility_271

    assert not hasattr(eligibility_270, "GroundTruthLink")
    assert not hasattr(eligibility_271, "GroundTruthLink")
    assert not hasattr(eligibility_271, "Patient")
    assert not hasattr(eligibility_271, "CoverageProfile")


def test_payer_engine_remains_x12_agnostic():
    import payer.system as payer_system_module

    assert not hasattr(payer_system_module, "X12Segment")
    assert not hasattr(payer_system_module, "Parsed270")
    assert not hasattr(payer_system_module, "Parsed271")
