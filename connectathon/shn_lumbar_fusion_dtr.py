from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from connectathon.shn_lumbar_fusion import build_lumbar_fusion_reality
from connectathon.shn_medilacra_crd import (
    SHN_ROUTE_00301,
    build_crd_order_sign_request,
)


DTR_QPACKAGE_INPUT_PROFILE = (
    "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/"
    "dtr-qpackage-input-parameters"
)
CRD_COVERAGE_INFORMATION = (
    "http://hl7.org/fhir/us/davinci-crd/StructureDefinition/"
    "ext-coverage-information"
)


def extract_questionnaire_canonical(crd_response: dict[str, Any]) -> str:
    """Extract the DTR questionnaire canonical from a CRD systemAction response."""
    canonicals: list[str] = []

    for action in crd_response.get("systemActions", []):
        resource = action.get("resource") or {}
        for extension in resource.get("extension", []):
            if extension.get("url") != CRD_COVERAGE_INFORMATION:
                continue
            for child in extension.get("extension", []):
                if child.get("url") == "questionnaire" and child.get("valueCanonical"):
                    canonicals.append(child["valueCanonical"])

    unique = list(dict.fromkeys(canonicals))
    if not unique:
        raise ValueError("CRD response contains no questionnaire canonical")
    if len(unique) != 1:
        raise ValueError(
            "CRD response contains multiple questionnaire canonicals: "
            + ", ".join(unique)
        )
    return unique[0]


def build_lumbar_fusion_dtr_request(
    crd_response: dict[str, Any],
    seed: int = 43,
    payer_route: str = SHN_ROUTE_00301,
) -> dict[str, Any]:
    """Build DTR package input from MediLacra reality + the live CRD answer."""
    reality = build_lumbar_fusion_reality(seed)
    crd_request = build_crd_order_sign_request(
        reality,
        payer_route=payer_route,
    )
    canonical = extract_questionnaire_canonical(crd_response)

    patient = copy.deepcopy(crd_request["prefetch"]["patient"])
    coverage = copy.deepcopy(crd_request["prefetch"]["coverage"])

    return {
        "resourceType": "Parameters",
        "meta": {"profile": [DTR_QPACKAGE_INPUT_PROFILE]},
        "parameter": [
            {
                "name": "coverage",
                "resource": coverage,
            },
            {
                "name": "referenced",
                "resource": patient,
            },
            {
                "name": "questionnaire",
                "valueCanonical": canonical,
            },
        ],
    }


def dtr_expected_invariants(
    crd_response: dict[str, Any],
    seed: int = 43,
    payer_route: str = SHN_ROUTE_00301,
) -> dict[str, Any]:
    reality = build_lumbar_fusion_reality(seed)
    canonical = extract_questionnaire_canonical(crd_response)
    return {
        "case_id": reality.case_id,
        "projection": "live CRD answer + MediLacra reality -> DTR questionnaire package request",
        "patient_reference": f"Patient/{reality.patient.patient_id}",
        "coverage_reference": f"Coverage/{reality.coverage_id}",
        "service_request_reference": f"ServiceRequest/{reality.service_request_id}",
        "payer_route": payer_route,
        "questionnaire_from_crd": canonical,
        "meaning": [
            "DTR is about the same MediLacra patient as CRD",
            "DTR carries the same MediLacra coverage used to route CRD",
            "the questionnaire canonical is taken from SHN's live CRD answer",
            "MediLacra does not invent or hardcode the payer-selected questionnaire",
        ],
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_dtr_case(
    request: dict[str, Any],
    invariants: dict[str, Any],
    output_dir: str | Path,
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "dtr_request.json").write_bytes(_json_bytes(request))
    (path / "dtr_expected_invariants.json").write_bytes(_json_bytes(invariants))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the MediLacra lumbar-fusion DTR request from a live CRD response"
        )
    )
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--payer-route", default=SHN_ROUTE_00301)
    parser.add_argument("--crd-response", required=True)
    parser.add_argument(
        "--out",
        default="connectathon/results/shn_lumbar_fusion",
    )
    args = parser.parse_args()

    response = json.loads(Path(args.crd_response).read_text())
    request = build_lumbar_fusion_dtr_request(
        response,
        seed=args.seed,
        payer_route=args.payer_route,
    )
    invariants = dtr_expected_invariants(
        response,
        seed=args.seed,
        payer_route=args.payer_route,
    )
    reality = build_lumbar_fusion_reality(args.seed)
    out = write_dtr_case(
        request,
        invariants,
        Path(args.out) / reality.case_id,
    )
    print(out / "dtr_request.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
