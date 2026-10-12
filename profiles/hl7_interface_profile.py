from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from fhir.fhir_convert_backend import split_messages, split_segments
from schemas.xml_to_registry import load_iris_schema


DEFAULT_SCHEMA_PATH = Path("schemas/HL7v25_from_IRIS.xml")

TARGETS = {
    "mrn": {
        "label": "MRN",
        "path": "PID-3.1",
        "recommended_format": "PID-3.1",
    },
    "assigning_authority": {
        "label": "Assigning Authority",
        "path": "PID-3.4",
        "recommended_format": "PID-3.4",
    },
    "date_of_birth": {
        "label": "Date of Birth",
        "path": "PID-7",
        "recommended_format": "PID-7",
    },
    "pv1_44": {
        "label": "PV1-44",
        "path": "PV1-44",
        "recommended_format": "PV1-44",
    },
}


def _segments(message: str) -> list[list[str]]:
    return [segment.split("|") for segment in split_segments(message)]


def _first_segment(message: str, name: str) -> list[str] | None:
    for parts in _segments(message):
        if parts and parts[0] == name:
            return parts
    return None


def _field(parts: list[str] | None, field_number: int) -> str:
    """Return an HL7 field with correct MSH numbering.

    For ordinary segments, split('|')[n] is field n.
    For MSH, split('|')[1] is MSH-2 because the separator itself is MSH-1.
    Therefore MSH-n (n >= 2) is parts[n-1].
    """
    if not parts:
        return ""
    if parts[0] == "MSH":
        if field_number == 1:
            return "|"
        index = field_number - 1
    else:
        index = field_number
    return parts[index] if 0 <= index < len(parts) else ""


def _component(value: str, component_number: int) -> str:
    if not value:
        return ""
    components = value.split("^")
    index = component_number - 1
    return components[index] if 0 <= index < len(components) else ""


def _first_repetition(value: str) -> str:
    return value.split("~", 1)[0] if value else ""


def message_semantics(message: str) -> dict[str, str]:
    msh = _first_segment(message, "MSH")
    msh9 = _field(msh, 9)
    return {
        "message_code": _component(msh9, 1),
        "trigger_event": _component(msh9, 2),
        "root_schema": _component(msh9, 3),
    }


def message_signature(semantics: dict[str, str]) -> str:
    return "^".join(
        [
            semantics.get("message_code", ""),
            semantics.get("trigger_event", ""),
            semantics.get("root_schema", ""),
        ]
    ).rstrip("^")


def extract_targets(message: str) -> dict[str, str]:
    pid = _first_segment(message, "PID")
    pv1 = _first_segment(message, "PV1")

    pid3 = _first_repetition(_field(pid, 3))
    return {
        "mrn": _component(pid3, 1),
        "assigning_authority": _component(pid3, 4),
        "date_of_birth": _field(pid, 7),
        "pv1_44": _field(pv1, 44),
    }


@lru_cache(maxsize=4)
def _registry(schema_path: str):
    path = Path(schema_path)
    if not path.is_file():
        return None
    return load_iris_schema(str(path), version_hint="2.5")


def resolve_root_schema(
    root_schema: str,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> dict[str, Any]:
    path = Path(schema_path)
    registry = _registry(str(path))
    if not root_schema:
        return {
            "root_schema": "",
            "registry_available": registry is not None,
            "resolved": False,
            "registry_version": registry.version if registry else None,
        }

    resolved = bool(registry and root_schema in registry.messages)
    return {
        "root_schema": root_schema,
        "registry_available": registry is not None,
        "resolved": resolved,
        "registry_version": registry.version if registry else None,
    }


def analyze_hl7(
    hl7_text: str,
    *,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    example_limit: int = 3,
) -> dict[str, Any]:
    messages = split_messages(hl7_text)
    if not messages:
        raise ValueError("No HL7 messages beginning with MSH were found.")

    groups: dict[str, dict[str, Any]] = {}

    for message in messages:
        semantics = message_semantics(message)
        signature = message_signature(semantics)
        if not semantics["message_code"] or not semantics["trigger_event"]:
            raise ValueError(
                "Every profiled message must contain MSH-9.1 and MSH-9.2."
            )

        group = groups.setdefault(
            signature,
            {
                "signature": signature,
                "message_code": semantics["message_code"],
                "trigger_event": semantics["trigger_event"],
                "root_schema": semantics["root_schema"],
                "message_count": 0,
                "_values": {key: [] for key in TARGETS},
            },
        )
        group["message_count"] += 1
        values = extract_targets(message)
        for key, value in values.items():
            if value:
                group["_values"][key].append(value)

    rendered_groups: list[dict[str, Any]] = []
    for signature in sorted(groups):
        group = groups[signature]
        total = group["message_count"]
        fields: dict[str, Any] = {}

        for key, definition in TARGETS.items():
            values = group["_values"][key]
            counts = Counter(values)
            examples = list(dict.fromkeys(values))[:example_limit]
            fields[key] = {
                "label": definition["label"],
                "path": definition["path"],
                "recommended_format": definition["recommended_format"],
                "present": len(values),
                "total": total,
                "coverage_pct": round((len(values) / total) * 100.0, 1),
                "unique_values": len(counts),
                # Examples are deliberately transient and excluded from saved config.
                "examples": examples,
            }

        rendered_groups.append(
            {
                "signature": signature,
                "message_code": group["message_code"],
                "trigger_event": group["trigger_event"],
                "root_schema": group["root_schema"],
                "message_count": total,
                "schema_resolution": resolve_root_schema(
                    group["root_schema"],
                    schema_path=schema_path,
                ),
                "fields": fields,
            }
        )

    return {
        "message_count": len(messages),
        "group_count": len(rendered_groups),
        "groups": rendered_groups,
    }


def build_interface_record(
    group: dict[str, Any],
    *,
    pv1_44_meaning: str,
) -> dict[str, Any]:
    """Build the persistable, PHI-minimized record for one MSH-9 triplet."""
    fields = group["fields"]

    def verification(*keys: str) -> dict[str, Any]:
        return {
            key: {
                "path": fields[key]["path"],
                "messages_present": fields[key]["present"],
                "messages_total": fields[key]["total"],
                "coverage_pct": fields[key]["coverage_pct"],
            }
            for key in keys
        }

    return {
        "message_code": group["message_code"],
        "trigger_event": group["trigger_event"],
        "root_schema": group["root_schema"],
        "schema_resolution": dict(group["schema_resolution"]),
        "sample_message_count": group["message_count"],
        "mappings": {
            "patient_identifier": {
                "transaction_dictionary_message": "MRN / Assigning Authority",
                "recommended_format": {
                    "mrn": "PID-3.1",
                    "assigning_authority": "PID-3.4",
                },
                "data_element_destination": {
                    "mrn": "PID-3.1",
                    "assigning_authority": "PID-3.4",
                },
                "forerun_verification": verification(
                    "mrn",
                    "assigning_authority",
                ),
            },
            "date_of_birth": {
                "transaction_dictionary_message": "Date of Birth",
                "recommended_format": "PID-7",
                "data_element_destination": "PID-7",
                "forerun_verification": verification("date_of_birth")[
                    "date_of_birth"
                ],
            },
            "pv1_44": {
                "transaction_dictionary_message": pv1_44_meaning.strip(),
                "recommended_format": "PV1-44",
                "data_element_destination": "PV1-44",
                "forerun_verification": verification("pv1_44")["pv1_44"],
            },
        },
    }
