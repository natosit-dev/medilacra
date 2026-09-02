from __future__ import annotations

from connectathon.fhir_control import prepare_control_bundle
from connectathon.preflight import control_quality_gate, preflight_bundle


def _raw_message_bundle() -> dict:
    patient_id = "pat-123"
    encounter_id = "enc-123"
    return {
        "resourceType": "Bundle",
        "type": "message",
        "id": "bundle-raw",
        "entry": [
            {
                "resource": {
                    "resourceType": "MessageHeader",
                    "id": "msg-123",
                    "source": {"name": "MEDILACRA"},
                }
            },
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": patient_id,
                    "identifier": [{"system": "urn:mrn", "value": "MRN1"}],
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": encounter_id,
                    "status": "finished",
                    "class": {"code": "O"},
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "extension": [
                        {
                            "url": "http://example.org/fhir/StructureDefinition/hl7v2-location",
                            "extension": [
                                {"url": "pointOfCare", "valueString": "RAD"},
                                {"url": "room", "valueString": ""},
                            ],
                        }
                    ],
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-wbc",
                    "status": "final",
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "encounter": {"reference": f"Encounter/{encounter_id}"},
                    "code": {"coding": [{"system": "http://loinc.org", "code": "6690-2", "display": "WBC"}]},
                    "valueQuantity": {"value": 7.8, "unit": "3/uL"},
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-gender",
                    "status": "final",
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "code": {"coding": [{"system": "http://loinc.org", "code": "76691-5"}]},
                    "effectiveDateTime": "2026-09-02T10:38:14",
                    "valueString": "446151000124109^Male^SCT",
                }
            },
        ],
    }


def test_prepare_control_bundle_removes_transport_and_repairs_known_semantics():
    bundle, report = prepare_control_bundle(_raw_message_bundle())

    assert bundle["type"] == "collection"
    assert report["message_headers_removed"] == 1
    assert all(entry.get("fullUrl", "").startswith("urn:uuid:") for entry in bundle["entry"])
    assert not any(entry["resource"]["resourceType"] == "MessageHeader" for entry in bundle["entry"])

    encounter = next(entry["resource"] for entry in bundle["entry"] if entry["resource"]["resourceType"] == "Encounter")
    assert encounter["class"]["code"] == "AMB"
    assert encounter["class"]["system"] == "http://terminology.hl7.org/CodeSystem/v3-ActCode"
    assert len(encounter["extension"][0]["extension"]) == 1
    assert encounter["subject"]["reference"].startswith("urn:uuid:")

    wbc = next(entry["resource"] for entry in bundle["entry"] if entry["resource"].get("id") == "obs-wbc")
    assert wbc["valueQuantity"]["system"] == "http://unitsofmeasure.org"
    assert wbc["valueQuantity"]["code"] == "10*3/uL"

    gender = next(entry["resource"] for entry in bundle["entry"] if entry["resource"].get("id") == "obs-gender")
    assert "valueString" not in gender
    assert gender["valueCodeableConcept"]["coding"][0]["system"] == "http://snomed.info/sct"
    assert gender["effectiveDateTime"].endswith("Z")

    assert preflight_bundle(bundle)["status"] == "PASS"
    assert control_quality_gate(bundle)["status"] == "PASS"


def test_control_quality_gate_rejects_implausible_lipid_control():
    bundle, _ = prepare_control_bundle(_raw_message_bundle())
    patient_ref = bundle["entry"][0]["fullUrl"]

    def observation(obs_id: str, code: str, value: float) -> dict:
        return {
            "fullUrl": f"urn:uuid:00000000-0000-4000-8000-{obs_id[-12:].rjust(12, '0')}",
            "resource": {
                "resourceType": "Observation",
                "id": obs_id,
                "status": "final",
                "subject": {"reference": patient_ref},
                "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
                "valueQuantity": {
                    "value": value,
                    "unit": "mg/dL",
                    "system": "http://unitsofmeasure.org",
                    "code": "mg/dL",
                },
            },
        }

    bundle["entry"].extend(
        [
            observation("obs-total0001", "2093-3", 120.0),
            observation("obs-ldl000001", "13457-7", 140.0),
            observation("obs-hdl000001", "2085-9", 45.0),
        ]
    )

    gate = control_quality_gate(bundle)
    lipid = next(row for row in gate["checks"] if row["check"] == "lipid.plausibility")
    assert lipid["status"] == "FAIL"
    assert gate["status"] == "FAIL"
