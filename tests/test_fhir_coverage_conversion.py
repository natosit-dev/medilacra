import json

import pytest

from fhir.fhir_convert_backend import (
    _is_fhir_resource_id,
    convert_message_to_bundle,
    detect_message_type,
    extract_coverage_context,
    parse_hl7,
)


ADT = "\r".join(
    [
        r"MSH|^~\&|FAKELAB|MEDILACRAHS|MLHS|STAGE|20261004122046||ADT^A01^ADT_A01|19|P|2.5|||AL|NE||UNICODE UTF-8",
        "EVN|A01|20260926111142||||20260926111142",
        "PID|1||RAD1054994||KELLEY^DEVIN||19490116|M||Asian|224 Stevens Mall^^Allenton^WI^53002||869-923-4470^PRN^PH~^NET^Internet^devin.kelley@fakermail.com||en^English^ISO639|M^Married^HL70002|||331-20-5428|||H^Hispanic or Latino^HL70189",
        "PV1|1|O|RAD_DEPT1||||P014552^WRIGHT^KAITLYN|REF493925^MUELLER^CHARLES||RAD||||SR|||||VN5614029278|||||||||||||||||02||||||||20260926111142|20260926151142|||||||ML749144^FIELDS^DOUGLAS",
        "GT1|1||KELLEY^DEVIN||||||||SEL^Self^HL70063|||||CVS Health Corporation||||1|||||||||CVS",
        "IN1|1|STANDARD_PPO^Standard PPO^L|KAISER|Kaiser Permanente||||GRP-CVS-398915|||CVS Health Corporation|20260101|20261231||PPO|KELLEY^DEVIN|SEL^Self^HL70063||||||||||||||||||||||||||||||||MEM-01374522",
        "IN2|||CVS^CVS Health Corporation",
    ]
)


DFT = "\r".join(
    [
        r"MSH|^~\&|FAKELAB|MEDILACRAHS|MLHS|STAGE|20261004122056||DFT^P03^DFT_P03|21|P|2.5|||AL|NE||UNICODE UTF-8",
        "EVN|P03|20260926111142||||20260926111142",
        "PID|1||RAD1054994||KELLEY^DEVIN||19490116|M||Asian|224 Stevens Mall^^Allenton^WI^53002||869-923-4470^PRN^PH~^NET^Internet^devin.kelley@fakermail.com||en^English^ISO639|M^Married^HL70002|||331-20-5428|||H^Hispanic or Latino^HL70189",
        "PV1|1|O|RAD_DEPT1||||P014552^WRIGHT^KAITLYN|REF493925^MUELLER^CHARLES||RAD||||SR|||||VN5614029278|||||||||||||||||02||||||||20260926111142|20260926151142|||||||ML749144^FIELDS^DOUGLAS",
        "FT1|1|6b202df7-8d8d-4bab-aeb2-d701365e30cc||20261004122046|20261004122046|CG|73610^Ankle X-ray, complete (3+ views)^CPT|Ankle X-ray, complete (3+ views)||1|288.81&USD|194.52&USD||STANDARD_PPO^Standard PPO^L|||PRO||M25.571^Pain in right ankle and joints of right foot^ICD-10-CM|PR183187^BURGESS^DONNA||194.52&USD|||73610^Ankle X-ray, complete (3+ views)^CPT",
        "GT1|1||KELLEY^DEVIN||||||||SEL^Self^HL70063|||||CVS Health Corporation||||1|||||||||CVS",
        "IN1|1|STANDARD_PPO^Standard PPO^L|KAISER|Kaiser Permanente||||GRP-CVS-398915|||CVS Health Corporation|20260101|20261231||PPO|KELLEY^DEVIN|SEL^Self^HL70063||||||||||||||||||||||||||||||||MEM-01374522",
        "IN2|||CVS^CVS Health Corporation",
    ]
)


ORU = "\r".join(
    [
        r"MSH|^~\&|FAKELAB|MEDILACRAHS|MLHS|STAGE|20261004122056||ORU^R01^ORU_R01|20|P|2.5|||AL|NE||UNICODE UTF-8",
        "PID|1||RAD1054994||KELLEY^DEVIN||19490116|M||Asian|224 Stevens Mall^^Allenton^WI^53002||869-923-4470^PRN^PH~^NET^Internet^devin.kelley@fakermail.com||en^English^ISO639|M^Married^HL70002|||331-20-5428|||H^Hispanic or Latino^HL70189",
        "PV1|1|O|RAD_DEPT1||||P014552^WRIGHT^KAITLYN|REF493925^MUELLER^CHARLES||RAD||||SR|||||VN5614029278|||||||||||||||||02||||||||20260926111142|20260926151142|||||||ML749144^FIELDS^DOUGLAS",
        "OBR|1|42b92903-2db7-43fb-85eb-ff8eda11fbc3|25c37c91-a0b3-4f00-9b19-2ee0abbfe411|73610^Ankle X-ray, complete (3+ views)^CPT|||20260926124251",
        "OBX|1|TX|73610^Ankle X-ray, complete (3+ views)^CPT|1|Impression: No radiographic evidence of fracture.||||||F|||20260926124251|MEDILACRAHS^DEPT1",
    ]
)


def _resources(bundle, resource_type):
    return [
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == resource_type
    ]


def _organization_by_role(bundle, role):
    target_system = f"urn:medilacra:{role}"
    for organization in _resources(bundle, "Organization"):
        for identifier in organization.get("identifier", []):
            if identifier.get("system") == target_system:
                return organization
    raise AssertionError(f"No {role} Organization found")


def _class_by_code(coverage, code):
    for item in coverage.get("class", []):
        codings = item.get("type", {}).get("coding", [])
        if any(coding.get("code") == code for coding in codings):
            return item
    raise AssertionError(f"No Coverage.class[{code}] found")


def _rewrite_segment(message, segment_name, replacements):
    lines = message.split("\r")
    rewritten = []

    for line in lines:
        if line.startswith(f"{segment_name}|"):
            parts = line.split("|")
            for field_number, value in replacements.items():
                while len(parts) <= field_number:
                    parts.append("")
                parts[field_number] = value
            line = "|".join(parts)
        rewritten.append(line)

    return "\r".join(rewritten)


def _drop_segment(message, segment_name):
    return "\r".join(
        line
        for line in message.split("\r")
        if not line.startswith(f"{segment_name}|")
    )


def _assert_referential_closure(bundle):
    resources = [
        entry["resource"]
        for entry in bundle["entry"]
    ]
    available = {
        f"{resource['resourceType']}/{resource['id']}"
        for resource in resources
        if resource.get("id")
    }

    references = []

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "reference" and isinstance(child, str):
                    references.append(child)
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for resource in resources:
        walk(resource)

    assert references
    assert set(references).issubset(available)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (ADT, "ADT^A01"),
        (DFT, "DFT^P03"),
        (ORU, "ORU^R01"),
    ],
)
def test_msh_specific_indexing_detects_message_type(message, expected):
    parsed = parse_hl7(message)

    assert detect_message_type(parsed) == expected

    bundle, message_type = convert_message_to_bundle(message)
    assert message_type == expected

    header = _resources(bundle, "MessageHeader")[0]
    assert header["eventCoding"]["code"] == expected
    assert header["source"]["name"] == "FAKELAB|MEDILACRAHS"
    assert header["destination"][0]["name"] == "MLHS|STAGE"


def test_extract_coverage_context_coalesces_gt1_in1_in2():
    context = extract_coverage_context(
        parse_hl7(ADT)
    )

    assert context is not None
    assert context["employer_id"] == "CVS"
    assert context["employer_name"] == "CVS Health Corporation"
    assert context["payer_id"] == "KAISER"
    assert context["payer_name"] == "Kaiser Permanente"
    assert context["plan_id"] == "STANDARD_PPO"
    assert context["plan_name"] == "Standard PPO"
    assert context["plan_type"] == "PPO"
    assert context["group_number"] == "GRP-CVS-398915"
    assert context["member_id"] == "MEM-01374522"
    assert context["effective_start"] == "20260101"
    assert context["effective_end"] == "20261231"
    assert context["patient_is_subscriber"] is True
    assert context["gt1_employment_status"] == "1"
    assert context["conflicts"] == []


def test_employer_falls_back_to_gt1_when_in2_is_absent():
    context = extract_coverage_context(
        parse_hl7(
            _drop_segment(
                ADT,
                "IN2",
            )
        )
    )

    assert context["employer_id"] == "CVS"
    assert context["employer_name"] == "CVS Health Corporation"


def test_employer_conflict_is_detectable_with_deterministic_precedence():
    mismatched = _rewrite_segment(
        ADT,
        "IN2",
        {
            3: "OTHER_EMPLOYER^Different Corporation",
        },
    )

    context = extract_coverage_context(
        parse_hl7(mismatched)
    )

    assert context["employer_id"] == "OTHER_EMPLOYER"
    assert context["employer_name"] == "Different Corporation"
    assert "employer_id" in context["conflicts"]
    assert "employer_name" in context["conflicts"]


def test_adt_materializes_one_coherent_coverage_graph():
    bundle, message_type = convert_message_to_bundle(ADT)

    assert message_type == "ADT^A01"

    patients = _resources(bundle, "Patient")
    coverages = _resources(bundle, "Coverage")
    organizations = _resources(bundle, "Organization")

    assert len(patients) == 1
    assert len(coverages) == 1
    assert len(organizations) == 2

    patient = patients[0]
    coverage = coverages[0]
    employer = _organization_by_role(bundle, "employer")
    payer = _organization_by_role(bundle, "payer")

    patient_ref = f"Patient/{patient['id']}"
    employer_ref = f"Organization/{employer['id']}"
    payer_ref = f"Organization/{payer['id']}"

    assert employer["identifier"][0]["value"] == "CVS"
    assert employer["name"] == "CVS Health Corporation"

    assert payer["identifier"][0]["value"] == "KAISER"
    assert payer["name"] == "Kaiser Permanente"

    assert coverage["beneficiary"]["reference"] == patient_ref
    assert coverage["subscriber"]["reference"] == patient_ref
    assert coverage["policyHolder"]["reference"] == employer_ref
    assert coverage["payor"] == [{"reference": payer_ref}]
    assert coverage["subscriberId"] == "MEM-01374522"

    relationship = coverage["relationship"]["coding"][0]
    assert relationship["code"] == "self"

    assert coverage["period"] == {
        "start": "2026-01-01",
        "end": "2026-12-31",
    }
    assert coverage["type"] == {"text": "PPO"}

    group_class = _class_by_code(
        coverage,
        "group",
    )
    assert group_class["value"] == "GRP-CVS-398915"

    plan_class = _class_by_code(
        coverage,
        "plan",
    )
    assert plan_class["value"] == "STANDARD_PPO"
    assert plan_class["name"] == "Standard PPO"

    # GT1-20 is recognized during reconciliation but deliberately not
    # materialized into Coverage in this MVP.
    assert "employment" not in json.dumps(
        coverage
    ).lower()

    _assert_referential_closure(bundle)


def test_dft_preserves_claim_and_adds_same_coverage_graph():
    bundle, message_type = convert_message_to_bundle(DFT)

    assert message_type == "DFT^P03"
    assert len(_resources(bundle, "Coverage")) == 1
    assert len(_resources(bundle, "Organization")) == 2
    assert len(_resources(bundle, "Claim")) == 1

    coverage = _resources(bundle, "Coverage")[0]
    assert coverage["subscriberId"] == "MEM-01374522"
    assert _class_by_code(
        coverage,
        "plan",
    )["value"] == "STANDARD_PPO"

    _assert_referential_closure(bundle)


def test_oru_remains_unchanged_without_coverage_graph():
    bundle, message_type = convert_message_to_bundle(ORU)

    assert message_type == "ORU^R01"
    assert _resources(bundle, "Coverage") == []
    assert _resources(bundle, "Organization") == []
    assert len(
        _resources(
            bundle,
            "DiagnosticReport",
        )
    ) == 1


def test_no_in1_means_no_coverage_graph():
    no_in1 = _drop_segment(
        _drop_segment(
            _drop_segment(
                ADT,
                "IN1",
            ),
            "IN2",
        ),
        "GT1",
    )

    bundle, _ = convert_message_to_bundle(
        no_in1
    )

    assert _resources(bundle, "Coverage") == []
    assert _resources(bundle, "Organization") == []


def test_missing_payer_does_not_emit_invalid_coverage():
    no_payer = _rewrite_segment(
        ADT,
        "IN1",
        {
            3: "",
            4: "",
        },
    )

    bundle, _ = convert_message_to_bundle(
        no_payer
    )

    assert _resources(bundle, "Coverage") == []
    assert _resources(bundle, "Organization") == []


def test_source_business_identifier_is_preserved_but_resource_id_is_fhir_legal():
    home_depot = _rewrite_segment(
        ADT,
        "GT1",
        {
            16: "The Home Depot, Inc.",
            29: "HOME_DEPOT",
        },
    )
    home_depot = _rewrite_segment(
        home_depot,
        "IN1",
        {
            11: "The Home Depot, Inc.",
        },
    )
    home_depot = _rewrite_segment(
        home_depot,
        "IN2",
        {
            3: "HOME_DEPOT^The Home Depot, Inc.",
        },
    )

    bundle, _ = convert_message_to_bundle(
        home_depot
    )

    employer = _organization_by_role(
        bundle,
        "employer",
    )

    assert (
        employer["identifier"][0]["value"]
        == "HOME_DEPOT"
    )
    assert employer["name"] == "The Home Depot, Inc."
    assert employer["id"] != "HOME_DEPOT"
    assert _is_fhir_resource_id(
        employer["id"]
    )
