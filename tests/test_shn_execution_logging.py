from __future__ import annotations

import base64
import json
import uuid
import zipfile
from pathlib import Path

from connectathon.shn_provider.client import SHNProviderClient, SHNResponse
from connectathon.shn_provider.export import build_export_zip
from connectathon.shn_provider.log_schema import validate_run_document
from connectathon.shn_provider.reference_suite import ReferenceSuiteRunner
from connectathon.shn_provider.run_logging import sha256_file


COVINFO = (
    "http://hl7.org/fhir/us/davinci-crd/StructureDefinition/"
    "ext-coverage-information"
)
REVIEW_CODE = (
    "http://hl7.org/fhir/us/davinci-pas/"
    "StructureDefinition/extension-reviewActionCode"
)


def _response(body, status=200):
    cid = str(uuid.uuid4())
    return SHNResponse(
        status_code=status,
        body=body,
        correlation_id=cid,
        sent_correlation_id=cid,
        leg_id=f"leg-{cid[:8]}",
        trace_url=f"https://example.invalid/trace/{cid}",
        elapsed_ms=1.0,
    )


def _crd_response():
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
                                {"url": "covered", "valueCode": "conditional"},
                                {"url": "pa-needed", "valueCode": "auth-needed"},
                                {"url": "doc-needed", "valueCode": "clinical"},
                                {
                                    "url": "questionnaire",
                                    "valueCanonical": (
                                        "http://example.org/fhir/Questionnaire/"
                                        "HomeHealthAssessment"
                                    ),
                                },
                            ],
                        }
                    ],
                },
            }
        ],
    }


def _dtr_response():
    canonical = (
        "http://example.org/fhir/Questionnaire/HomeHealthAssessment"
    )
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
                                "url": canonical,
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


def _pas_pend_response():
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "ClaimResponse",
                    "outcome": "complete",
                    "extension": [
                        {
                            "url": REVIEW_CODE,
                            "valueCodeableConcept": {
                                "coding": [
                                    {
                                        "code": "A4",
                                        "display": "Pending",
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
            {
                "resource": {
                    "resourceType": "CommunicationRequest",
                    "status": "active",
                    "identifier": [{"value": "TRACE-LOG-001"}],
                    "payload": [{"contentString": "102089-0"}],
                }
            },
        ],
    }


def _inquiry_response():
    return {
        "resourceType": "Parameters",
        "parameter": [
            {
                "name": "responseBundle",
                "resource": _pas_pend_response(),
            }
        ],
    }


class HappyPathClient:
    base_url = "https://example.invalid"

    def __init__(self):
        self.event_sink = None

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
        if path == "/cds-services/shn-order-sign":
            return _response(_crd_response())
        if path == "/Questionnaire/$questionnaire-package":
            return _response(_dtr_response())
        if path == "/Claim/$submit":
            return _response(_pas_pend_response())
        if path == "/Claim/$inquire":
            return _response(_inquiry_response())
        raise AssertionError(path)


def test_tp01_log_captures_derivation_transport_assertions_and_artifacts(tmp_path):
    runner = ReferenceSuiteRunner(
        client=HappyPathClient(),
        artifact_root=tmp_path,
        execution_mode="pytest",
    )
    result = runner.run("TP-01")

    assert result.passed is True
    assert result.events[0]["event_type"] == "run.started"
    assert result.events[-1]["event_type"] == "run.completed"
    assert [event["sequence"] for event in result.events] == list(
        range(1, len(result.events) + 1)
    )

    event_types = [event["event_type"] for event in result.events]
    assert "config.loaded" in event_types
    assert "payload.build.started" in event_types
    assert "payload.built" in event_types
    assert "value.extracted" in event_types
    assert "payload.derived" in event_types
    assert "http.request.sent" in event_types
    assert "http.response.received" in event_types
    assert "response.normalized" in event_types
    assert "assertion.evaluated" in event_types
    assert "artifact.written" in event_types

    assert event_types.count("operation.started") == 5
    assert event_types.count("operation.completed") == 5

    run_dir = Path(result.artifact_dir)
    run_document = json.loads((run_dir / "run.json").read_text())
    validate_run_document(run_document)

    jsonl_events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text().splitlines()
    ]
    assert jsonl_events == result.events

    for artifact in result.artifact_index:
        path = run_dir / artifact["path"]
        assert path.is_file()
        assert path.stat().st_size == artifact["size_bytes"]
        assert sha256_file(path) == artifact["sha256"]


def test_negative_log_records_before_after_structural_diff(tmp_path):
    class NegativeClient(HappyPathClient):
        def post(self, path, payload, **kwargs):
            if path == "/cds-services/shn-order-sign":
                return _response(
                    {"error": "no registered payer for identifier"},
                    status=422,
                )
            return super().post(path, payload, **kwargs)

    result = ReferenceSuiteRunner(
        client=NegativeClient(),
        artifact_root=tmp_path,
        execution_mode="pytest",
    ).run("TN-01")

    assert result.passed is True
    mutation = next(
        event
        for event in result.events
        if event["event_type"] == "mutation.applied"
    )
    assert mutation["data"]["mutation"] == "unknown_payer"
    assert mutation["data"]["before"] != mutation["data"]["after"]
    assert mutation["data"]["diff"]
    assert any(
        change["path"].endswith(".value")
        for change in mutation["data"]["diff"]
    )


def test_real_client_auth_metadata_logs_without_secret_or_token_values(tmp_path):
    client_id = "logging-test-client"
    secret = "SECRET-MARKER-DO-NOT-LOG"
    access_token = "TOKEN-MARKER-DO-NOT-LOG"
    client_file = tmp_path / "client.json"
    client_file.write_text(
        json.dumps(
            {
                "client_id": client_id,
                "client_secret": secret,
            }
        )
    )

    client = SHNProviderClient(
        client_file=client_file,
        base_url="https://example.invalid",
        console_url="https://console.example.invalid",
    )

    def fake_open(request):
        if request.full_url.endswith("/oauth/token"):
            return (
                200,
                {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "expires_in": 300,
                },
                {},
            )
        return (
            422,
            {"error": "no registered payer for identifier"},
            {
                "X-Correlation-Id": request.headers.get("X-correlation-id"),
                "X-SHN-Leg-Id": "leg-safe",
            },
        )

    client._open = fake_open

    result = ReferenceSuiteRunner(
        client=client,
        artifact_root=tmp_path / "runs",
        execution_mode="pytest",
    ).run("TN-01")
    assert result.passed is True

    auth_events = [
        event
        for event in result.events
        if event["phase"] == "authentication"
    ]
    assert [event["event_type"] for event in auth_events] == [
        "auth.token.requested",
        "auth.token.acquired",
    ]
    assert auth_events[-1]["data"]["expires_in_seconds"] == 300

    zip_path = build_export_zip(result.artifact_dir)
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert "README.txt" in names
        assert "run.json" in names
        assert "events.jsonl" in names
        assert "result.json" in names
        assert any(name.startswith("artifacts/") for name in names)
        uncompressed = b"\n".join(
            archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        )

    basic = base64.b64encode(
        f"{client_id}:{secret}".encode()
    )
    assert secret.encode() not in uncompressed
    assert access_token.encode() not in uncompressed
    assert basic not in uncompressed
    assert b"Bearer TOKEN-MARKER-DO-NOT-LOG" not in uncompressed

    decoded = uncompressed.decode("utf-8", errors="ignore")
    assert "auth.token.requested" in decoded
    assert "auth.token.acquired" in decoded
    assert "authorization_header_present" in decoded


def test_export_zip_maps_operation_evidence_under_artifacts(tmp_path):
    result = ReferenceSuiteRunner(
        client=HappyPathClient(),
        artifact_root=tmp_path,
        execution_mode="pytest",
    ).run("TP-01")
    zip_path = build_export_zip(result.artifact_dir)

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        assert "run.json" in names
        assert "events.jsonl" in names
        assert any(
            name.endswith("/request.json")
            and name.startswith("artifacts/")
            for name in names
        )
        assert any(
            name.endswith("/response.json")
            and name.startswith("artifacts/")
            for name in names
        )
