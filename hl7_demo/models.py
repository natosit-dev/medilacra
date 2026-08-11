from dataclasses import dataclass


@dataclass
class Encounter:
    # Core encounter identifiers
    encounter_id: str
    patient_id: str
    visit_number: str
    account_number: str

    # Visit context
    patient_class: str
    assigned_patient_location: str
    admit_datetime: str
    discharge_datetime: str
    hospital_service: str

    # Admission / discharge context
    admit_source: str
    discharge_disposition: str

    # Ordering provider
    ordering_provider_id: str
    ordering_provider_name: str

    # Attending provider
    attending_provider_id: str
    attending_provider_name: str
    attending_provider_taxonomy: str
    attending_provider_specialty: str

    # Mid-level provider
    mid_level_provider_id: str
    mid_level_provider_name: str

    # Referring provider
    referring_provider_id: str
    referring_provider_name: str

    # Order identifiers
    placer_order_number: str
    filler_order_number: str

    # Billing / encounter classification
    place_of_service_code: str
    place_of_service_description: str


@dataclass
class Transaction:
    # Transaction identity
    transaction_id: str
    encounter_id: str
    transaction_date: str

    # Charge information
    transaction_amount: float
    unit_cost: float
    transaction_quantity: int
    fee_schedule: str

    # Insurance / coverage information
    insurance_plan_id: str
    insurance_plan_name: str
    member_id: str
    group_number: str
    plan_type: str
    subscriber_relationship: str
    authorization_number: str

    # Billing provider
    billing_provider_id: str
    billing_provider_name: str
    billing_provider_npi: str

    # Guarantor
    guarantor_name: str
    guarantor_relationship: str


@dataclass
class Observation:
    # Observation identity
    encounter_id: str
    observation_id: str

    # Procedure / service coding
    cpt_code: str
    cpt_description: str
    procedure_description: str

    # Diagnosis
    icd_code: str
    icd_description: str
    diagnosis_type: str
    diagnosis_rank: int

    # Order linkage
    placer_order_number: str
    filler_order_number: str

    # Result
    observation_text: str
    observation_sub_id: str
    result_status: str
    completed_time: str

    # Performing provider
    performing_provider_id: str
    performing_provider_name: str


@dataclass
class Patient:
    # Patient identity
    patient_id: str
    patient_name: str
    date_of_birth: str

    # Demographics
    sex: str
    gender: str
    race: str
    ethnicity: str
    marital_status: str
    language: str
    employer: str

    # Synthetic identifiers
    ssn: str

    # Contact information
    address: str
    phone: str
    email: str

    # Geography
    zip_code: str
    city: str
    state: str