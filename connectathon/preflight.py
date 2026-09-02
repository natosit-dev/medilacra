from __future__ import annotations

from typing import Any


def preflight_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Run deliberately small local checks before external PIQI ingestion.

    A PASS here means the artifact is locally well-shaped enough to submit. It does not
    claim conformance to US Core, the PIQI IG, or any external endpoint's ingestion rules.
    """
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    is_bundle = isinstance(bundle, dict) and bundle.get("resourceType") == "Bundle"
    record("resourceType", is_bundle, f"resourceType={bundle.get('resourceType') if isinstance(bundle, dict) else None}")

    bundle_type = bundle.get("type") if isinstance(bundle, dict) else None
    record("bundle.type", bool(bundle_type), f"type={bundle_type!r}")

    entries = bundle.get("entry") if isinstance(bundle, dict) else None
    entries_ok = isinstance(entries, list) and len(entries) > 0
    record("bundle.entry", entries_ok, f"entries={len(entries) if isinstance(entries, list) else 0}")

    malformed_entries = []
    resource_types: dict[str, int] = {}
    if isinstance(entries, list):
        for index, entry in enumerate(entries):
            resource = entry.get("resource") if isinstance(entry, dict) else None
            if not isinstance(resource, dict) or not resource.get("resourceType"):
                malformed_entries.append(index)
                continue
            resource_type = str(resource["resourceType"])
            resource_types[resource_type] = resource_types.get(resource_type, 0) + 1

    record(
        "entry.resources",
        not malformed_entries,
        "all entries contain resource.resourceType"
        if not malformed_entries
        else f"malformed entry indexes={malformed_entries}",
    )

    passed = all(row["status"] == "PASS" for row in checks)
    return {
        "status": "PASS" if passed else "FAIL",
        "scope": "LOCAL_ONLY",
        "claim": "Locally inspectable FHIR Bundle shape; external PIQI ingest not yet exercised.",
        "checks": checks,
        "resource_types": resource_types,
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
