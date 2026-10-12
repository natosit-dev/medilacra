from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path
from typing import Any

from utils.scenario_profile import VISIT_CLASSES, compute_pv1_fields


DEFAULT_PROFILE_DIR = Path("data/scenario_profiles")
LOCATION_TYPES = [
    "ICU",
    "MEDSURG",
    "ED",
    "OR",
    "CLINIC",
    "LAB",
    "RAD",
    "OBS",
    "OTHER",
]


def default_profile() -> dict[str, Any]:
    """Return the existing site-generation model with an empty interface layer."""
    return {
        "profile_version": "2.0",
        "profile_name": "New Site Profile",
        "description": "",
        "notes": "Site generation model plus HL7 interface profile.",
        "facilities": [],
        "departments": [],
        "visit_mix": {
            "IP": 25,
            "OP": 40,
            "ED": 20,
            "OBS": 10,
            "AS": 3,
            "CL": 2,
        },
        "routing": {
            "IP": {
                "location_types": {"MEDSURG": 80, "ICU": 20},
                "default_department_code": "MED",
            },
            "OP": {
                "location_types": {"CLINIC": 70, "RAD": 30},
                "default_department_code": "MED",
            },
            "ED": {
                "location_types": {"ED": 100},
                "default_department_code": "ED",
            },
            "OBS": {
                "location_types": {"OBS": 80, "MEDSURG": 20},
                "default_department_code": "MED",
            },
            "AS": {
                "location_types": {"OR": 100},
                "default_department_code": "SUR",
            },
            "CL": {
                "location_types": {"CLINIC": 100},
                "default_department_code": "MED",
            },
        },
        "interfaces": {},
        "preview_seed": 1234,
        "provenance": {
            "format": "medilacra-site-profile",
            "config_format": "json",
        },
    }


def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Add new profile keys without changing the old site/generation grain."""
    normalized = dict(profile or {})
    normalized.setdefault("profile_version", "2.0")
    normalized.setdefault("profile_name", "Site Profile")
    normalized.setdefault("description", "")
    normalized.setdefault("notes", "")
    normalized.setdefault("facilities", [])
    normalized.setdefault("departments", [])
    normalized.setdefault("visit_mix", {})
    normalized.setdefault("routing", {})
    normalized.setdefault("interfaces", {})
    normalized.setdefault("preview_seed", 1234)
    normalized.setdefault(
        "provenance",
        {
            "format": "medilacra-site-profile",
            "config_format": "json",
        },
    )
    return normalized


def _profile_dir(profile_dir: str | Path | None = None) -> Path:
    path = Path(profile_dir) if profile_dir is not None else DEFAULT_PROFILE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_profiles(profile_dir: str | Path | None = None) -> list[str]:
    path = _profile_dir(profile_dir)
    return sorted(
        child.name
        for child in path.iterdir()
        if child.is_file() and child.suffix.lower() in {".json", ".yaml", ".yml"}
    )


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    return safe.strip("._") or "Site_Profile"


def profile_path(
    name: str,
    profile_dir: str | Path | None = None,
) -> Path:
    return _profile_dir(profile_dir) / f"{_safe_name(name)}.json"


def load_profile(
    filename: str,
    profile_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = _profile_dir(profile_dir) / filename
    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                "PyYAML is required to read legacy site profiles"
            ) from exc
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        raise ValueError(f"unsupported profile format: {path.suffix}")

    if not isinstance(data, dict):
        raise ValueError(f"profile root must be an object: {path}")
    return normalize_profile(data)


def save_profile(
    profile: dict[str, Any],
    name_override: str | None = None,
    profile_dir: str | Path | None = None,
) -> str:
    """Save new/edited profiles as JSON. Raw HL7 is never part of this contract."""
    normalized = normalize_profile(profile)
    name = name_override or normalized.get("profile_name") or "Site Profile"
    path = profile_path(str(name), profile_dir)
    path.write_text(
        json.dumps(normalized, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return path.name


def validate_profile(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    profile = normalize_profile(profile)

    facilities = profile.get("facilities") or []
    departments = profile.get("departments") or []
    visit_mix = profile.get("visit_mix") or {}
    routing = profile.get("routing") or {}

    if not facilities:
        errors.append("At least one facility is required.")
    elif not any((facility.get("locations") or []) for facility in facilities):
        errors.append("At least one location across all facilities is required.")

    if not departments:
        errors.append("At least one department is required.")

    try:
        total = sum(float(visit_mix.get(vc, 0)) for vc in VISIT_CLASSES)
    except (TypeError, ValueError):
        errors.append("Visit mix weights must be numeric.")
        total = 0.0
    if round(total, 4) != 100.0:
        errors.append(f"Visit mix must sum to 100. Current sum: {total}")

    dept_codes = {
        department.get("department_code")
        for department in departments
        if department.get("department_code")
    }
    valid_location_types = set(LOCATION_TYPES)

    for visit_class, rule in routing.items():
        if visit_class not in VISIT_CLASSES:
            errors.append(f"Unknown visit class in routing: {visit_class}")
            continue
        for location_type in (rule or {}).get("location_types", {}):
            if location_type not in valid_location_types:
                errors.append(
                    f"Routing for {visit_class} references unknown "
                    f"location_type: {location_type}"
                )
        default_department = (rule or {}).get("default_department_code")
        if default_department and default_department not in dept_codes:
            errors.append(
                f"Routing for {visit_class} references unknown "
                f"department_code: {default_department}"
            )

    if not isinstance(profile.get("interfaces"), dict):
        errors.append("interfaces must be a JSON object.")

    return errors


def generate_preview(
    profile: dict[str, Any],
    n: int = 10,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    if seed is not None:
        random.seed(seed)
    return [compute_pv1_fields(profile) for _ in range(max(0, int(n)))]
