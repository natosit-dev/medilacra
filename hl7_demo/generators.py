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
        patient_id=fake.unique.bothify("MRN#######"),
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
    account_number=fake.unique.bothify("ACCT########")
    return Encounter(
        encounter_id=f"{patient_id}_{visit}",
        patient_id=patient_id,
        visit_number=visit,
        account_number=account_number,
        patient_class="OUTPATIENT",
        assigned_patient_location="DEPT1",
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


# --- Add near your other helpers in generators.py ---

import random
from datetime import datetime

def pick_gender_identity():
    # SNOMED examples; swap as you like
    return random.choice([
        ("446151000124109", "Male", "SCT"),
        ("446141000124107", "Female", "SCT"),
        ("33791000087105",  "Non-binary gender", "SCT"),
        ("74964007",        "Intersex", "SCT"),
    ])

def pick_pronouns():
    # LOINC LA codes (examples)
    return random.choice([
        ("LA29520-6", "they/them/their/theirs/themselves", "LN"),
        ("LA29519-8", "she/her/her/hers/herself", "LN"),
        ("LA29518-0", "he/him/his/his/himself", "LN"),
    ])

# --- Gender Harmony biased selectors (drop in) ---

from typing import Tuple, Dict

# Canonical option pools
_GI_POOL = [
    ("446151000124109", "Male", "SCT"),
    ("446141000124107", "Female", "SCT"),
    ("33791000087105",  "Non-binary gender", "SCT"),
    ("74964007",        "Intersex", "SCT"),
]

_PRONOUN_POOL = [
    ("LA29518-0", "he/him/his/his/himself", "LN"),
    ("LA29519-8", "she/her/her/hers/herself", "LN"),
    ("LA29520-6", "they/them/their/theirs/themselves", "LN"),
]

_SPCU_POOL = [
    ("M-T", "Apply male-typical settings", "HL7"),
    ("F-T", "Apply female-typical settings", "HL7"),
    ("S",   "Specific (organ/system-specific)", "HL7"),
]

# Typical mappings for alignment with PID-8 Administrative Sex
_TYPICAL_BY_SEX: Dict[str, Dict[str, Tuple[str, str, str]]] = {
    "M": {
        "gi": _GI_POOL[0],        # Male
        "pro": _PRONOUN_POOL[0],  # he/him
        "spcu": _SPCU_POOL[0],    # M-T
    },
    "F": {
        "gi": _GI_POOL[1],        # Female
        "pro": _PRONOUN_POOL[1],  # she/her
        "spcu": _SPCU_POOL[1],    # F-T
    },
}

def _rand_other(pool, not_this: Tuple[str, str, str]):
    choices = [x for x in pool if x != not_this]
    return random.choice(choices) if choices else not_this

def choose_gender_harmony_values(admin_sex: str, match_bias: float = 0.95):
    """
    Returns a dict: {"gi": (code,text,system), "pro": (...), "spcu": (...)}
    - With probability `match_bias`, values align to PID-8 (M/F typical).
    - Otherwise, pick values outside the typical mapping.
    """
    sex = (admin_sex or "").upper()
    typical = _TYPICAL_BY_SEX.get(sex)

    if not typical:
        # Unknown/other admin sex -> fully random
        return {
            "gi": random.choice(_GI_POOL),
            "pro": random.choice(_PRONOUN_POOL),
            "spcu": random.choice(_SPCU_POOL),
        }

    if random.random() < match_bias:
        # Align with PID-8
        return typical

    # Non-typical case (5%): choose alternatives not equal to the typical picks
    return {
        "gi": _rand_other(_GI_POOL, typical["gi"]),
        "pro": _rand_other(_PRONOUN_POOL, typical["pro"]),
        "spcu": _rand_other(_SPCU_POOL, typical["spcu"]),
    }


def pick_spcu():
    # Example SPCU values; align with the set you choose to use
    return random.choice([
        ("F-T", "Apply female-typical settings", "HL7"),
        ("M-T", "Apply male-typical settings", "HL7"),
        ("S",   "Specific (organ/system-specific)", "HL7"),
    ])

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
