"""Experiment-oriented MediLacra batch generation.

This path keeps the current entity generators and message structure, while
exposing explicit cardinality controls similar to the structured-sparsity
experiments. External SDOH enrichment is intentionally excluded.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from faker import Faker
from rich.progress import track

from .batch_messages import (
    build_dft_batch,
    build_orm_labs_batch,
    build_oru_batch,
    build_oru_labs_batch,
)
from .generators import (
    choose_gender_harmony_values,
    gen_encounter,
    gen_observation,
    gen_patient,
    gen_transaction,
)
from .offline_adt import build_adt_offline
from .reports import load_reports


BULK_FLUSH_EVERY_PATIENTS = 1000


def _positive(name: str, value: int) -> int:
    if value < 1:
        raise ValueError(f"{name} must be >= 1; got {value}")
    return value


def _nonnegative(name: str, value: int) -> int:
    if value < 0:
        raise ValueError(f"{name} must be >= 0; got {value}")
    return value


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", value)


def _write_message(path: Path, message: str, *, append: bool) -> None:
    """Write one standalone/per-encounter message file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.exists() else "w"
    with path.open(mode, encoding="utf-8") as handle:
        if mode == "a":
            handle.write("\n\n")
        handle.write(message)


def _write_bulk_message(handle: TextIO, message: str, *, first: bool) -> None:
    """Write to an already-open bulk file handle."""
    if not first:
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
    show_progress: bool = True,
    scenario_profile: dict | None = None,
) -> Dict[str, Any]:
    """Generate linked MediLacra data using explicit cardinalities.

    One ADT, narrative ORU, and DFT is emitted per encounter. ORU and DFT
    aggregate the requested observations/transactions for that encounter.
    Optional lab ORM/ORU messages remain one pair per encounter.

    In bulk mode, each output file is opened once for the entire run instead
    of once per message. Handles are flushed periodically so files remain
    visibly current during long-running generation without paying repeated
    open/append/close overhead.

    Lightweight counters are accumulated during generation so the caller can
    report PID sex, diagnosis, and Gender Harmony distributions without a
    second pass over the generated HL7 files.
    """

    patients = _positive("patients", patients)
    encounters_per_patient = _positive(
        "encounters_per_patient", encounters_per_patient
    )
    observations_per_encounter = _nonnegative(
        "observations_per_encounter", observations_per_encounter
    )
    transactions_per_encounter = _nonnegative(
        "transactions_per_encounter", transactions_per_encounter
    )

    if seed is not None:
        random.seed(seed)
        Faker.seed(seed)

    reports = load_reports(report_glob)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    counts: Dict[str, Any] = {
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

    pid_sex = Counter()
    diagnoses = Counter()
    gender_identity = Counter()
    pronouns = Counter()
    spcu = Counter()

    active_message_types = ["ADT", "ORU", "DFT"]
    if include_labs:
        active_message_types.extend(["ORM", "ORU_LABS"])

    bulk_paths = {
        name: out_path / f"{name}_{run_ts}.hl7"
        for name in active_message_types
    }

    patient_iter = range(patients)
    if show_progress:
        patient_iter = track(
            patient_iter,
            total=patients,
            description="MediLacra batch",
            transient=False,
        )

    with ExitStack() as stack:
        bulk_handles: Dict[str, TextIO] = {}
        if not per_encounter:
            bulk_handles = {
                name: stack.enter_context(path.open("w", encoding="utf-8"))
                for name, path in bulk_paths.items()
            }

        for patient_index in patient_iter:
            patient = gen_patient()
            counts["PATIENT"] += 1
            pid_sex[getattr(patient, "sex", "") or "(blank)"] += 1

            for _ in range(encounters_per_patient):
                encounter = gen_encounter(
                    patient.patient_id,
                    profile=scenario_profile,
                )
                counts["ENCOUNTER"] += 1

                transactions = [
                    gen_transaction(encounter.encounter_id)
                    for _ in range(transactions_per_encounter)
                ]
                counts["TRANSACTION"] += len(transactions)

                if observations_per_encounter:
                    replace = observations_per_encounter > len(reports)
                    sampled_reports = reports.sample(
                        n=observations_per_encounter,
                        replace=replace,
                    )
                    observations = [
                        gen_observation(encounter, report_row)
                        for _, report_row in sampled_reports.iterrows()
                    ]
                else:
                    observations = []
                counts["OBSERVATION"] += len(observations)

                for observation in observations:
                    code = (getattr(observation, "icd_code", "") or "").strip()
                    description = (
                        getattr(observation, "icd_description", "") or ""
                    ).strip()
                    if code:
                        diagnoses[(code, description)] += 1

                gender_values = None
                if include_gender_harmony:
                    gender_values = choose_gender_harmony_values(
                        getattr(patient, "sex", ""),
                        match_bias=0.95,
                    )
                    gender_identity[gender_values["gi"]] += 1
                    pronouns[gender_values["pro"]] += 1
                    spcu[gender_values["spcu"]] += 1

                messages = {
                    "ADT": build_adt_offline(
                        patient,
                        encounter,
                        tx=transactions[0] if transactions else None,
                        obs=observations[0] if observations else None,
                        include_vitals=include_vitals,
                        include_gender_harmony=include_gender_harmony,
                        gender_values=gender_values,
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
                        _write_bulk_message(
                            bulk_handles[message_type],
                            message,
                            first=(counts[message_type] == 0),
                        )
                    counts[message_type] += 1

            if (
                not per_encounter
                and (patient_index + 1) % BULK_FLUSH_EVERY_PATIENTS == 0
            ):
                for handle in bulk_handles.values():
                    handle.flush()

        if not per_encounter:
            for handle in bulk_handles.values():
                handle.flush()

    counts["PID_SEX_DISTRIBUTION"] = dict(pid_sex)
    counts["TOP_DIAGNOSES"] = diagnoses.most_common(5)
    counts["GENDER_HARMONY_DISTRIBUTION"] = {
        "gender_identity": dict(gender_identity),
        "pronouns": dict(pronouns),
        "spcu": dict(spcu),
    }

    return counts
