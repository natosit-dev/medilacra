from __future__ import annotations

import uuid

import pytest

from connectathon.shn_provider.client import SHNProviderClient, SHNResponse
from connectathon.shn_provider.reference_payloads import (
    build_crd,
    build_pas,
    service,
)
from connectathon.shn_provider.reference_suite import ReferenceSuiteRunner
from connectathon.shn_provider.test_case import list_test_cases


COVINFO = (
    "http://hl7.org/fhir/us/davinci-crd/StructureDefinition/"
    "ext-coverage-information"
)
REVIEW_CODE = (
    "http://hl7.org/fhir/us/davinci-pas/"
    "StructureDefinition/extension-reviewActionCode"
)
REVIEW_ACTION = (
    "http://hl7.org/fhir/us/davinci-pas/"
    "StructureDefinition/extension-reviewAction"
)


def _response(body, status=200, correlation_id=None):
    cid = correlation_id or str(uuid.uuid4())
    return SHNResponse(
        status_code=status,
        body=body,
        correlation_id=cid,
        sent_correlation_id=cid,
        leg_id=f"leg-{cid[:8]}",
        trace_url=f"https://example.invalid/trace/{cid}",
        elapsed_ms=1.0,
    )


def _coverage_route(payload):
    if payload.get("hook"):
        coverage = payload.get("prefetch", {}).get("coverage", {})
        for org in coverage.get("contained", []):
            for identifier in org.get("identifier", []):
                if identifier.get("system") == "urn:oid:2.16.840.1.113883.6.300":
                    return identifier.get("value")
    if payload.get("resourceType") == "Bundle":
        for entry in payload.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Coverage":
                for payor in resource.get("payor", []):
                    identifier = payor.get("identifier", {})
                    if identifier.get("system") == "urn:oid:2.16.840.1.113883.6.300":
                        return identifier.get("value")
    if payload.get("resourceType") == "Parameters":
        for parameter in payload.get("parameter", []):
            if parameter.get("name") == "coverage":
                coverage = parameter.get("resource", {})
                for org in coverage.get("contained", []):
                    for identifier in org.get("identifier", []):
                        if identifier.get("system") == "urn:oid:2.16.840.1.113883.6.300":
                            return identifier.get("value")
    return None


def _service_code(payload):
    if payload.get("hook"):
        return (
            payload["context"]["draftOrders"]["entry"][0]["resource"]
            ["code"]["coding"][0]["code"]
        )
    if payload.get("resourceType") == "Bundle":
        for entry in payload.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Claim":
                return resource["item"][0]["productOrService"]["coding"][0]["code"]
    return None


def _crd_body(route, code):
    if route == "00300" and code == "L8000":
        doc_needed = "no-doc"
        questionnaire = "http://example.org/fhir/Questionnaire/PriorAuthRequired"
        covered = "covered"
    else:
        doc_needed = "clinical"
        questionnaire = "http://example.org/fhir/Questionnaire/HomeHealthAssessment"
        covered = "conditional"

    return {
        "cards": [],
        "systemActions": [
            {
                "type": "update",
                "resource": {
                    "resourceType": "ServiceRequest",
                    "extension": [
                        {
                            "url": COVINFO,
                            "extension": [
                                {"url": "covered", "valueCode": covered},
                                {"url": "pa-needed", "valueCode": "auth-needed"},
                                {"url": "doc-needed", "valueCode": doc_needed},
                                {
                                    "url": "questionnaire",
                                    "valueCanonical": questionnaire,
                                },
                            ],
                        }
                    ],
                },
            }
        ],
    }


def _dtr_body(canonical):
    return {
        "resourceType": "Parameters",
        "parameter": [
            {
                "name": "packagebundle",
                "resource": {
                    "resourceType": "Bundle",
                    "type": "collection",
                    "entry": [
                        {
                            "resource": {
                                "resourceType": "Questionnaire",
                                "id": canonical.rsplit("/", 1)[-1],
                                "url": canonical,
                                "status": "active",
                            }
                        },
                        {
                            "resource": {
                                "resourceType": "QuestionnaireResponse",
                                "status": "in-progress",
                                "questionnaire": canonical,
                            }
                        },
                    ],
                },
            }
        ],
    }


def _claim_response(outcome, review_code, display, authorization=None):
    extensions = [
        {
            "url": REVIEW_CODE,
            "valueCodeableConcept": {
                "coding": [{"code": review_code, "display": display}]
            },
        }
    ]
    if authorization:
        extensions.append(
            {
                "url": REVIEW_ACTION,
                "extension": [
                    {"url": "number", "valueString": authorization}
                ],
            }
        )
    return {
        "resourceType": "ClaimResponse",
        "outcome": outcome,
        "extension": extensions,
    }


def _pas_bundle(route, code):
    if route == "00301":
        resources = [
            _claim_response("complete", "A4", "Pending"),
            {
                "resourceType": "CommunicationRequest",
                "status": "active",
                "identifier": [{"value": "TRACE-001"}],
                "payload": [{"contentString": "102089-0"}],
            },
        ]
    elif code == "L8000":
        resources = [
            _claim_response("complete", "A1", "Certified in total", "AUTH-0001")
        ]
    elif code == "E1390":
        resources = [
            _claim_response("queued", "A4", "Pending"),
            {
                "resourceType": "Task",
                "status": "requested",
                "code": {
                    "coding": [
                        {"code": "attachment-request-questionnaire"}
                    ]
                },
            },
        ]
    else:
        resources = [_claim_response("complete", "A3", "Not Certified")]

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": resource} for resource in resources],
    }


def _inquiry_body(empty=False):
    if empty:
        return {"resourceType": "Parameters", "parameter": []}
    return {
        "resourceType": "Parameters",
        "parameter": [
            {
                "name": "responseBundle",
                "resource": {
                    "resourceType": "Bundle",
                    "type": "collection",
                    "entry": [
                        {
                            "resource": _claim_response(
                                "complete", "A1", "Certified in total", "AUTH-0001"
                            )
                        }
                    ],
                },
            }
        ],
    }


class FakeClient:
    def __init__(self):
        self.seen_correlations = set()

    def crd(self, payload, *, correlation_prefix):
        return self.post(
            "/cds-services/shn-order-sign",
            payload,
            correlation_prefix=correlation_prefix,
        )

    def dtr(self, payload, *, correlation_prefix):
        return self.post(
            "/Questionnaire/$questionnaire-package",
            payload,
            correlation_prefix=correlation_prefix,
        )

    def pas_submit(self, payload, *, correlation_prefix):
        return self.post(
            "/Claim/$submit",
            payload,
            correlation_prefix=correlation_prefix,
            content_type="application/fhir+json",
        )

    def pas_inquire(self, payload, *, correlation_prefix):
        return self.post(
            "/Claim/$inquire",
            payload,
            correlation_prefix=correlation_prefix,
            content_type="application/fhir+json",
        )

    def post(
        self,
        path,
        payload,
        *,
        correlation_prefix=None,
        correlation_id=None,
        content_type="application/json",
        bearer_token=None,
        retry_429=True,
    ):
        cid = correlation_id or str(uuid.uuid4())
        if correlation_id is not None:
            if cid in self.seen_correlations:
                return _response({"error": "correlation id reused"}, 502, cid)
            self.seen_correlations.add(cid)

        if path == "/cds-services/shn-order-dispatch":
            return _response({"error": "service not offered"}, 404, cid)

        if path == "/cds-services/shn-order-sign":
            if payload.get("hook") == "order-dispatch":
                return _response({"error": "hook/service mismatch"}, 400, cid)
            route = _coverage_route(payload)
            if route == "99999":
                return _response({"error": "no registered payer"}, 422, cid)
            return _response(_crd_body(route, _service_code(payload)), 200, cid)

        if path == "/Questionnaire/$questionnaire-package":
            coverage = [
                p for p in payload.get("parameter", [])
                if p.get("name") == "coverage"
            ]
            if not coverage:
                return _response({"error": "no coverage to route by"}, 422, cid)
            qparams = [
                p for p in payload.get("parameter", [])
                if p.get("name") == "questionnaire"
            ]
            if qparams:
                canonical = qparams[0]["valueCanonical"]
                if canonical.endswith("|9.9.9"):
                    return _response(
                        {
                            "resourceType": "Parameters",
                            "parameter": [
                                {
                                    "name": "outcome",
                                    "resource": {
                                        "resourceType": "OperationOutcome",
                                        "issue": [
                                            {
                                                "severity": "error",
                                                "diagnostics": "Questionnaire not found",
                                            }
                                        ],
                                    },
                                }
                            ],
                        },
                        200,
                        cid,
                    )
            else:
                canonical = "http://example.org/fhir/Questionnaire/HomeHealthAssessment"
            return _response(_dtr_body(canonical), 200, cid)

        if path == "/Claim/$submit":
            claims = [
                entry["resource"]
                for entry in payload.get("entry", [])
                if entry.get("resource", {}).get("resourceType") == "Claim"
            ]
            coverages = [
                entry["resource"]
                for entry in payload.get("entry", [])
                if entry.get("resource", {}).get("resourceType") == "Coverage"
            ]
            patients = [
                entry["resource"]
                for entry in payload.get("entry", [])
                if entry.get("resource", {}).get("resourceType") == "Patient"
            ]
            claim = claims[0]
            if "reference" not in claim.get("patient", {}):
                return _response(
                    {
                        "resourceType": "OperationOutcome",
                        "issue": [{"diagnostics": "PAS bundle missing Claim.patient"}],
                    },
                    500,
                    cid,
                )
            if not coverages[0].get("beneficiary"):
                return _response(
                    {
                        "resourceType": "Bundle",
                        "type": "collection",
                        "entry": [
                            {
                                "resource": _claim_response(
                                    "complete", "A3", "Not Required"
                                )
                            }
                        ],
                    },
                    200,
                    cid,
                )
            ids = patients[0].get("identifier", [])
            has_reference_member = any(
                identifier.get("system") == "http://example.org/MIN"
                and identifier.get("value") == "12345678901"
                for identifier in ids
            )
            if not has_reference_member:
                return _response({"error": "inconsistent patient linkage"}, 502, cid)

            route = _coverage_route(payload)
            code = _service_code(payload)
            return _response(_pas_bundle(route, code), 200, cid)

        if path == "/Claim/$inquire":
            patients = [
                entry["resource"]
                for entry in payload.get("entry", [])
                if entry.get("resource", {}).get("resourceType") == "Patient"
            ]
            empty = any(
                str(identifier.get("value", "")).startswith("NO-MATCH-")
                for identifier in patients[0].get("identifier", [])
            )
            return _response(_inquiry_body(empty=empty), 200, cid)

        raise AssertionError(f"unexpected fake path {path}")


def test_reference_registry_contains_tp01_through_tp05_and_tn01_through_tn10():
    ids = [case.id for case in list_test_cases()]
    assert ids == [
        "TP-01", "TP-02", "TP-03", "TP-04", "TP-05",
        "TN-01", "TN-02", "TN-03", "TN-04", "TN-05",
        "TN-06", "TN-07", "TN-08", "TN-09", "TN-10",
    ]


def test_reference_payload_builder_changes_only_explicit_route_and_service():
    payload = build_crd(
        route="00300",
        service_def=service("L8000"),
    )
    assert _coverage_route(payload) == "00300"
    assert _service_code(payload) == "L8000"

    pas = build_pas(
        route="00300",
        service_def=service("E1390"),
        tag="test",
    )
    assert _coverage_route(pas) == "00300"
    assert _service_code(pas) == "E1390"


def test_normal_correlation_ids_are_uuid4_shape():
    cid = SHNProviderClient._correlation_id("ignored-human-prefix")
    parsed = uuid.UUID(cid)
    assert parsed.version == 4
    assert str(parsed) == cid


def test_transport_metadata_cannot_leak_token_or_client_secret():
    response = _response({"ok": True})
    serialized = str(response.transport_dict()).lower()
    assert "access_token" not in serialized
    assert "client_secret" not in serialized
    assert "authorization" not in serialized


@pytest.mark.parametrize("test_id", ["TP-01", "TP-02", "TP-03", "TP-04", "TP-05"])
def test_positive_reference_suite_cases_pass_with_known_behavior(tmp_path, test_id):
    runner = ReferenceSuiteRunner(
        client=FakeClient(),
        artifact_root=tmp_path,
        persist_artifacts=True,
    )
    result = runner.run(test_id)
    assert result.passed is True
    assert all(operation.passed is True for operation in result.operations)
    assert (tmp_path / result.run_id / "result.json").exists()


@pytest.mark.parametrize(
    "test_id",
    ["TN-01", "TN-02", "TN-03", "TN-04", "TN-05", "TN-06", "TN-07", "TN-08", "TN-09"],
)
def test_automated_negative_reference_suite_cases_pass_with_expected_refusals(
    tmp_path,
    test_id,
):
    runner = ReferenceSuiteRunner(
        client=FakeClient(),
        artifact_root=tmp_path,
    )
    result = runner.run(test_id)
    assert result.passed is True
    assert result.operations[0].passed is True


def test_tn10_is_explicitly_manual_and_never_persists_a_token(tmp_path):
    runner = ReferenceSuiteRunner(
        client=None,
        artifact_root=tmp_path,
    )
    result = runner.run("TN-10")
    assert result.manual is True
    assert result.passed is None
    assert result.operations[0].passed is None
    assert "token" in result.operations[0].observed["manual_instruction"].lower()
