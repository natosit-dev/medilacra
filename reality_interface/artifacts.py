from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class RunArtifacts:
    run_id: str
    run_dir: Path
    source_path: Path
    manifest_path: Path
    validation_path: Path
    hl7_path: Path
    fhir_path: Path

    @property
    def source_filename(self) -> str:
        return self.source_path.name

    @property
    def source_location(self) -> str:
        return self.source_path.as_posix()


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid4().hex[:6]}"


def _paths(run_dir: Path, source_name: str, run_id: str) -> RunArtifacts:
    return RunArtifacts(
        run_id=run_id,
        run_dir=run_dir,
        source_path=run_dir / source_name,
        manifest_path=run_dir / "manifest.json",
        validation_path=run_dir / "validation.json",
        hl7_path=run_dir / "message.hl7",
        fhir_path=run_dir / "bundle.json",
    )


def create_run(
    source_path: str | Path,
    *,
    artifacts_root: str | Path = "artifacts/reality_interface",
) -> RunArtifacts:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(source)

    run_id = _new_run_id()
    run_dir = Path(artifacts_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    artifacts = _paths(run_dir, source.name, run_id)
    shutil.copy2(source, artifacts.source_path)
    return artifacts


def create_run_from_bytes(
    filename: str,
    data: bytes,
    *,
    artifacts_root: str | Path = "artifacts/reality_interface",
) -> RunArtifacts:
    safe_name = Path(filename).name or "source.wav"
    run_id = _new_run_id()
    run_dir = Path(artifacts_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    artifacts = _paths(run_dir, safe_name, run_id)
    artifacts.source_path.write_bytes(data)
    return artifacts


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_manifest(
    artifacts: RunArtifacts,
    *,
    source_metadata: dict[str, Any],
    analysis: dict[str, Any] | None = None,
    acquisition_band_hz: tuple[int, int] | None = (10, 300),
) -> dict[str, Any]:
    source = {
        "filename": artifacts.source_filename,
        "location": artifacts.source_location,
        "sha256": sha256_file(artifacts.source_path),
        **source_metadata,
    }
    if acquisition_band_hz is not None:
        source["acquisition_band_hz"] = list(acquisition_band_hz)

    payload: dict[str, Any] = {
        "run_id": artifacts.run_id,
        "source": source,
    }
    if analysis is not None:
        payload["analysis"] = analysis

    write_json(artifacts.manifest_path, payload)
    return payload
