import random, re, uuid
from datetime import datetime, timedelta
from typing import List
from faker import Faker
from .models import Patient, Encounter, Transaction, Observation
from .utils import one_line

fake = Faker()
ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")


from .models import Patient, Encounter, Transaction, Observation
from .refdata import sample_zip_city_state


def gen_patient() -> Patient:
    # street only from Faker; zip/city/state from reference table
    place = sample_zip_city_state()
    first_last = fake.name().split()
    first, last = first_last[0], first_last[-1]
    return Patient(
        patient_id=fake.unique.bothify("RAD#######"),
        patient_name=f"{last.upper()}, {first.upper()}",
        date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=90).strftime("%Y-%m-%d"),
        sex=random.choice(["M","F"]),
        race=random.choice(["White","Black","Asian","Hispanic","Other"]),
        ssn=fake.ssn(),
        address=fake.street_address(),           # <— street only
        phone=one_line(fake.phone_number()),
        zip_code=place["zip"],                   # <— from ref
        city=place["city"],                      # <— from ref
        state=place["state"],                    # <— from ref
    )


def gen_encounter(patient_id: str) -> Encounter:
    admit_dt = fake.date_time_between(start_date="-14d", end_date="-1d")
    disch_dt = admit_dt + timedelta(hours=random.randint(1,6))
    visit = fake.unique.bothify("VN##########")
    prov = fake.name().split(); first, last = prov[0], prov[-1]
    prov_disp = f"{last.upper()}, {first.upper()}"
    return Encounter(
        encounter_id=f"{patient_id}_{visit}",
        patient_id=patient_id,
        visit_number=visit,
        patient_class="OUTPATIENT",
        assigned_patient_location="RAD_DEPT1",
        admit_datetime=admit_dt.strftime("%Y-%m-%d %H:%M:%S"),
        discharge_datetime=disch_dt.strftime("%Y-%m-%d %H:%M:%S"),
        hospital_service="RAD",
        ordering_provider_id=fake.bothify("R######"),
        ordering_provider_name=prov_disp,
        attending_provider_id=fake.bothify("P######"),
        attending_provider_name=prov_disp,
        placer_order_number=str(uuid.uuid4()),
        filler_order_number=str(uuid.uuid4()),
    )

def gen_transaction(encounter_id: str) -> Transaction:
    prov = fake.name().split(); first, last = prov[0], prov[-1]
    prov_disp = f"{last.upper()}, {first.upper()}"
    return Transaction(
        transaction_id=str(uuid.uuid4()),
        encounter_id=encounter_id,
        transaction_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        transaction_amount=round(random.uniform(100,500),2),
        unit_cost=round(random.uniform(50,250),2),
        transaction_quantity=1,
        fee_schedule=random.choice(["TECH","PRO"]),
        insurance_plan_id=fake.unique.bothify("INS#######"),
        billing_provider_id=fake.bothify("R######"),
        billing_provider_name=prov_disp,
    )

def gen_observation(enc: Encounter, report_row) -> Observation:
    admit_ts = datetime.strptime(enc.admit_datetime, "%Y-%m-%d %H:%M:%S")
    disch_ts = datetime.strptime(enc.discharge_datetime, "%Y-%m-%d %H:%M:%S")
    delta_sec = int((disch_ts - admit_ts).total_seconds())
    from datetime import timedelta
    completed = admit_ts + timedelta(seconds=random.randint(0, max(1, delta_sec)))
    return Observation(
        encounter_id=enc.encounter_id,
        observation_id=str(report_row["report_uid"]),
        cpt_code=str(report_row["cpt_code"]),
        icd_code=str(report_row["icd_code"]),
        placer_order_number=enc.placer_order_number,
        filler_order_number=enc.filler_order_number,
        procedure_description=str(report_row["procedure_description"]),
        observation_text=str(report_row["report_text"]),
        observation_sub_id="1",
        result_status="F",
        completed_time=completed.strftime("%Y-%m-%d %H:%M:%S"),
    )
