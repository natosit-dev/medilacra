from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
B_ROOT = REPO_ROOT / "experiments" / "method_b_workflow_reconstruction"
DEFAULT_DETAIL = B_ROOT / "output" / "workflow_detail.csv"
DEFAULT_SOURCE = B_ROOT / "source_artifacts"
DEFAULT_OUTPUT = ROOT / "output"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def boolish(value: str) -> bool:
    return str(value).lower() in {"true", "1", "yes"}


def add_check(checks: list[dict], check_id: str, name: str, status: str, classification: str, evidence: str) -> None:
    checks.append(
        {
            "check_id": check_id,
            "check_name": name,
            "status": status,
            "classification": classification,
            "evidence": evidence,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail", default=str(DEFAULT_DETAIL))
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--skip-reconstruct", action="store_true")
    args = parser.parse_args()

    detail_path = Path(args.detail)
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_reconstruct:
        subprocess.run([sys.executable, str(B_ROOT / "reconstruct.py")], check=True, cwd=REPO_ROOT)

    detail = read_csv(detail_path)
    tasks = read_json(source_dir / "tasks.json")
    actions = read_json(source_dir / "actions.json")
    forms = read_json(source_dir / "forms.json")
    appointments = read_csv(source_dir / "appointments.csv")
    staff = read_csv(source_dir / "staff.csv")

    checks: list[dict] = []

    # VAL-0: declared grain
    distinct_ids = {r["workflow_id"] for r in detail}
    add_check(
        checks,
        "VAL-0",
        "One row per workflow instance",
        "PASS" if len(detail) == len(distinct_ids) else "FAIL",
        "EXPECTED_BEHAVIOR" if len(detail) == len(distinct_ids) else "PIPELINE_DEFECT",
        f"rows={len(detail)} distinct_workflow_ids={len(distinct_ids)}",
    )

    # VAL-1: deliberately test the incomplete documentation, not the pipeline.
    documented_states = {"queued", "active", "complete"}
    observed_states = {r["workflow_state"] for r in detail}
    undocumented = sorted(observed_states - documented_states)
    add_check(
        checks,
        "VAL-1",
        "Documented lifecycle matches observed lifecycle",
        "FAIL" if undocumented else "PASS",
        "DOCUMENTATION_CORRECTION" if undocumented else "EXPECTED_BEHAVIOR",
        f"documented={sorted(documented_states)} observed={sorted(observed_states)} undocumented={undocumented}",
    )

    # VAL-2: workflow type mapping
    expected_types = {"CARE_FOLLOWUP", "MEDICATION_REVIEW", "SOCIAL_SUPPORT"}
    observed_types = {r["workflow_type"] for r in detail}
    add_check(
        checks,
        "VAL-2",
        "Workflow types remain within the inferred model",
        "PASS" if observed_types == expected_types else "FAIL",
        "EXPECTED_BEHAVIOR" if observed_types == expected_types else "UNKNOWN",
        f"observed={sorted(observed_types)}",
    )

    # VAL-3: assignment resolution
    bad_assignment = [
        r["workflow_id"]
        for r in detail
        if (r["workflow_type"] == "SOCIAL_SUPPORT" and r["assignment_source"] != "specialist_staff_id")
        or (r["workflow_type"] != "SOCIAL_SUPPORT" and r["assignment_source"] != "owner_id")
    ]
    add_check(
        checks,
        "VAL-3",
        "Type-specific assignment precedence",
        "PASS" if not bad_assignment else "FAIL",
        "EXPECTED_BEHAVIOR" if not bad_assignment else "PIPELINE_DEFECT",
        f"violating_workflows={bad_assignment}",
    )

    # VAL-4: appointment reconciliation is internally consistent.
    staff_by_patient = {r["patient_id"]: r["scheduled_staff_id"] for r in appointments}
    bad_appt = []
    mismatch_ids = []
    for row in detail:
        scheduled = staff_by_patient.get(row["patient_id"])
        expected = "NO_APPOINTMENT" if not scheduled else ("MATCH" if scheduled == row["assigned_staff_id"] else "MISMATCH")
        if row["appointment_match_status"] != expected:
            bad_appt.append(row["workflow_id"])
        if expected == "MISMATCH":
            mismatch_ids.append(row["workflow_id"])
    add_check(
        checks,
        "VAL-4",
        "Appointment assignment reconciliation",
        "PASS" if not bad_appt else "FAIL",
        "EXPECTED_BEHAVIOR" if not bad_appt else "PIPELINE_DEFECT",
        f"calculation_errors={bad_appt}; observed_mismatches={mismatch_ids}",
    )

    # VAL-5: prove the two-hop form linkage with source-level keys.
    actions_by_workflow = {r["workflow_id"]: r for r in actions}
    forms_by_action = {r["action_id"]: r for r in forms}
    missing_two_hop = []
    for row in detail:
        if row["workflow_state"] in {"complete", "canceled"}:
            action = actions_by_workflow.get(row["workflow_id"])
            form = forms_by_action.get(action["action_id"]) if action else None
            if not action or not form or form["form_id"] != row["closure_form_id"]:
                missing_two_hop.append(row["workflow_id"])
    add_check(
        checks,
        "VAL-5",
        "Two-hop closure form relationship",
        "PASS" if not missing_two_hop else "FAIL",
        "EXPECTED_BEHAVIOR" if not missing_two_hop else "PIPELINE_DEFECT",
        f"unresolved_closed_workflows={missing_two_hop}",
    )

    # VAL-6: open work should not silently carry closure outcomes in this fixture.
    open_with_closure = [
        r["workflow_id"]
        for r in detail
        if r["workflow_state"] in {"queued", "active"} and boolish(r["has_closure"])
    ]
    add_check(
        checks,
        "VAL-6",
        "Closure state consistency",
        "PASS" if not open_with_closure else "WARN",
        "EXPECTED_BEHAVIOR" if not open_with_closure else "SOURCE_QUALITY",
        f"open_workflows_with_closure={open_with_closure}",
    )

    # VAL-7: due status vocabulary and closed-state handling.
    allowed_due = {"OVERDUE", "DUE_TODAY", "SCHEDULED", "NO_DUE_DATE", "CLOSED"}
    bad_due = [r["workflow_id"] for r in detail if r["due_status"] not in allowed_due]
    closed_not_closed = [
        r["workflow_id"]
        for r in detail
        if r["workflow_state"] in {"complete", "canceled"} and r["due_status"] != "CLOSED"
    ]
    add_check(
        checks,
        "VAL-7",
        "Due-status derivation",
        "PASS" if not bad_due and not closed_not_closed else "FAIL",
        "EXPECTED_BEHAVIOR" if not bad_due and not closed_not_closed else "PIPELINE_DEFECT",
        f"invalid_values={bad_due}; closed_state_errors={closed_not_closed}",
    )

    # VAL-8: source population reconciles to output population.
    task_ids = {r["workflow_id"] for r in tasks}
    add_check(
        checks,
        "VAL-8",
        "Task population reconciliation",
        "PASS" if task_ids == distinct_ids else "FAIL",
        "EXPECTED_BEHAVIOR" if task_ids == distinct_ids else "PIPELINE_DEFECT",
        f"source_tasks={len(task_ids)} detail_tasks={len(distinct_ids)} missing={sorted(task_ids - distinct_ids)} extra={sorted(distinct_ids - task_ids)}",
    )

    # VAL-9: critical field coverage.
    critical = ["workflow_id", "patient_id", "workflow_type", "workflow_state", "assigned_staff_id", "assignment_source"]
    missing_critical = [
        r["workflow_id"]
        for r in detail
        if any(not r.get(col) for col in critical)
    ]
    add_check(
        checks,
        "VAL-9",
        "Critical field coverage",
        "PASS" if not missing_critical else "FAIL",
        "EXPECTED_BEHAVIOR" if not missing_critical else "PIPELINE_DEFECT",
        f"missing_critical_workflows={missing_critical}",
    )

    # VAL-10: intentionally unanswerable from current evidence.
    add_check(
        checks,
        "VAL-10",
        "Staff was organizationally active at workflow creation time",
        "NOT_TESTABLE",
        "VALIDATOR_LIMITATION",
        "staff.csv has current identity/role only; no effective-dated employment history exists in the synthetic evidence",
    )

    run_ts = datetime.now(timezone.utc).isoformat()
    for row in checks:
        row["run_ts"] = run_ts

    results_path = output_dir / "validation_results.csv"
    with results_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(checks[0]))
        writer.writeheader()
        writer.writerows(checks)

    history_path = output_dir / "validation_history.csv"
    history_exists = history_path.exists()
    with history_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(checks[0]))
        if not history_exists:
            writer.writeheader()
        writer.writerows(checks)

    counts = {}
    for row in checks:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    markdown = [
        "# Validation Results",
        "",
        f"Run: `{run_ts}`",
        "",
        "| Check | Status | Classification | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for row in checks:
        evidence = row["evidence"].replace("|", "\\|")
        markdown.append(f"| {row['check_id']} {row['check_name']} | {row['status']} | {row['classification']} | {evidence} |")
    markdown.extend(
        [
            "",
            "## Interpretation",
            "",
            "A FAIL is not automatically a pipeline defect. `VAL-1` is expected to fail because the source documentation omits the valid `canceled` state. The evidence therefore corrects the documentation rather than forcing the data into the prior story.",
            "",
            "`VAL-10` is explicitly `NOT_TESTABLE`: the evidence needed to answer the question does not exist in this fixture.",
        ]
    )
    (output_dir / "VALIDATION_RESULTS.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

    summary = {"run_ts": run_ts, "counts": counts, "checks": len(checks)}
    (output_dir / "validation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
