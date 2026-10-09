from __future__ import annotations

import argparse
import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from connectathon.shn_lumbar_fusion import (
    LUMBAR_FUSION_QUESTIONNAIRE,
    build_lumbar_fusion_reality,
)


DTR_QR_COVERAGE = (
    "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/qr-coverage"
)
DTR_INFO_ORIGIN = (
    "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/information-origin"
)


def _auto_origin_extension() -> dict[str, Any]:
    return {
        "url": DTR_INFO_ORIGIN,
        "extension": [{"url": "source", "valueCode": "auto"}],
    }


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
        resource
        for resource in resources
        if resource.get("resourceType") == "Questionnaire"
    ]
    responses = [
        resource
        for resource in resources
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


def _qr_coverage_reference(questionnaire_response: dict[str, Any]) -> str | None:
    refs = [
        extension.get("valueReference", {}).get("reference")
        for extension in questionnaire_response.get("extension", [])
        if extension.get("url") == DTR_QR_COVERAGE
    ]
    refs = [ref for ref in refs if ref]
    if not refs:
        return None
    if len(set(refs)) != 1:
        raise ValueError("QuestionnaireResponse contains multiple qr-coverage references")
    return refs[0]


def _lumbar_question_map() -> dict[str, dict[str, Any]]:
    return {
        "1.1": {
            "text": "Weeks of conservative therapy completed",
            "type": "integer",
            "fact": "conservative_therapy_weeks",
            "getter": lambda reality: reality.therapy_weeks,
        },
        "1.2": {
            "text": "Imaging confirms instability or spondylolisthesis",
            "type": "boolean",
            "fact": "imaging_confirms_instability_or_spondylolisthesis",
            "getter": (
                lambda reality:
                reality.imaging_confirms_instability_or_spondylolisthesis
            ),
        },
    }


QUESTION_MAPS: dict[str, Callable[[], dict[str, dict[str, Any]]]] = {
    LUMBAR_FUSION_QUESTIONNAIRE: _lumbar_question_map,
}


def _answer_value(item_type: str, value: Any) -> dict[str, Any]:
    if item_type == "integer":
        if type(value) is not int:
            raise ValueError(f"expected integer answer, got {type(value).__name__}")
        return {"valueInteger": value}
    if item_type == "boolean":
        if type(value) is not bool:
            raise ValueError(f"expected boolean answer, got {type(value).__name__}")
        return {"valueBoolean": value}
    raise ValueError(f"unsupported mapped Questionnaire item type: {item_type}")


def _materialize_items(
    questionnaire_items: list[dict[str, Any]],
    reality: Any,
    question_map: dict[str, dict[str, Any]],
    answered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    for item in questionnaire_items:
        link_id = item.get("linkId")
        item_type = item.get("type")
        text = item.get("text")
        required = bool(item.get("required"))

        rendered: dict[str, Any] = {"linkId": link_id}
        if text is not None:
            rendered["text"] = text

        children = item.get("item") or []
        if children:
            rendered["item"] = _materialize_items(
                children,
                reality,
                question_map,
                answered,
            )
            output.append(rendered)
            continue

        mapping = question_map.get(link_id)
        if mapping is None:
            if required:
                raise ValueError(
                    f"required Questionnaire item {link_id!r} has no semantic mapping"
                )
            output.append(rendered)
            continue

        if text != mapping["text"]:
            raise ValueError(
                f"Questionnaire item {link_id!r} text changed: {text!r}"
            )
        if item_type != mapping["type"]:
            raise ValueError(
                f"Questionnaire item {link_id!r} type changed: {item_type!r}"
            )

        value = mapping["getter"](reality)
        if value is None:
            raise ValueError(
                f"reality has no value for required fact {mapping['fact']!r} "
                f"(Questionnaire item {link_id})"
            )

        answer = _answer_value(item_type, value)
        answer["extension"] = [_auto_origin_extension()]
        rendered["answer"] = [answer]
        answered.append(
            {
                "linkId": link_id,
                "text": text,
                "fact": mapping["fact"],
                "value": value,
            }
        )
        output.append(rendered)

    return output


def materialize_questionnaire_response(
    dtr_response: dict[str, Any],
    seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Answer a payer-returned DTR Questionnaire from established MediLacra reality.

    The materializer is fail-closed: a required question must have an exact semantic
    mapping and the mapped fact must already exist in reality.
    """
    reality = build_lumbar_fusion_reality(seed)
    questionnaire, template = _package_resources(dtr_response)

    canonical = questionnaire.get("url")
    if not canonical:
        raise ValueError("Questionnaire has no canonical url")
    if template.get("questionnaire") != canonical:
        raise ValueError(
            "QuestionnaireResponse template does not reference the returned Questionnaire"
        )

    question_map_factory = QUESTION_MAPS.get(canonical)
    if question_map_factory is None:
        raise ValueError(f"no semantic mapping registered for Questionnaire {canonical}")
    question_map = question_map_factory()

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
        question_map,
        answered,
    )

    result = copy.deepcopy(template)
    result["id"] = f"qr-lumbar-fusion-{seed:04d}"
    result["status"] = "completed"
    result["subject"] = {"reference": expected_patient}
    result["questionnaire"] = canonical
    result["item"] = items
    result.pop("authored", None)

    provenance = {
        "case_id": reality.case_id,
        "seed": seed,
        "projection": "MediLacra reality -> payer-returned DTR Questionnaire -> completed QuestionnaireResponse",
        "questionnaire": canonical,
        "patient_reference": expected_patient,
        "coverage_reference": expected_coverage,
        "service_request_reference": f"ServiceRequest/{reality.service_request_id}",
        "diagnosis": {
            "system": reality.diagnosis_system,
            "code": reality.diagnosis_code,
            "display": reality.diagnosis_display,
        },
        "answers": answered,
        "semantic_guardrail": (
            "prior_imaging is not used to answer imaging-confirmed instability; "
            "the explicit imaging finding fact is required"
        ),
    }
    return result, provenance


def materialize_dtr_batch(
    dtr_batch_dir: str | Path,
) -> dict[str, Any]:
    batch_dir = Path(dtr_batch_dir)
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"missing DTR batch manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    cases_out: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    provenance: dict[str, dict[str, Any]] = {}

    for case in manifest.get("cases", []):
        seed = int(case["seed"])
        case_id = case["case_id"]
        response_path = batch_dir / "live" / f"{case_id}.response.json"
        if not response_path.exists():
            raise ValueError(f"missing live DTR response: {response_path}")

        dtr_response = json.loads(response_path.read_text())
        response, trace = materialize_questionnaire_response(dtr_response, seed)

        if response["subject"]["reference"] != f"Patient/{case['patient_id']}":
            raise ValueError(f"seed {seed} materialized Patient identity drift")
        if trace["coverage_reference"] != f"Coverage/{case['coverage_id']}":
            raise ValueError(f"seed {seed} materialized Coverage identity drift")

        cases_out.append(
            {
                "seed": seed,
                "case_id": case_id,
                "patient_id": case["patient_id"],
                "coverage_id": case["coverage_id"],
                "service_request_id": case["service_request_id"],
                "diagnosis": trace["diagnosis"],
                "questionnaire": response["questionnaire"],
                "status": response["status"],
                "answer_count": len(trace["answers"]),
                "questionnaire_response": (
                    f"materialized/{case_id}/questionnaire_response.json"
                ),
                "provenance": f"materialized/{case_id}/materialization.json",
            }
        )
        payloads[case_id] = response
        provenance[case_id] = trace

    return {
        "batch_id": manifest["batch_id"],
        "source_dtr_batch": str(batch_dir),
        "count": len(cases_out),
        "cases": cases_out,
        "_payloads": payloads,
        "_provenance": provenance,
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_materialized_batch(
    batch: dict[str, Any],
    dtr_batch_dir: str | Path,
) -> Path:
    root = Path(dtr_batch_dir) / "materialized"
    root.mkdir(parents=True, exist_ok=True)

    for case in batch["cases"]:
        case_id = case["case_id"]
        case_dir = root / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "questionnaire_response.json").write_bytes(
            _json_bytes(batch["_payloads"][case_id])
        )
        (case_dir / "materialization.json").write_bytes(
            _json_bytes(batch["_provenance"][case_id])
        )

    manifest = {
        key: value
        for key, value in batch.items()
        if key not in {"_payloads", "_provenance"}
    }
    (root / "manifest.json").write_bytes(_json_bytes(manifest))
    return root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize payer-returned DTR Questionnaires from MediLacra reality"
    )
    parser.add_argument("--dtr-batch", required=True)
    args = parser.parse_args()

    batch = materialize_dtr_batch(args.dtr_batch)
    out = write_materialized_batch(batch, args.dtr_batch)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
