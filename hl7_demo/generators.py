# generators.py
# Synthetic entity and observation generators for MediLacra.
#
# The goal of this module is to create straightforward, understandable
# synthetic healthcare data that is linked across Patient, Encounter,
# Transaction, and Observation entities.
#
# Most values are intentionally generated from small lookup pools rather
# than complex simulation logic. This keeps the data predictable enough
# for testing while still providing realistic healthcare context.

import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, Tuple

from faker import Faker

# --- Logging -------------------------------------------------------------

try:
    from utils.log_utils import get_logger
except Exception:
    from log_utils import get_logger  # type: ignore

logger = get_logger(name="MediLacra", context={"component": "generators"})
logger.info("generators module loaded")


# --- MediLacra imports ---------------------------------------------------

from .models import Patient, Encounter, Transaction, Observation
from .utils import one_line
from .refdata import sample_zip_city_state
from utils.scenario_profile import compute_pv1_fields


fake = Faker()


# =========================================================================
# Simple reference pools
# =========================================================================
#
# These are intentionally small.
#
# The purpose is not to model every healthcare organization or payer.
# They simply make generated data more internally consistent than choosing
# every field independently.


# Place of Service values commonly useful in healthcare testing.
POS_BY_PATIENT_CLASS = {
    "INPATIENT": ("21", "Inpatient Hospital"),
    "OUTPATIENT": ("22", "On Campus-Outpatient Hospital"),
    "EMERGENCY": ("23", "Emergency Room - Hospital"),
}


# A small provider specialty/taxonomy pool.
#
# Taxonomy codes are stored alongside their human-readable specialty so
# those two values always remain consistent.
PROVIDER_SPECIALTIES = [
    ("2085R0202X", "Diagnostic Radiology"),
    ("207R00000X", "Internal Medicine"),
    ("207X00000X", "Orthopaedic Surgery"),
    ("207Q00000X", "Family Medicine"),
    ("207P00000X", "Emergency Medicine"),
]


# Simplified insurance plans.
#
# Keeping plan name and plan type together prevents combinations such as
# an HMO plan accidentally being labeled as a PPO.
INSURANCE_PLANS = [
    ("Blue Cross PPO", "PPO"),
    ("Community Health HMO", "HMO"),
    ("Regional Health EPO", "EPO"),
    ("Medicare", "MEDICARE"),
    ("Medicaid", "MEDICAID"),
]


LANGUAGES = [
    "English",
    "Spanish",
    "Portuguese",
    "French",
    "Chinese",
]


MARITAL_STATUSES = [
    "Single",
    "Married",
    "Divorced",
    "Widowed",
]


ETHNICITIES = [
    "Not Hispanic or Latino",
    "Hispanic or Latino",
]


RACES = [
    "White",
    "Black or African American",
    "Asian",
    "American Indian or Alaska Native",
    "Other",
]


ADMIT_SOURCES = [
    "Physician Referral",
    "Clinic Referral",
    "Emergency Department",
    "Transfer",
    "Self Referral",
]


DISCHARGE_DISPOSITIONS = [
    "Home",
    "Home with Services",
    "Skilled Nursing Facility",
    "Transfer to Another Facility",
]


SUBSCRIBER_RELATIONSHIPS = [
    "SELF",
    "SPOUSE",
    "CHILD",
    "OTHER",
]


GUARANTOR_RELATIONSHIPS = [
    "SELF",
    "SPOUSE",
    "PARENT",
    "GUARDIAN",
    "OTHER",
]


# =========================================================================
# Small helper functions
# =========================================================================


def _provider_name() -> str:
    """
    Generate a provider display name in LAST, FIRST format.

    This matches the general naming convention already used throughout
    MediLacra and can later be converted into HL7 XPN/XCN formatting.
    """
    parts = fake.name().split()

    first = parts[0]
    last = parts[-1]

    return f"{last.upper()}, {first.upper()}"


def _synthetic_npi() -> str:
    """
    Generate a 10-digit synthetic NPI-shaped value.

    This produces the correct basic format for testing but does not
    currently calculate or validate the official NPI check digit.
    """
    return fake.numerify("##########")


def _choose_provider_specialty(hospital_service: str) -> Tuple[str, str]:
    """
    Choose a provider taxonomy and specialty.

    Radiology encounters are intentionally biased toward Diagnostic
    Radiology. Other services use the general specialty pool.
    """
    if (hospital_service or "").upper() == "RAD":
        return "2085R0202X", "Diagnostic Radiology"

    return random.choice(PROVIDER_SPECIALTIES)


def _employer_for_age(age: int) -> str:
    """
    Generate a simple employment value.

    Employer is kept as a single demographic field for now because the
    initial goal is SDOH experimentation rather than employment modeling.

    Older patients are somewhat more likely to be retired. Other patients
    usually receive a synthetic employer name.
    """
    if age >= 67 and random.random() < 0.65:
        return "RETIRED"

    if random.random() < 0.08:
        return "SELF EMPLOYED"

    if random.random() < 0.05:
        return "NOT EMPLOYED"

    return fake.company().upper()

def _patient_email(patient_name: str) -> str:
    """
    Convert MediLacra's LAST, FIRST display name into a simple synthetic
    email address.

    Example:
        "SMITH, JANE" -> "jane.smith@fakermail.com"
    """
    last, first = [part.strip().lower() for part in patient_name.split(",", 1)]

    # Keep the address simple and predictable for synthetic test data.
    first = "".join(ch for ch in first if ch.isalnum())
    last = "".join(ch for ch in last if ch.isalnum())

    return f"{first}.{last}@fakermail.com"

# =========================================================================
# Patient generation
# =========================================================================


def gen_patient() -> Patient:
    """
    Create one synthetic patient.

    Geography is sampled from MediLacra's ZIP reference data so that
    ZIP, city, and state remain linked.

    Demographics are intentionally simple. They provide enough variation
    for HL7, SDOH, analytics, and data-quality testing without trying to
    simulate a complete population model.
    """
    try:
        # Sample a real ZIP/city/state combination from reference data.
        place = sample_zip_city_state()

        # Administrative sex remains the simple M/F value currently used
        # by PID and the existing Gender Harmony logic.
        sex = random.choice(["M", "F"])

        # Generate a name roughly aligned with administrative sex.
        if sex == "F":
            name_parts = fake.name_female().split()
        else:
            name_parts = fake.name_male().split()

        first = name_parts[0]
        last = name_parts[-1]

        patient_name = f"{last.upper()}, {first.upper()}"

        # Generate DOB first so employer logic can make a basic
        # age-aware decision.
        dob = fake.date_of_birth(
            minimum_age=18,
            maximum_age=90,
        )

        age = datetime.now().year - dob.year

        # Gender is persisted independently from administrative sex.
        # Most records remain aligned for simple baseline test data,
        # while a small percentage provide non-binary variation.
        if random.random() < 0.95:
            gender = "Woman" if sex == "F" else "Man"
        else:
            gender = "Non-binary"

        patient = Patient(
            # Identity
            patient_id=fake.unique.bothify("RAD#######"),
            patient_name=patient_name,
            date_of_birth=dob.strftime("%Y-%m-%d"),

            # Demographics
            sex=sex,
            gender=gender,
            race=random.choice(RACES),
            ethnicity=random.choice(ETHNICITIES),
            marital_status=random.choice(MARITAL_STATUSES),
            language=random.choice(LANGUAGES),
            employer=_employer_for_age(age),

            # Synthetic identifiers
            ssn=fake.ssn(),

            # Contact information
            address=fake.street_address(),
            phone=one_line(fake.phone_number()),
            email=_patient_email(patient_name),

            # Geography
            zip_code=place["zip"],
            city=place["city"],
            state=place["state"],
        )

        logger.info(
            "Generated patient",
            extra={
                "extra": {
                    "patient_id": patient.patient_id,
                    "zip": patient.zip_code,
                    "sex": patient.sex,
                    "gender": patient.gender,
                    "employer": patient.employer,
                }
            },
        )

        return patient

    except Exception as e:
        logger.error(
            "gen_patient failed",
            extra={"extra": {"error": str(e)}},
        )
        raise


# =========================================================================
# Encounter generation
# =========================================================================


def gen_encounter(
    patient_id: str,
    profile: dict | None = None,
) -> Encounter:
    """
    Generate one encounter linked to a patient.

    When a scenario profile is provided, the existing scenario logic
    determines patient class, assigned location, and hospital service.

    Additional encounter values such as POS, providers, admit source,
    and discharge disposition are then generated around that context.
    """
    try:
        # Generate a recent encounter lasting between one and six hours.
        admit_dt = fake.date_time_between(
            start_date="-14d",
            end_date="-1d",
        )

        discharge_dt = admit_dt + timedelta(
            hours=random.randint(1, 6)
        )

        visit_number = fake.unique.bothify("VN##########")
        account_number = fake.unique.bothify("ACC#######%?")

        # -----------------------------------------------------------------
        # Scenario-driven visit context
        # -----------------------------------------------------------------

        if profile:
            pv1 = compute_pv1_fields(profile)

            patient_class = {
                "I": "INPATIENT",
                "O": "OUTPATIENT",
                "E": "EMERGENCY",
            }.get(
                pv1["pv1_2"],
                "OUTPATIENT",
            )

            assigned_patient_location = pv1["pv1_3"]
            hospital_service = pv1["hospital_service"] or "RAD"

        else:
            # Existing Radiology-centric defaults.
            patient_class = "OUTPATIENT"
            assigned_patient_location = "RAD_DEPT1"
            hospital_service = "RAD"

        # -----------------------------------------------------------------
        # Place of Service
        # -----------------------------------------------------------------
        #
        # POS is derived from patient class instead of being selected
        # independently so the encounter and billing context agree.

        pos_code, pos_description = POS_BY_PATIENT_CLASS.get(
            patient_class,
            ("22", "On Campus-Outpatient Hospital"),
        )

        # -----------------------------------------------------------------
        # Providers
        # -----------------------------------------------------------------

        ordering_provider_name = _provider_name()
        attending_provider_name = _provider_name()
        mid_level_provider_name = _provider_name()
        referring_provider_name = _provider_name()

        taxonomy, specialty = _choose_provider_specialty(
            hospital_service
        )

        enc = Encounter(
            # Core encounter identifiers
            encounter_id=f"{patient_id}_{visit_number}",
            patient_id=patient_id,
            visit_number=visit_number,
            account_number=account_number,

            # Visit context
            patient_class=patient_class,
            assigned_patient_location=assigned_patient_location,
            admit_datetime=admit_dt.strftime("%Y-%m-%d %H:%M:%S"),
            discharge_datetime=discharge_dt.strftime("%Y-%m-%d %H:%M:%S"),
            hospital_service=hospital_service,

            # Admission / discharge context
            admit_source=random.choice(ADMIT_SOURCES),
            discharge_disposition=random.choice(
                DISCHARGE_DISPOSITIONS
            ),

            # Ordering provider
            ordering_provider_id=fake.bothify("R######"),
            ordering_provider_name=ordering_provider_name,

            # Attending provider
            attending_provider_id=fake.bothify("P######"),
            attending_provider_name=attending_provider_name,
            attending_provider_taxonomy=taxonomy,
            attending_provider_specialty=specialty,

            # Mid-level provider
            mid_level_provider_id=fake.bothify("ML######"),
            mid_level_provider_name=mid_level_provider_name,

            # Referring provider
            referring_provider_id=fake.bothify("REF######"),
            referring_provider_name=referring_provider_name,

            # Order identifiers
            placer_order_number=str(uuid.uuid4()),
            filler_order_number=str(uuid.uuid4()),

            # Billing / encounter classification
            place_of_service_code=pos_code,
            place_of_service_description=pos_description,
        )

        logger.info(
            "Generated encounter",
            extra={
                "extra": {
                    "encounter_id": enc.encounter_id,
                    "visit_number": enc.visit_number,
                    "patient_class": enc.patient_class,
                    "assigned_location": (
                        enc.assigned_patient_location
                    ),
                    "hospital_service": enc.hospital_service,
                    "place_of_service": (
                        enc.place_of_service_code
                    ),
                    "specialty": (
                        enc.attending_provider_specialty
                    ),
                }
            },
        )

        return enc

    except Exception as e:
        logger.error(
            "gen_encounter failed",
            extra={
                "extra": {
                    "patient_id": patient_id,
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# Transaction generation
# =========================================================================


def gen_transaction(encounter_id: str) -> Transaction:
    """
    Create one synthetic charge transaction linked to an encounter.

    Insurance values are generated together so plan name and plan type
    remain consistent.

    Guarantor and subscriber values are intentionally lightweight for now.
    They can later be normalized into separate Coverage or Guarantor
    entities if MediLacra needs a more complete financial model.
    """
    try:
        insurance_plan_name, plan_type = random.choice(
            INSURANCE_PLANS
        )

        billing_provider_name = _provider_name()
        guarantor_name = _provider_name()

        transaction = Transaction(
            # Transaction identity
            transaction_id=str(uuid.uuid4()),
            encounter_id=encounter_id,
            transaction_date=datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            # Charge information
            transaction_amount=round(
                random.uniform(100, 500),
                2,
            ),
            unit_cost=round(
                random.uniform(50, 250),
                2,
            ),
            transaction_quantity=1,
            fee_schedule=random.choice(
                ["TECH", "PRO"]
            ),

            # Insurance / coverage
            insurance_plan_id=fake.unique.bothify(
                "INS#######"
            ),
            insurance_plan_name=insurance_plan_name,
            member_id=fake.unique.bothify(
                "MEM########"
            ),
            group_number=fake.bothify(
                "GRP######"
            ),
            plan_type=plan_type,
            subscriber_relationship=random.choice(
                SUBSCRIBER_RELATIONSHIPS
            ),
            authorization_number=fake.bothify(
                "AUTH########"
            ),

            # Billing provider
            billing_provider_id=fake.bothify(
                "R######"
            ),
            billing_provider_name=billing_provider_name,
            billing_provider_npi=_synthetic_npi(),

            # Guarantor
            guarantor_name=guarantor_name,
            guarantor_relationship=random.choice(
                GUARANTOR_RELATIONSHIPS
            ),
        )

        logger.info(
            "Generated transaction",
            extra={
                "extra": {
                    "transaction_id": (
                        transaction.transaction_id
                    ),
                    "encounter_id": encounter_id,
                    "amount": (
                        transaction.transaction_amount
                    ),
                    "fee_schedule": (
                        transaction.fee_schedule
                    ),
                    "plan_type": (
                        transaction.plan_type
                    ),
                }
            },
        )

        return transaction

    except Exception as e:
        logger.error(
            "gen_transaction failed",
            extra={
                "extra": {
                    "encounter_id": encounter_id,
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# Observation generation
# =========================================================================


def gen_observation(
    enc: Encounter,
    report_row,
) -> Observation:
    """
    Produce one Observation from a source report row.

    CPT, ICD, procedure description, and report text remain sourced from
    the report catalog.

    The observation completion timestamp is generated somewhere between
    encounter admission and discharge so the result remains temporally
    consistent with the encounter.
    """
    try:
        admit_ts = datetime.strptime(
            enc.admit_datetime,
            "%Y-%m-%d %H:%M:%S",
        )

        discharge_ts = datetime.strptime(
            enc.discharge_datetime,
            "%Y-%m-%d %H:%M:%S",
        )

        delta_seconds = int(
            (discharge_ts - admit_ts).total_seconds()
        )

        completed = admit_ts + timedelta(
            seconds=random.randint(
                0,
                max(1, delta_seconds),
            )
        )

        performing_provider_name = _provider_name()

        observation = Observation(
            # Observation identity
            encounter_id=enc.encounter_id,
            observation_id=str(
                report_row["report_uid"]
            ),

            # Procedure / service coding
            cpt_code=str(
                report_row["cpt_code"]
            ),
            cpt_description=str(
                report_row["cpt_description"]
            ),
            procedure_description=str(
                report_row["procedure_description"]
            ),

            # Diagnosis
            icd_code=str(
                report_row["icd_code"]
            ),
            icd_description=str(
                report_row["icd_description"]
            ),

            # One diagnosis currently exists per generated observation.
            # It is therefore treated as the primary/final diagnosis.
            diagnosis_type="FINAL",
            diagnosis_rank=1,

            # Order linkage
            placer_order_number=enc.placer_order_number,
            filler_order_number=enc.filler_order_number,

            # Result
            observation_text=str(
                report_row["report_text"]
            ),
            observation_sub_id="1",
            result_status="F",
            completed_time=completed.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            # Performing provider
            performing_provider_id=fake.bothify(
                "PR######"
            ),
            performing_provider_name=(
                performing_provider_name
            ),
        )

        logger.info(
            "Generated observation",
            extra={
                "extra": {
                    "encounter_id": (
                        enc.encounter_id
                    ),
                    "observation_id": (
                        observation.observation_id
                    ),
                    "cpt": observation.cpt_code,
                    "icd": observation.icd_code,
                    "diagnosis_rank": (
                        observation.diagnosis_rank
                    ),
                }
            },
        )

        return observation

    except Exception as e:
        logger.error(
            "gen_observation failed",
            extra={
                "extra": {
                    "encounter_id": getattr(
                        enc,
                        "encounter_id",
                        None,
                    ),
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# Gender Harmony helpers
# =========================================================================
#
# These functions are retained because the existing ADT builder uses them
# when generating Gender Identity, Pronouns, and SPCU OBX segments.


_GI_POOL = [
    (
        "446151000124109",
        "Male",
        "SCT",
    ),
    (
        "446141000124107",
        "Female",
        "SCT",
    ),
    (
        "33791000087105",
        "Non-binary gender",
        "SCT",
    ),
    (
        "74964007",
        "Intersex",
        "SCT",
    ),
]


_PRONOUN_POOL = [
    (
        "LA29518-0",
        "he/him/his/his/himself",
        "LN",
    ),
    (
        "LA29519-8",
        "she/her/her/hers/herself",
        "LN",
    ),
    (
        "LA29520-6",
        "they/them/their/theirs/themselves",
        "LN",
    ),
]


_SPCU_POOL = [
    (
        "M-T",
        "Apply male-typical settings",
        "HL7",
    ),
    (
        "F-T",
        "Apply female-typical settings",
        "HL7",
    ),
    (
        "S",
        "Specific (organ/system-specific)",
        "HL7",
    ),
]


# Typical Gender Harmony mappings based on PID-8 Administrative Sex.
_TYPICAL_BY_SEX: Dict[
    str,
    Dict[str, Tuple[str, str, str]],
] = {
    "M": {
        "gi": _GI_POOL[0],
        "pro": _PRONOUN_POOL[0],
        "spcu": _SPCU_POOL[0],
    },
    "F": {
        "gi": _GI_POOL[1],
        "pro": _PRONOUN_POOL[1],
        "spcu": _SPCU_POOL[1],
    },
}


def _rand_other(
    pool,
    not_this: Tuple[str, str, str],
):
    """
    Select a value from a pool that differs from the supplied value.
    """
    choices = [
        item
        for item in pool
        if item != not_this
    ]

    return (
        random.choice(choices)
        if choices
        else not_this
    )


def choose_gender_harmony_values(
    admin_sex: str,
    match_bias: float = 0.95,
):
    """
    Select Gender Identity, Pronouns, and SPCU values.

    Most generated records align with administrative sex to preserve the
    existing MediLacra behavior. A small percentage intentionally differ
    to create useful edge cases for interface and data-quality testing.
    """
    try:
        sex = (admin_sex or "").upper()
        typical = _TYPICAL_BY_SEX.get(sex)

        if not typical:
            bundle = {
                "gi": random.choice(_GI_POOL),
                "pro": random.choice(_PRONOUN_POOL),
                "spcu": random.choice(_SPCU_POOL),
            }

            logger.info(
                "GH selection (random)",
                extra={
                    "extra": {
                        "admin_sex": sex,
                        "match_bias": match_bias,
                    }
                },
            )

            return bundle

        if random.random() < match_bias:
            logger.info(
                "GH selection (typical)",
                extra={
                    "extra": {
                        "admin_sex": sex,
                        "match_bias": match_bias,
                    }
                },
            )

            return typical

        bundle = {
            "gi": _rand_other(
                _GI_POOL,
                typical["gi"],
            ),
            "pro": _rand_other(
                _PRONOUN_POOL,
                typical["pro"],
            ),
            "spcu": _rand_other(
                _SPCU_POOL,
                typical["spcu"],
            ),
        }

        logger.info(
            "GH selection (non-typical)",
            extra={
                "extra": {
                    "admin_sex": sex,
                    "match_bias": match_bias,
                }
            },
        )

        return bundle

    except Exception as e:
        logger.error(
            "choose_gender_harmony_values failed",
            extra={"extra": {"error": str(e)}},
        )
        raise


def pick_spcu():
    """
    Select one SPCU value from the existing synthetic value pool.
    """
    try:
        value = random.choice(_SPCU_POOL)

        logger.info(
            "SPCU picked",
            extra={
                "extra": {
                    "code": value[0],
                }
            },
        )

        return value

    except Exception as e:
        logger.error(
            "pick_spcu failed",
            extra={"extra": {"error": str(e)}},
        )
        raise


def now_str():
    """
    Return the current timestamp in MediLacra's standard string format.
    """
    try:
        return datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    except Exception as e:
        logger.error(
            "now_str failed",
            extra={"extra": {"error": str(e)}},
        )
        raise