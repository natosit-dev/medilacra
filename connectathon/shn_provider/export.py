from __future__ import annotations

import io
import zipfile
from pathlib import Path


README = """MediLacra SHN Full Test Log

This archive contains one synthetic SHN reference-suite run.

Files:
- run.json: complete nested execution record.
- events.jsonl: chronological machine-readable event stream.
- result.json: compact run result used by the existing harness.
- artifacts/: request, response, summary and transport evidence for each operation.

Credential values are intentionally excluded. The archive may contain synthetic
member identifiers, test payloads, payer responses, correlation identifiers and
operator-console trace links.

The log records observed behavior. A FAIL can mean the live endpoint behaved
differently from the test contract; it is not synonymous with transport failure.
"""


def build_export_zip(
    run_dir: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run directory not found: {run_dir}")

    export_dir = run_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = (
        Path(output_path)
        if output_path is not None
        else export_dir / f"medilacra-test-log-{run_dir.name}.zip"
    )

    with zipfile.ZipFile(
        target,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("README.txt", README)
        for name in ("run.json", "events.jsonl", "result.json"):
            path = run_dir / name
            if path.is_file():
                archive.write(path, name)

        operations = run_dir / "operations"
        if operations.is_dir():
            for path in sorted(operations.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(operations)
                    archive.write(path, Path("artifacts") / relative)
    return target


def export_zip_bytes(run_dir: str | Path) -> bytes:
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run directory not found: {run_dir}")

    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("README.txt", README)
        for name in ("run.json", "events.jsonl", "result.json"):
            path = run_dir / name
            if path.is_file():
                archive.writestr(name, path.read_bytes())

        operations = run_dir / "operations"
        if operations.is_dir():
            for path in sorted(operations.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(operations)
                    archive.writestr(
                        (Path("artifacts") / relative).as_posix(),
                        path.read_bytes(),
                    )
    return buffer.getvalue()
