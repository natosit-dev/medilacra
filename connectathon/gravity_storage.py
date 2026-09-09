from __future__ import annotations

import json
from typing import Any, Mapping

from connectathon.gravity_response import answer_absent_reason, iter_response_items
from utils.db import reader, writer


QUESTIONNAIRE_RESPONSE_DDL = """
CREATE TABLE IF NOT EXISTS questionnaire_responses (
    response_id TEXT PRIMARY KEY,
    questionnaire_url TEXT,
    questionnaire_version TEXT,
    patient_id TEXT,
    authored TIMESTAMP,
    status TEXT,
    items STRUCT(
        path TEXT,
        link_id TEXT,
        answer_type TEXT,
        value_text TEXT,
        value_number DOUBLE,
        unit TEXT,
        code_system TEXT,
        code TEXT,
        absent_reason TEXT
    )[],
    raw_input_json JSON,
    fhir_json JSON,
    bundle_json JSON,
    created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def init_questionnaire_storage(db_path: str | None = None) -> None:
    """Create the Phase 1 response table using the existing MediLacra DuckDB writer."""
    with writer(db_path) as connection:
        connection.execute(QUESTIONNAIRE_RESPONSE_DDL)


def flatten_response_items(questionnaire_response: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project leaf FHIR response items into a DuckDB STRUCT[] for easy inspection.

    The authoritative artifact remains the complete FHIR QuestionnaireResponse JSON. This
    projection exists so the same answers can also be queried without reparsing JSON.
    """
    rows: list[dict[str, Any]] = []

    for path, item in iter_response_items(list(questionnaire_response.get("item") or [])):
        if item.get("item"):
            continue

        answers = item.get("answer") or []
        if not answers:
            rows.append(
                {
                    "path": path,
                    "link_id": item.get("linkId"),
                    "answer_type": "unanswered",
                    "value_text": None,
                    "value_number": None,
                    "unit": None,
                    "code_system": None,
                    "code": None,
                    "absent_reason": None,
                }
            )
            continue

        for answer in answers:
            if not isinstance(answer, Mapping):
                continue

            absent_reason = answer_absent_reason(answer)
            row: dict[str, Any] = {
                "path": path,
                "link_id": item.get("linkId"),
                "answer_type": "absent" if absent_reason else "unknown",
                "value_text": None,
                "value_number": None,
                "unit": None,
                "code_system": None,
                "code": None,
                "absent_reason": absent_reason,
            }

            if "valueQuantity" in answer:
                quantity = answer.get("valueQuantity") or {}
                row.update(
                    {
                        "answer_type": "quantity",
                        "value_number": quantity.get("value"),
                        "unit": quantity.get("code") or quantity.get("unit"),
                        "code_system": quantity.get("system"),
                    }
                )
            elif "valueInteger" in answer:
                row.update(
                    {
                        "answer_type": "integer",
                        "value_number": answer.get("valueInteger"),
                    }
                )
            elif "valueDecimal" in answer:
                row.update(
                    {
                        "answer_type": "decimal",
                        "value_number": answer.get("valueDecimal"),
                    }
                )
            elif "valueBoolean" in answer:
                row.update(
                    {
                        "answer_type": "boolean",
                        "value_text": str(answer.get("valueBoolean")).lower(),
                    }
                )
            elif "valueCoding" in answer:
                coding = answer.get("valueCoding") or {}
                row.update(
                    {
                        "answer_type": "coding",
                        "value_text": coding.get("display"),
                        "code_system": coding.get("system"),
                        "code": coding.get("code"),
                    }
                )
            elif "valueString" in answer:
                row.update(
                    {
                        "answer_type": "string",
                        "value_text": answer.get("valueString"),
                    }
                )

            rows.append(row)

    return rows


def save_questionnaire_response(
    questionnaire_response: Mapping[str, Any],
    raw_input: Mapping[str, Any],
    *,
    bundle: Mapping[str, Any] | None = None,
    db_path: str | None = None,
) -> None:
    """Persist FHIR JSON, raw UI input, and a nested STRUCT projection."""
    init_questionnaire_storage(db_path)

    response_id = str(questionnaire_response.get("id") or "")
    patient_reference = str((questionnaire_response.get("subject") or {}).get("reference") or "")
    patient_id = (
        patient_reference.split("/", 1)[1]
        if patient_reference.startswith("Patient/")
        else patient_reference
    )
    canonical = str(questionnaire_response.get("questionnaire") or "")
    questionnaire_url, separator, questionnaire_version = canonical.partition("|")

    with writer(db_path) as connection:
        connection.execute("DELETE FROM questionnaire_responses WHERE response_id = ?", [response_id])
        connection.execute(
            """
            INSERT INTO questionnaire_responses (
                response_id,
                questionnaire_url,
                questionnaire_version,
                patient_id,
                authored,
                status,
                items,
                raw_input_json,
                fhir_json,
                bundle_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON), CAST(? AS JSON), CAST(? AS JSON))
            """,
            [
                response_id,
                questionnaire_url,
                questionnaire_version if separator else None,
                patient_id,
                questionnaire_response.get("authored"),
                questionnaire_response.get("status"),
                flatten_response_items(questionnaire_response),
                json.dumps(raw_input, sort_keys=True),
                json.dumps(questionnaire_response, sort_keys=True),
                json.dumps(bundle, sort_keys=True) if bundle is not None else None,
            ],
        )


def load_questionnaire_responses(
    limit: int = 20,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent questionnaire responses for UI inspection."""
    init_questionnaire_storage(db_path)
    safe_limit = max(1, min(int(limit), 500))

    with reader(db_path=db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                response_id,
                questionnaire_url,
                questionnaire_version,
                patient_id,
                authored,
                status,
                items,
                CAST(raw_input_json AS VARCHAR),
                CAST(fhir_json AS VARCHAR),
                CAST(bundle_json AS VARCHAR),
                created_ts
            FROM questionnaire_responses
            ORDER BY created_ts DESC
            LIMIT {safe_limit}
            """
        ).fetchall()

    columns = [
        "response_id",
        "questionnaire_url",
        "questionnaire_version",
        "patient_id",
        "authored",
        "status",
        "items",
        "raw_input_json",
        "fhir_json",
        "bundle_json",
        "created_ts",
    ]
    return [dict(zip(columns, row)) for row in rows]
