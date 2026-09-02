from __future__ import annotations

import re
from typing import Any


UCUM_SYSTEM = "http://unitsofmeasure.org"
_DATE_TIME_TZ = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _references(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "reference" and isinstance(item, str):
                refs.append(item)
            else:
                refs.extend(_references(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_references(item))
    return refs


def _resources(bundle: dict[str, Any], resource_type: str | None = None) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            continue
        if resource_type is None or resource.get("resourceType") == resource_type:
            resources.append(resource)
    return resources


def _first_loinc_value(bundle: dict[str, Any], loinc: str) -> float | None:
    for obs in _resources(bundle, "Observation"):
        codings = ((obs.get("code") or {}).get("coding") or [])
        if not any(isinstance(c, dict) and c.get("system") == "http://loinc.org" and c.get("code") == loinc for c in codings):
            continue
        quantity = obs.get("valueQuantity")
        if isinstance(quantity, dict) and isinstance(quantity.get("value"), (int, float)):
            return float(quantity["value"])
    return None


def preflight_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Run local structural checks before external PIQI ingestion.

    PASS means the artifact is a self-contained Bundle whose resources/references can be
    inspected locally. It intentionally does not fail a mutant for information-quality
    defects such as a missing identifier or coding system; those are the subject of PIQI.
    """
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    is_bundle = isinstance(bundle, dict) and bundle.get("resourceType") == "Bundle"
    record("resourceType", is_bundle, f"resourceType={bundle.get('resourceType') if isinstance(bundle, dict) else None}")

    bundle_type = bundle.get("type") if isinstance(bundle, dict) else None
    record("bundle.type", bundle_type == "collection", f"type={bundle_type!r}; expected 'collection'")

    entries = bundle.get("entry") if isinstance(bundle, dict) else None
    entries_ok = isinstance(entries, list) and len(entries) > 0
    record("bundle.entry", entries_ok, f"entries={len(entries) if isinstance(entries, list) else 0}")

    malformed_entries: list[int] = []
    missing_full_urls: list[int] = []
    full_urls: list[str] = []
    resource_types: dict[str, int] = {}
    if isinstance(entries, list):
        for index, entry in enumerate(entries):
            resource = entry.get("resource") if isinstance(entry, dict) else None
            if not isinstance(resource, dict) or not resource.get("resourceType") or not resource.get("id"):
                malformed_entries.append(index)
                continue
            resource_type = str(resource["resourceType"])
            resource_types[resource_type] = resource_types.get(resource_type, 0) + 1
            full_url = entry.get("fullUrl") if isinstance(entry, dict) else None
            if not isinstance(full_url, str) or not full_url:
                missing_full_urls.append(index)
            else:
                full_urls.append(full_url)

    record(
        "entry.resources",
        not malformed_entries,
        "all entries contain resource.resourceType and resource.id"
        if not malformed_entries
        else f"malformed entry indexes={malformed_entries}",
    )
    record(
        "entry.fullUrl",
        not missing_full_urls,
        "all entries have fullUrl" if not missing_full_urls else f"missing fullUrl indexes={missing_full_urls}",
    )
    record(
        "entry.fullUrl.unique",
        len(full_urls) == len(set(full_urls)),
        f"fullUrls={len(full_urls)} unique={len(set(full_urls))}",
    )

    has_message_header = resource_types.get("MessageHeader", 0) > 0
    record(
        "collection.transport_boundary",
        not has_message_header,
        "no MessageHeader in PIQI collection" if not has_message_header else "MessageHeader remains in collection",
    )

    refs = _references(bundle)
    urn_refs = [ref for ref in refs if ref.startswith("urn:uuid:")]
    relative_refs = [ref for ref in refs if "/" in ref and not ref.startswith(("http://", "https://", "urn:"))]
    unresolved = sorted(set(urn_refs) - set(full_urls))
    record(
        "references.internal",
        not unresolved and not relative_refs,
        "all internal references resolve by fullUrl"
        if not unresolved and not relative_refs
        else f"unresolved_urn={unresolved}; relative_refs={relative_refs}",
    )

    passed = all(row["status"] == "PASS" for row in checks)
    return {
        "status": "PASS" if passed else "FAIL",
        "scope": "LOCAL_INGEST_SHAPE",
        "claim": "Self-contained FHIR collection shape; external PIQI ingest not yet exercised.",
        "checks": checks,
        "resource_types": resource_types,
    }


def control_quality_gate(bundle: dict[str, Any]) -> dict[str, Any]:
    """Check that the unmutated baseline is clean enough to function as experimental control.

    Unlike preflight_bundle(), these checks intentionally inspect information quality.
    They are applied to the baseline only, never used to reject an intentional mutant.
    """
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    structural = preflight_bundle(bundle)
    record("structural_preflight", structural["status"] == "PASS", structural["claim"])

    bad_encounters = []
    for resource in _resources(bundle, "Encounter"):
        coding = resource.get("class")
        if not isinstance(coding, dict) or not coding.get("system") or not coding.get("code"):
            bad_encounters.append(resource.get("id"))
    record(
        "encounter.class.coded",
        not bad_encounters,
        "all Encounter.class values are system-qualified" if not bad_encounters else f"bad encounter ids={bad_encounters}",
    )

    bad_quantities = []
    packed_strings = []
    unzoned_datetimes = []
    empty_extension_values = []
    for resource in _resources(bundle):
        resource_id = resource.get("id")
        for node in _walk(resource):
            if isinstance(node, dict):
                if node.get("valueString") == "":
                    empty_extension_values.append(resource_id)
                for key, item in node.items():
                    if isinstance(item, str) and key.endswith("DateTime") and "T" in item and not _DATE_TIME_TZ.search(item):
                        unzoned_datetimes.append(f"{resource_id}:{key}={item}")
        if resource.get("resourceType") == "Observation":
            raw = resource.get("valueString")
            if isinstance(raw, str) and raw.count("^") >= 2:
                packed_strings.append(resource_id)
            quantity = resource.get("valueQuantity")
            if isinstance(quantity, dict) and quantity.get("unit"):
                if quantity.get("system") != UCUM_SYSTEM or not quantity.get("code"):
                    bad_quantities.append(resource_id)

    record(
        "observation.quantity.ucum",
        not bad_quantities,
        "all coded quantities use UCUM" if not bad_quantities else f"bad observation ids={bad_quantities}",
    )
    record(
        "observation.coded_values",
        not packed_strings,
        "no caret-packed coded values remain in valueString" if not packed_strings else f"packed valueString observation ids={packed_strings}",
    )
    record(
        "datetime.timezone",
        not unzoned_datetimes,
        "all dateTimes with clock time include timezone" if not unzoned_datetimes else f"unzoned={unzoned_datetimes}",
    )
    record(
        "extensions.empty_values",
        not empty_extension_values,
        "no empty valueString elements remain" if not empty_extension_values else f"resource ids={sorted(set(empty_extension_values))}",
    )

    total = _first_loinc_value(bundle, "2093-3")
    ldl = _first_loinc_value(bundle, "13457-7")
    hdl = _first_loinc_value(bundle, "2085-9")
    if total is None or (ldl is None and hdl is None):
        record("lipid.plausibility", True, "lipid relationship not present in this baseline")
    else:
        components = [value for value in (ldl, hdl) if value is not None]
        plausible = all(total >= value for value in components)
        record(
            "lipid.plausibility",
            plausible,
            f"total={total}; ldl={ldl}; hdl={hdl}; total must not be lower than a component",
        )

    passed = all(row["status"] == "PASS" for row in checks)
    return {
        "status": "PASS" if passed else "FAIL",
        "scope": "CONTROL_QUALITY_GATE",
        "claim": "Baseline is clean with respect to the local PIQI control invariants checked here.",
        "checks": checks,
    }


def preflight_pair(baseline: dict[str, Any], mutant: dict[str, Any]) -> dict[str, Any]:
    baseline_result = preflight_bundle(baseline)
    mutant_result = preflight_bundle(mutant)
    return {
        "baseline": baseline_result,
        "mutant": mutant_result,
        "status": (
            "PASS"
            if baseline_result["status"] == "PASS" and mutant_result["status"] == "PASS"
            else "FAIL"
        ),
    }
