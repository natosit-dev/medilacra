"""Print one deterministic employer-coverage reality and its HL7 v2.5 core.

This is intentionally a small demonstration surface: it uses the real
CoverageProfile assignment, Transaction generator, and HL7 segment builders,
but omits optional SDOH/vitals/Gender Harmony enrichment so the institutional
coverage mapping is easy to inspect.
"""

from dataclasses import asdict
import json
import random
import sys
from pathlib import Path

from faker import Faker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hl7_demo.coverage import assign_coverage_profile
from hl7_demo.generators import gen_transaction
from hl7_demo.models import Encounter, Patient
from hl7_demo.segments import (
    seg_evn,
    seg_gt1,
    seg_in1,
    seg_in2,
    seg_msh,
    seg_pid,
    seg_pv1,
)


SEED = 42


def build_demo():
    random.seed(SEED)
    Faker.seed(SEED)

    patient = Patient(
        patient_id="RAD1234567",
        patient_name="RIVERA, JAMIE",
        date_of_birth="1983-06-14",
        sex="F",
        gender="Woman",
        race="White",
        ethnicity="Not Hispanic or Latino",
        marital_status="Single",
        language="English",
        employer="UNASSIGNED",
        ssn="111-22-3333",
        address="MEDILACRA TEST ADDRESS 0001",
        phone="978-555-0142",
        email="jamie.rivera@example.invalid",
        zip_code="01852",
        city="Lowell",
        state="MA",
    )

    coverage = assign_coverage_profile(
        patient,
        seed=SEED,
    )

    encounter = Encounter(
        encounter_id="ENC-COVERAGE-DEMO-001",
        patient_id=patient.patient_id,
        visit_number="VN0000000001",
        account_number="ACC-COVERAGE-DEMO-001",
        patient_class="OUTPATIENT",
        assigned_patient_location="RAD^ROOM1^MEDILACRAHS",
        admit_datetime="2026-10-03 14:00:00",
        discharge_datetime="2026-10-03 15:00:00",
        hospital_service="RAD",
        admit_source="Physician Referral",
        discharge_disposition="Home",
        ordering_provider_id="R123456",
        ordering_provider_name="LEE, MORGAN",
        attending_provider_id="P123456",
        attending_provider_name="PATEL, ALEX",
        attending_provider_taxonomy="2085R0202X",
        attending_provider_specialty="Diagnostic Radiology",
        mid_level_provider_id="ML123456",
        mid_level_provider_name="NGUYEN, CASEY",
        referring_provider_id="REF123456",
        referring_provider_name="LEE, MORGAN",
        placer_order_number="PLACER-COVERAGE-DEMO-001",
        filler_order_number="FILLER-COVERAGE-DEMO-001",
        place_of_service_code="22",
        place_of_service_description="On Campus-Outpatient Hospital",
    )

    transaction = gen_transaction(
        encounter.encounter_id,
        coverage_profile=coverage,
    )

    reality = {
        "seed": SEED,
        "patient": {
            "patient_id": patient.patient_id,
            "patient_name": patient.patient_name,
            "date_of_birth": patient.date_of_birth,
            "sex": patient.sex,
            "gender": patient.gender,
            "address": patient.address,
            "city": patient.city,
            "state": patient.state,
            "zip_code": patient.zip_code,
            "employer_compatibility_projection": patient.employer,
        },
        "coverage_profile": asdict(coverage),
        "encounter": {
            "encounter_id": encounter.encounter_id,
            "visit_number": encounter.visit_number,
            "patient_class": encounter.patient_class,
            "hospital_service": encounter.hospital_service,
            "admit_datetime": encounter.admit_datetime,
            "discharge_datetime": encounter.discharge_datetime,
        },
        "transaction_coverage_projection": {
            "insurance_plan_id": transaction.insurance_plan_id,
            "insurance_plan_name": transaction.insurance_plan_name,
            "member_id": transaction.member_id,
            "group_number": transaction.group_number,
            "plan_type": transaction.plan_type,
            "subscriber_relationship": transaction.subscriber_relationship,
        },
    }

    message = "\r".join(
        [
            seg_msh("ADT^A01"),
            seg_evn(encounter, "A01"),
            seg_pid(patient),
            seg_pv1(encounter),
            seg_gt1(
                transaction,
                patient=patient,
                coverage_profile=coverage,
                set_id=1,
            ),
            seg_in1(
                transaction,
                patient=patient,
                coverage_profile=coverage,
                set_id=1,
            ),
            seg_in2(coverage),
        ]
    )

    return reality, message


if __name__ == "__main__":
    reality, message = build_demo()

    print("=== SYNTHETIC REALITY ===")
    print(
        json.dumps(
            reality,
            indent=2,
            sort_keys=False,
        )
    )

    print("\n=== HL7 V2.5 COVERAGE-FOCUSED ADT ===")
    print(message.replace("\r", "\n"))
