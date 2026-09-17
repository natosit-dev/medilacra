from __future__ import annotations

import io
import zipfile

from connectathon.gravity_caregiver import build_artifact_files, build_artifact_zip
from connectathon.gravity_hl7v2 import build_caregiver_oru
from connectathon.gravity_questionnaire import QUESTIONNAIRE_VERSION, build_questionnaire
from connectathon.gravity_response import build_questionnaire_response


PATIENT = {
    "patient_id": "PAT-GRAVITY-001",
    "mrn": "MRN-GRAVITY-001",
    "patient_name": "CAREGIVER, CASEY",
    "date_of_birth": "1982-03-14",
    "sex": "F",
    "phone": "555-0100",
    "address": "1 Test Way",
    "city": "Lowell",
    "state": "MA",
    "zip": "01852",
}

HAPPY_INPUT = {
    "sleep-hours": "6.5",
    "pain-score": 4,
    "phq2-interest": "LA6569-3",
    "phq2-depressed": "LA6568-5",
    "heart-rate": "82",
    "medication-status": True,
    "medications": [
        {
            "name": "lisinopril",
            "dose_value": "10",
            "dose_unit": "mg",
            "route": "oral",
            "frequency": "daily",
        }
    ],
    "feeling-today": "Tired, but pretty steady today.",
    "life-today": "My mom has an appointment and work is busy.",
}


def _response(raw_input=HAPPY_INPUT, declined=None):
    return build_questionnaire_response(
        PATIENT["patient_id"],
        raw_input,
        declined=set(declined or []),
        response_id="gravity-v2-test-response",
        authored="2026-09-08T22:00:00+00:00",
    )


def _segments(message: str, name: str) -> list[list[str]]:
    return [segment.split("|") for segment in message.strip("\r").split("\r") if segment.startswith(f"{name}|")]


def test_caregiver_oru_has_no_invented_encounter_or_order_segments():
    message = build_caregiver_oru(PATIENT, _response(), control_id="CG-TEST-1")
    segment_names = [segment.split("|", 1)[0] for segment in message.strip("\r").split("\r")]

    assert segment_names[:3] == ["MSH", "PID", "OBR"]
    assert "PV1" not in segment_names
    assert "ORC" not in segment_names
    assert "RXE" not in segment_names
    assert "RXA" not in segment_names

    msh = _segments(message, "MSH")[0]
    assert msh[8] == "ORU^R01^ORU_R01"
    assert msh[9] == "CG-TEST-1"
    assert msh[11] == "2.5"


def test_caregiver_oru_projects_numeric_coded_medication_and_journal_answers():
    message = build_caregiver_oru(PATIENT, _response())
    obxs = _segments(message, "OBX")
    by_code = {obx[3].split("^")[0]: obx for obx in obxs}

    assert by_code["sleep-hours-24h"][2] == "NM"
    assert by_code["sleep-hours-24h"][5] == "6.5"
    assert by_code["sleep-hours-24h"][6] == "h^hour^UCUM"

    assert by_code["72514-3"][5] == "4"
    assert by_code["44250-9"][2] == "CWE"
    assert by_code["44250-9"][5] == "LA6569-3^Several days^LN"
    assert by_code["55757-9"][5] == "1"
    assert by_code["8867-4"][5] == "82.0"
    assert by_code["8867-4"][6] == "/min^beats/minute^UCUM"

    assert by_code["medication-status"][5] == "Y^Yes^HL70136"
    assert by_code["medication-name"][4] == "1"
    assert by_code["medication-name"][5] == "lisinopril"
    assert by_code["medication-dose-value"][5] == "10.0"
    assert by_code["medication-dose-unit"][5] == "mg"
    assert by_code["medication-route"][5] == "oral"
    assert by_code["medication-frequency"][5] == "daily"

    assert by_code["feeling-today"][5] == HAPPY_INPUT["feeling-today"]
    assert by_code["life-today"][5] == HAPPY_INPUT["life-today"]


def test_declined_answer_is_preserved_as_explicit_local_absent_reason():
    raw = dict(HAPPY_INPUT)
    raw["sleep-hours"] = ""
    message = build_caregiver_oru(PATIENT, _response(raw, declined={"sleep-hours"}))
    obxs = _segments(message, "OBX")

    sleep = [obx for obx in obxs if obx[3].startswith("sleep-hours-24h^")]
    absent = [obx for obx in obxs if obx[3].startswith("sleep-hours-24h-data-absent-reason^")]

    assert sleep == []
    assert len(absent) == 1
    assert absent[0][2] == "CWE"
    assert absent[0][5] == "asked-declined^Asked but declined^99MEDILACRA"


def test_hl7_special_characters_are_escaped_in_free_text():
    raw = dict(HAPPY_INPUT)
    raw["feeling-today"] = "Tired | wired ^ still here & okay ~ mostly \\ yep"
    message = build_caregiver_oru(PATIENT, _response(raw))
    feeling = next(obx for obx in _segments(message, "OBX") if obx[3].startswith("feeling-today^"))

    assert feeling[5] == "Tired \\F\\ wired \\S\\ still here \\T\\ okay \\R\\ mostly \\E\\ yep"


def test_artifact_zip_can_package_hl7_alongside_fhir_json():
    response = _response()
    message = build_caregiver_oru(PATIENT, response)
    result = {
        "questionnaire": build_questionnaire(),
        "questionnaire_response": response,
        "bundle": {"resourceType": "Bundle", "type": "collection", "entry": []},
        "hl7v2": message,
        "quality": {"status": "PASS"},
        "cleanup": {},
    }

    files = build_artifact_files(result)
    expected_hl7 = "caregiver_health_oru_r01.hl7"
    assert expected_hl7 in files
    assert files[expected_hl7].decode("utf-8") == message
    assert f"caregiver_health_baseline_questionnaire_v{QUESTIONNAIRE_VERSION}.json" in files

    with zipfile.ZipFile(io.BytesIO(build_artifact_zip(result)), "r") as archive:
        assert expected_hl7 in archive.namelist()
        assert archive.read(expected_hl7).decode("utf-8") == message
