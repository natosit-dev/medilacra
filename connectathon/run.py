from __future__ import annotations

import argparse
import json
from pathlib import Path

from connectathon.piqitt_bridge import convert_hl7_file, default_piqitt_repo
from connectathon.scenarios import DEFAULT_SCENARIOS, build_scenario_pack


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize one MediLacra HL7 message through PIQITT into a FHIR baseline, "
            "then build the local PIQI Connectathon control/mutant scenario pack."
        )
    )
    parser.add_argument("--input", required=True, help="HL7/.txt source file")
    parser.add_argument(
        "--piqitt-repo",
        default=str(default_piqitt_repo()),
        help="Local PIQITT checkout containing scripts/fhir_convert_backend.py",
    )
    parser.add_argument("--message-index", type=int, default=1, help="1-based HL7 message number")
    parser.add_argument("--mutation-seed", type=int, default=666)
    parser.add_argument("--output-root", default="connectathon/results")
    parser.add_argument(
        "--cases",
        nargs="*",
        default=[item["case_id"] for item in DEFAULT_SCENARIOS],
        help="Scenario case IDs; defaults to the full local MVP pack",
    )
    args = parser.parse_args()

    baseline, metadata = convert_hl7_file(
        args.input,
        message_index=args.message_index,
        piqitt_repo=args.piqitt_repo,
    )
    metadata["input"] = str(Path(args.input).resolve())

    result = build_scenario_pack(
        baseline,
        output_root=args.output_root,
        case_ids=args.cases,
        mutation_seed=args.mutation_seed,
        source_metadata=metadata,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
