from __future__ import annotations

import copy
from typing import Any

from connectathon.shn_dtr_questionnaire_response import (
    DTR_INFO_ORIGIN,
    DTR_QR_COVERAGE,
)
from connectathon.shn_lumbar_fusion_dtr import (
    DTR_QPACKAGE_INPUT_PROFILE,
    extract_questionnaire_canonical,
)

from .scenario import ScenarioConfig
from .scenario_registry import build_scenario_reality
from .summaries import summarize_dtr
from .crd import build_request as build_crd_request


def build_request(
    scenario: ScenarioConfig,
    seed: int,
    crd_response: dict[str, Any],
) -> dict[str, Any]:
    if not scenario.has_stage("dtr"):
        raise ValueError(f"scenario {scenario.id!r} has no DTR stage")

    reality = build_scenario_reality(scenario, seed)
    crd_request = build_crd_request(scenario, seed)
    canonical = extract_questionnaire_canonical(crd_response)

    patient = copy.deepcopy(crd_request["prefetch"]["patient"])
    coverage = copy.deepcopy(crd_request["prefetch"]["coverage"])

    return {
        "resourceType": "Parameters",
        "meta": {"profile": [DTR_QPACKAGE_INPUT_PROFILE]},
        "parameter": [
            {"name": "coverage", "resource": coverage},
            {"name": "referenced", "resource": patient},
            {"name": "questionnaire", "valueCanonical": canonical},
        ],
    }


def interpret_response(body: dict[str, Any]) -> dict[str, Any]:
    return summarize_dtr(body)


def _package_resources(
    dtr_response: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    bundles = [
        parameter.get("resource")
        for parameter in dtr_response.get("parameter", [])
        if parameter.get("name") == "packagebundle"
        and isinstance(parameter.get("resource"), dict)
    ]
    if len(bundles) != 1:
        raise ValueError(f"DTR response contains {len(bundles)} packagebundle resources")

    resources = [
        entry.get("resource")
        for entry in bundles[0].get("entry", [])
        if isinstance(entry.get("resource"), dict)
    ]
    questionnaires = [
        resource for resource in resources
        if resource.get("resourceType") == "Questionnaire"
    ]
    responses = [
        resource for resource in resources
        if resource.get("resourceType") == "QuestionnaireResponse"
    ]
    if len(questionnaires) != 1:
        raise ValueError(
            f"DTR package contains {len(questionnaires)} Questionnaire resources"
        )
    if len(responses) != 1:
        raise ValueError(
            f"DTR package contains {len(responses)} QuestionnaireResponse resources"
        )
    return questionnaires[0], responses[0]


def _qr_coverage_reference(qr: dict[str, Any]) -> str | None:
    refs = [
        extension.get("valueReference", {}).get("reference")
        for extension in qr.get("extension", [])
        if extension.get("url") == DTR_QR_COVERAGE
    ]
    refs = [ref for ref in refs if ref]
    if not refs:
        return None
    if len(set(refs)) != 1:
        raise ValueError("QuestionnaireResponse contains multiple qr-coverage references")
    return refs[0]


def _resolve_fact(reality: Any, path: str) -> Any:
    value = reality
    for part in path.split("."):
        if isinstance(value, dict):
            if part not in value:
                raise ValueError(f"reality fact path {path!r} does not exist")
            value = value[part]
        else:
            if not hasattr(value, part):
                raise ValueError(f"reality fact path {path!r} does not exist")
            value = getattr(value, part)
    return value


def _answer_value(item_type: str, value: Any) -> dict[str, Any]:
    if item_type == "integer":
        if type(value) is not int:
            raise ValueError(f"expected integer answer, got {type(value).__name__}")
        return {"valueInteger": value}
    if item_type == "boolean":
        if type(value) is not bool:
            raise ValueError(f"expected boolean answer, got {type(value).__name__}")
        return {"valueBoolean": value}
    if item_type == "string":
        if type(value) is not str:
            raise ValueError(f"expected string answer, got {type(value).__name__}")
        return {"valueString": value}
    if item_type == "decimal":
        if type(value) not in {int, float}:
            raise ValueError(f"expected decimal answer, got {type(value).__name__}")
        return {"valueDecimal": value}
    raise ValueError(f"unsupported Questionnaire item type: {item_type}")


def _auto_origin_extension() -> dict[str, Any]:
    return {
        "url": DTR_INFO_ORIGIN,
        "extension": [{"url": "source", "valueCode": "auto"}],
    }


def _materialize_items(
    questionnaire_items: list[dict[str, Any]],
    reality: Any,
    mapping: dict[str, Any],
    answered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    mapped_items = mapping["items"]

    for item in questionnaire_items:
        link_id = str(item.get("linkId"))
        item_type = item.get("type")
        text = item.get("text")
        required = bool(item.get("required"))

        rendered: dict[str, Any] = {"linkId": item.get("linkId")}
        if text is not None:
            rendered["text"] = text

        children = item.get("item") or []
        if children:
            rendered["item"] = _materialize_items(
                children,
                reality,
                mapping,
                answered,
            )
            output.append(rendered)
            continue

        item_mapping = mapped_items.get(link_id)
        if item_mapping is None:
            if required:
                raise ValueError(
                    f"required Questionnaire item {link_id!r} has no semantic mapping"
                )
            output.append(rendered)
            continue

        if text != item_mapping["text"]:
            raise ValueError(
                f"Questionnaire item {link_id!r} text changed: {text!r}"
            )
        if item_type != item_mapping["type"]:
            raise ValueError(
                f"Questionnaire item {link_id!r} type changed: {item_type!r}"
            )

        value = _resolve_fact(reality, item_mapping["fact_path"])
        if value is None:
            raise ValueError(
                f"reality has no value for required fact "
                f"{item_mapping['semantic_name']!r} (Questionnaire item {link_id})"
            )

        answer = _answer_value(item_type, value)
        answer["extension"] = [_auto_origin_extension()]
        rendered["answer"] = [answer]
        answered.append(
            {
                "linkId": link_id,
                "text": text,
                "semantic_name": item_mapping["semantic_name"],
                "fact_path": item_mapping["fact_path"],
                "value": value,
            }
        )
        output.append(rendered)

    return output


def materialize_documentation(
    scenario: ScenarioConfig,
    seed: int,
    dtr_response: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    reality = build_scenario_reality(scenario, seed)
    questionnaire, template = _package_resources(dtr_response)

    canonical = questionnaire.get("url")
    if not canonical:
        raise ValueError("Questionnaire has no canonical url")
    if template.get("questionnaire") != canonical:
        raise ValueError(
            "QuestionnaireResponse template does not reference returned Questionnaire"
        )

    mapping = scenario.questionnaire_mapping(canonical)
    if mapping is None:
        raise ValueError(
            f"scenario {scenario.id!r} has no semantic mapping for Questionnaire "
            f"{canonical!r}"
        )

    expected_patient = f"Patient/{reality.patient.patient_id}"
    expected_coverage = f"Coverage/{reality.coverage_id}"
    if template.get("subject", {}).get("reference") != expected_patient:
        raise ValueError(
            "QuestionnaireResponse subject does not match MediLacra reality"
        )
    if _qr_coverage_reference(template) != expected_coverage:
        raise ValueError(
            "QuestionnaireResponse qr-coverage does not match MediLacra reality"
        )

    answered: list[dict[str, Any]] = []
    items = _materialize_items(
        questionnaire.get("item") or [],
        reality,
        mapping,
        answered,
    )

    result = copy.deepcopy(template)
    qr_slug = scenario.id.removesuffix("-auth")
    result["id"] = f"qr-{qr_slug}-{seed:04d}"
    result["status"] = "completed"
    result["subject"] = {"reference": expected_patient}
    result["questionnaire"] = canonical
    result["item"] = items
    result.pop("authored", None)

    provenance = {
        "case_id": reality.case_id,
        "scenario_id": scenario.id,
        "seed": seed,
        "projection": (
            "MediLacra reality -> payer-returned DTR Questionnaire -> "
            "completed QuestionnaireResponse"
        ),
        "questionnaire": canonical,
        "patient_reference": expected_patient,
        "coverage_reference": expected_coverage,
        "service_request_reference": f"ServiceRequest/{reality.service_request_id}",
        "answers": answered,
        "semantic_guardrail": (
            "Only explicitly mapped reality facts may answer payer questions."
        ),
    }
    return result, provenance
