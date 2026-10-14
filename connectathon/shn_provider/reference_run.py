from __future__ import annotations

import argparse
import json

from .client import SHNProviderClient
from .export import build_export_zip
from .reference_suite import ReferenceSuiteRunner
from .test_case import list_test_cases


def main() -> int:
    cases = list_test_cases()
    parser = argparse.ArgumentParser(
        description="Run an SHN Connectathon reference test case"
    )
    parser.add_argument(
        "test_id",
        choices=[case.id for case in cases],
        help="TP/TN test id",
    )
    parser.add_argument(
        "--no-artifacts",
        action="store_true",
        help="Do not persist request/response evidence or full logs",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Create a ZIP containing the complete run log and evidence",
    )
    args = parser.parse_args()

    case = next(case for case in cases if case.id == args.test_id)
    client = None if case.manual else SHNProviderClient.from_environment()
    runner = ReferenceSuiteRunner(
        client=client,
        persist_artifacts=not args.no_artifacts,
        execution_mode="cli",
    )
    result = runner.run(args.test_id)

    if args.export:
        if args.no_artifacts or not result.artifact_dir:
            raise SystemExit("--export requires persisted artifacts")
        export_path = build_export_zip(result.artifact_dir)
        result_manifest = result.manifest()
        result_manifest["export_path"] = str(export_path)
    else:
        result_manifest = result.manifest()

    print(json.dumps(result_manifest, indent=2, sort_keys=True))

    if result.manual:
        return 2
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
