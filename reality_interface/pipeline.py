from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fhir.fhir_convert_backend import convert_message_to_bundle

from .artifacts import RunArtifacts, create_run, write_json, write_manifest
from .audio import AudioSignal, load_wav
from .binding import ClinicalBinding, bind_to_synthetic_context
from .hl7 import build_reality_oru
from .periodicity import PeriodicityResult, analyze_periodicity
from .validation import ValidatedMeasurement, validate_measurement


@dataclass(frozen=True)
class AnalysisRun:
    artifacts: RunArtifacts
    audio: AudioSignal
    measurement: PeriodicityResult


@dataclass(frozen=True)
class FinalizedRun:
    analysis: AnalysisRun
    validated: ValidatedMeasurement
    clinical: ClinicalBinding
    hl7_message: str
    fhir_bundle: dict[str, Any]
    fhir_message_type: str


def analyze_source(
    source_path: str | Path,
    *,
    artifacts_root: str | Path = "artifacts/reality_interface",
    acquisition_band_hz: tuple[int, int] | None = (10, 300),
) -> AnalysisRun:
    """Persist a source WAV, analyze it, and write the initial manifest."""

    artifacts = create_run(source_path, artifacts_root=artifacts_root)
    audio = load_wav(artifacts.source_path)
    measurement = analyze_periodicity(audio)

    write_manifest(
        artifacts,
        source_metadata={
            "sample_rate_hz": audio.source_sample_rate_hz,
            "channels": audio.source_channels,
            "duration_seconds": audio.duration_seconds,
            "analysis_sample_rate_hz": audio.analysis_sample_rate_hz,
        },
        analysis={
            "estimated_cycle_period_seconds": measurement.estimated_cycle_period_seconds,
            "estimated_rate_per_minute": measurement.estimated_rate_per_minute,
            "periodicity_score": measurement.periodicity_score,
        },
        acquisition_band_hz=acquisition_band_hz,
    )

    return AnalysisRun(artifacts=artifacts, audio=audio, measurement=measurement)


def finalize_run(
    analysis: AnalysisRun,
    *,
    interpretation: str,
    accepted: bool,
    override_rate_per_minute: float | None = None,
    notes: str | None = None,
    observed_at: str | None = None,
    profile: dict[str, Any] | None = None,
) -> FinalizedRun:
    """Apply human validation, synthetic context, HL7, then FHIR projection."""

    validated = validate_measurement(
        analysis.measurement,
        interpretation=interpretation,
        accepted=accepted,
        override_rate_per_minute=override_rate_per_minute,
        notes=notes,
        observed_at=observed_at,
    )
    write_json(analysis.artifacts.validation_path, validated.model_dump())

    clinical = bind_to_synthetic_context(validated, profile=profile)
    hl7_message = build_reality_oru(
        clinical,
        source_filename=analysis.artifacts.source_filename,
        source_location=analysis.artifacts.source_location,
    )
    analysis.artifacts.hl7_path.write_text(hl7_message + "\n", encoding="utf-8")

    fhir_bundle, message_type = convert_message_to_bundle(hl7_message)
    write_json(analysis.artifacts.fhir_path, fhir_bundle)

    return FinalizedRun(
        analysis=analysis,
        validated=validated,
        clinical=clinical,
        hl7_message=hl7_message,
        fhir_bundle=fhir_bundle,
        fhir_message_type=message_type,
    )
