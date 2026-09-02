from __future__ import annotations

import copy
import hashlib
import json
import random
import re
from typing import Any


_PATH_TOKEN = re.compile(r"^(?P<key>[^\[\]]+)(?:\[(?P<index>\d+)\])?$")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _tokens(path: str) -> list[tuple[str, int | None]]:
    if not path:
        return []
    parsed: list[tuple[str, int | None]] = []
    for raw in path.split("."):
        match = _PATH_TOKEN.match(raw)
        if not match:
            raise ValueError(f"Unsupported FHIR path token: {raw!r}")
        index = match.group("index")
        parsed.append((match.group("key"), int(index) if index is not None else None))
    return parsed


def get_path(value: Any, path: str) -> Any:
    current = value
    for key, index in _tokens(path):
        if not isinstance(current, dict) or key not in current:
            raise KeyError(path)
        current = current[key]
        if index is not None:
            if not isinstance(current, list) or index >= len(current):
                raise KeyError(path)
            current = current[index]
    return current


def path_exists(value: Any, path: str) -> bool:
    try:
        get_path(value, path)
        return True
    except (KeyError, TypeError):
        return False


def _parent_for_path(value: Any, path: str) -> tuple[Any, str, int | None]:
    tokens = _tokens(path)
    if not tokens:
        raise ValueError("FHIR path may not be empty")

    current = value
    for key, index in tokens[:-1]:
        if not isinstance(current, dict) or key not in current:
            raise KeyError(path)
        current = current[key]
        if index is not None:
            if not isinstance(current, list) or index >= len(current):
                raise KeyError(path)
            current = current[index]
    final_key, final_index = tokens[-1]
    return current, final_key, final_index


def remove_path(value: Any, path: str) -> Any:
    parent, key, index = _parent_for_path(value, path)
    if not isinstance(parent, dict) or key not in parent:
        raise KeyError(path)
    if index is None:
        return parent.pop(key)

    target = parent[key]
    if not isinstance(target, list) or index >= len(target):
        raise KeyError(path)
    return target.pop(index)


def replace_path(value: Any, path: str, replacement: Any) -> Any:
    parent, key, index = _parent_for_path(value, path)
    if not isinstance(parent, dict) or key not in parent:
        raise KeyError(path)
    if index is None:
        before = parent[key]
        parent[key] = replacement
        return before

    target = parent[key]
    if not isinstance(target, list) or index >= len(target):
        raise KeyError(path)
    before = target[index]
    target[index] = replacement
    return before


def diff_json_paths(left: Any, right: Any, prefix: str = "") -> list[str]:
    """Return leaf-ish JSON paths that differ.

    The Connectathon mutations intentionally remove or replace a single dictionary path.
    This is not intended to be a general JSON Patch implementation; it exists to enforce
    the one-declared-mutation experiment boundary.
    """
    if type(left) is not type(right):
        return [prefix or "$ "]

    if isinstance(left, dict):
        differences: list[str] = []
        for key in sorted(set(left) | set(right)):
            child = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                differences.append(child)
            else:
                differences.extend(diff_json_paths(left[key], right[key], child))
        return differences

    if isinstance(left, list):
        if len(left) != len(right):
            return [prefix]
        differences: list[str] = []
        for index, (lval, rval) in enumerate(zip(left, right)):
            child = f"{prefix}[{index}]"
            differences.extend(diff_json_paths(lval, rval, child))
        return differences

    return [] if left == right else [prefix]


def _candidate_resources(bundle: dict[str, Any], resource_type: str, path: str) -> list[tuple[int, dict[str, Any]]]:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for entry_index, entry in enumerate(bundle.get("entry", [])):
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            continue
        if resource.get("resourceType") != resource_type:
            continue
        if path_exists(resource, path):
            candidates.append((entry_index, resource))
    return candidates


def apply_fhir_mutation(
    baseline_bundle: dict[str, Any],
    spec: dict[str, Any],
    mutation_seed: int = 666,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply one deterministic controlled mutation to a deep copy of a FHIR Bundle."""
    baseline_hash = sha256_json(baseline_bundle)
    mutant = copy.deepcopy(baseline_bundle)
    operator = spec["operator"]
    case_id = spec["case_id"]

    if operator == "control":
        manifest = {
            "case_id": case_id,
            "baseline_sha256": baseline_hash,
            "mutant_sha256": sha256_json(mutant),
            "mutation_seed": mutation_seed,
            "mutation": {
                "operator": "control",
                "resource": None,
                "resource_id": None,
                "entry_index": None,
                "path": None,
                "before": None,
                "after": None,
            },
            "expected": copy.deepcopy(spec.get("expected", {})),
            "changed_paths": [],
        }
        return mutant, manifest

    resource_type = spec["resource"]
    path = spec["path"]
    candidates = _candidate_resources(mutant, resource_type, path)
    if not candidates:
        raise ValueError(
            f"Case {case_id}: no {resource_type} resource contains path {path!r}"
        )

    rng = random.Random(mutation_seed)
    entry_index, target = rng.choice(candidates)
    before = copy.deepcopy(get_path(target, path))

    if operator in {"remove_element", "remove_coding_component"}:
        remove_path(target, path)
        after = None
    elif operator == "replace_value":
        if "replacement" not in spec:
            raise ValueError(f"Case {case_id}: replace_value requires replacement")
        replacement = copy.deepcopy(spec["replacement"])
        replace_path(target, path, replacement)
        after = copy.deepcopy(replacement)
    else:
        raise ValueError(f"Unsupported FHIR mutation operator: {operator}")

    changed_paths = diff_json_paths(baseline_bundle, mutant)
    mutant_hash = sha256_json(mutant)
    resource_id = target.get("id")

    manifest = {
        "case_id": case_id,
        "baseline_sha256": baseline_hash,
        "mutant_sha256": mutant_hash,
        "mutation_seed": mutation_seed,
        "mutation": {
            "operator": operator,
            "resource": resource_type,
            "resource_id": resource_id,
            "entry_index": entry_index,
            "path": path,
            "before": before,
            "after": after,
        },
        "expected": copy.deepcopy(spec.get("expected", {})),
        "changed_paths": changed_paths,
    }

    if sha256_json(baseline_bundle) != baseline_hash:
        raise AssertionError("Baseline FHIR Bundle was mutated in place")
    if mutant_hash == baseline_hash:
        raise AssertionError(f"Case {case_id} produced no mutation")
    if len(changed_paths) != 1:
        raise AssertionError(
            f"Case {case_id} changed {len(changed_paths)} JSON paths; expected exactly one: {changed_paths}"
        )

    return mutant, manifest
