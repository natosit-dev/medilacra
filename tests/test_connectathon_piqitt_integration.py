from __future__ import annotations

import os
from pathlib import Path

from connectathon.piqitt_bridge import convert_hl7_text
from connectathon.scenarios import build_scenario_pack, load_case


def _oru_message() -> str:
    return "\r".join(
        [
            r"MSH|^~\&|MEDILACRA|FAC|PIQITT|TEST|20260902100000||ORU^R01|MSG1|P|2.5",
            "PID|1||MRN1^^^FAC||Doe^Jane||19800101|F|||1 Main St^^Lowell^MA^01854",
            "PV1|1|I|WARD^101^A^FAC",
            "OBR|1|||4548-4^Hemoglobin A1c^LN",
            "OBX|1|NM|4548-4^Hemoglobin A1c^LN||6.1|%|||||F|||20260901100000",
        ]
    )


def test_real_piqitt_converter_can_feed_local_connectathon_pack(tmp_path: Path):
    piqitt_repo = os.environ.get("PIQITT_REPO")
    assert piqitt_repo, "PIQITT_REPO must point to the checked-out PIQITT Connectathon branch"

    bundle, metadata = convert_hl7_text(
        _oru_message(),
        message_index=1,
        piqitt_repo=piqitt_repo,
    )

    assert metadata["message_type"] == "ORU^R01"
    resource_types = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert "Patient" in resource_types
    assert "Observation" in resource_types

    run = build_scenario_pack(
        bundle,
        output_root=tmp_path,
        case_ids=[
            "case_000_control",
            "case_001_availability",
            "case_002_code_system",
            "case_003_invalid_member",
        ],
        mutation_seed=666,
        run_id="integration-run",
        source_metadata=metadata,
    )

    assert all(case["preflight"] == "PASS" for case in run["cases"])
    assert len(run["cases"]) == 4

    code_system_case = load_case(run["run_dir"], "case_002_code_system")
    assert code_system_case["manifest"]["changed_paths"]
    observation = next(
        entry["resource"]
        for entry in code_system_case["mutant"]["entry"]
        if entry["resource"]["resourceType"] == "Observation"
    )
    assert "system" not in observation["code"]["coding"][0]
