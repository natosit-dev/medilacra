from __future__ import annotations

from collections import Counter
from typing import Any


CRD_COVERAGE_INFORMATION = (
    "http://hl7.org/fhir/us/davinci-crd/StructureDefinition/"
    "ext-coverage-information"
)
DTR_QR_COVERAGE = (
    "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/qr-coverage"
)


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _extension_scalar(extension: dict[str, Any]) -> Any:
    for key in (
        "valueCode",
        "valueString",
        "valueCanonical",
        "valueBoolean",
        "valueInteger",
        "valueDecimal",
    ):
        if key in extension:
            return extension[key]
    return None


def summarize_crd(
    body: dict[str, Any],
    expected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    questionnaires: list[str] = []

    for node in _walk(body):
        if node.get("url") != CRD_COVERAGE_INFORMATION:
            continue
        for child in node.get("extension", []):
            key = child.get("url")
            value = _extension_scalar(child)
            if key == "questionnaire" and value:
                questionnaires.append(str(value))
            elif key and value is not None:
                values[key] = value

    unique_questionnaires = list(dict.fromkeys(questionnaires))
    if len(unique_questionnaires) > 1:
        questionnaire: str | list[str] | None = unique_questionnaires
    elif unique_questionnaires:
        questionnaire = unique_questionnaires[0]
    else:
        questionnaire = None

    summary: dict[str, Any] = {
        "cards": len(body.get("cards", [])),
        "system_actions": len(body.get("systemActions", [])),
        "covered": values.get("covered"),
        "pa-needed": values.get("pa-needed"),
        "doc-needed": values.get("doc-needed"),
        "doc-purpose": values.get("doc-purpose"),
        "info-needed": values.get("info-needed"),
        "coverage-assertion-id": values.get("coverage-assertion-id"),
        "questionnaire": questionnaire,
    }

    if expected is not None:
        checks = {
            key: summary.get(key) == value
            for key, value in expected.items()
            if key in summary
        }
        summary["expected_checks"] = checks
        summary["behavior_match"] = all(checks.values())
    return summary


def _dtr_package_resources(body: dict[str, Any]) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for parameter in body.get("parameter", []):
        if parameter.get("name") != "packagebundle":
            continue
        bundle = parameter.get("resource") or {}
        for entry in bundle.get("entry", []):
            resource = entry.get("resource")
            if isinstance(resource, dict):
                resources.append(resource)
    return resources


def summarize_dtr(body: dict[str, Any]) -> dict[str, Any]:
    resources = _dtr_package_resources(body)
    counts = Counter(resource.get("resourceType") for resource in resources)
    questionnaires = [
        resource for resource in resources
        if resource.get("resourceType") == "Questionnaire"
    ]
    qrs = [
        resource for resource in resources
        if resource.get("resourceType") == "QuestionnaireResponse"
    ]
    outcomes = []
    for parameter in body.get("parameter", []):
        resource = parameter.get("resource") or {}
        if parameter.get("name") == "outcome" and resource.get("resourceType") == "OperationOutcome":
            outcomes.extend(resource.get("issue", []))

    canonical = questionnaires[0].get("url") if len(questionnaires) == 1 else None
    qr_subject = None
    qr_coverage = None
    if len(qrs) == 1:
        qr_subject = qrs[0].get("subject", {}).get("reference")
        coverage_refs = [
            ext.get("valueReference", {}).get("reference")
            for ext in qrs[0].get("extension", [])
            if ext.get("url") == DTR_QR_COVERAGE
        ]
        coverage_refs = [ref for ref in coverage_refs if ref]
        if len(set(coverage_refs)) == 1:
            qr_coverage = coverage_refs[0]

    return {
        "resource_counts": dict(sorted((k, v) for k, v in counts.items() if k)),
        "questionnaire_count": len(questionnaires),
        "questionnaire": canonical,
        "questionnaire_response_count": len(qrs),
        "questionnaire_response_subject": qr_subject,
        "questionnaire_response_coverage": qr_coverage,
        "outcome_issue_count": len(outcomes),
        "warnings": [
            issue.get("diagnostics") or issue.get("details", {}).get("text")
            for issue in outcomes
            if issue.get("severity") in {"warning", "information"}
        ],
    }


def summarize_pas(
    body: dict[str, Any],
    expected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resources = [
        entry.get("resource")
        for entry in body.get("entry", [])
        if isinstance(entry.get("resource"), dict)
    ]
    claim_responses = [
        resource for resource in resources
        if resource.get("resourceType") == "ClaimResponse"
    ]
    communication_requests = [
        resource for resource in resources
        if resource.get("resourceType") == "CommunicationRequest"
    ]

    outcome = claim_responses[0].get("outcome") if len(claim_responses) == 1 else None
    review_codes: list[tuple[str | None, str | None]] = []
    authorization_numbers: list[str] = []

    for node in _walk(body):
        url = node.get("url", "")
        if url.endswith("extension-reviewActionCode"):
            coding = node.get("valueCodeableConcept", {}).get("coding", [])
            if coding:
                review_codes.append((coding[0].get("code"), coding[0].get("display")))
        if url.endswith("extension-reviewAction"):
            for child in node.get("extension", []):
                if child.get("url") == "number" and child.get("valueString"):
                    authorization_numbers.append(child["valueString"])

    review_codes = list(dict.fromkeys(review_codes))
    review_code = review_codes[0][0] if len(review_codes) == 1 else None
    review_display = review_codes[0][1] if len(review_codes) == 1 else None
    authorization_numbers = list(dict.fromkeys(authorization_numbers))
    authorization = authorization_numbers[0] if len(authorization_numbers) == 1 else None

    summary: dict[str, Any] = {
        "claim_response_count": len(claim_responses),
        "claim_response_outcome": outcome,
        "review_action_code": review_code,
        "review_action_display": review_display,
        "communication_request_count": len(communication_requests),
        "authorization": authorization,
    }

    if expected is not None:
        checks = {
            "claim_response_outcome": outcome == expected.get("claim_response_outcome"),
            "review_action_code": review_code == expected.get("review_action_code"),
            "review_action_display": review_display == expected.get("review_action_display"),
            "communication_request_count": (
                len(communication_requests)
                == expected.get("communication_request_count")
            ),
        }
        if expected.get("authorization_required"):
            checks["authorization_required"] = bool(authorization)
        summary["expected_checks"] = checks
        summary["behavior_match"] = all(checks.values())

    return summary
