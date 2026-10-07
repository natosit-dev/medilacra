from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from payer.models import (
    BenefitPlan,
    EligibilityResponse,
    EnrollmentRecord,
    MemberRecord,
)

from .eligibility_r4 import (
    FHIR_RELEASE,
    FHIR_VERSION,
    build_clinical_coverage,
    build_clinical_patient,
    build_coverage_eligibility_request,
    build_coverage_eligibility_response,
    build_organization,
    build_payer_coverage,
    build_payer_patient,
    build_request_bundle,
    build_response_bundle,
)


DEFAULT_REQUESTER_ID = "MEDILACRA01"
DEFAULT_REQUESTER_NAME = "MEDILACRA CLINIC"


@dataclass(frozen=True)
class FHIREligibilityArtifacts:
    encounter_id: str
    exchange_id: str
    request_bundle: dict[str, Any]
    response_bundle: dict[str, Any]


def generate_fhir_eligibility_artifacts(
    *,
    patient,
    coverage_profile,
    inquiry,
    response: EligibilityResponse,
    exchange_identity,
    run_at: datetime,
    payer_member: MemberRecord,
    payer_enrollment: EnrollmentRecord,
    payer_plan: BenefitPlan,
    requester_id: str = DEFAULT_REQUESTER_ID,
    requester_name: str = DEFAULT_REQUESTER_NAME,
    encounter_id: str,
) -> FHIREligibilityArtifacts:
    """
    Project one synthetic eligibility event directly into FHIR R4 4.0.1.

    This function consumes clinical/payer reality plus the shared semantic
    inquiry/response. It does not parse or inspect X12.
    """
    clinical_patient = build_clinical_patient(patient)

    requester = build_organization(
        role="requester",
        source_id=requester_id,
        name=requester_name,
    )
    payer = build_organization(
        role="payer",
        source_id=str(coverage_profile.payer_id),
        name=str(coverage_profile.payer_name),
    )

    employer = None
    if (
        getattr(coverage_profile, "employer_id", "")
        or getattr(coverage_profile, "employer_name", "")
    ):
        employer = build_organization(
            role="employer",
            source_id=str(
                getattr(coverage_profile, "employer_id", "")
                or getattr(coverage_profile, "employer_name", "")
            ),
            name=str(
                getattr(coverage_profile, "employer_name", "")
                or getattr(coverage_profile, "employer_id", "")
            ),
        )

    clinical_coverage = build_clinical_coverage(
        coverage_profile,
        patient=clinical_patient,
        payer=payer,
        employer=employer,
    )

    request = build_coverage_eligibility_request(
        inquiry=inquiry,
        exchange_identity=exchange_identity,
        run_at=run_at,
        patient=clinical_patient,
        coverage=clinical_coverage,
        requester=requester,
        payer=payer,
    )

    request_bundle = build_request_bundle(
        request=request,
        clinical_patient=clinical_patient,
        clinical_coverage=clinical_coverage,
        requester=requester,
        payer=payer,
        employer=employer,
        exchange_identity=exchange_identity,
    )

    payer_patient = build_payer_patient(payer_member)
    payer_coverage = build_payer_coverage(
        member=payer_member,
        enrollment=payer_enrollment,
        plan=payer_plan,
        patient=payer_patient,
        payer=payer,
    )

    response_resource = build_coverage_eligibility_response(
        response=response,
        inquiry=inquiry,
        exchange_identity=exchange_identity,
        run_at=run_at,
        patient=payer_patient,
        coverage=payer_coverage,
        requester=requester,
        payer=payer,
        request=request,
    )

    response_bundle = build_response_bundle(
        response_resource=response_resource,
        request=request,
        clinical_patient=clinical_patient,
        clinical_coverage=clinical_coverage,
        payer_patient=payer_patient,
        payer_coverage=payer_coverage,
        requester=requester,
        payer=payer,
        employer=employer,
        exchange_identity=exchange_identity,
    )

    return FHIREligibilityArtifacts(
        encounter_id=str(encounter_id),
        exchange_id=str(exchange_identity.exchange_id),
        request_bundle=request_bundle,
        response_bundle=response_bundle,
    )


def write_fhir_eligibility_artifacts(
    artifacts: FHIREligibilityArtifacts,
    *,
    out_dir: str,
    run_ts: str,
    per_encounter: bool,
    safe_encounter: str,
) -> dict[str, str]:
    """
    Write one request/response bundle pair.

    Per-encounter mode writes pretty JSON files. Bulk mode appends one compact
    Bundle JSON object per NDJSON line. This is MediLacra packaging, not FHIR
    Bulk Data IG output.
    """
    os.makedirs(out_dir, exist_ok=True)

    prefix = f"FHIR_{FHIR_RELEASE}_{FHIR_VERSION}"

    if per_encounter:
        paths = {
            "FHIR_ELIGIBILITY_REQUEST": os.path.join(
                out_dir,
                (
                    f"{prefix}_CoverageEligibilityRequest_"
                    f"{safe_encounter}_{run_ts}.json"
                ),
            ),
            "FHIR_ELIGIBILITY_RESPONSE": os.path.join(
                out_dir,
                (
                    f"{prefix}_CoverageEligibilityResponse_"
                    f"{safe_encounter}_{run_ts}.json"
                ),
            ),
        }
        payloads = {
            "FHIR_ELIGIBILITY_REQUEST": artifacts.request_bundle,
            "FHIR_ELIGIBILITY_RESPONSE": artifacts.response_bundle,
        }

        for name, path in paths.items():
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    payloads[name],
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")

        return paths

    paths = {
        "FHIR_ELIGIBILITY_REQUEST": os.path.join(
            out_dir,
            (
                f"{prefix}_CoverageEligibilityRequest_"
                f"{run_ts}.ndjson"
            ),
        ),
        "FHIR_ELIGIBILITY_RESPONSE": os.path.join(
            out_dir,
            (
                f"{prefix}_CoverageEligibilityResponse_"
                f"{run_ts}.ndjson"
            ),
        ),
    }
    payloads = {
        "FHIR_ELIGIBILITY_REQUEST": artifacts.request_bundle,
        "FHIR_ELIGIBILITY_RESPONSE": artifacts.response_bundle,
    }

    for name, path in paths.items():
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    payloads[name],
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            handle.write("\n")

    return paths
