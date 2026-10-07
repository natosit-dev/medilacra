"""FHIR projection utilities for MediLacra."""

from .eligibility_generation import (
    FHIREligibilityArtifacts,
    generate_fhir_eligibility_artifacts,
    write_fhir_eligibility_artifacts,
)

__all__ = [
    "FHIREligibilityArtifacts",
    "generate_fhir_eligibility_artifacts",
    "write_fhir_eligibility_artifacts",
]
