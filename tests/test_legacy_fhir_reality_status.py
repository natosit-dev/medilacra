"""Legacy HL7 v2 -> FHIR converter must preserve event/result source meaning."""
from __future__ import annotations

from fhir.fhir_convert_backend import convert_message_to_bundle


def resources(bundle, kind):
    return [x["resource"] for x in bundle["entry"]
            if x["resource"]["resourceType"] == kind]


def _msh(event):
    return f"MSH|^~\\&|SYN|SENDER|APP|RECEIVER|20261008180000||{event}|CTRL|P|2.5"


def test_admission_cannot_become_finished_encounter():
    raw = "\r".join([
        _msh("ADT^A01"),
        "PID|1||PAT-1||TEST^JANE||19800101|F",
        "PV1|1|O|RAD1",
    ])
    bundle, _ = convert_message_to_bundle(raw)
    assert resources(bundle, "Encounter")[0]["status"] == "in-progress"


def test_discharge_can_become_finished_encounter():
    raw = "\r".join([
        _msh("ADT^A03"),
        "PID|1||PAT-1||TEST^JANE||19800101|F",
        "PV1|1|O|RAD1",
    ])
    bundle, _ = convert_message_to_bundle(raw)
    assert resources(bundle, "Encounter")[0]["status"] == "finished"


def test_observation_source_status_not_forced_final():
    raw = "\r".join([
        _msh("ORU^R01"),
        "PID|1||PAT-1||TEST^JANE||19800101|F",
        "OBR|1|||1234^SYNTHETIC PANEL^L",
        "OBX|1|TX|111^Sample^L|1|provisional||||||P",
        "OBX|2|TX|112^Sample^L|1|uncertain",
    ])
    bundle, _ = convert_message_to_bundle(raw)
    observations = resources(bundle, "Observation")
    assert [x["status"] for x in observations] == ["preliminary", "unknown"]
    assert resources(bundle, "DiagnosticReport")[0]["status"] == "unknown"


def test_oru_without_obr_does_not_invent_diagnostic_report():
    raw = "\r".join([
        _msh("ORU^R01"),
        "PID|1||PAT-1||TEST^JANE||19800101|F",
        "OBX|1|TX|111^Sample^L|1|Synthetic result||||||F",
    ])
    bundle, _ = convert_message_to_bundle(raw)
    assert not resources(bundle, "DiagnosticReport")
    assert resources(bundle, "Observation")[0]["status"] == "final"
