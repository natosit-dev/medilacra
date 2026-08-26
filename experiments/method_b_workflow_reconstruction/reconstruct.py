from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from generate_sources import main as generate_sources

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE_DIR = ROOT / "source_artifacts"
DEFAULT_OUTPUT_DIR = ROOT / "output"
DEFAULT_AS_OF = "2026-08-05T12:00:00"


def load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def due_status(state: str, due_at: str | None, as_of: datetime) -> str:
    if state in {"complete", "canceled"}:
        return "CLOSED"
    if not due_at:
        return "NO_DUE_DATE"
    due = datetime.fromisoformat(due_at)
    if due.date() < as_of.date():
        return "OVERDUE"
    if due.date() == as_of.date():
        return "DUE_TODAY"
    return "SCHEDULED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--skip-generate", action="store_true")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_generate:
        generate_sources(source_dir)

    tasks = load_json(source_dir / "tasks.json")
    actions = load_json(source_dir / "actions.json")
    forms = load_json(source_dir / "forms.json")
    appointments = load_csv(source_dir / "appointments.csv")
    staff = load_csv(source_dir / "staff.csv")

    staff_by_id = {row["staff_id"]: row for row in staff}
    appointment_by_patient = {row["patient_id"]: row for row in appointments}
    action_by_workflow = {row["workflow_id"]: row for row in actions}
    form_by_action = {row["action_id"]: row for row in forms}
    as_of = datetime.fromisoformat(args.as_of)

    detail = []
    for task in tasks:
        assigned_staff_id = task.get("owner_id")
        assignment_source = "owner_id"
        if task["workflow_type"] == "SOCIAL_SUPPORT" and task.get("specialist_staff_id"):
            assigned_staff_id = task["specialist_staff_id"]
            assignment_source = "specialist_staff_id"

        assigned_staff = staff_by_id.get(assigned_staff_id, {})
        appointment = appointment_by_patient.get(task["patient_id"])
        action = action_by_workflow.get(task["workflow_id"])
        form = form_by_action.get(action["action_id"]) if action else None

        if not appointment:
            appointment_match_status = "NO_APPOINTMENT"
        elif appointment["scheduled_staff_id"] == assigned_staff_id:
            appointment_match_status = "MATCH"
        else:
            appointment_match_status = "MISMATCH"

        detail.append(
            {
                "workflow_id": task["workflow_id"],
                "patient_id": task["patient_id"],
                "workflow_type": task["workflow_type"],
                "workflow_state": task["state"],
                "assigned_staff_id": assigned_staff_id,
                "assigned_staff_name": assigned_staff.get("display_name"),
                "assigned_staff_role": assigned_staff.get("role"),
                "assignment_source": assignment_source,
                "created_at": task["created_at"],
                "due_at": task.get("due_at"),
                "due_status": due_status(task["state"], task.get("due_at"), as_of),
                "appointment_id": appointment.get("appointment_id") if appointment else None,
                "appointment_staff_id": appointment.get("scheduled_staff_id") if appointment else None,
                "appointment_type": appointment.get("appointment_type") if appointment else None,
                "appointment_match_status": appointment_match_status,
                "closure_action_id": action.get("action_id") if action else None,
                "closure_action_type": action.get("action_type") if action else None,
                "closure_form_id": form.get("form_id") if form else None,
                "closure_form_type": form.get("form_type") if form else None,
                "closure_outcome": form.get("outcome") if form else None,
                "has_closure": bool(form),
            }
        )

    observed_states = sorted({row["workflow_state"] for row in detail})
    observed_types = sorted({row["workflow_type"] for row in detail})
    summary = {
        "grain": "one row per workflow_id",
        "workflow_rows": len(detail),
        "distinct_workflow_ids": len({row["workflow_id"] for row in detail}),
        "workflow_types": observed_types,
        "observed_states": observed_states,
        "two_hop_closure_join": "forms.action_id -> actions.action_id -> actions.workflow_id",
        "assignment_rule": "SOCIAL_SUPPORT specialist_staff_id overrides generic owner_id when populated",
        "appointment_rule": "appointment staff is compared with reconstructed assigned staff",
        "source_artifacts": ["tasks.json", "actions.json", "forms.json", "appointments.csv", "staff.csv"],
        "as_of": args.as_of,
    }

    write_csv(output_dir / "workflow_detail.csv", detail)
    (output_dir / "reconstruction_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
