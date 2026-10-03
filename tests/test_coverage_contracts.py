from copy import deepcopy

import pytest

from hl7_demo.coverage import (
    assign_coverage_profile,
    load_coverage_config,
)
from hl7_demo.models import Patient


def _patient(patient_id: str) -> Patient:
    return Patient(
        patient_id=patient_id,
        patient_name="CONTRACT, CASEY",
        date_of_birth="1990-02-03",
        sex="F",
        gender="Woman",
        race="Other",
        ethnicity="Not Hispanic or Latino",
        marital_status="Single",
        language="English",
        employer="LEGACY EMPLOYER",
        ssn="000-00-0000",
        address="100 Test Ave",
        phone="555-0101",
        email="casey.contract@example.invalid",
        zip_code="01852",
        city="Lowell",
        state="MA",
    )


def test_none_seed_is_still_deterministic_for_same_patient():
    first = assign_coverage_profile(
        _patient("PAT-NONE-SEED"),
        seed=None,
    )
    second = assign_coverage_profile(
        _patient("PAT-NONE-SEED"),
        seed=None,
    )

    assert first == second


def test_seed_is_part_of_coverage_identity():
    first = assign_coverage_profile(
        _patient("PAT-SEED-IDENTITY"),
        seed=1,
    )
    second = assign_coverage_profile(
        _patient("PAT-SEED-IDENTITY"),
        seed=2,
    )

    # Even if random selection happens to land on the same employer/payer/
    # plan, the generated reality came from a different deterministic seed.
    assert first.assignment_seed != second.assignment_seed
    assert first.coverage_profile_id != second.coverage_profile_id


def test_patient_identity_is_part_of_coverage_identity():
    first = assign_coverage_profile(
        _patient("PAT-IDENTITY-A"),
        seed=42,
    )
    second = assign_coverage_profile(
        _patient("PAT-IDENTITY-B"),
        seed=42,
    )

    assert first.assignment_seed != second.assignment_seed
    assert first.coverage_profile_id != second.coverage_profile_id


def test_yaml_mapping_order_does_not_change_assignment():
    config = load_coverage_config()
    reordered = deepcopy(config)

    for key in ("employers", "payers", "plans"):
        reordered[key] = dict(
            reversed(
                list(reordered[key].items())
            )
        )

    first = assign_coverage_profile(
        _patient("PAT-ORDER-INDEPENDENT"),
        seed=2026,
        config=config,
    )
    second = assign_coverage_profile(
        _patient("PAT-ORDER-INDEPENDENT"),
        seed=2026,
        config=reordered,
    )

    assert first == second


def test_actual_plan_reference_documentation_does_not_affect_assignment():
    config = load_coverage_config()
    modified = deepcopy(config)

    for payer in modified["payers"].values():
        payer["actual_plan_references"] = {
            "status": "changed_for_test",
            "plans": [
                {
                    "name": "THIS MUST NEVER ENTER MVP GENERATION",
                    "source": "https://example.invalid/not-a-real-plan",
                }
            ],
        }

    first = assign_coverage_profile(
        _patient("PAT-REFERENCE-ISOLATION"),
        seed=99,
        config=config,
    )
    second = assign_coverage_profile(
        _patient("PAT-REFERENCE-ISOLATION"),
        seed=99,
        config=modified,
    )

    assert first == second
    assert "THIS MUST NEVER" not in second.plan_name


def test_assignment_rejects_unsupported_strategy():
    config = load_coverage_config()
    invalid = deepcopy(config)
    invalid["assignment"]["payer"]["strategy"] = "weighted"

    with pytest.raises(
        ValueError,
        match="Unsupported payer assignment strategy",
    ):
        assign_coverage_profile(
            _patient("PAT-BAD-STRATEGY"),
            seed=1,
            config=invalid,
        )


def test_generated_profiles_only_reference_configured_entities():
    config = load_coverage_config()

    employer_ids = set(config["employers"])
    payer_ids = set(config["payers"])
    plan_ids = set(config["plans"])

    for index in range(100):
        profile = assign_coverage_profile(
            _patient(f"PAT-CONTRACT-{index:03d}"),
            seed=314159,
            config=config,
        )

        assert profile.employer_id in employer_ids
        assert profile.payer_id in payer_ids
        assert profile.plan_id in plan_ids

        assert (
            profile.employer_name
            == config["employers"][
                profile.employer_id
            ]["name"]
        )
        assert (
            profile.payer_name
            == config["payers"][
                profile.payer_id
            ]["name"]
        )
        assert (
            profile.plan_name
            == config["plans"][
                profile.plan_id
            ]["name"]
        )
        assert (
            profile.plan_type
            == config["plans"][
                profile.plan_id
            ]["plan_type"]
        )


def test_deterministic_cohort_reaches_all_mvp_fixture_categories():
    config = load_coverage_config()

    employers = set()
    payers = set()
    plans = set()

    for index in range(500):
        profile = assign_coverage_profile(
            _patient(f"PAT-COHORT-{index:04d}"),
            seed=271828,
            config=config,
        )
        employers.add(profile.employer_id)
        payers.add(profile.payer_id)
        plans.add(profile.plan_id)

    assert employers == set(config["employers"])
    assert payers == set(config["payers"])
    assert plans == set(config["plans"])


def test_generated_identifier_shapes_and_profile_links_are_coherent():
    patient = _patient("PAT-ID-SHAPES")
    profile = assign_coverage_profile(
        patient,
        seed=123456,
    )

    assert profile.coverage_profile_id.startswith("COV-")
    assert len(profile.coverage_profile_id) == 20

    assert profile.member_id.startswith("MEM-")
    assert profile.policy_number.startswith("POL-")
    assert profile.group_number.startswith(
        f"GRP-{profile.employer_id}-"
    )

    assert profile.patient_id == patient.patient_id
    assert patient.coverage_profile is profile
    assert patient.employer == profile.employer_name
