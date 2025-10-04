# generators.py
# Synthetic entity and observation generators for MediLacra.
# NOTE: Logic is unchanged; only structured logging and explanatory comments were added.

import random, uuid
from datetime import datetime, timedelta
from typing import List
from faker import Faker

# --- Logging (structured) ---
try:
    from utils.log_utils import get_logger
except Exception:
    from log_utils import get_logger  # type: ignore

logger = get_logger(name="MediLacra", context={"component": "generators"})
logger.info("generators module loaded")

from .models import Patient, Encounter, Transaction, Observation
from .utils import one_line
from .refdata import sample_zip_city_state

fake = Faker()

# Generate each type of data to feed to segments and messages scripts

def gen_patient() -> Patient:
    """
    Create a synthetic Patient with street from Faker and ZIP/city/state from refdata.
    Ensures patient name aligns with sex.
    """
    try:
        place = sample_zip_city_state()  # {'zip','city','state'}
        sex = random.choice(["M", "F"])

        # Pick name generator based on sex
        if sex == "F":
            first_last = fake.name_female().split()
        else:
            first_last = fake.name_male().split()

        first, last = first_last[0], first_last[-1]

        patient = Patient(
            patient_id=fake.unique.bothify("RAD#######"),
            patient_name=f"{last.upper()}, {first.upper()}",
            date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=90).strftime("%Y-%m-%d"),
            sex=sex,
            race=random.choice(["White", "Black", "Asian", "Hispanic", "Other"]),
            ssn=fake.ssn(),
            address=fake.street_address(),           # street only
            phone=one_line(fake.phone_number()),
            zip_code=place["zip"],                   # from refdata
            city=place["city"],                      # from refdata
            state=place["state"],                    # from refdata
        )
        logger.info(
            "Generated patient",
            extra={"extra": {"patient_id": patient.patient_id, "zip": patient.zip_code, "sex": patient.sex}},
        )
        return patient
    except Exception as e:
        logger.error("gen_patient failed", extra={"extra": {"error": str(e)}})
        raise



def gen_encounter(patient_id: str) -> Encounter:
    """
    Generate a single Encounter for a patient, including admit/discharge, visit/account,
    and provider/placer/filler identifiers.
    """
    try:
        admit_dt = fake.date_time_between(start_date="-14d", end_date="-1d")
        disch_dt = admit_dt + timedelta(hours=random.randint(1,6))
        visit = fake.unique.bothify("VN##########")
        account_number = fake.unique.bothify("ACC#######%?")
        prov = fake.name().split(); first, last = prov[0], prov[-1]
        prov_disp = f"{last.upper()}, {first.upper()}"
        enc = Encounter(
            encounter_id=f"{patient_id}_{visit}",
            patient_id=patient_id,
            visit_number=visit,
            account_number=account_number,
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
        logger.info(
            "Generated encounter",
            extra={"extra": {
                "encounter_id": enc.encounter_id,
                "visit_number": enc.visit_number,
                "admit": enc.admit_datetime,
                "discharge": enc.discharge_datetime,
            }},
        )
        return enc
    except Exception as e:
        logger.error("gen_encounter failed", extra={"extra": {"patient_id": patient_id, "error": str(e)}})
        raise


def gen_transaction(encounter_id: str) -> Transaction:
    """
    Create a Transaction (charge) linked to an encounter with simple pricing.
    """
    try:
        prov = fake.name().split(); first, last = prov[0], prov[-1]
        prov_disp = f"{last.upper()}, {first.upper()}"
        tx = Transaction(
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
        logger.info(
            "Generated transaction",
            extra={"extra": {
                "transaction_id": tx.transaction_id,
                "encounter_id": encounter_id,
                "amount": tx.transaction_amount,
                "fee_schedule": tx.fee_schedule,
            }},
        )
        return tx
    except Exception as e:
        logger.error("gen_transaction failed", extra={"extra": {"encounter_id": encounter_id, "error": str(e)}})
        raise


def gen_observation(enc: Encounter, report_row) -> Observation:
    """
    Produce an Observation from a report row (CPT/ICD/description/text) aligned to the encounter window.
    """
    try:
        admit_ts = datetime.strptime(enc.admit_datetime, "%Y-%m-%d %H:%M:%S")
        disch_ts = datetime.strptime(enc.discharge_datetime, "%Y-%m-%d %H:%M:%S")
        delta_sec = int((disch_ts - admit_ts).total_seconds())
        from datetime import timedelta
        completed = admit_ts + timedelta(seconds=random.randint(0, max(1, delta_sec)))
        obs = Observation(
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
        logger.info(
            "Generated observation",
            extra={"extra": {
                "encounter_id": enc.encounter_id,
                "observation_id": obs.observation_id,
                "cpt": obs.cpt_code,
                "icd": obs.icd_code,
            }},
        )
        return obs
    except Exception as e:
        logger.error(
            "gen_observation failed",
            extra={"extra": {"encounter_id": getattr(enc, "encounter_id", None), "error": str(e)}},
        )
        raise


from typing import Tuple, Dict

# Canonical option pools (used by Gender Harmony helpers)
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
    """
    Helper: choose an alternative triple from the pool (if available).
    """
    choices = [x for x in pool if x != not_this]
    return random.choice(choices) if choices else not_this

def choose_gender_harmony_values(admin_sex: str, match_bias: float = 0.95):
    """
    Returns a dict: {"gi": (code,text,system), "pro": (...), "spcu": (...)}.
    With probability `match_bias`, values align to PID-8 (M/F typical), otherwise pick
    non-typical alternatives (about 5% by default). Unknown admin sex -> fully random.
    """
    try:
        sex = (admin_sex or "").upper()
        typical = _TYPICAL_BY_SEX.get(sex)

        if not typical:
            # Unknown/other admin sex -> fully random
            bundle = {
                "gi": random.choice(_GI_POOL),
                "pro": random.choice(_PRONOUN_POOL),
                "spcu": random.choice(_SPCU_POOL),
            }
            logger.info("GH selection (random)", extra={"extra": {"admin_sex": sex, "match_bias": match_bias}})
            return bundle

        if random.random() < match_bias:
            logger.info("GH selection (typical)", extra={"extra": {"admin_sex": sex, "match_bias": match_bias}})
            return typical

        # Non-typical case (~5%)
        bundle = {
            "gi": _rand_other(_GI_POOL, typical["gi"]),
            "pro": _rand_other(_PRONOUN_POOL, typical["pro"]),
            "spcu": _rand_other(_SPCU_POOL, typical["spcu"]),
        }
        logger.info("GH selection (non-typical)", extra={"extra": {"admin_sex": sex, "match_bias": match_bias}})
        return bundle
    except Exception as e:
        logger.error("choose_gender_harmony_values failed", extra={"extra": {"error": str(e)}})
        raise


def pick_spcu():
    """
    Pick a single SPCU triple from the canonical pool (random).
    """
    try:
        value = random.choice([
            ("F-T", "Apply female-typical settings", "HL7"),
            ("M-T", "Apply male-typical settings", "HL7"),
            ("S",   "Specific (organ/system-specific)", "HL7"),
        ])
        logger.info("SPCU picked", extra={"extra": {"code": value[0]}})
        return value
    except Exception as e:
        logger.error("pick_spcu failed", extra={"extra": {"error": str(e)}})
        raise


def now_str():
    """
    Current timestamp as 'YYYY-MM-DD HH:MM:SS' (used in several generators).
    """
    try:
        v = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return v
    except Exception as e:
        logger.error("now_str failed", extra={"extra": {"error": str(e)}})
        raise
