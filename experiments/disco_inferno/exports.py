from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from types import FunctionType
from typing import Iterable
from zipfile import ZIP_DEFLATED, ZipFile

import duckdb
import pandas as pd

from hl7_demo import messages as hl7_messages
from hl7_demo.messages import (
    build_dft,
    build_orm_labs,
    build_oru,
    build_oru_labs,
)


def write_source_duckdb(model: dict[str, pd.DataFrame], db_path: Path) -> Path:
    """Write the untouched Beatrice tables into one DuckDB source-reality file."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    try:
        for table_name, frame in model.items():
            temp_name = f"_frame_{table_name}"
            con.register(temp_name, frame)
            con.execute(
                f'CREATE TABLE "{table_name}" AS SELECT * FROM "{temp_name}"'
            )
            con.unregister(temp_name)
    finally:
        con.close()
    return db_path


def _group_by_encounter(objects: Iterable[object]) -> dict[str, list[object]]:
    grouped: dict[str, list[object]] = defaultdict(list)
    for obj in objects:
        grouped[str(getattr(obj, "encounter_id"))].append(obj)
    return grouped


def _write_bulk(path: Path, messages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(messages), encoding="utf-8")


def _build_adt_for_export(
    patient: object,
    encounter: object,
    transaction: object | None,
    observation: object | None,
    *,
    include_sdoh: bool,
) -> str:
    """Build the normal ADT, optionally replacing slow SDOH lookups with neutral values.

    The fast path executes the existing build_adt function bytecode against a copied
    globals dictionary. This keeps normal MediLacra behavior untouched and avoids
    process-global monkeypatching while preserving all non-SDOH ADT generation.
    """

    if include_sdoh:
        return hl7_messages.build_adt(
            patient,
            encounter,
            tx=transaction,
            obs=observation,
        )

    fast_globals = dict(hl7_messages.build_adt.__globals__)
    fast_globals["get_air_quality_by_zip"] = lambda *_args, **_kwargs: None
    fast_globals["get_poverty_pct_by_zcta"] = lambda *_args, **_kwargs: 0.0

    fast_build_adt = FunctionType(
        hl7_messages.build_adt.__code__,
        fast_globals,
        name=hl7_messages.build_adt.__name__,
        argdefs=hl7_messages.build_adt.__defaults__,
        closure=hl7_messages.build_adt.__closure__,
    )
    fast_build_adt.__kwdefaults__ = hl7_messages.build_adt.__kwdefaults__

    return fast_build_adt(
        patient,
        encounter,
        tx=transaction,
        obs=observation,
        add_air_obx=False,
        add_poverty_obx=False,
        add_places_obesity_obx=False,
        add_unemployment_obx=False,
    )


def write_hl7_exports(
    cases: Iterable[object],
    output_dir: Path,
    *,
    run_id: str,
    include_labs: bool = True,
    include_sdoh: bool = True,
) -> dict[str, object]:
    """Project the untouched source reality into timestamped bulk HL7 files.

    One output file is written for each message family already produced by
    MediLacra's pipeline. Narrative ORU and laboratory ORU are kept distinct
    because the existing pipeline treats them as separate generated products.

    include_sdoh controls the slow public-data enrichment used by ADT output.
    When disabled, SDOH OBX output is omitted and vitals use neutral poverty/AQI
    lookup results while all other HL7 generation remains unchanged.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    messages: dict[str, list[str]] = {
        "ADT_A01": [],
        "ORU_R01": [],
        "DFT_P03": [],
    }
    if include_labs:
        messages["ORM_O01_LABS"] = []
        messages["ORU_R01_LABS"] = []

    for case in cases:
        patient = case.patient
        observations_by_encounter = _group_by_encounter(case.observations)
        transactions_by_encounter = _group_by_encounter(case.transactions)

        for encounter in case.encounters:
            encounter_id = str(encounter.encounter_id)
            observations = observations_by_encounter.get(encounter_id, [])
            transactions = transactions_by_encounter.get(encounter_id, [])
            primary_observation = observations[0] if observations else None
            primary_transaction = transactions[0] if transactions else None

            messages["ADT_A01"].append(
                _build_adt_for_export(
                    patient,
                    encounter,
                    primary_transaction,
                    primary_observation,
                    include_sdoh=include_sdoh,
                )
            )
            messages["ORU_R01"].append(
                build_oru(patient, encounter, observations)
            )
            messages["DFT_P03"].append(
                build_dft(patient, encounter, transactions, observations)
            )

            if include_labs:
                messages["ORM_O01_LABS"].append(
                    build_orm_labs(patient, encounter)
                )
                messages["ORU_R01_LABS"].append(
                    build_oru_labs(patient, encounter, start_set_id=20)
                )

    paths: dict[str, Path] = {}
    counts: dict[str, int] = {}
    for message_type, rendered_messages in messages.items():
        path = output_dir / f"{message_type}_{run_id}.hl7"
        _write_bulk(path, rendered_messages)
        paths[message_type] = path
        counts[message_type] = len(rendered_messages)

    return {"paths": paths, "counts": counts}


def write_bundle_zip(run_dir: Path, bundle_path: Path) -> Path:
    """Zip one completed experiment directory for convenient UI download."""

    if bundle_path.exists():
        bundle_path.unlink()

    with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if not path.is_file() or path == bundle_path:
                continue
            archive.write(path, path.relative_to(run_dir))
    return bundle_path
