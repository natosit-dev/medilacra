from __future__ import annotations

import argparse
import json

from .collection import (
    build_collection_data,
    build_collection_zip,
    discover_runs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bundle recorded SHN reference-suite transaction logs "
            "without sending new SHN traffic"
        )
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all recorded reference-suite runs",
    )
    parser.add_argument(
        "--since",
        help="Include runs at or after YYYY-MM-DD or an ISO-8601 timestamp",
    )
    parser.add_argument(
        "--tests",
        nargs="+",
        help="Include only the listed test IDs, e.g. TP-01 TN-05",
    )
    parser.add_argument(
        "--kind",
        choices=["positive", "negative"],
        help="Include only positive or negative test runs",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Write the collection ZIP under the ignored results directory",
    )
    args = parser.parse_args()

    runs = discover_runs(
        since=args.since,
        test_ids=args.tests,
        kind=args.kind,
    )
    manifest, _transactions, _events = build_collection_data(runs)

    output = {
        "filters": {
            "all": args.all,
            "since": args.since,
            "tests": args.tests,
            "kind": args.kind,
        },
        "summary": manifest["summary"],
        "collection_id": manifest["collection_id"],
    }

    if args.export:
        path, _ = build_collection_zip(runs)
        output["export_path"] = str(path)

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
