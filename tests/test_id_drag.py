from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest

from connectathon.id_drag import (
    ID_DRAG_HUMAN_VERIFIED_CODE,
    ID_DRAG_IMAGE_CODE,
    build_id_drag_artifacts,
    encode_image,
)


PATIENT = {
    "patient_id": "PAT-IDDRAG-001",
    "patient_name": "PUBLIC, PAT",
    "date_of_birth": "1980-01-02",
    "sex": "F",
    "phone": "555-0100",
    "address": "1 Test Way",
    "city": "Lowell",
    "state": "MA",
    "zip": "01852",
}


def _component(observation: dict, code: str) -> dict:
    return next(
        component
        for component in observation.get("component", [])
        if component.get("code", {}).get("coding", [{}])[0].get("code") == code
    )


def test_encode_image_round_trip():
    raw = b"\x89PNG\r\n\x1a\nid-drag-test"
    encoded = encode_image(raw)

    assert base64.b64decode(encoded) == raw


@pytest.mark.parametrize("human_verified", [False, None, 0, "Yes"])
def test_build_rejects_anything_other_than_boolean_true(human_verified):
    with pytest.raises(ValueError, match="human must verify"):
        build_id_drag_artifacts(
            PATIENT,
            b"fake-image-bytes",
            "image/jpeg",
            human_verified=human_verified,
        )


def test_build_materializes_fhir_observation_with_base64_and_verification():
    raw = b"\x89PNG\r\n\x1a\nsynthetic-hand"
    when = datetime(2026, 9, 13, 22, 30, tzinfo=timezone.utc)

    result = build_id_drag_artifacts(
        PATIENT,
        raw,
        "image/png",
        human_verified=True,
        source_filename="hand.png",
        effective_datetime=when,
    )

    expected = base64.b64encode(raw).decode("ascii")
    observation = result["observation"]

    assert result["human_verified"] is True
    assert result["image_base64"] == expected
    assert observation["resourceType"] == "Observation"
    assert observation["status"] == "final"
    assert observation["code"]["coding"][0]["code"] == ID_DRAG_IMAGE_CODE
    assert observation["subject"]["reference"] == "Patient/PAT-IDDRAG-001"
    assert observation["valueString"] == expected
    assert observation["effectiveDateTime"] == "2026-09-13T22:30:00Z"

    verification = _component(observation, ID_DRAG_HUMAN_VERIFIED_CODE)
    assert verification["valueBoolean"] is True

    resources = [entry["resource"] for entry in result["bundle"]["entry"]]
    assert [resource["resourceType"] for resource in resources] == ["Patient", "Observation"]
    assert resources[1]["valueString"] == expected


def test_hl7_uses_ed_obx_for_image_and_separate_human_verified_obx():
    raw = b"jpeg-ish-test-image"
    expected = base64.b64encode(raw).decode("ascii")

    result = build_id_drag_artifacts(
        PATIENT,
        raw,
        "image/jpeg",
        human_verified=True,
        source_filename="hand.jpg",
    )
    hl7 = result["hl7"]

    assert "MSH|^~\\&|MEDILACRA|IDDRAG|" in hl7
    assert "PID|1||PAT-IDDRAG-001^^^MEDILACRA^MR||PUBLIC^PAT||19800102|F" in hl7
    assert (
        "OBX|1|ED|IDDRAG-HAND-IMAGE^Hand identity image^99MEDILACRA||"
        f"^IM^JPEG^Base64^{expected}||||||F"
    ) in hl7
    assert (
        "OBX|2|ID|IDDRAG-HUMAN-VERIFIED^Human verified^99MEDILACRA||Y||||||F"
        in hl7
    )


def test_png_maps_to_png_ed_subtype():
    result = build_id_drag_artifacts(
        PATIENT,
        b"png-test-image",
        "image/png",
        human_verified=True,
    )

    assert "^IM^PNG^Base64^" in result["hl7"]
    assert result["content_type"] == "image/png"


def test_unsupported_image_type_is_rejected():
    with pytest.raises(ValueError, match="JPEG or PNG"):
        build_id_drag_artifacts(
            PATIENT,
            b"gif-data",
            "image/gif",
            human_verified=True,
        )
