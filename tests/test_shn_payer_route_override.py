from __future__ import annotations

import json

import pytest

from connectathon.shn_provider import crd, dtr
from connectathon.shn_provider.scenario import get_scenario
from connectathon.shn_provider.workflow import ProviderWorkflow
import connectathon.shn_lumbar_fusion_pas as pas_builder


SYSTEM = "urn:oid:2.16.840.1.113883.6.300"


@pytest.mark.parametrize("route", ["00301", "00999", "payer-22"])
def test_payer_override_is_string_in_crd_and_case_manifest(tmp_path, route):
    workflow = ProviderWorkflow(artifact_root=tmp_path)
    case = workflow.create_case("lumbar-fusion-auth", 300, payer_route=route)
    request = workflow.build_crd(case)

    payer = request["prefetch"]["coverage"]["contained"][0]
    assert payer["identifier"][0] == {"system": SYSTEM, "value": route}
    assert payer["name"] == f"SHN reference payer route {route}"
    assert case.payer_route == route
    assert case.manifest()["payer_route"] == route
    assert json.loads((tmp_path / case.case_id / "manifest.json").read_text())["payer_route"] == route

    # The underlying clinical case is invariant; only the network adapter is overridden.
    default_case = workflow.create_case("lumbar-fusion-auth", 300)
    default_request = workflow.build_crd(default_case)
    assert case.reality == default_case.reality
    assert request["prefetch"]["patient"] == default_request["prefetch"]["patient"]
    assert request["context"] == default_request["context"]
    assert default_case.payer_route == "00301"
    if route != "00301":
        assert case.case_id != default_case.case_id  # route-specific artifact directory
        assert request != default_request


@pytest.mark.parametrize("route", ["00301", "00999"])
def test_selected_payer_flows_into_dtr_and_pas(tmp_path, monkeypatch, route):
    scenario = get_scenario("lumbar-fusion-auth")
    monkeypatch.setattr(
        dtr, "extract_questionnaire_canonical", lambda response: "https://example.org/q"
    )
    questionnaire_package = dtr.build_request(
        scenario, 300, {}, payer_route=route
    )
    coverage = questionnaire_package["parameter"][0]["resource"]
    assert coverage["contained"][0]["identifier"][0]["value"] == route

    # Isolate PAS payer serialization without requiring a returned DTR questionnaire.
    monkeypatch.setattr(
        pas_builder, "validate_documented_questionnaire_response", lambda qr, seed: None
    )
    qr = {"resourceType": "QuestionnaireResponse", "id": "test-qr"}
    workflow = ProviderWorkflow(artifact_root=tmp_path)
    case = workflow.create_case("lumbar-fusion-auth", 300, payer_route=route)
    case.questionnaire_response = qr
    pas_request = workflow.build_pas(case)
    resources = [entry["resource"] for entry in pas_request["entry"]]
    insurer = next(
        r for r in resources
        if r["resourceType"] == "Organization" and any(
            ident.get("system") == SYSTEM for ident in r.get("identifier", [])
        )
    )
    coverage = next(r for r in resources if r["resourceType"] == "Coverage")
    claim = next(r for r in resources if r["resourceType"] == "Claim")

    assert insurer["identifier"][0]["value"] == route
    assert insurer["id"] == f"shn-payer-{route}"
    assert coverage["payor"][0]["identifier"] == {"system": SYSTEM, "value": route}
    assert coverage["payor"][0]["reference"] == f"Organization/shn-payer-{route}"
    assert claim["insurer"]["reference"] == f"Organization/shn-payer-{route}"


def test_cohort_propagates_single_payer_override(tmp_path, monkeypatch):
    observed = []

    def fake_run_to_completion(self, case):
        observed.append(case.payer_route)
        case.status = "complete"
        return case

    monkeypatch.setattr(ProviderWorkflow, "run_to_completion", fake_run_to_completion)
    workflow = ProviderWorkflow(artifact_root=tmp_path, persist_artifacts=False)
    cases = workflow.run_cohort(
        start_seed=300, count=3, scenario_ids=["no-rule-default"],
        payer_route="00042",
    )
    assert observed == ["00042"] * 3
    assert [case.payer_route for case in cases] == observed


@pytest.mark.parametrize("value", ["", " 00301", "00301 ", "bad/route", "!", "x" * 54, None, 301])
def test_reject_invalid_payer_ids(value):
    with pytest.raises(ValueError, match="payer ID"):
        crd.validate_payer_route(value)
