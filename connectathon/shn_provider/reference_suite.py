from __future__ import annotations

import time
import traceback
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

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
from .run_logging import (
    RunLogger,
    artifact_record,
    json_diff,
    utc_now,
    write_json,
    write_jsonl,
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
    completed_at: str | None = None
    duration_ms: float | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    execution_context: dict[str, Any] = field(default_factory=dict)
    artifact_index: list[dict[str, Any]] = field(default_factory=list)

    def manifest(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "label": self.label,
            "kind": self.kind,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "passed": self.passed,
            "manual": self.manual,
            "artifact_dir": self.artifact_dir,
            "notes": self.notes,
            "event_count": len(self.events),
            "execution_context": self.execution_context,
            "artifact_index": self.artifact_index,
            "operations": [operation.manifest() for operation in self.operations],
        }


def _evaluate(
    expected: dict[str, Any],
    observed: dict[str, Any],
) -> tuple[bool, dict[str, bool]]:
    checks: dict[str, bool] = {}
    for key, expected_value in expected.items():
        if key.endswith("_min"):
            observed_key = key[:-4]
            actual = observed.get(observed_key)
            checks[key] = (
                isinstance(actual, (int, float))
                and actual >= expected_value
            )
        elif key == "authorization_required":
            checks[key] = (
                bool(observed.get("authorization")) is bool(expected_value)
            )
        elif key == "error_contains":
            checks[key] = (
                str(expected_value).lower()
                in str(observed.get("error_text") or "").lower()
            )
        elif key == "token_rejected":
            checks[key] = (
                bool(observed.get("token_rejected")) is bool(expected_value)
            )
        else:
            checks[key] = observed.get(key) == expected_value
    return all(checks.values()), checks


def _assertion_observed_value(
    key: str,
    observed: dict[str, Any],
) -> Any:
    if key.endswith("_min"):
        return observed.get(key[:-4])
    if key == "authorization_required":
        return bool(observed.get("authorization"))
    if key == "error_contains":
        return observed.get("error_text")
    if key == "token_rejected":
        return bool(observed.get("token_rejected"))
    return observed.get(key)


class ReferenceSuiteRunner:
    def __init__(
        self,
        client: SHNProviderClient | None = None,
        artifact_root: str | Path = DEFAULT_REFERENCE_ROOT,
        persist_artifacts: bool = True,
        execution_mode: str = "python",
    ) -> None:
        self.client = client
        self.artifact_root = Path(artifact_root)
        self.persist_artifacts = persist_artifacts
        self.execution_mode = execution_mode
        self._logger: RunLogger | None = None

    def _require_client(self) -> SHNProviderClient:
        if self.client is None:
            raise RuntimeError(
                "live reference-suite execution requires SHNProviderClient"
            )
        return self.client

    @staticmethod
    def _route(
        case: ReferenceTestCase,
        operation: dict[str, Any],
    ) -> str:
        route = operation.get("route") or case.route
        if not route:
            raise ValueError(
                f"{case.id}/{operation['id']} has no payer route"
            )
        return str(route)

    @staticmethod
    def _service(
        case: ReferenceTestCase,
        operation: dict[str, Any],
    ) -> dict[str, str]:
        code = operation.get("service_code")
        if code:
            return service(str(code))
        if case.service:
            return dict(case.service)
        raise ValueError(
            f"{case.id}/{operation['id']} has no service"
        )

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

    def _emit(
        self,
        event_type: str,
        phase: str,
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> None:
        if self._logger is not None:
            self._logger.emit(
                event_type,
                phase,
                data or {},
                **kwargs,
            )

    def _payload_build_started(
        self,
        *,
        builder: str,
        inputs: dict[str, Any],
        source_artifact: str,
    ) -> None:
        self._emit(
            "payload.build.started",
            "construction",
            {
                "builder": builder,
                "inputs": inputs,
                "source_artifact": source_artifact,
            },
        )

    def _payload_built(
        self,
        *,
        builder: str,
        payload: dict[str, Any],
        source_artifact: str,
    ) -> None:
        self._emit(
            "payload.built",
            "construction",
            {
                "builder": builder,
                "source_artifact": source_artifact,
                "payload": payload,
            },
        )

    def _send(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        content_type: str = "application/json",
        correlation_id: str | None = None,
        retry_429: bool = True,
        request_label: str | None = None,
    ) -> SHNResponse:
        client = self._require_client()
        cid = correlation_id or str(uuid.uuid4())
        self._emit(
            "http.request.sent",
            "transport",
            {
                "method": "POST",
                "path": path,
                "url": f"{getattr(client, 'base_url', 'https://example.invalid')}{path}",
                "content_type": content_type,
                "correlation_id": cid,
                "request_label": request_label,
                "authorization_header_present": True,
                "authorization_scheme": "Bearer",
                "body": payload,
            },
        )
        response = client.post(
            path,
            payload,
            correlation_id=cid,
            content_type=content_type,
            retry_429=retry_429,
        )
        self._emit(
            "http.response.received",
            "transport",
            {
                "path": path,
                "request_label": request_label,
                "http_status": response.status_code,
                "correlation_id": response.correlation_id,
                "sent_correlation_id": response.sent_correlation_id,
                "shn_leg_id": response.leg_id,
                "elapsed_ms": round(response.elapsed_ms, 1),
                "warning": response.warning,
                "link": response.link,
                "trace_url": response.trace_url,
                "attempts": response.attempts,
                "body": response.body,
            },
        )
        return response

    def _record(
        self,
        result: ReferenceRunResult,
        operation: OperationResult,
    ) -> OperationResult:
        self._emit(
            "response.normalized",
            "interpretation",
            {
                "operation_type": operation.operation_type,
                "normalized": operation.observed,
            },
        )
        operation.passed, checks = _evaluate(
            operation.expected,
            operation.observed,
        )
        operation.observed["checks"] = checks

        for field_name, passed in checks.items():
            self._emit(
                "assertion.evaluated",
                "evaluation",
                {
                    "field": field_name,
                    "expected": operation.expected.get(field_name),
                    "observed": _assertion_observed_value(
                        field_name,
                        operation.observed,
                    ),
                    "passed": passed,
                },
            )

        result.operations.append(operation)
        return operation

    def _write_evidence(
        self,
        result: ReferenceRunResult,
        logger: RunLogger,
    ) -> tuple[Path | None, list[dict[str, Any]]]:
        if not self.persist_artifacts:
            return None, []

        run_dir = self.artifact_root / result.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        result.artifact_dir = str(run_dir)
        artifact_index: list[dict[str, Any]] = []

        for index, operation in enumerate(
            result.operations,
            start=1,
        ):
            op_dir = (
                run_dir
                / "operations"
                / f"{index:02d}-{operation.operation_id}"
            )
            files: list[tuple[str, Path, Any]] = []
            if operation.request is not None:
                files.append(
                    ("request", op_dir / "request.json", operation.request)
                )
            if operation.response is not None:
                files.append(
                    ("response", op_dir / "response.json", operation.response)
                )
            files.append(
                ("summary", op_dir / "summary.json", operation.manifest())
            )
            if operation.transport is not None:
                files.append(
                    ("transport", op_dir / "transport.json", operation.transport)
                )

            for role, path, value in files:
                write_json(path, value)
                record = artifact_record(
                    path,
                    run_dir,
                    f"{operation.operation_id}.{role}",
                )
                artifact_index.append(record)
                logger.emit(
                    "artifact.written",
                    "persistence",
                    record,
                    artifact_refs=[record["path"]],
                    operation_id=operation.operation_id,
                )

        return run_dir, artifact_index

    def _finalize(
        self,
        result: ReferenceRunResult,
        case: ReferenceTestCase,
        logger: RunLogger,
        started_monotonic: float,
    ) -> None:
        result.completed_at = utc_now()
        result.duration_ms = round(
            (time.monotonic() - started_monotonic) * 1000.0,
            1,
        )

        run_dir, artifact_index = self._write_evidence(
            result,
            logger,
        )
        result.artifact_index = artifact_index

        logger.set_operation(None)
        logger.emit(
            "run.completed",
            "run",
            {
                "result": (
                    "MANUAL"
                    if result.passed is None
                    else "PASS" if result.passed else "FAIL"
                ),
                "passed": result.passed,
                "completed_at": result.completed_at,
                "duration_ms": result.duration_ms,
                "operation_count": len(result.operations),
                "artifact_count": len(artifact_index),
            },
        )

        result.events = deepcopy(logger.events)
        result.execution_context = deepcopy(logger.context)

        if run_dir is not None:
            write_json(run_dir / "result.json", result.manifest())
            write_jsonl(run_dir / "events.jsonl", result.events)
            run_document = logger.build_run_document(
                run_manifest=result.manifest(),
                test_contract=case.raw,
                artifact_index=artifact_index,
            )
            write_json(run_dir / "run.json", run_document)

    def run(self, test_id: str) -> ReferenceRunResult:
        case = get_test_case(test_id)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        result = ReferenceRunResult(
            test_id=case.id,
            label=case.label,
            kind=case.kind,
            run_id=(
                f"{case.id.lower().replace('-', '')}-"
                f"{stamp}-{uuid.uuid4().hex[:8]}"
            ),
            started_at=utc_now(),
            manual=case.manual,
            notes=case.notes,
        )
        started_monotonic = time.monotonic()
        logger = RunLogger(
            run_id=result.run_id,
            test_id=case.id,
            execution_mode=self.execution_mode,
        )
        self._logger = logger
        logger.emit(
            "run.started",
            "run",
            {
                "label": case.label,
                "kind": case.kind,
                "route": case.route,
                "manual": case.manual,
                "started_at": result.started_at,
                "execution_context": logger.context,
            },
        )
        logger.emit(
            "config.loaded",
            "configuration",
            {
                "source_path": str(case.source_path),
                "contract": case.raw,
            },
        )

        previous_sink = None
        if self.client is not None:
            previous_sink = getattr(self.client, "event_sink", None)
            self.client.event_sink = logger.emit

        try:
            if case.manual:
                operation_def = case.operations[0]
                logger.set_operation(operation_def["id"])
                op_started = time.monotonic()
                logger.emit(
                    "operation.started",
                    "workflow",
                    {
                        "operation_type": operation_def["type"],
                        "expected": operation_def["expected"],
                        "mutation": operation_def.get("mutation"),
                    },
                )
                logger.emit(
                    "manual.observation.required",
                    "workflow",
                    {
                        "instruction": (
                            "Send a previously issued provider-test bearer token only "
                            "after its five-minute lifetime has elapsed. Do not paste or "
                            "persist the token in MediLacra artifacts."
                        )
                    },
                )
                operation = OperationResult(
                    operation_id=operation_def["id"],
                    operation_type=operation_def["type"],
                    expected=operation_def["expected"],
                    observed={
                        "token_rejected": None,
                        "manual_instruction": (
                            "Send a previously issued provider-test bearer token only "
                            "after its five-minute lifetime has elapsed. Do not paste or "
                            "persist the token in MediLacra artifacts."
                        ),
                    },
                    passed=None,
                )
                result.operations.append(operation)
                result.passed = None
                logger.emit(
                    "operation.completed",
                    "workflow",
                    {
                        "status": "MANUAL",
                        "passed": None,
                        "duration_ms": round(
                            (time.monotonic() - op_started) * 1000.0,
                            1,
                        ),
                    },
                )
                self._finalize(
                    result,
                    case,
                    logger,
                    started_monotonic,
                )
                return result

            self._require_client()
            state: dict[str, Any] = {
                "requests": {},
                "responses": {},
                "summaries": {},
            }

            for operation_def in case.operations:
                op_id = operation_def["id"]
                logger.set_operation(op_id)
                op_started = time.monotonic()
                logger.emit(
                    "operation.started",
                    "workflow",
                    {
                        "operation_type": operation_def["type"],
                        "source": operation_def.get("source"),
                        "mutation": operation_def.get("mutation"),
                        "expected": operation_def["expected"],
                    },
                )
                try:
                    if operation_def["type"] == "negative":
                        operation = self._run_negative(
                            case,
                            operation_def,
                            state,
                        )
                    else:
                        operation = self._run_positive(
                            case,
                            operation_def,
                            state,
                        )
                    self._record(result, operation)
                    logger.emit(
                        "operation.completed",
                        "workflow",
                        {
                            "status": (
                                "PASS" if operation.passed else "FAIL"
                            ),
                            "passed": operation.passed,
                            "duration_ms": round(
                                (time.monotonic() - op_started) * 1000.0,
                                1,
                            ),
                        },
                    )
                except Exception as exc:
                    logger.emit(
                        "error.raised",
                        "error",
                        {
                            "exception_type": type(exc).__name__,
                            "message": str(exc),
                            "traceback": traceback.format_exc(),
                        },
                    )
                    operation = OperationResult(
                        operation_id=op_id,
                        operation_type=operation_def["type"],
                        expected=operation_def["expected"],
                        error=str(exc),
                        observed={"exception": str(exc)},
                        passed=False,
                    )
                    result.operations.append(operation)
                    logger.emit(
                        "operation.completed",
                        "workflow",
                        {
                            "status": "ERROR",
                            "passed": False,
                            "duration_ms": round(
                                (time.monotonic() - op_started) * 1000.0,
                                1,
                            ),
                        },
                    )
                    break

            result.passed = all(
                op.passed is True
                for op in result.operations
            )
            self._finalize(
                result,
                case,
                logger,
                started_monotonic,
            )
            return result
        finally:
            if self.client is not None:
                self.client.event_sink = previous_sink
            self._logger = None

    def _run_positive(
        self,
        case: ReferenceTestCase,
        operation_def: dict[str, Any],
        state: dict[str, Any],
    ) -> OperationResult:
        op_id = operation_def["id"]
        op_type = operation_def["type"]
        expected = operation_def["expected"]
        route = self._route(case, operation_def)

        if op_type == "crd":
            service_def = self._service(case, operation_def)
            inputs = {
                "route": route,
                "member_id": case.member_id,
                "service": service_def,
            }
            self._payload_build_started(
                builder="build_crd",
                inputs=inputs,
                source_artifact="shn_live_baseline_00301/crd-00301.json",
            )
            payload = build_crd(
                route=route,
                service_def=service_def,
                member_id=case.member_id,
            )
            self._payload_built(
                builder="build_crd",
                payload=payload,
                source_artifact="shn_live_baseline_00301/crd-00301.json",
            )
            response = self._send(
                path="/cds-services/shn-order-sign",
                payload=payload,
            )
            observed = self._response_summary(
                response,
                summarize_crd,
            )

        elif op_type == "dtr":
            crd_summary = state["summaries"].get("crd")
            if not crd_summary or not crd_summary.get("questionnaire"):
                raise RuntimeError(
                    "DTR requires the live CRD questionnaire canonical"
                )
            canonical = str(crd_summary["questionnaire"])
            self._emit(
                "value.extracted",
                "derivation",
                {
                    "source_operation": "crd",
                    "source_path": "coverage-information.questionnaire",
                    "value": canonical,
                    "target": "DTR.questionnaire",
                },
            )
            inputs = {
                "route": route,
                "member_id": case.member_id,
                "questionnaire": canonical,
            }
            self._payload_build_started(
                builder="build_dtr",
                inputs=inputs,
                source_artifact="shn_live_baseline_00301/dtr-00301.json",
            )
            payload = build_dtr(
                route=route,
                questionnaire=canonical,
                member_id=case.member_id,
            )
            self._payload_built(
                builder="build_dtr",
                payload=payload,
                source_artifact="shn_live_baseline_00301/dtr-00301.json",
            )
            self._emit(
                "payload.derived",
                "derivation",
                {
                    "source_operation": "crd",
                    "target_operation": op_id,
                    "derived_value": canonical,
                    "target_path": "Parameters.questionnaire.valueCanonical",
                },
            )
            response = self._send(
                path="/Questionnaire/$questionnaire-package",
                payload=payload,
            )
            observed = self._response_summary(
                response,
                summarize_dtr,
            )

        elif op_type == "pas_submit":
            service_def = self._service(case, operation_def)
            inputs = {
                "route": route,
                "service": service_def,
                "tag": f"{case.id.lower()}-{op_id}",
            }
            self._payload_build_started(
                builder="build_pas",
                inputs=inputs,
                source_artifact="shn_live_baseline_00301/pas-00301.json",
            )
            payload = build_pas(
                route=route,
                service_def=service_def,
                tag=f"{case.id.lower()}-{op_id}",
            )
            self._payload_built(
                builder="build_pas",
                payload=payload,
                source_artifact="shn_live_baseline_00301/pas-00301.json",
            )
            response = self._send(
                path="/Claim/$submit",
                payload=payload,
                content_type="application/fhir+json",
            )
            observed = self._response_summary(
                response,
                summarize_pas,
            )

        elif op_type == "dtr_relaunch":
            source = operation_def.get("source")
            pas_response = state["responses"].get(source)
            if not isinstance(pas_response, dict):
                raise RuntimeError(
                    "DTR relaunch requires the source PAS response"
                )
            trace = communication_trace(pas_response)
            self._emit(
                "value.extracted",
                "derivation",
                {
                    "source_operation": source,
                    "source_path": "CommunicationRequest.identifier",
                    "value": trace,
                    "target": "DTR.relaunch.context",
                },
            )
            inputs = {
                "route": route,
                "member_id": case.member_id,
                "trace_number": trace,
            }
            self._payload_build_started(
                builder="build_dtr_relaunch",
                inputs=inputs,
                source_artifact="shn_live_baseline_00301/dtr-00301.json",
            )
            payload = build_dtr_relaunch(
                route=route,
                trace_number=trace,
                member_id=case.member_id,
            )
            self._payload_built(
                builder="build_dtr_relaunch",
                payload=payload,
                source_artifact="shn_live_baseline_00301/dtr-00301.json",
            )
            self._emit(
                "payload.derived",
                "derivation",
                {
                    "source_operation": source,
                    "target_operation": op_id,
                    "derived_value": trace,
                    "target_path": "Parameters.context.valueString",
                },
            )
            response = self._send(
                path="/Questionnaire/$questionnaire-package",
                payload=payload,
            )
            observed = self._response_summary(
                response,
                summarize_dtr,
            )

        elif op_type == "pas_inquire":
            source = operation_def.get("source")
            source_request = state["requests"].get(source)
            if not isinstance(source_request, dict):
                raise RuntimeError(
                    "PAS inquiry requires the source PAS request"
                )
            no_match = (
                operation_def.get("mutation")
                == "no_match_inquiry"
            )
            base_inquiry = build_inquiry_request(
                source_request,
                no_match=False,
            )
            if no_match:
                payload = build_inquiry_request(
                    source_request,
                    no_match=True,
                )
                self._emit(
                    "mutation.applied",
                    "mutation",
                    {
                        "mutation": "no_match_inquiry",
                        "before": base_inquiry,
                        "after": payload,
                        "diff": json_diff(base_inquiry, payload),
                        "note": (
                            "Deliberately replace the typed member identifier "
                            "so inquiry returns no matching payer-held claim."
                        ),
                    },
                )
            else:
                payload = base_inquiry
            self._emit(
                "payload.derived",
                "derivation",
                {
                    "source_operation": source,
                    "target_operation": op_id,
                    "builder": "build_inquiry",
                    "no_match": no_match,
                    "payload": payload,
                },
            )
            response = self._send(
                path="/Claim/$inquire",
                payload=payload,
                content_type="application/fhir+json",
            )
            observed = self._response_summary(
                response,
                summarize_inquiry,
            )

        else:
            raise ValueError(
                f"unsupported reference operation type {op_type!r}"
            )

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

    def _apply_logged_mutation(
        self,
        mutation: str,
        payload: dict[str, Any],
    ):
        self._emit(
            "mutation.started",
            "mutation",
            {
                "mutation": mutation,
                "before": payload,
            },
        )
        mutated = apply_mutation(mutation, payload)
        self._emit(
            "mutation.applied",
            "mutation",
            {
                "mutation": mutation,
                "before": payload,
                "after": mutated.payload,
                "diff": json_diff(payload, mutated.payload),
                "path_override": mutated.path,
                "note": mutated.note,
            },
        )
        return mutated

    def _run_negative(
        self,
        case: ReferenceTestCase,
        operation_def: dict[str, Any],
        state: dict[str, Any],
    ) -> OperationResult:
        mutation = operation_def.get("mutation")
        expected = operation_def["expected"]
        route = case.route or "00301"
        op_id = operation_def["id"]
        hcpcs_g0151 = service("G0151")

        if mutation == "unknown_payer":
            self._payload_build_started(
                builder="build_crd",
                inputs={"route": route, "service": hcpcs_g0151},
                source_artifact="shn_live_baseline_00301/crd-00301.json",
            )
            payload = build_crd(
                route=route,
                service_def=hcpcs_g0151,
            )
            self._payload_built(
                builder="build_crd",
                payload=payload,
                source_artifact="shn_live_baseline_00301/crd-00301.json",
            )
            mutated = self._apply_logged_mutation(
                mutation,
                payload,
            )
            response = self._send(
                path="/cds-services/shn-order-sign",
                payload=mutated.payload,
            )
            observed = self._response_summary(
                response,
                summarize_crd,
            )

        elif mutation == "missing_coverage_unknown_member":
            canonical = (
                "http://example.org/fhir/Questionnaire/"
                "PriorAuthRequired"
            )
            self._payload_build_started(
                builder="build_dtr",
                inputs={
                    "route": route,
                    "member_id": "MEDILACRA-UNKNOWN",
                    "questionnaire": canonical,
                },
                source_artifact="shn_live_baseline_00301/dtr-00301.json",
            )
            payload = build_dtr(
                route=route,
                questionnaire=canonical,
                member_id="MEDILACRA-UNKNOWN",
            )
            self._payload_built(
                builder="build_dtr",
                payload=payload,
                source_artifact="shn_live_baseline_00301/dtr-00301.json",
            )
            mutated = self._apply_logged_mutation(
                mutation,
                payload,
            )
            response = self._send(
                path="/Questionnaire/$questionnaire-package",
                payload=mutated.payload,
            )
            observed = self._response_summary(
                response,
                summarize_dtr,
            )

        elif mutation in {
            "bad_patient_linkage",
            "remove_coverage_beneficiary",
            "identifier_only_claim_patient",
        }:
            self._payload_build_started(
                builder="build_pas",
                inputs={
                    "route": route,
                    "service": hcpcs_g0151,
                    "tag": case.id.lower(),
                },
                source_artifact="shn_live_baseline_00301/pas-00301.json",
            )
            payload = build_pas(
                route=route,
                service_def=hcpcs_g0151,
                tag=case.id.lower(),
            )
            self._payload_built(
                builder="build_pas",
                payload=payload,
                source_artifact="shn_live_baseline_00301/pas-00301.json",
            )
            mutated = self._apply_logged_mutation(
                mutation,
                payload,
            )
            response = self._send(
                path="/Claim/$submit",
                payload=mutated.payload,
                content_type="application/fhir+json",
            )
            observed = self._response_summary(
                response,
                summarize_pas,
            )

        elif mutation == "bad_questionnaire_version":
            canonical = (
                "http://example.org/fhir/Questionnaire/"
                "HomeHealthAssessment"
            )
            self._payload_build_started(
                builder="build_dtr",
                inputs={
                    "route": route,
                    "questionnaire": canonical,
                },
                source_artifact="shn_live_baseline_00301/dtr-00301.json",
            )
            payload = build_dtr(
                route=route,
                questionnaire=canonical,
            )
            self._payload_built(
                builder="build_dtr",
                payload=payload,
                source_artifact="shn_live_baseline_00301/dtr-00301.json",
            )
            mutated = self._apply_logged_mutation(
                mutation,
                payload,
            )
            response = self._send(
                path="/Questionnaire/$questionnaire-package",
                payload=mutated.payload,
            )
            observed = self._response_summary(
                response,
                summarize_dtr,
            )

        elif mutation in {
            "hook_service_mismatch",
            "order_dispatch",
        }:
            self._payload_build_started(
                builder="build_crd",
                inputs={"route": route, "service": hcpcs_g0151},
                source_artifact="shn_live_baseline_00301/crd-00301.json",
            )
            payload = build_crd(
                route=route,
                service_def=hcpcs_g0151,
            )
            self._payload_built(
                builder="build_crd",
                payload=payload,
                source_artifact="shn_live_baseline_00301/crd-00301.json",
            )
            mutated = self._apply_logged_mutation(
                mutation,
                payload,
            )
            response = self._send(
                path=(
                    mutated.path
                    or "/cds-services/shn-order-sign"
                ),
                payload=mutated.payload,
            )
            observed = self._response_summary(
                response,
                summarize_crd,
            )

        elif mutation == "reuse_correlation_id":
            self._payload_build_started(
                builder="build_crd",
                inputs={"route": route, "service": hcpcs_g0151},
                source_artifact="shn_live_baseline_00301/crd-00301.json",
            )
            payload = build_crd(
                route=route,
                service_def=hcpcs_g0151,
            )
            self._payload_built(
                builder="build_crd",
                payload=payload,
                source_artifact="shn_live_baseline_00301/crd-00301.json",
            )
            reused = str(uuid.uuid4())
            self._emit(
                "mutation.started",
                "mutation",
                {
                    "mutation": mutation,
                    "before": payload,
                },
            )
            self._emit(
                "mutation.applied",
                "mutation",
                {
                    "mutation": mutation,
                    "before": payload,
                    "after": payload,
                    "diff": [],
                    "reused_correlation_id": reused,
                    "note": (
                        "Payload is unchanged; the same correlation UUID "
                        "is deliberately supplied to both sends."
                    ),
                },
            )
            first = self._send(
                path="/cds-services/shn-order-sign",
                payload=payload,
                correlation_id=reused,
                retry_429=False,
                request_label="first",
            )
            second = self._send(
                path="/cds-services/shn-order-sign",
                payload=payload,
                correlation_id=reused,
                retry_429=False,
                request_label="second",
            )
            response = second
            mutated = apply_mutation(
                mutation,
                payload,
            )
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
                response={
                    "first": first.body,
                    "second": second.body,
                },
                transport=transport,
            )

        else:
            raise ValueError(
                f"unsupported automated mutation {mutation!r}"
            )

        return OperationResult(
            operation_id=op_id,
            operation_type="negative",
            expected=expected,
            observed=observed,
            request=mutated.payload,
            response=response.body,
            transport=response.transport_dict(),
        )


def result_rows(
    result: ReferenceRunResult,
) -> list[dict[str, Any]]:
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
