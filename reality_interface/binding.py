from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from hl7_demo.generators import gen_encounter, gen_patient
from hl7_demo.models import Encounter, Patient

from .validation import ValidatedMeasurement


@dataclass(frozen=True)
class ClinicalBinding:
    patient: Patient
    encounter: Encounter
    validated_measurement: ValidatedMeasurement
    observation_code: str
    observation_display: str
    coding_system: str
    unit: str

    @property
    def value(self) -> float:
        return self.validated_measurement.clinical_rate_per_minute


def _parse_observed_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def bind_to_synthetic_context(
    validated: ValidatedMeasurement,
    *,
    profile: dict[str, Any] | None = None,
) -> ClinicalBinding:
    """Bind a validated external measurement to synthetic MediLacra context."""

    if not validated.human_validation.accepted:
        raise ValueError("Measurement must be accepted before clinical binding")

    interpretation = validated.human_validation.interpretation.strip().lower()
    if interpretation != "heart_rate":
        raise ValueError(
            "Reality Interface v0.1 only supports semantic binding to heart_rate"
        )

    patient = gen_patient()
    encounter = gen_encounter(patient.patient_id, profile=profile)

    observed_at = _parse_observed_at(validated.observed_at)
    encounter.admit_datetime = (observed_at - timedelta(minutes=30)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    encounter.discharge_datetime = (observed_at + timedelta(minutes=30)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    return ClinicalBinding(
        patient=patient,
        encounter=encounter,
        validated_measurement=validated,
        observation_code="8867-4",
        observation_display="Heart rate",
        coding_system="LN",
        unit="/min",
    )
