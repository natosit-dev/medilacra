from hl7_demo.models import Encounter, Patient
from fhir.fhir_convert_backend import convert_message_to_bundle

from reality_interface.binding import ClinicalBinding
from reality_interface.hl7 import build_reality_oru
from reality_interface.validation import HumanValidation, MachineMeasurement, ValidatedMeasurement


def _patient() -> Patient:
    return Patient(
        patient_id="PAT001",
        patient_name="RIVERA, JAMIE",
        date_of_birth="1984-03-12",
        sex="F",
        gender="Woman",
        race="White",
        ethnicity="Not Hispanic or Latino",
        marital_status="Single",
        language="English",
        employer="SYNTHETIC EMPLOYER",
        ssn="000-00-0000",
        address="1 Test Street",
        phone="555-0100",
        email="jamie.rivera@example.invalid",
        zip_code="01854",
        city="Lowell",
        state="MA",
    )


def _encounter() -> Encounter:
    return Encounter(
        encounter_id="ENC001",
        patient_id="PAT001",
        visit_number="VN001",
        account_number="ACC001",
        patient_class="OUTPATIENT",
        assigned_patient_location="DEMO",
        admit_datetime="2026-08-25 20:00:00",
        discharge_datetime="2026-08-25 21:00:00",
        hospital_service="CARD",
        admit_source="Self Referral",
        discharge_disposition="Home",
        ordering_provider_id="P001",
        ordering_provider_name="TEST, PROVIDER",
        attending_provider_id="P001",
        attending_provider_name="TEST, PROVIDER",
        attending_provider_taxonomy="207RC0000X",
        attending_provider_specialty="Cardiovascular Disease",
        mid_level_provider_id="ML001",
        mid_level_provider_name="TEST, MIDLEVEL",
        referring_provider_id="REF001",
        referring_provider_name="TEST, REFERRER",
        placer_order_number="PLACER001",
        filler_order_number="FILLER001",
        place_of_service_code="22",
        place_of_service_description="On Campus-Outpatient Hospital",
    )


def test_validated_rate_survives_hl7_to_fhir():
    validated = ValidatedMeasurement(
        machine_measurement=MachineMeasurement(
            estimated_cycle_period_seconds=0.8,
            estimated_rate_per_minute=75.0,
            periodicity_score=0.9,
        ),
        human_validation=HumanValidation(
            interpretation="heart_rate",
            accepted=True,
        ),
        observed_at="2026-08-25T20:30:00-04:00",
    )
    binding = ClinicalBinding(
        patient=_patient(),
        encounter=_encounter(),
        validated_measurement=validated,
        observation_code="8867-4",
        observation_display="Heart rate",
        coding_system="LN",
        unit="/min",
    )

    hl7 = build_reality_oru(
        binding,
        source_filename="Nat_heart_8.25.wav",
        source_location="artifacts/reality_interface/run/Nat_heart_8.25.wav",
    )

    assert "OBX|1|NM|8867-4^Heart rate^LN||75|/min" in hl7
    assert "Nat_heart_8.25.wav" in hl7

    bundle, message_type = convert_message_to_bundle(hl7)
    assert message_type.startswith("ORU^")

    observations = [
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"].get("resourceType") == "Observation"
    ]

    heart_rate = next(
        obs
        for obs in observations
        if any(
            coding.get("code") == "8867-4"
            for coding in obs.get("code", {}).get("coding", [])
        )
    )
    assert heart_rate["valueQuantity"]["value"] == 75.0
    assert heart_rate["valueQuantity"]["unit"] == "/min"

    source = next(
        obs
        for obs in observations
        if any(
            coding.get("code") == "SOURCE-WAV"
            for coding in obs.get("code", {}).get("coding", [])
        )
    )
    assert "Nat_heart_8.25.wav" in source["valueString"]
