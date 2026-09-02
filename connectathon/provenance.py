from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def git_revision(repo_path: str | Path) -> str | None:
    repo = Path(repo_path)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        revision = result.stdout.strip()
        return revision or None
    except Exception:
        return None


def _candidate_disco_run_dir(source_path: Path) -> Path | None:
    resolved = source_path.resolve()
    parts = list(resolved.parts)
    try:
        index = parts.index("disco_inferno")
    except ValueError:
        return None

    # Expected: .../experiments/disco_inferno/output/<run-id>/hl7/<file>
    suffix = parts[index:]
    if len(suffix) < 5 or suffix[1] != "output":
        return None
    return Path(*parts[: index + 3])


def disco_provenance(source_path: str | Path) -> dict[str, Any]:
    path = Path(source_path)
    run_dir = _candidate_disco_run_dir(path)
    if run_dir is None or not run_dir.exists():
        return {}

    manifests = sorted(run_dir.glob("manifest_*.json"))
    if not manifests:
        return {"disco_run_dir": str(run_dir), "disco_run_id": run_dir.name}

    manifest_path = manifests[-1]
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        payload = None

    provenance: dict[str, Any] = {
        "disco_run_dir": str(run_dir),
        "disco_run_id": run_dir.name,
        "disco_manifest": str(manifest_path),
        "disco_manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
    }
    if isinstance(payload, dict):
        settings = payload.get("settings")
        if isinstance(settings, dict):
            for key in ("reality_seed", "inferno_seed", "include_sdoh", "include_labs"):
                if key in settings:
                    provenance[key] = settings[key]
    return provenance


def build_source_provenance(
    hl7_text: str,
    source_name: str | None,
    medilacra_root: str | Path,
    piqitt_repo: str | Path,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "source_name": source_name,
        "source_hl7_sha256": sha256_text(hl7_text),
        "medilacra_revision": git_revision(medilacra_root),
        "piqitt_revision": git_revision(piqitt_repo),
    }
    if source_name:
        path = Path(source_name)
        if path.exists():
            provenance["source_file"] = str(path.resolve())
            provenance.update(disco_provenance(path))
    return provenance
