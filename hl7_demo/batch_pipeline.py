"""Experiment-oriented MediLacra batch generation.

This path keeps the current entity generators and message structure, while
exposing explicit cardinality controls similar to the structured-sparsity
experiments. External SDOH enrichment is intentionally excluded.
"""

from __future__ import annotations

import random
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from faker import Faker

from .batch_messages import (
    build_dft_batch,
    build_orm_labs_batch,
    build_oru_batch,
    build_oru_labs_batch,
)
from .generators import gen_encounter, gen_observation, gen_patient, gen_transaction
from .offline_adt import build_adt_offline
from .reports import load_reports


def _positive(name: str, value: int) -> int:
    if value < 1:
        raise ValueError(f"{name} must be >= 1; got {value}")
    return value


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", value)


def _write_message(path: Path, message: str, *, append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.exists() else "w"
    with path.open(mode, encoding="utf-8") as handle:
        if mode == "a":
            handle.write("\n\n")
        handle.write(message)


def run_batch_pipeline(
    *,
    patients: int = 100,
    encounters_per_patient: int = 1,
    observations_per_encounter: int = 1,
    transactions_per_encounter: int = 1,
    report_glob: str = "./input/reports/*.csv",
    seed: Optional[int] = None,
    out_dir: str = "./output",
    per_encounter: bool = False,
    include_labs: bool = True,
    include_vitals: bool = True,
    include_gender_harmony: bool = True,
    scenario_profile: dict | None = None,
) -> Dict[str, int]:
    """Generate linked MediLacra data using explicit cardinalities.

    One ADT, narrative ORU, and DFT is emitted per encounter. ORU and DFT
    aggregate the requested observations/transactions for that encounter.
    Optional lab ORM/ORU messages remain one pair per encounter.
    """

    patients = _positive("patients", patients)
    encounters_per_patient = _positive(
        "encounters_per_patient", encounters_per_patient
    )
    observations_per_encounter = _positive(
        "observations_per_encounter", observations_per_encounter
    )
    transactions_per_encounter = _positive(
        "transactions_per_encounter", transactions_per_encounter
    )

    if seed is not None:
        random.seed(seed)
        Faker.seed(seed)

    reports = load_reports(report_glob)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    counts: Dict[str, int] = {
        "PATIENT": 0,
        "ENCOUNTER": 0,
        "OBSERVATION": 0,
        "TRANSACTION": 0,
        "ADT": 0,
        "ORU": 0,
        "DFT": 0,
        "ORM": 0,
        "ORU_LABS": 0,
    }

    bulk_paths = {
        name: out_path / f"{name}_{run_ts}.hl7"
        for name in ("ADT", "ORU", "DFT", "ORM", "ORU_LABS")
    }

    for _ in range(patients):
        patient = gen_patient()
        counts["PATIENT"] += 1

        for _ in range(encounters_per_patient):
            encounter = gen_encounter(patient.patient_id, profile=scenario_profile)
            counts["ENCOUNTER"] += 1

            transactions = [
                gen_transaction(encounter.encounter_id)
                for _ in range(transactions_per_encounter)
            ]
            counts["TRANSACTION"] += len(transactions)

            replace = observations_per_encounter > len(reports)
            sampled_reports = reports.sample(
                n=observations_per_encounter,
                replace=replace,
            )
            observations = [
                gen_observation(encounter, report_row)
                for _, report_row in sampled_reports.iterrows()
            ]
            counts["OBSERVATION"] += len(observations)

            messages = {
                "ADT": build_adt_offline(
                    patient,
                    encounter,
                    tx=transactions[0] if transactions else None,
                    obs=observations[0] if observations else None,
                    include_vitals=include_vitals,
                    include_gender_harmony=include_gender_harmony,
                ),
                "ORU": build_oru_batch(patient, encounter, observations),
                "DFT": build_dft_batch(
                    patient,
                    encounter,
                    transactions,
                    observations,
                ),
            }

            if include_labs:
                messages["ORM"] = build_orm_labs_batch(patient, encounter)
                messages["ORU_LABS"] = build_oru_labs_batch(
                    patient,
                    encounter,
                    start_set_id=20,
                )

            safe_encounter = _safe_id(encounter.encounter_id)
            for message_type, message in messages.items():
                if per_encounter:
                    target = out_path / (
                        f"{message_type}_{safe_encounter}_{run_ts}.hl7"
                    )
                    _write_message(target, message, append=False)
                else:
                    _write_message(
                        bulk_paths[message_type],
                        message,
                        append=True,
                    )
                counts[message_type] += 1

    return counts
