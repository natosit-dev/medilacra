from __future__ import annotations

import json
import zipfile
from io import BytesIO

from connectathon.shn_mvp0 import (
    DTR_QR_CONTEXT,
    DTR_QR_COVERAGE,
    SHN_CONTRACT,
    SHN_FROM,
    SHN_TO,
    build_case,
    case_zip_bytes,
)


def _refs_for_url(resource: dict, url: str) -> list[str]:
    refs = []
    for ext in resource.get("extension", []):
        if ext.get("url") == url:
            ref = (ext.get("valueReference") or {}).get("reference")
            if ref:
                refs.append(ref)
    return refs


def test_shn_mvp0_case_is_coherent():
    case = build_case(seed=43)
    reality = case["reality"]
    qr = case["dtr_input"]

    rels = {(r["predicate"], r["object"]) for r in reality["relationships"]}
    coverage_ref = next(obj for pred, obj in rels if pred == "hasCoverage")
    order_ref = next(obj for pred, obj in rels if pred == "hasOrder")
    patient_ref = next(r["subject"] for r in reality["relationships"] if r["predicate"] == "hasCoverage")

    assert qr["subject"]["reference"] == patient_ref
    assert _refs_for_url(qr, DTR_QR_CONTEXT) == [coverage_ref, order_ref]
    assert _refs_for_url(qr, DTR_QR_COVERAGE) == []


def test_shn_request_wraps_dtr_21_payload():
    case = build_case(seed=43)
    request = case["shn_request"]

    assert request["contract"] == SHN_CONTRACT
    assert request["from"] == SHN_FROM
    assert request["to"] == SHN_TO
    assert request["payload"] == case["dtr_input"]


def test_case_build_is_deterministic_for_seed():
    assert build_case(seed=43) == build_case(seed=43)
    assert build_case(seed=43) != build_case(seed=44)


def test_case_zip_contains_handoff_artifacts():
    case = build_case(seed=43)
    archive = zipfile.ZipFile(BytesIO(case_zip_bytes(case)))
    names = set(archive.namelist())

    assert "reality.json" in names
    assert "dtr_2_1.fhir.json" in names
    assert "shn_transform_request.json" in names
    assert "expected_invariants.json" in names
    assert "supporting/patient.fhir.json" in names
    assert "supporting/coverage.fhir.json" in names
    assert "supporting/service_request.fhir.json" in names

    request = json.loads(archive.read("shn_transform_request.json"))
    assert request["payload"]["resourceType"] == "QuestionnaireResponse"
