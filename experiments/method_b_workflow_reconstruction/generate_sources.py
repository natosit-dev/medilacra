from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "source_artifacts"


def write_json(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_sources() -> dict[str, list[dict]]:
    staff = [
        {"staff_id": "STF-CN-1", "display_name": "Avery Quinn", "role": "CARE_NAVIGATOR"},
        {"staff_id": "STF-CN-2", "display_name": "Morgan Reed", "role": "CARE_NAVIGATOR"},
        {"staff_id": "STF-RN-1", "display_name": "Jordan Bell", "role": "NURSE"},
        {"staff_id": "STF-SW-1", "display_name": "Riley Stone", "role": "SOCIAL_WORKER"},
    ]

    tasks = [
        {"workflow_id": "WF001", "patient_id": "MEDI-P001", "workflow_type": "CARE_FOLLOWUP", "state": "queued", "owner_id": "STF-CN-1", "specialist_staff_id": None, "created_at": "2026-08-01T08:00:00", "due_at": "2026-08-04T17:00:00"},
        {"workflow_id": "WF002", "patient_id": "MEDI-P002", "workflow_type": "CARE_FOLLOWUP", "state": "active", "owner_id": "STF-CN-1", "specialist_staff_id": None, "created_at": "2026-08-01T09:00:00", "due_at": "2026-08-03T17:00:00"},
        {"workflow_id": "WF003", "patient_id": "MEDI-P003", "workflow_type": "CARE_FOLLOWUP", "state": "complete", "owner_id": "STF-CN-2", "specialist_staff_id": None, "created_at": "2026-08-01T10:00:00", "due_at": "2026-08-02T17:00:00"},
        {"workflow_id": "WF004", "patient_id": "MEDI-P004", "workflow_type": "CARE_FOLLOWUP", "state": "canceled", "owner_id": "STF-CN-2", "specialist_staff_id": None, "created_at": "2026-08-01T11:00:00", "due_at": "2026-08-03T17:00:00"},
        {"workflow_id": "WF005", "patient_id": "MEDI-P005", "workflow_type": "MEDICATION_REVIEW", "state": "queued", "owner_id": "STF-RN-1", "specialist_staff_id": None, "created_at": "2026-08-02T08:00:00", "due_at": "2026-08-06T17:00:00"},
        {"workflow_id": "WF006", "patient_id": "MEDI-P006", "workflow_type": "MEDICATION_REVIEW", "state": "active", "owner_id": "STF-RN-1", "specialist_staff_id": None, "created_at": "2026-08-02T09:00:00", "due_at": "2026-08-05T17:00:00"},
        {"workflow_id": "WF007", "patient_id": "MEDI-P007", "workflow_type": "MEDICATION_REVIEW", "state": "complete", "owner_id": "STF-RN-1", "specialist_staff_id": None, "created_at": "2026-08-02T10:00:00", "due_at": "2026-08-04T17:00:00"},
        {"workflow_id": "WF008", "patient_id": "MEDI-P008", "workflow_type": "SOCIAL_SUPPORT", "state": "queued", "owner_id": "STF-CN-1", "specialist_staff_id": "STF-SW-1", "created_at": "2026-08-03T08:00:00", "due_at": "2026-08-07T17:00:00"},
        {"workflow_id": "WF009", "patient_id": "MEDI-P009", "workflow_type": "SOCIAL_SUPPORT", "state": "active", "owner_id": "STF-CN-2", "specialist_staff_id": "STF-SW-1", "created_at": "2026-08-03T09:00:00", "due_at": "2026-08-04T17:00:00"},
        {"workflow_id": "WF010", "patient_id": "MEDI-P010", "workflow_type": "SOCIAL_SUPPORT", "state": "complete", "owner_id": "STF-CN-1", "specialist_staff_id": "STF-SW-1", "created_at": "2026-08-03T10:00:00", "due_at": "2026-08-05T17:00:00"},
    ]

    actions = [
        {"action_id": "ACT003", "workflow_id": "WF003", "action_type": "CLOSE", "created_at": "2026-08-02T14:00:00"},
        {"action_id": "ACT004", "workflow_id": "WF004", "action_type": "CANCEL", "created_at": "2026-08-02T15:00:00"},
        {"action_id": "ACT007", "workflow_id": "WF007", "action_type": "CLOSE", "created_at": "2026-08-04T11:00:00"},
        {"action_id": "ACT010", "workflow_id": "WF010", "action_type": "CLOSE", "created_at": "2026-08-05T10:00:00"},
    ]

    forms = [
        {"form_id": "FORM003", "action_id": "ACT003", "form_type": "FOLLOWUP_CLOSE", "outcome": "REACHED_PATIENT"},
        {"form_id": "FORM004", "action_id": "ACT004", "form_type": "FOLLOWUP_CLOSE", "outcome": "DUPLICATE"},
        {"form_id": "FORM007", "action_id": "ACT007", "form_type": "MED_REVIEW_CLOSE", "outcome": "REVIEW_COMPLETE"},
        {"form_id": "FORM010", "action_id": "ACT010", "form_type": "SOCIAL_CLOSE", "outcome": "RESOURCES_PROVIDED"},
    ]

    appointments = [
        {"appointment_id": "APT001", "patient_id": "MEDI-P001", "scheduled_staff_id": "STF-CN-1", "appointment_type": "CARE_FOLLOWUP", "scheduled_at": "2026-08-04T13:00:00"},
        {"appointment_id": "APT002", "patient_id": "MEDI-P002", "scheduled_staff_id": "STF-CN-2", "appointment_type": "CARE_FOLLOWUP", "scheduled_at": "2026-08-03T13:00:00"},
        {"appointment_id": "APT005", "patient_id": "MEDI-P005", "scheduled_staff_id": "STF-RN-1", "appointment_type": "MEDICATION_REVIEW", "scheduled_at": "2026-08-06T10:00:00"},
        {"appointment_id": "APT006", "patient_id": "MEDI-P006", "scheduled_staff_id": "STF-RN-1", "appointment_type": "MEDICATION_REVIEW", "scheduled_at": "2026-08-05T10:00:00"},
        {"appointment_id": "APT008", "patient_id": "MEDI-P008", "scheduled_staff_id": "STF-SW-1", "appointment_type": "SOCIAL_SUPPORT", "scheduled_at": "2026-08-07T09:00:00"},
        {"appointment_id": "APT009", "patient_id": "MEDI-P009", "scheduled_staff_id": "STF-CN-2", "appointment_type": "SOCIAL_SUPPORT", "scheduled_at": "2026-08-04T09:00:00"},
    ]

    return {
        "tasks": tasks,
        "actions": actions,
        "forms": forms,
        "appointments": appointments,
        "staff": staff,
    }


def main(output_dir: Path = DEFAULT_OUTPUT) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = build_sources()
    write_json(output_dir / "tasks.json", sources["tasks"])
    write_json(output_dir / "actions.json", sources["actions"])
    write_json(output_dir / "forms.json", sources["forms"])
    write_csv(output_dir / "appointments.csv", sources["appointments"])
    write_csv(output_dir / "staff.csv", sources["staff"])
    print(f"Wrote fragmented synthetic workflow evidence to {output_dir}")


if __name__ == "__main__":
    main()
