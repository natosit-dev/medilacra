# generators.py
import random
import re
import uuid
import inspect
from datetime import datetime, timedelta
from typing import Optional

from faker import Faker

# Package models & helpers
from .models import Patient, Encounter, Transaction, Observation
from .utils import one_line
from .refdata import sample_zip_city_state

# Structured logging
try:
    from utils.log_utils import get_logger
except Exception:
    # Minimal fallback so app still runs even if utils path isn't ready yet
    import logging
    def get_logger(name="MediLacra", context=None, level=logging.INFO):
        logger = logging.getLogger(name)
        if not logger.handlers:
            logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        return logger

logger = get_logger(
    name="MediLacra",
    context={"component": "gen", "module": "generators", "env": "dev"}
)

fake = Faker()
ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")


# ----------------------------
# Helpers
# ----------------------------
def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_construct(model_cls, **kwargs):
    """
    Safely instantiate models by filtering kwargs against the model's __init__
    signature. Logs any dropped keys and any missing required parameters before
    raising a clear TypeError (so Streamlit shows the exact problem).
    """
    try:
        sig = inspect.signature(model_cls)
        params = sig.parameters
        accepted = {k: v for k, v in kwargs.items() if k in params}
        dropped = sorted(set(kwargs) - set(accepted))
        required = sorted(
            name for name, p in params.items()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
            and p.default is inspect._empty
        )
        missing = sorted(set(required) - set(accepted))
    except Exception as e:
        logger.warning(
            "Model signature inspection failed",
            extra={"extra": {"model": getattr(model_cls, "__name__", str(model_cls)), "error": str(e)}}
        )
        return model_cls(**kwargs)

    if dropped:
        logger.warning(
            "Dropped constructor kwargs not in model",
            extra={"extra": {"model": model_cls.__name__, "dropped": dropped}}
        )
    if missing:
        logger.error(
            "Missing required kwargs for model",
            extra={"extra": {"model": model_cls.__name__, "missing": missing, "provided_keys": sorted(accepted.keys())}}
        )
        raise TypeError(f"{model_cls.__name__}.__init__() missing required kwargs: {', '.join(missing)}")

    return model_cls(**accepted)


def _extract_zip(text: str) -> Optional[str]:
    if not text:
        return None
    m = ZIP_RE.search(text)
    return m.group(0)[:5] if m else None


# ----------------------------
# Generators
# ----------------------------
def gen_patient() -> Patient:
    """
    Create a synthetic patient aligned to the legacy Patient model fields:
      REQUIRED: patient_id, patient_name, sex, race, ssn, address, zip_code
    Extra attributes are included for downstream convenience and will be
    dropped if the model doesn't accept them.
    """
    mrn = fake.unique.bothify("MRN########")
    first = fake.first_name()
    last = fake.last_name()
    sex_admin = random.choice(["F", "M", "U"])  # PID-8 Administrative Sex
    dob_dt = fake.date_of_birth(minimum_age=1, maximum_age=95)
    line1 = fake.street_address()

    try:
        zip_code, city, state = sample_zip_city_state()
    except Exception as e:
        logger.warning("sample_zip_city_state failed; using fallback", extra={"extra": {"error": str(e)}})
        zip_code, city, state = "02139", "Cambridge", "MA"

    full_name = f"{last}, {first}"
    race = random.choice([
        "White", "Black or African American", "Asian",
        "American Indian or Alaska Native", "Native Hawaiian or Other Pacific Islander", "Other"
    ])
    ssn = fake.ssn().replace("-", "")
    address_str = f"{line1}, {city}, {state} {zip_code}"

    data = dict(
        # REQUIRED by your Patient model
        patient_id=mrn,
        patient_name=full_name,
        sex=sex_admin,
        race=race,
        ssn=ssn,
        address=address_str,
        zip_code=zip_code,

        # Optional extras
        first_name=first,
        last_name=last,
        administrative_sex=sex_admin,
        date_of_birth=str(dob_dt),
        address_line1=line1,
        city=city,
        state=state,
        postal_code=zip_code,
        country="US",
        phone=fake.numerify("617#######"),
        email=f"{first.lower()}.{last.lower()}@example.org",
        created_at=_now_str(),
    )

    p = _safe_construct(Patient, **data)
    logger.info(
        "Patient generated",
        extra={"extra": {
            "patient_id": mrn, "sex": sex_admin, "zip": zip_code,
            "model_accepts_extras": any(hasattr(p, a) for a in ["first_name", "administrative_sex"])
        }}
    )
    return p


def gen_encounter(patient_id: str) -> Encounter:
    """
    Create a synthetic encounter for a given patient.
    Includes 'account_number' to support PID-18/PV1-18 usage.
    """
    admit_dt = fake.date_time_between(start_date="-14d", end_date="-1d")
    disch_dt = admit_dt + timedelta(hours=random.randint(1, 24))
    visit = fake.unique.bothify("VN##########")
    account_number = fake.unique.bothify("ACCT########")

    prov_first, prov_last = fake.first_name(), fake.last_name()
    prov_disp = f"{prov_last.upper()}, {prov_first.upper()}"

    data = dict(
        encounter_id=f"{patient_id}_{visit}",
        patient_id=patient_id,
        visit_number=visit,               # PV1-19
        account_number=account_number,    # NEW (model updated)
        patient_class=random.choice(["OUTPATIENT", "INPATIENT", "EMERGENCY"]),
        assigned_patient_location=random.choice(["DEPT1", "DEPT2", "DEPT3"]),
        admit_datetime=admit_dt.strftime("%Y-%m-%d %H:%M:%S"),
        discharge_datetime=disch_dt.strftime("%Y-%m-%d %H:%M:%S"),
        hospital_service=random.choice(["RAD", "LAB", "SUR"]),
        ordering_provider_id=fake.bothify("R######"),
        ordering_provider_name=prov_disp,
        attending_provider_id=fake.bothify("P######"),
        attending_provider_name=prov_disp,
        placer_order_number=str(uuid.uuid4()),
        filler_order_number=str(uuid.uuid4()),
        created_at=_now_str(),
    )

    e = _safe_construct(Encounter, **data)
    logger.info(
        "Encounter generated",
        extra={"extra": {
            "encounter_id": e.encounter_id,
            "patient_id": patient_id,
            "visit_number": visit,
            "account_number_present": hasattr(e, "account_number"),
        }}
    )
    return e


def gen_transaction(encounter_id: str) -> Transaction:
    """
    Create a synthetic transaction aligned to the legacy Transaction model.
    REQUIRED (per your error): billing_provider_id, billing_provider_name,
    fee_schedule, insurance_plan_id, transaction_amount, transaction_date,
    transaction_quantity, unit_cost
    """
    tx_id = f"TX-{uuid.uuid4()}"
    cpt = random.choice(["71045", "71046", "70450", "93000", "80053"])
    icd = random.choice(["R07.9", "M54.5", "R51.9", "I10", "E11.9"])

    # Quantity / pricing
    qty = random.choice([1, 1, 1, 2])  # bias to 1
    unit_cost = round(random.uniform(25, 400), 2)
    amount = round(qty * unit_cost, 2)

    # Dates
    tx_dt = fake.date_time_between(start_date="-14d", end_date="now")

    # Provider / plan / schedule
    prov_first, prov_last = fake.first_name(), fake.last_name()
    billing_provider_name = f"{prov_last.upper()}, {prov_first.upper()}"
    billing_provider_id = fake.bothify("BP######")
    fee_schedule = random.choice(["CMS", "LOCAL", "HOSPITAL", "DEFAULT"])
    insurance_plan_id = random.choice(["AETNA_PPO", "BCBS_HMO", "MEDICARE", "MEDICAID", "SELF_PAY"])

    data = dict(
        # likely common identifiers
        transaction_id=tx_id,
        encounter_id=encounter_id,
        procedure_cpt=cpt,
        diagnosis_icd=icd,

        # REQUIRED legacy fields
        billing_provider_id=billing_provider_id,
        billing_provider_name=billing_provider_name,
        fee_schedule=fee_schedule,
        insurance_plan_id=insurance_plan_id,
        transaction_amount=amount,
        transaction_date=tx_dt.strftime("%Y-%m-%d %H:%M:%S"),
        transaction_quantity=qty,
        unit_cost=unit_cost,

        # Optional extras
        created_at=_now_str(),
    )

    t = _safe_construct(Transaction, **data)
    logger.info(
        "Transaction generated",
        extra={"extra": {
            "transaction_id": tx_id, "encounter_id": encounter_id,
            "cpt": cpt, "icd": icd, "qty": qty, "unit_cost": unit_cost, "amount": amount
        }}
    )
    return t


def gen_observation(encounter: Encounter, report_row) -> Observation:
    """
    Create a synthetic observation aligned to the legacy Observation model.
    REQUIRED: completed_time, cpt_code, filler_order_number, icd_code,
              observation_sub_id, observation_text, placer_order_number,
              procedure_description, result_status
    """
    obs_id = f"OBS-{uuid.uuid4()}"
    enc_id = getattr(encounter, "encounter_id", None)

    # Defensive extraction from the report row (pandas.Series)
    def _get(col: str, default=None):
        try:
            return report_row[col]
        except Exception:
            return default

    # Try to pull semantics from report; fall back to reasonable defaults
    loinc_code = _get("loinc_code") or _get("LOINC") or random.choice(["2951-2", "17861-6", "2345-7"])
    loinc_display = _get("loinc_display") or _get("test_name") or "Sodium"
    units = _get("units") or "mmol/L"
    value = _get("result")
    if value is None:
        # simple numeric fallback in a reasonable clinical range
        value = round(random.uniform(3.5, 145.0), 1)

    # Procedure coding (some reports include CPT/ICD; otherwise synthesize)
    cpt = _get("cpt") or _get("CPT") or random.choice(["71045", "70450", "93000", "80053"])
    icd = _get("icd") or _get("ICD10") or _get("ICD") or random.choice(["R07.9", "M54.5", "R51.9", "I10", "E11.9"])

    # Order numbers – prefer encounter-level if available
    placer = getattr(encounter, "placer_order_number", str(uuid.uuid4()))
    filler = getattr(encounter, "filler_order_number", str(uuid.uuid4()))

    # Required, model-aligned fields
    data = dict(
        # Linkage (often accepted by the model; harmless if dropped)
        encounter_id=enc_id,

        # REQUIRED by your Observation model
        completed_time=_now_str(),
        cpt_code=str(cpt),
        filler_order_number=str(filler),
        icd_code=str(icd),
        observation_sub_id="1",
        observation_text=f"{value} {units}".strip(),
        placer_order_number=str(placer),
        procedure_description=str(loinc_display),
        result_status="F",

        # Useful extras (accepted if present on the model, otherwise safely dropped)
        observation_id=obs_id,
        loinc_code=str(loinc_code),
        loinc_display=str(loinc_display),
        units=str(units),
        value=str(value),
        created_at=_now_str(),
    )

    o = _safe_construct(Observation, **data)
    logger.info(
        "Observation generated",
        extra={"extra": {
            "observation_id": obs_id,
            "encounter_id": enc_id,
            "loinc": str(loinc_code),
            "cpt": str(cpt),
            "icd": str(icd),
            "status": "F"
        }}
    )
    return o


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
