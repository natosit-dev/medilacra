from __future__ import annotations

import argparse
import json

from .client import SHNProviderClient
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
        help="Do not persist request/response evidence",
    )
    args = parser.parse_args()

    case = next(case for case in cases if case.id == args.test_id)
    client = None if case.manual else SHNProviderClient.from_environment()
    runner = ReferenceSuiteRunner(
        client=client,
        persist_artifacts=not args.no_artifacts,
    )
    result = runner.run(args.test_id)
    print(json.dumps(result.manifest(), indent=2, sort_keys=True))

    if result.manual:
        return 2
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
