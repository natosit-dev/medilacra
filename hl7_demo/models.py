from dataclasses import dataclass


@dataclass
class Encounter:
    encounter_id: str
    patient_id: str
    visit_number: str
    account_number: str 
    patient_class: str
    assigned_patient_location: str
    admit_datetime: str
    discharge_datetime: str
    hospital_service: str
    ordering_provider_id: str
    ordering_provider_name: str
    attending_provider_id: str
    attending_provider_name: str
    placer_order_number: str
    filler_order_number: str

@dataclass
class Transaction:
    transaction_id: str
    encounter_id: str
    transaction_date: str
    transaction_amount: float
    unit_cost: float
    transaction_quantity: int
    fee_schedule: str
    insurance_plan_id: str
    billing_provider_id: str
    billing_provider_name: str

@dataclass
class Observation:
    encounter_id: str
    observation_id: str
    cpt_code: str
    cpt_description: str
    icd_code: str
    icd_description: str
    placer_order_number: str
    filler_order_number: str
    procedure_description: str
    observation_text: str
    observation_sub_id: str
    result_status: str
    completed_time: str


@dataclass
class Patient:
    patient_id: str
    patient_name: str
    date_of_birth: str
    sex: str
    race: str
    ssn: str
    address: str         # street only
    phone: str
    zip_code: str        # 5-digit
    city: str            # NEW
    state: str           # NEW
