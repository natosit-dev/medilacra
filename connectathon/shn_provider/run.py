from __future__ import annotations

import argparse
import json

from .client import SHNProviderClient
from .scenario import get_scenario, list_scenarios
from .workflow import ProviderWorkflow, cohort_rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the MediLacra provider-side SHN workflow"
    )
    parser.add_argument(
        "--scenario",
        default="lumbar-fusion-auth",
        choices=[scenario.id for scenario in list_scenarios()],
    )
    parser.add_argument("--seed", type=int, default=300)
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Build the CRD request without sending live traffic",
    )
    parser.add_argument(
        "--cohort-count",
        type=int,
        default=None,
        help="Run a live cohort cycling all configured scenarios",
    )
    args = parser.parse_args()

    client = None if args.build_only else SHNProviderClient.from_environment()
    workflow = ProviderWorkflow(client=client)

    if args.cohort_count is not None:
        if args.build_only:
            parser.error("--cohort-count requires live transport")
        cases = workflow.run_cohort(
            start_seed=args.seed,
            count=args.cohort_count,
        )
        print(json.dumps(cohort_rows(cases), indent=2, sort_keys=True))
        return 0 if all(case.status == "complete" for case in cases) else 1

    case = workflow.create_case(args.scenario, args.seed)
    if args.build_only:
        workflow.build_crd(case)
    else:
        workflow.run_to_completion(case)

    print(json.dumps(case.manifest(), indent=2, sort_keys=True))
    return 0 if case.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
