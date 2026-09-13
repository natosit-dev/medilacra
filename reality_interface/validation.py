from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .periodicity import PeriodicityResult


class MachineMeasurement(BaseModel):
    estimated_cycle_period_seconds: float = Field(gt=0)
    estimated_rate_per_minute: float = Field(gt=0)
    periodicity_score: float = Field(ge=0)


class HumanValidation(BaseModel):
    interpretation: str
    accepted: bool
    override_rate_per_minute: float | None = Field(default=None, gt=0)
    notes: str | None = None


class ValidatedMeasurement(BaseModel):
    machine_measurement: MachineMeasurement
    human_validation: HumanValidation
    observed_at: str

    @property
    def clinical_rate_per_minute(self) -> float:
        override = self.human_validation.override_rate_per_minute
        if override is not None:
            return float(override)
        return float(self.machine_measurement.estimated_rate_per_minute)


def validate_measurement(
    result: PeriodicityResult,
    *,
    interpretation: str,
    accepted: bool,
    override_rate_per_minute: float | None = None,
    notes: str | None = None,
    observed_at: str | None = None,
) -> ValidatedMeasurement:
    """Attach human semantic interpretation to a machine periodicity result."""

    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return ValidatedMeasurement(
        machine_measurement=MachineMeasurement(
            estimated_cycle_period_seconds=result.estimated_cycle_period_seconds,
            estimated_rate_per_minute=result.estimated_rate_per_minute,
            periodicity_score=result.periodicity_score,
        ),
        human_validation=HumanValidation(
            interpretation=interpretation,
            accepted=accepted,
            override_rate_per_minute=override_rate_per_minute,
            notes=notes,
        ),
        observed_at=observed_at,
    )
