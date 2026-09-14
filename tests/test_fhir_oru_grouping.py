from fhir.fhir_convert_backend import convert_oru, parse_hl7


HL7_TWO_REPORTS = "\n".join(
    [
        "MSH|^~\\&|MEDILACRA|TEST|FHIR|TEST|20260913200000||ORU^R01|CTRL1|P|2.5",
        "PID|1||TEST123^^^MRN||HILL^ALEXANDER||19511226|M",
        "PV1|1|O|RAD_DEPT1",
        "OBR|1|PLACER1|FILLER1|76705^Limited abdominal ultrasound (e.g., RUQ)^CPT",
        "OBX|1|TX|76705^Limited abdominal ultrasound (e.g., RUQ)^CPT||RUQ result 1||||||F",
        "OBX|2|TX|76705^Limited abdominal ultrasound (e.g., RUQ)^CPT||RUQ result 2||||||F",
        "OBX|3|TX|76705^Limited abdominal ultrasound (e.g., RUQ)^CPT||RUQ result 3||||||F",
        "OBX|4|TX|76705^Limited abdominal ultrasound (e.g., RUQ)^CPT||RUQ result 4||||||F",
        "OBX|5|TX|76705^Limited abdominal ultrasound (e.g., RUQ)^CPT||RUQ result 5||||||F",
        "OBX|6|TX|76705^Limited abdominal ultrasound (e.g., RUQ)^CPT||RUQ result 6||||||F",
        "OBR|2|PLACER2|FILLER2|76830^Transvaginal pelvic ultrasound^CPT",
        "OBX|1|TX|76830^Transvaginal pelvic ultrasound^CPT||Pelvic result 1||||||F",
        "OBX|2|TX|76830^Transvaginal pelvic ultrasound^CPT||Pelvic result 2||||||F",
        "OBX|3|TX|76830^Transvaginal pelvic ultrasound^CPT||Pelvic result 3||||||F",
        "OBX|4|TX|76830^Transvaginal pelvic ultrasound^CPT||Pelvic result 4||||||F",
        "OBX|5|TX|76830^Transvaginal pelvic ultrasound^CPT||Pelvic result 5||||||F",
        "OBX|6|TX|76830^Transvaginal pelvic ultrasound^CPT||Pelvic result 6||||||F",
    ]
)


def _resources(bundle, resource_type):
    return [
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == resource_type
    ]


def _code(resource):
    return resource["code"]["coding"][0]["code"]


def test_oru_preserves_obr_obx_result_grouping():
    bundle = convert_oru(parse_hl7(HL7_TWO_REPORTS))

    reports = _resources(bundle, "DiagnosticReport")
    observations = _resources(bundle, "Observation")

    assert len(reports) == 2
    assert len(observations) == 12

    reports_by_code = {_code(report): report for report in reports}
    observations_by_ref = {
        f"Observation/{observation['id']}": observation
        for observation in observations
    }

    assert set(reports_by_code) == {"76705", "76830"}

    ruq_refs = {
        result["reference"] for result in reports_by_code["76705"]["result"]
    }
    pelvic_refs = {
        result["reference"] for result in reports_by_code["76830"]["result"]
    }

    assert len(ruq_refs) == 6
    assert len(pelvic_refs) == 6
    assert ruq_refs.isdisjoint(pelvic_refs)
    assert ruq_refs | pelvic_refs == set(observations_by_ref)

    assert {_code(observations_by_ref[ref]) for ref in ruq_refs} == {"76705"}
    assert {_code(observations_by_ref[ref]) for ref in pelvic_refs} == {"76830"}


def test_oru_without_obr_keeps_legacy_generic_report_behavior():
    hl7 = "\n".join(
        [
            "MSH|^~\\&|MEDILACRA|TEST|FHIR|TEST|20260913200000||ORU^R01|CTRL2|P|2.5",
            "PID|1||TEST123^^^MRN||HILL^ALEXANDER||19511226|M",
            "OBX|1|TX|1234^Unscoped observation^99TEST||hello||||||F",
        ]
    )

    bundle = convert_oru(parse_hl7(hl7))
    reports = _resources(bundle, "DiagnosticReport")
    observations = _resources(bundle, "Observation")

    assert len(reports) == 1
    assert len(observations) == 1
    assert reports[0]["code"] == {"text": "Diagnostic Report"}
    assert reports[0]["result"] == [
        {"reference": f"Observation/{observations[0]['id']}"}
    ]
