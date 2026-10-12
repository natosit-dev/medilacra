from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import SHNProviderClient, SHNResponse
from .inquiry import build_request as build_inquiry_request
from .mutations import apply_mutation
from .reference_payloads import (
    build_crd,
    build_dtr,
    build_dtr_relaunch,
    build_pas,
    communication_trace,
    service,
)
from .summaries import (
    error_text,
    summarize_crd,
    summarize_dtr,
    summarize_inquiry,
    summarize_pas,
)
from .test_case import ReferenceTestCase, get_test_case


DEFAULT_REFERENCE_ROOT = Path("connectathon/results/shn_reference_suite")
SENSITIVE_KEYS = {"client_secret", "access_token", "bearer_token", "Authorization"}


@dataclass
class OperationResult:
    operation_id: str
    operation_type: str
    expected: dict[str, Any]
    observed: dict[str, Any] = field(default_factory=dict)
    passed: bool | None = None
    request: dict[str, Any] | None = None
    response: Any = None
    transport: dict[str, Any] | None = None
    error: str | None = None

    def manifest(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "expected": self.expected,
            "observed": self.observed,
            "passed": self.passed,
            "transport": self.transport,
            "error": self.error,
        }


@dataclass
class ReferenceRunResult:
    test_id: str
    label: str
    kind: str
    run_id: str
    started_at: str
    operations: list[OperationResult] = field(default_factory=list)
    passed: bool | None = None
    manual: bool = False
    artifact_dir: str | None = None
    notes: list[str] = field(default_factory=list)

    def manifest(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "label": self.label,
            "kind": self.kind,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "passed": self.passed,
            "manual": self.manual,
            "artifact_dir": self.artifact_dir,
            "notes": self.notes,
            "operations": [operation.manifest() for operation in self.operations],
        }


def _assert_no_sensitive(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in SENSITIVE_KEYS:
                raise ValueError(f"sensitive key {key!r} cannot be persisted at {path}")
            _assert_no_sensitive(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_sensitive(child, f"{path}[{index}]")


def _write_json(path: Path, value: Any) -> None:
    _assert_no_sensitive(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _evaluate(expected: dict[str, Any], observed: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    checks: dict[str, bool] = {}
    for key, expected_value in expected.items():
        if key.endswith("_min"):
            observed_key = key[:-4]
            actual = observed.get(observed_key)
            checks[key] = isinstance(actual, (int, float)) and actual >= expected_value
        elif key == "authorization_required":
            checks[key] = bool(observed.get("authorization")) is bool(expected_value)
        elif key == "error_contains":
            checks[key] = str(expected_value).lower() in str(observed.get("error_text") or "").lower()
        elif key == "token_rejected":
            checks[key] = bool(observed.get("token_rejected")) is bool(expected_value)
        else:
            checks[key] = observed.get(key) == expected_value
    return all(checks.values()), checks


class ReferenceSuiteRunner:
    def __init__(
        self,
        client: SHNProviderClient | None = None,
        artifact_root: str | Path = DEFAULT_REFERENCE_ROOT,
        persist_artifacts: bool = True,
    ) -> None:
        self.client = client
        self.artifact_root = Path(artifact_root)
        self.persist_artifacts = persist_artifacts

    def _require_client(self) -> SHNProviderClient:
        if self.client is None:
            raise RuntimeError("live reference-suite execution requires SHNProviderClient")
        return self.client

    @staticmethod
    def _route(case: ReferenceTestCase, operation: dict[str, Any]) -> str:
        route = operation.get("route") or case.route
        if not route:
            raise ValueError(f"{case.id}/{operation['id']} has no payer route")
        return str(route)

    @staticmethod
    def _service(case: ReferenceTestCase, operation: dict[str, Any]) -> dict[str, str]:
        code = operation.get("service_code")
        if code:
            return service(str(code))
        if case.service:
            return dict(case.service)
        raise ValueError(f"{case.id}/{operation['id']} has no service")

    @staticmethod
    def _response_summary(
        response: SHNResponse,
        parser,
    ) -> dict[str, Any]:
        if isinstance(response.body, dict):
            summary = parser(response.body)
        else:
            summary = {"error_text": error_text(response.body)}
        summary["http_status"] = response.status_code
        return summary

    def _record(
        self,
        result: ReferenceRunResult,
        operation: OperationResult,
    ) -> OperationResult:
        operation.passed, checks = _evaluate(operation.expected, operation.observed)
        operation.observed["checks"] = checks
        result.operations.append(operation)
        return operation

    def _persist(self, result: ReferenceRunResult) -> None:
        if not self.persist_artifacts:
            return
        if result.artifact_dir:
            run_dir = Path(result.artifact_dir)
        else:
            run_dir = self.artifact_root / result.run_id
            result.artifact_dir = str(run_dir)
        for index, operation in enumerate(result.operations, start=1):
            op_dir = run_dir / "operations" / f"{index:02d}-{operation.operation_id}"
            if operation.request is not None:
                _write_json(op_dir / "request.json", operation.request)
            if operation.response is not None:
                _write_json(op_dir / "response.json", operation.response)
            _write_json(op_dir / "summary.json", operation.manifest())
            if operation.transport is not None:
                _write_json(op_dir / "transport.json", operation.transport)
        _write_json(run_dir / "result.json", result.manifest())

    def run(self, test_id: str) -> ReferenceRunResult:
        case = get_test_case(test_id)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        result = ReferenceRunResult(
            test_id=case.id,
            label=case.label,
            kind=case.kind,
            run_id=f"{case.id.lower().replace('-', '')}-{stamp}-{uuid.uuid4().hex[:8]}",
            started_at=datetime.now(timezone.utc).isoformat(),
            manual=case.manual,
            notes=case.notes,
        )

        if case.manual:
            operation_def = case.operations[0]
            operation = OperationResult(
                operation_id=operation_def["id"],
                operation_type=operation_def["type"],
                expected=operation_def["expected"],
                observed={
                    "token_rejected": None,
                    "manual_instruction": (
                        "Send a previously issued provider-test bearer token only after its "
                        "five-minute lifetime has elapsed. Do not paste or persist the token "
                        "in MediLacra artifacts."
                    ),
                },
                passed=None,
            )
            result.operations.append(operation)
            result.passed = None
            self._persist(result)
            return result

        client = self._require_client()
        state: dict[str, Any] = {"requests": {}, "responses": {}, "summaries": {}}

        for operation_def in case.operations:
            try:
                if operation_def["type"] == "negative":
                    operation = self._run_negative(case, operation_def, state)
                else:
                    operation = self._run_positive(case, operation_def, state)
                self._record(result, operation)
            except Exception as exc:
                operation = OperationResult(
                    operation_id=operation_def["id"],
                    operation_type=operation_def["type"],
                    expected=operation_def["expected"],
                    error=str(exc),
                    observed={"exception": str(exc)},
                    passed=False,
                )
                result.operations.append(operation)
                break

        result.passed = all(op.passed is True for op in result.operations)
        self._persist(result)
        return result

    def _run_positive(
        self,
        case: ReferenceTestCase,
        operation_def: dict[str, Any],
        state: dict[str, Any],
    ) -> OperationResult:
        client = self._require_client()
        op_id = operation_def["id"]
        op_type = operation_def["type"]
        expected = operation_def["expected"]
        route = self._route(case, operation_def)

        if op_type == "crd":
            payload = build_crd(
                route=route,
                service_def=self._service(case, operation_def),
                member_id=case.member_id,
            )
            response = client.crd(payload, correlation_prefix=f"{case.id}-{op_id}")
            observed = self._response_summary(response, summarize_crd)

        elif op_type == "dtr":
            crd_summary = state["summaries"].get("crd")
            if not crd_summary or not crd_summary.get("questionnaire"):
                raise RuntimeError("DTR requires the live CRD questionnaire canonical")
            payload = build_dtr(
                route=route,
                questionnaire=str(crd_summary["questionnaire"]),
                member_id=case.member_id,
            )
            response = client.dtr(payload, correlation_prefix=f"{case.id}-{op_id}")
            observed = self._response_summary(response, summarize_dtr)

        elif op_type == "pas_submit":
            payload = build_pas(
                route=route,
                service_def=self._service(case, operation_def),
                tag=f"{case.id.lower()}-{op_id}",
            )
            response = client.pas_submit(payload, correlation_prefix=f"{case.id}-{op_id}")
            observed = self._response_summary(response, summarize_pas)

        elif op_type == "dtr_relaunch":
            source = operation_def.get("source")
            pas_response = state["responses"].get(source)
            if not isinstance(pas_response, dict):
                raise RuntimeError("DTR relaunch requires the source PAS response")
            trace = communication_trace(pas_response)
            payload = build_dtr_relaunch(
                route=route,
                trace_number=trace,
                member_id=case.member_id,
            )
            response = client.dtr(payload, correlation_prefix=f"{case.id}-{op_id}")
            observed = self._response_summary(response, summarize_dtr)

        elif op_type == "pas_inquire":
            source = operation_def.get("source")
            source_request = state["requests"].get(source)
            if not isinstance(source_request, dict):
                raise RuntimeError("PAS inquiry requires the source PAS request")
            payload = build_inquiry_request(
                source_request,
                no_match=operation_def.get("mutation") == "no_match_inquiry",
            )
            response = client.pas_inquire(
                payload,
                correlation_prefix=f"{case.id}-{op_id}",
            )
            observed = self._response_summary(response, summarize_inquiry)

        else:
            raise ValueError(f"unsupported reference operation type {op_type!r}")

        state["requests"][op_id] = payload
        state["responses"][op_id] = response.body
        state["summaries"][op_id] = observed
        if op_type == "crd":
            state["summaries"]["crd"] = observed

        return OperationResult(
            operation_id=op_id,
            operation_type=op_type,
            expected=expected,
            observed=observed,
            request=payload,
            response=response.body,
            transport=response.transport_dict(),
        )

    def _run_negative(
        self,
        case: ReferenceTestCase,
        operation_def: dict[str, Any],
        state: dict[str, Any],
    ) -> OperationResult:
        client = self._require_client()
        mutation = operation_def.get("mutation")
        expected = operation_def["expected"]
        route = case.route or "00301"
        op_id = operation_def["id"]
        hcpcs_g0151 = service("G0151")

        if mutation == "unknown_payer":
            payload = build_crd(route=route, service_def=hcpcs_g0151)
            mutated = apply_mutation(mutation, payload)
            response = client.post(
                "/cds-services/shn-order-sign",
                mutated.payload,
                correlation_prefix=f"{case.id}-{mutation}",
            )
            observed = self._response_summary(response, summarize_crd)

        elif mutation == "missing_coverage_unknown_member":
            payload = build_dtr(
                route=route,
                questionnaire="http://example.org/fhir/Questionnaire/PriorAuthRequired",
                member_id="MEDILACRA-UNKNOWN",
            )
            mutated = apply_mutation(mutation, payload)
            response = client.dtr(
                mutated.payload,
                correlation_prefix=f"{case.id}-{mutation}",
            )
            observed = self._response_summary(response, summarize_dtr)

        elif mutation in {
            "bad_patient_linkage",
            "remove_coverage_beneficiary",
            "identifier_only_claim_patient",
        }:
            payload = build_pas(
                route=route,
                service_def=hcpcs_g0151,
                tag=case.id.lower(),
            )
            mutated = apply_mutation(mutation, payload)
            response = client.pas_submit(
                mutated.payload,
                correlation_prefix=f"{case.id}-{mutation}",
            )
            observed = self._response_summary(response, summarize_pas)

        elif mutation == "bad_questionnaire_version":
            payload = build_dtr(
                route=route,
                questionnaire="http://example.org/fhir/Questionnaire/HomeHealthAssessment",
            )
            mutated = apply_mutation(mutation, payload)
            response = client.dtr(
                mutated.payload,
                correlation_prefix=f"{case.id}-{mutation}",
            )
            observed = self._response_summary(response, summarize_dtr)

        elif mutation in {"hook_service_mismatch", "order_dispatch"}:
            payload = build_crd(route=route, service_def=hcpcs_g0151)
            mutated = apply_mutation(mutation, payload)
            response = client.post(
                mutated.path or "/cds-services/shn-order-sign",
                mutated.payload,
                correlation_prefix=f"{case.id}-{mutation}",
            )
            observed = self._response_summary(response, summarize_crd)

        elif mutation == "reuse_correlation_id":
            payload = build_crd(route=route, service_def=hcpcs_g0151)
            reused = str(uuid.uuid4())
            first = client.post(
                "/cds-services/shn-order-sign",
                payload,
                correlation_id=reused,
                retry_429=False,
            )
            second = client.post(
                "/cds-services/shn-order-sign",
                payload,
                correlation_id=reused,
                retry_429=False,
            )
            response = second
            mutated = apply_mutation(mutation, payload)
            observed = {
                "first_http_status": first.status_code,
                "second_http_status": second.status_code,
                "http_status": second.status_code,
                "error_text": error_text(second.body),
                "reused_correlation_id": reused,
            }
            transport = {
                "first": first.transport_dict(),
                "second": second.transport_dict(),
            }
            return OperationResult(
                operation_id=op_id,
                operation_type="negative",
                expected=expected,
                observed=observed,
                request=mutated.payload,
                response={"first": first.body, "second": second.body},
                transport=transport,
            )

        else:
            raise ValueError(f"unsupported automated mutation {mutation!r}")

        return OperationResult(
            operation_id=op_id,
            operation_type="negative",
            expected=expected,
            observed=observed,
            request=mutated.payload,
            response=response.body,
            transport=response.transport_dict(),
        )


def result_rows(result: ReferenceRunResult) -> list[dict[str, Any]]:
    rows = []
    for operation in result.operations:
        rows.append(
            {
                "test_id": result.test_id,
                "operation": operation.operation_id,
                "type": operation.operation_type,
                "http": operation.observed.get("http_status"),
                "outcome": (
                    operation.observed.get("claim_response_outcome")
                    or operation.observed.get("review_action_code")
                    or operation.observed.get("questionnaire")
                    or operation.observed.get("error_text")
                ),
                "pass": operation.passed,
                "correlation_id": (
                    (operation.transport or {}).get("correlation_id")
                    if isinstance(operation.transport, dict)
                    else None
                ),
            }
        )
    return rows
