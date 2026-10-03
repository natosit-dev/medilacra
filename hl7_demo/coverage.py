# coverage.py
# Deterministic employer-sponsored coverage assignment for MediLacra.
#
# YAML files describe the institutions and synthetic plan primitives that
# *can* be assigned. CoverageProfile records what was actually assigned to
# one synthetic patient.

from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Any, Dict, Mapping

import yaml

from .models import CoverageProfile, Patient


DEFAULT_CONFIG_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "coverage"
)


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load one coverage YAML file and require a mapping at the root."""
    if not path.exists():
        raise FileNotFoundError(
            f"Coverage configuration file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(
            f"Coverage configuration must be a mapping: {path}"
        )

    return data


def _require_mapping(
    data: Mapping[str, Any],
    key: str,
    source_name: str,
) -> Dict[str, Any]:
    value = data.get(key)

    if not isinstance(value, dict) or not value:
        raise ValueError(
            f"{source_name} must contain a non-empty '{key}' mapping"
        )

    return dict(value)


def load_coverage_config(
    config_dir: str | Path | None = None,
) -> Dict[str, Any]:
    """
    Load and minimally validate the employer coverage configuration.

    actual_plan_references in payers.yaml are deliberately documentation-only;
    assignment logic consumes only the payer identity itself.
    """
    root = (
        Path(config_dir)
        if config_dir is not None
        else DEFAULT_CONFIG_DIR
    )

    employer_doc = _load_yaml(root / "employers.yaml")
    payer_doc = _load_yaml(root / "payers.yaml")
    plan_doc = _load_yaml(root / "plans.yaml")
    assignment_doc = _load_yaml(root / "assignment.yaml")

    employers = _require_mapping(
        employer_doc,
        "employers",
        "employers.yaml",
    )
    payers = _require_mapping(
        payer_doc,
        "payers",
        "payers.yaml",
    )
    plans = _require_mapping(
        plan_doc,
        "plans",
        "plans.yaml",
    )
    assignment = _require_mapping(
        assignment_doc,
        "assignment",
        "assignment.yaml",
    )

    for employer_id, employer in employers.items():
        if not isinstance(employer, dict):
            raise ValueError(
                f"Employer {employer_id} must be a mapping"
            )
        if not employer.get("name"):
            raise ValueError(
                f"Employer {employer_id} is missing name"
            )

    for payer_id, payer in payers.items():
        if not isinstance(payer, dict):
            raise ValueError(
                f"Payer {payer_id} must be a mapping"
            )
        if not payer.get("name"):
            raise ValueError(
                f"Payer {payer_id} is missing name"
            )

    for plan_id, plan in plans.items():
        if not isinstance(plan, dict):
            raise ValueError(
                f"Plan {plan_id} must be a mapping"
            )
        if not plan.get("name") or not plan.get("plan_type"):
            raise ValueError(
                f"Plan {plan_id} requires name and plan_type"
            )

    defaults = assignment.get("defaults", {})
    identifiers = assignment.get("generated_identifiers", {})
    period = assignment.get("effective_period", {})

    if not defaults.get("worker_profile"):
        raise ValueError(
            "assignment.yaml is missing defaults.worker_profile"
        )

    if not defaults.get("subscriber_relationship"):
        raise ValueError(
            "assignment.yaml is missing defaults.subscriber_relationship"
        )

    for key in (
        "member_id_prefix",
        "group_number_prefix",
        "policy_number_prefix",
    ):
        if not identifiers.get(key):
            raise ValueError(
                f"assignment.yaml is missing generated_identifiers.{key}"
            )

    if not period.get("start_date") or not period.get("end_date"):
        raise ValueError(
            "assignment.yaml requires effective_period start_date and end_date"
        )

    return {
        "employers": employers,
        "payers": payers,
        "plans": plans,
        "assignment": assignment,
        "source_dir": str(root),
    }


def _stable_seed(
    patient_id: str,
    seed: int | str | None,
    namespace: str = "coverage",
) -> int:
    """
    Derive a stable integer seed without using Python's randomized hash().

    The resulting coverage stream is isolated from global random state and
    from unrelated synthetic generators.
    """
    seed_value = 0 if seed is None else seed
    material = (
        f"{seed_value}|{patient_id}|{namespace}"
    ).encode("utf-8")

    digest = hashlib.sha256(material).digest()

    return int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=False,
    )


def _make_coverage_rng(
    patient_id: str,
    seed: int | str | None,
) -> tuple[random.Random, int]:
    derived_seed = _stable_seed(
        patient_id=patient_id,
        seed=seed,
        namespace="coverage",
    )

    return random.Random(derived_seed), derived_seed


def _select_uniform(
    records: Mapping[str, Any],
    rng: random.Random,
    *,
    label: str,
) -> tuple[str, Dict[str, Any]]:
    if not records:
        raise ValueError(
            f"No {label} records are available for assignment"
        )

    # Sort IDs so YAML reordering alone does not change assignment.
    record_id = rng.choice(
        sorted(records.keys())
    )

    record = records[record_id]

    if not isinstance(record, dict):
        raise ValueError(
            f"{label} {record_id} must be a mapping"
        )

    return record_id, record


def _select_record(
    records: Mapping[str, Any],
    strategy: str,
    rng: random.Random,
    *,
    label: str,
) -> tuple[str, Dict[str, Any]]:
    normalized = (strategy or "uniform").strip().lower()

    if normalized != "uniform":
        raise ValueError(
            f"Unsupported {label} assignment strategy: {strategy}. "
            "MVP currently supports only 'uniform'."
        )

    return _select_uniform(
        records,
        rng,
        label=label,
    )


def _numeric_identifier(
    prefix: str,
    rng: random.Random,
    digits: int = 8,
) -> str:
    upper = 10 ** digits
    value = rng.randrange(upper)

    return f"{prefix}-{value:0{digits}d}"


def _group_number(
    prefix: str,
    employer_id: str,
    rng: random.Random,
) -> str:
    suffix = rng.randrange(1_000_000)

    return (
        f"{prefix}-{employer_id}-"
        f"{suffix:06d}"
    )


def _profile_id(
    *,
    patient_id: str,
    derived_seed: int,
    employer_id: str,
    payer_id: str,
    plan_id: str,
    effective_start: str,
    effective_end: str,
) -> str:
    material = "|".join(
        [
            patient_id,
            str(derived_seed),
            employer_id,
            payer_id,
            plan_id,
            effective_start,
            effective_end,
        ]
    ).encode("utf-8")

    token = (
        hashlib.sha256(material)
        .hexdigest()[:16]
        .upper()
    )

    return f"COV-{token}"


def assign_coverage_profile(
    patient: Patient,
    seed: int | str | None = None,
    *,
    config: Dict[str, Any] | None = None,
    config_dir: str | Path | None = None,
) -> CoverageProfile:
    """
    Assign one deterministic employer-sponsored CoverageProfile.

    The returned profile becomes authoritative for the coverage-enabled path.
    For backward compatibility, Patient.employer is synchronized to the
    selected employer and Patient.coverage_profile is populated.
    """
    if config is None:
        config = load_coverage_config(
            config_dir=config_dir
        )

    assignment = config["assignment"]

    rng, derived_seed = _make_coverage_rng(
        patient.patient_id,
        seed,
    )

    employer_strategy = (
        assignment.get("employer", {})
        .get("strategy", "uniform")
    )
    payer_strategy = (
        assignment.get("payer", {})
        .get("strategy", "uniform")
    )
    plan_strategy = (
        assignment.get("plan", {})
        .get("strategy", "uniform")
    )

    employer_id, employer = _select_record(
        config["employers"],
        employer_strategy,
        rng,
        label="employer",
    )

    payer_id, payer = _select_record(
        config["payers"],
        payer_strategy,
        rng,
        label="payer",
    )

    plan_id, plan = _select_record(
        config["plans"],
        plan_strategy,
        rng,
        label="plan",
    )

    defaults = assignment["defaults"]
    identifiers = assignment["generated_identifiers"]
    period = assignment["effective_period"]

    effective_start = str(period["start_date"])
    effective_end = str(period["end_date"])

    member_id = _numeric_identifier(
        identifiers["member_id_prefix"],
        rng,
    )

    group_number = _group_number(
        identifiers["group_number_prefix"],
        employer_id,
        rng,
    )

    policy_number = _numeric_identifier(
        identifiers["policy_number_prefix"],
        rng,
    )

    profile = CoverageProfile(
        coverage_profile_id=_profile_id(
            patient_id=patient.patient_id,
            derived_seed=derived_seed,
            employer_id=employer_id,
            payer_id=payer_id,
            plan_id=plan_id,
            effective_start=effective_start,
            effective_end=effective_end,
        ),
        patient_id=patient.patient_id,

        employer_id=employer_id,
        employer_name=str(employer["name"]),

        payer_id=payer_id,
        payer_name=str(payer["name"]),

        plan_id=plan_id,
        plan_name=str(plan["name"]),
        plan_type=str(plan["plan_type"]),

        worker_profile=str(
            defaults["worker_profile"]
        ),
        subscriber_relationship=str(
            defaults["subscriber_relationship"]
        ),

        member_id=member_id,
        group_number=group_number,
        policy_number=policy_number,

        effective_start=effective_start,
        effective_end=effective_end,

        employer_provenance=str(
            employer.get("provenance", {})
            .get("status", "unknown")
        ),
        payer_provenance=str(
            payer.get("provenance", {})
            .get("status", "unknown")
        ),
        employer_payer_provenance="synthetic",
        plan_provenance=str(
            plan.get("provenance", {})
            .get("status", "synthetic")
        ),

        assignment_seed=str(derived_seed),
    )

    # Compatibility projections. The CoverageProfile remains authoritative.
    patient.employer = profile.employer_name
    patient.coverage_profile = profile

    return profile
