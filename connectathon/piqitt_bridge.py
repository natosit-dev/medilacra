from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
from typing import Any

from connectathon.fhir_control import prepare_control_bundle


_BACKEND_CACHE: dict[str, ModuleType] = {}


def default_piqitt_repo() -> Path:
    """Return the most likely local PIQITT checkout without requiring it to be installed."""
    configured = os.getenv("PIQITT_REPO")
    if configured:
        return Path(configured).expanduser().resolve()

    medilacra_root = Path(__file__).resolve().parents[1]
    return (medilacra_root.parent / "piqitt").resolve()


def backend_path(piqitt_repo: str | Path | None = None) -> Path:
    repo = Path(piqitt_repo).expanduser().resolve() if piqitt_repo else default_piqitt_repo()
    return repo / "scripts" / "fhir_convert_backend.py"


def load_backend(piqitt_repo: str | Path | None = None) -> ModuleType:
    """Load PIQITT's existing converter directly from its checkout.

    This deliberately avoids copying PIQITT mapping code into MediLacra. The local PIQITT
    repository remains the source of truth for HL7 -> FHIR conversion.
    """
    path = backend_path(piqitt_repo)
    if not path.exists():
        raise FileNotFoundError(
            f"PIQITT converter not found at {path}. Set PIQITT_REPO or select the local PIQITT checkout."
        )

    cache_key = str(path)
    if cache_key in _BACKEND_CACHE:
        return _BACKEND_CACHE[cache_key]

    module_name = f"piqitt_fhir_convert_backend_{abs(hash(cache_key))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load PIQITT converter from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _BACKEND_CACHE[cache_key] = module
    return module


def inspect_hl7_text(hl7_text: str, piqitt_repo: str | Path | None = None) -> list[dict[str, Any]]:
    """Return message index/type information using PIQITT's parser without materializing FHIR."""
    backend = load_backend(piqitt_repo)
    messages = backend.split_messages(hl7_text)
    summary: list[dict[str, Any]] = []
    for index, message in enumerate(messages, start=1):
        parsed = backend.parse_hl7(message)
        summary.append(
            {
                "message_index": index,
                "message_type": backend.detect_message_type(parsed),
                "segment_count": len(backend.split_segments(message)),
            }
        )
    return summary


def convert_hl7_text(
    hl7_text: str,
    message_index: int = 1,
    piqitt_repo: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert one 1-based HL7 message to the PIQI Connectathon FHIR control representation.

    PIQITT performs the actual HL7 -> FHIR mapping. The Connectathon layer then removes
    message-transport semantics and normalizes the resulting Bundle into a self-contained
    collection suitable for baseline/mutation experiments.
    """
    backend = load_backend(piqitt_repo)
    messages = backend.split_messages(hl7_text)
    if not messages:
        raise ValueError("No HL7 messages beginning with MSH| were found.")
    if message_index < 1 or message_index > len(messages):
        raise IndexError(f"message_index {message_index} is outside 1..{len(messages)}")

    raw_bundle, message_type = backend.convert_message_to_bundle(messages[message_index - 1])
    bundle, cleanup = prepare_control_bundle(raw_bundle)
    metadata = {
        "message_index": message_index,
        "message_count": len(messages),
        "message_type": message_type,
        "piqitt_backend": str(backend_path(piqitt_repo)),
        "piqitt_raw_bundle_type": raw_bundle.get("type"),
        "connectathon_bundle_type": bundle.get("type"),
        "connectathon_cleanup": cleanup,
    }
    return bundle, metadata


def convert_hl7_file(
    input_path: str | Path,
    message_index: int = 1,
    piqitt_repo: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(input_path)
    raw = path.read_text(encoding="utf-8", errors="ignore")
    bundle, metadata = convert_hl7_text(raw, message_index=message_index, piqitt_repo=piqitt_repo)
    metadata["source_file"] = str(path.resolve())
    return bundle, metadata
