from __future__ import annotations

import copy
import re
import uuid
from typing import Any


FHIR_REFERENCE_NAMESPACE = uuid.UUID("f4b2f1d4-7793-4f32-b0d3-7c8d60ea6b43")
ACT_CODE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
UCUM_SYSTEM = "http://unitsofmeasure.org"

ENCOUNTER_CLASS_MAP = {
    "O": {"system": ACT_CODE_SYSTEM, "code": "AMB", "display": "ambulatory"},
    "I": {"system": ACT_CODE_SYSTEM, "code": "IMP", "display": "inpatient encounter"},
    "E": {"system": ACT_CODE_SYSTEM, "code": "EMER", "display": "emergency"},
}

CODE_SYSTEM_MAP = {
    "LN": "http://loinc.org",
    "LOINC": "http://loinc.org",
    "SCT": "http://snomed.info/sct",
    "SNOMEDCT": "http://snomed.info/sct",
    "SNOMED": "http://snomed.info/sct",
    "UCUM": UCUM_SYSTEM,
}

UCUM_BY_TEXT = {
    "mg/dL": ("mg/dL", "mg/dL"),
    "%": ("%", "%"),
    "U/L": ("U/L", "U/L"),
    "mg/L": ("mg/L", "mg/L"),
    "mmHg": ("mmHg", "mm[Hg]"),
    "mm[Hg]": ("mmHg", "mm[Hg]"),
    "kg/m2": ("kg/m2", "kg/m2"),
    "/min": ("/min", "/min"),
    "10*3/uL": ("10*3/uL", "10*3/uL"),
    "10^3/uL": ("10*3/uL", "10*3/uL"),
}

_DATE_TIME_TZ = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value if item is not None]
    return value


def _clean_extensions(resource: dict[str, Any]) -> int:
    removed = 0
    extensions = resource.get("extension")
    if not isinstance(extensions, list):
        return removed

    cleaned_outer: list[dict[str, Any]] = []
    for outer in extensions:
        if not isinstance(outer, dict):
            cleaned_outer.append(outer)
            continue
        nested = outer.get("extension")
        if isinstance(nested, list):
            cleaned_nested = []
            for item in nested:
                if isinstance(item, dict) and item.get("valueString") == "":
                    removed += 1
                    continue
                cleaned_nested.append(item)
            outer = dict(outer)
            outer["extension"] = cleaned_nested
            if not cleaned_nested and set(outer) <= {"url", "extension"}:
                removed += 1
                continue
        cleaned_outer.append(outer)

    if cleaned_outer:
        resource["extension"] = cleaned_outer
    else:
        resource.pop("extension", None)
    return removed


def _normalize_encounter_class(resource: dict[str, Any]) -> bool:
    if resource.get("resourceType") != "Encounter":
        return False
    coding = resource.get("class")
    if not isinstance(coding, dict):
        return False
    code = str(coding.get("code") or "").upper()
    mapped = ENCOUNTER_CLASS_MAP.get(code)
    if not mapped:
        return False
    if coding == mapped:
        return False
    resource["class"] = dict(mapped)
    return True


def _normalize_datetime_values(value: Any) -> int:
    changed = 0
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if isinstance(item, str) and key.endswith("DateTime") and "T" in item and not _DATE_TIME_TZ.search(item):
                value[key] = item + "Z"
                changed += 1
            else:
                changed += _normalize_datetime_values(item)
    elif isinstance(value, list):
        for item in value:
            changed += _normalize_datetime_values(item)
    return changed


def _coded_value_from_string(raw: str) -> dict[str, Any] | None:
    parts = raw.split("^")
    if len(parts) < 3:
        return None
    code, display, system_token = parts[0].strip(), parts[1].strip(), parts[2].strip()
    if not code or not system_token:
        return None
    system = CODE_SYSTEM_MAP.get(system_token.upper())
    if system is None:
        if system_token.upper() == "HL7":
            system = "urn:hl7v2:HL7"
        else:
            return None
    coding: dict[str, Any] = {"system": system, "code": code}
    if display:
        coding["display"] = display
    return {"coding": [coding]}


def _normalize_coded_value(resource: dict[str, Any]) -> bool:
    if resource.get("resourceType") != "Observation":
        return False
    raw = resource.get("valueString")
    if not isinstance(raw, str) or "^" not in raw:
        return False
    concept = _coded_value_from_string(raw)
    if concept is None:
        return False
    resource.pop("valueString", None)
    resource["valueCodeableConcept"] = concept
    return True


def _quantity_unit_for_observation(resource: dict[str, Any]) -> tuple[str, str] | None:
    quantity = resource.get("valueQuantity")
    if not isinstance(quantity, dict):
        return None

    coding = ((resource.get("code") or {}).get("coding") or [{}])[0]
    loinc = coding.get("code") if isinstance(coding, dict) else None
    raw_unit = str(quantity.get("unit") or "").strip()

    # The MediLacra WBC source historically emitted `10^3/uL` into an HL7 field,
    # which the v2 component delimiter reduced to `3/uL`. Recover the known LOINC unit.
    if loinc == "6690-2" and raw_unit in {"3/uL", "10^3/uL", "10*3/uL"}:
        return ("10*3/uL", "10*3/uL")

    return UCUM_BY_TEXT.get(raw_unit)


def _normalize_quantity(resource: dict[str, Any]) -> bool:
    if resource.get("resourceType") != "Observation":
        return False
    quantity = resource.get("valueQuantity")
    if not isinstance(quantity, dict):
        return False
    normalized = _quantity_unit_for_observation(resource)
    if normalized is None:
        return False
    display, code = normalized
    before = dict(quantity)
    quantity["unit"] = display
    quantity["system"] = UCUM_SYSTEM
    quantity["code"] = code
    return before != quantity


def _entry_full_url(resource: dict[str, Any]) -> str:
    resource_type = resource.get("resourceType")
    resource_id = resource.get("id")
    if not resource_type or not resource_id:
        raise ValueError("Every Connectathon Bundle resource must have resourceType and id before fullUrl assignment")
    stable_uuid = uuid.uuid5(FHIR_REFERENCE_NAMESPACE, f"{resource_type}/{resource_id}")
    return f"urn:uuid:{stable_uuid}"


def _rewrite_references(value: Any, reference_map: dict[str, str]) -> int:
    changed = 0
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "reference" and isinstance(item, str) and item in reference_map:
                value[key] = reference_map[item]
                changed += 1
            else:
                changed += _rewrite_references(item, reference_map)
    elif isinstance(value, list):
        for item in value:
            changed += _rewrite_references(item, reference_map)
    return changed


def prepare_control_bundle(raw_bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert PIQITT's transport-shaped Bundle into a self-contained PIQI test artifact.

    PIQITT remains responsible for HL7 -> FHIR materialization. This Connectathon-only
    normalization removes FHIR Messaging transport semantics that are outside the PIQI
    track, makes the Bundle self-contained, and repairs known representation issues that
    would otherwise contaminate the control case.
    """
    if raw_bundle.get("resourceType") != "Bundle":
        raise ValueError("PIQITT did not return a FHIR Bundle")

    bundle = copy.deepcopy(raw_bundle)
    report = {
        "raw_bundle_type": raw_bundle.get("type"),
        "bundle_type": "collection",
        "message_headers_removed": 0,
        "full_urls_added": 0,
        "references_rewritten": 0,
        "encounter_classes_mapped": 0,
        "coded_values_materialized": 0,
        "quantities_ucum_normalized": 0,
        "datetimes_zoned": 0,
        "empty_extensions_removed": 0,
    }

    entries = bundle.get("entry")
    if not isinstance(entries, list):
        raise ValueError("PIQITT Bundle has no entry list")

    retained_entries = []
    for entry in entries:
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if isinstance(resource, dict) and resource.get("resourceType") == "MessageHeader":
            report["message_headers_removed"] += 1
            continue
        retained_entries.append(entry)
    bundle["entry"] = retained_entries
    bundle["type"] = "collection"

    reference_map: dict[str, str] = {}
    for entry in retained_entries:
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            continue
        resource_type = resource.get("resourceType")
        resource_id = resource.get("id")
        full_url = _entry_full_url(resource)
        entry["fullUrl"] = full_url
        report["full_urls_added"] += 1
        reference_map[f"{resource_type}/{resource_id}"] = full_url

        report["empty_extensions_removed"] += _clean_extensions(resource)
        report["encounter_classes_mapped"] += int(_normalize_encounter_class(resource))
        report["coded_values_materialized"] += int(_normalize_coded_value(resource))
        report["quantities_ucum_normalized"] += int(_normalize_quantity(resource))
        report["datetimes_zoned"] += _normalize_datetime_values(resource)

    report["references_rewritten"] = _rewrite_references(bundle, reference_map)
    bundle = _drop_none(bundle)
    return bundle, report
