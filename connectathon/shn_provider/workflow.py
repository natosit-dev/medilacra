from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from . import crd, dtr, pas
from .artifacts import DEFAULT_ROOT, write_case_artifacts
from .client import SHNProviderClient, SHNResponse
from .scenario import ScenarioConfig, get_scenario, list_scenarios
from .scenario_registry import scenario_reality_manifest
from .state import ProviderCase


class ProviderWorkflow:
    """Provider-side CRD -> DTR -> PAS orchestration.

    Branching follows the live payer response. Scenario expectations are used
    for evaluation, never as a substitute for a network response.
    """

    def __init__(
        self,
        client: SHNProviderClient | None = None,
        artifact_root: str | Path = DEFAULT_ROOT,
        persist_artifacts: bool = True,
    ) -> None:
        self.client = client
        self.artifact_root = Path(artifact_root)
        self.persist_artifacts = persist_artifacts

    def _scenario(self, case: ProviderCase) -> ScenarioConfig:
        return get_scenario(case.scenario_id)

    def _persist(self, case: ProviderCase) -> None:
        if self.persist_artifacts:
            write_case_artifacts(case, self.artifact_root)

    @staticmethod
    def _body_dict(response: SHNResponse, stage: str) -> dict[str, Any]:
        if not isinstance(response.body, dict):
            raise RuntimeError(
                f"{stage} returned HTTP {response.status_code} with a non-JSON object body: "
                f"{str(response.body)[:300]}"
            )
        return response.body

    def create_case(
        self,
        scenario_id: str,
        seed: int,
    ) -> ProviderCase:
        scenario = get_scenario(scenario_id)
        reality = scenario_reality_manifest(scenario, seed)
        case = ProviderCase(
            scenario_id=scenario.id,
            scenario_label=scenario.label,
            seed=int(seed),
            case_id=reality["case_id"],
            reality=reality,
        )
        self._persist(case)
        return case

    def build_crd(self, case: ProviderCase) -> dict[str, Any]:
        scenario = self._scenario(case)
        case.crd.request = crd.build_request(scenario, case.seed)
        case.status = "crd-built"
        self._persist(case)
        return case.crd.request

    def run_crd(self, case: ProviderCase) -> ProviderCase:
        if self.client is None:
            raise RuntimeError("live CRD requires an SHNProviderClient")
        scenario = self._scenario(case)
        request = case.crd.request or self.build_crd(case)

        response = self.client.crd(
            request,
            correlation_prefix=f"medilacra-{scenario.id}-crd-{case.seed}",
        )
        case.crd.transport = response.transport_dict()
        case.crd.response = response.body

        if not response.ok:
            case.crd.error = f"HTTP {response.status_code}"
            case.status = "failed"
            case.stop_reason = "CRD transport/refusal"
            self._persist(case)
            return case

        body = self._body_dict(response, "CRD")
        case.crd.summary = crd.interpret_response(scenario, body)

        if crd.should_enter_dtr(scenario, case.crd.summary):
            case.status = "crd-complete"
            case.stop_reason = None
        else:
            case.status = "complete"
            case.stop_reason = (
                "live CRD response selected no DTR questionnaire"
                if not case.crd.summary.get("questionnaire")
                else "scenario has no DTR stage"
            )

        self._persist(case)
        return case

    def build_dtr(self, case: ProviderCase) -> dict[str, Any]:
        scenario = self._scenario(case)
        if not isinstance(case.crd.response, dict):
            raise RuntimeError("DTR requires a successful live CRD response")
        case.dtr.request = dtr.build_request(
            scenario,
            case.seed,
            case.crd.response,
        )
        case.status = "dtr-built"
        self._persist(case)
        return case.dtr.request

    def run_dtr(self, case: ProviderCase) -> ProviderCase:
        if self.client is None:
            raise RuntimeError("live DTR requires an SHNProviderClient")
        scenario = self._scenario(case)
        request = case.dtr.request or self.build_dtr(case)

        response = self.client.dtr(
            request,
            correlation_prefix=f"medilacra-{scenario.id}-dtr-{case.seed}",
        )
        case.dtr.transport = response.transport_dict()
        case.dtr.response = response.body

        if not response.ok:
            case.dtr.error = f"HTTP {response.status_code}"
            case.status = "failed"
            case.stop_reason = "DTR transport/refusal"
            self._persist(case)
            return case

        body = self._body_dict(response, "DTR")
        case.dtr.summary = dtr.interpret_response(body)
        case.status = "dtr-complete"
        case.stop_reason = None
        self._persist(case)
        return case

    def materialize_documentation(self, case: ProviderCase) -> ProviderCase:
        scenario = self._scenario(case)
        if not isinstance(case.dtr.response, dict):
            raise RuntimeError(
                "QuestionnaireResponse materialization requires a successful live DTR response"
            )
        qr, provenance = dtr.materialize_documentation(
            scenario,
            case.seed,
            case.dtr.response,
        )
        case.questionnaire_response = qr
        case.materialization = provenance
        case.status = "documentation-complete"
        self._persist(case)
        return case

    def build_pas(self, case: ProviderCase) -> dict[str, Any]:
        scenario = self._scenario(case)
        if case.questionnaire_response is None:
            raise RuntimeError("PAS requires completed DTR documentation")
        case.pas.request = pas.build_request(
            scenario,
            case.seed,
            case.questionnaire_response,
        )
        case.status = "pas-built"
        self._persist(case)
        return case.pas.request

    def run_pas(self, case: ProviderCase) -> ProviderCase:
        if self.client is None:
            raise RuntimeError("live PAS requires an SHNProviderClient")
        scenario = self._scenario(case)
        request = case.pas.request or self.build_pas(case)

        response = self.client.pas_submit(
            request,
            correlation_prefix=f"medilacra-{scenario.id}-pas-{case.seed}",
        )
        case.pas.transport = response.transport_dict()
        case.pas.response = response.body

        if not response.ok:
            case.pas.error = f"HTTP {response.status_code}"
            case.status = "failed"
            case.stop_reason = "PAS transport/refusal"
            self._persist(case)
            return case

        body = self._body_dict(response, "PAS")
        case.pas.summary = pas.interpret_response(scenario, body)
        case.status = "complete"
        case.stop_reason = None
        self._persist(case)
        return case

    def run_next(self, case: ProviderCase) -> ProviderCase:
        scenario = self._scenario(case)

        if case.crd.response is None:
            return self.run_crd(case)
        if case.status == "failed":
            return case

        crd_summary = case.crd.summary or {}
        if not crd.should_enter_dtr(scenario, crd_summary):
            case.status = "complete"
            if case.stop_reason is None:
                case.stop_reason = "live CRD response selected no DTR path"
            self._persist(case)
            return case

        if case.dtr.response is None:
            return self.run_dtr(case)
        if case.status == "failed":
            return case

        if case.questionnaire_response is None:
            return self.materialize_documentation(case)

        if scenario.has_stage("pas") and case.pas.response is None:
            return self.run_pas(case)

        case.status = "complete"
        self._persist(case)
        return case

    def run_to_completion(self, case: ProviderCase) -> ProviderCase:
        while case.status not in {"complete", "failed"}:
            before = (
                case.status,
                case.crd.response is not None,
                case.dtr.response is not None,
                case.questionnaire_response is not None,
                case.pas.response is not None,
            )
            self.run_next(case)
            after = (
                case.status,
                case.crd.response is not None,
                case.dtr.response is not None,
                case.questionnaire_response is not None,
                case.pas.response is not None,
            )
            if after == before:
                raise RuntimeError("provider workflow made no progress")
        return case

    def run_cohort(
        self,
        *,
        start_seed: int,
        count: int,
        scenario_ids: Iterable[str] | None = None,
    ) -> list[ProviderCase]:
        if count < 1:
            raise ValueError("count must be at least 1")
        ids = list(scenario_ids or [scenario.id for scenario in list_scenarios()])
        if not ids:
            raise ValueError("at least one scenario is required")

        cases: list[ProviderCase] = []
        for index in range(count):
            scenario_id = ids[index % len(ids)]
            case = self.create_case(scenario_id, start_seed + index)
            try:
                self.run_to_completion(case)
            except Exception as exc:
                case.status = "failed"
                case.stop_reason = str(exc)
                self._persist(case)
            cases.append(case)
        return cases


def cohort_rows(cases: Iterable[ProviderCase]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        crd_summary = case.crd.summary or {}
        pas_summary = case.pas.summary or {}
        rows.append(
            {
                "seed": case.seed,
                "scenario": case.scenario_id,
                "case_id": case.case_id,
                "patient": case.reality["entities"]["patient"]["patient_id"],
                "service": case.reality["clinical_facts"]["ordered_service"]["code"],
                "crd_covered": crd_summary.get("covered"),
                "crd_pa_needed": crd_summary.get("pa-needed"),
                "questionnaire": crd_summary.get("questionnaire"),
                "dtr": case.dtr.response is not None,
                "documentation": case.questionnaire_response is not None,
                "pas_review": pas_summary.get("review_action_code"),
                "authorization": pas_summary.get("authorization"),
                "status": case.status,
                "stop_reason": case.stop_reason,
            }
        )
    return rows
