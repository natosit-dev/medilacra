from __future__ import annotations

import json

from profiles.hl7_interface_profile import (
    analyze_hl7,
    build_interface_record,
    extract_targets,
    message_semantics,
)
from profiles.site_profile import (
    generate_preview,
    load_profile,
    normalize_profile,
    save_profile,
)


def _segment(name: str, field_count: int, values: dict[int, str]) -> str:
    fields = [""] * field_count
    for field_number, value in values.items():
        fields[field_number - 1] = value
    return name + "|" + "|".join(fields)


def _message(
    *,
    trigger: str,
    structure: str,
    mrn: str,
    authority: str,
    dob: str,
    pv1_44: str,
) -> str:
    msh = (
        "MSH|^~\\&|SRC|FAC|DEST|DESTFAC|20261011210000||"
        f"ADT^{trigger}^{structure}|CTRL-{trigger}-{mrn}|P|2.5"
    )
    pid = _segment(
        "PID",
        22,
        {
            1: "1",
            3: f"{mrn}^^^{authority}",
            5: "TEST^PATIENT",
            7: dob,
        },
    )
    pv1 = _segment(
        "PV1",
        50,
        {
            1: "1",
            2: "I",
            3: "UNIT^101^A^FAC",
            44: pv1_44,
        },
    )
    return "\r".join([msh, pid, pv1])


def test_msh_9_uses_hl7_msh_numbering_not_generic_pipe_indexing():
    message = _message(
        trigger="A01",
        structure="ADT_A01",
        mrn="MRN1",
        authority="HOSP",
        dob="19800102",
        pv1_44="20261011100000",
    )

    assert message_semantics(message) == {
        "message_code": "ADT",
        "trigger_event": "A01",
        "root_schema": "ADT_A01",
    }


def test_basic_profile_targets_extract_exact_requested_fields():
    message = _message(
        trigger="A01",
        structure="ADT_A01",
        mrn="123456",
        authority="HOSPITAL-A",
        dob="19791231",
        pv1_44="20261011153000",
    )

    assert extract_targets(message) == {
        "mrn": "123456",
        "assigning_authority": "HOSPITAL-A",
        "date_of_birth": "19791231",
        "pv1_44": "20261011153000",
    }


def test_analyzer_groups_by_exact_msh_triplet_and_resolves_root_schema():
    text = "\n\n".join(
        [
            _message(
                trigger="A01",
                structure="ADT_A01",
                mrn="A1",
                authority="AA",
                dob="19800101",
                pv1_44="20261011080000",
            ),
            _message(
                trigger="A01",
                structure="ADT_A01",
                mrn="A2",
                authority="AA",
                dob="19810202",
                pv1_44="20261011090000",
            ),
            _message(
                trigger="A08",
                structure="ADT_A01",
                mrn="A3",
                authority="AA",
                dob="19820303",
                pv1_44="20261010120000",
            ),
        ]
    )

    analysis = analyze_hl7(text)

    assert analysis["message_count"] == 3
    assert analysis["group_count"] == 2

    groups = {group["signature"]: group for group in analysis["groups"]}
    assert set(groups) == {"ADT^A01^ADT_A01", "ADT^A08^ADT_A01"}
    assert groups["ADT^A01^ADT_A01"]["message_count"] == 2
    assert groups["ADT^A08^ADT_A01"]["message_count"] == 1
    assert groups["ADT^A01^ADT_A01"]["schema_resolution"]["resolved"] is True
    assert groups["ADT^A08^ADT_A01"]["schema_resolution"]["resolved"] is True


def test_pv1_44_verification_is_scoped_to_message_semantics():
    text = "\n\n".join(
        [
            _message(
                trigger="A01",
                structure="ADT_A01",
                mrn="A1",
                authority="AA",
                dob="19800101",
                pv1_44="20261011080000",
            ),
            _message(
                trigger="A08",
                structure="ADT_A01",
                mrn="A2",
                authority="AA",
                dob="19800101",
                pv1_44="",
            ),
        ]
    )

    analysis = analyze_hl7(text)
    groups = {group["signature"]: group for group in analysis["groups"]}

    assert groups["ADT^A01^ADT_A01"]["fields"]["pv1_44"]["coverage_pct"] == 100.0
    assert groups["ADT^A08^ADT_A01"]["fields"]["pv1_44"]["coverage_pct"] == 0.0


def test_persisted_interface_record_drops_examples_and_raw_messages():
    analysis = analyze_hl7(
        _message(
            trigger="A01",
            structure="ADT_A01",
            mrn="SECRET-MRN",
            authority="SECRET-AUTH",
            dob="19800101",
            pv1_44="20261011080000",
        )
    )
    record = build_interface_record(
        analysis["groups"][0],
        pv1_44_meaning="Admission date/time",
    )

    serialized = json.dumps(record)
    assert "SECRET-MRN" not in serialized
    assert "SECRET-AUTH" not in serialized
    assert "examples" not in serialized
    assert record["mappings"]["pv1_44"]["transaction_dictionary_message"] == (
        "Admission date/time"
    )


def test_new_profile_saves_json_and_reloads_without_losing_interface(tmp_path):
    profile = normalize_profile(
        {
            "profile_name": "Test Hospital",
            "facilities": [],
            "departments": [],
            "visit_mix": {},
            "routing": {},
            "interfaces": {
                "ADT^A01^ADT_A01": {
                    "message_code": "ADT",
                    "trigger_event": "A01",
                    "root_schema": "ADT_A01",
                }
            },
        }
    )

    filename = save_profile(profile, profile_dir=tmp_path)
    assert filename == "Test_Hospital.json"

    reloaded = load_profile(filename, profile_dir=tmp_path)
    assert reloaded["interfaces"] == profile["interfaces"]
    assert reloaded["profile_name"] == "Test Hospital"


def test_existing_site_probability_shape_still_drives_preview():
    profile = normalize_profile(
        {
            "profile_name": "One Route",
            "facilities": [
                {
                    "facility_code": "FAC",
                    "locations": [
                        {
                            "location_code": "ED1",
                            "location_type": "ED",
                            "weight": 1,
                            "room_format": "",
                            "bed_format": "",
                            "beds_per_room": 0,
                        }
                    ],
                }
            ],
            "departments": [
                {
                    "facility_code": "FAC",
                    "department_code": "ED",
                    "hospital_service": "EMERGENCY",
                }
            ],
            "visit_mix": {
                "IP": 0,
                "OP": 0,
                "ED": 100,
                "OBS": 0,
                "AS": 0,
                "CL": 0,
            },
            "routing": {
                "ED": {
                    "location_types": {"ED": 100},
                    "default_department_code": "ED",
                }
            },
        }
    )

    rows = generate_preview(profile, n=3, seed=43)

    assert len(rows) == 3
    assert {row["visit_class"] for row in rows} == {"ED"}
    assert {row["pv1_2"] for row in rows} == {"E"}
    assert {row["facility_code"] for row in rows} == {"FAC"}
    assert {row["hospital_service"] for row in rows} == {"EMERGENCY"}
