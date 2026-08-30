from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


def _rows(objects: Iterable[object]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for obj in objects:
        if not is_dataclass(obj):
            raise TypeError(f"Expected MediLacra dataclass object, got {type(obj)!r}")
        output.append(asdict(obj))
    return output


def materialize_cases(cases: Iterable[object]) -> dict[str, pd.DataFrame]:
    """Materialize the full MediLacra dataclasses as the Beatrice reference model."""

    patients: list[object] = []
    encounters: list[object] = []
    observations: list[object] = []
    transactions: list[object] = []

    for case in cases:
        patients.append(case.patient)
        encounters.extend(case.encounters)
        observations.extend(case.observations)
        transactions.extend(case.transactions)

    return {
        "patients": pd.DataFrame(_rows(patients)),
        "encounters": pd.DataFrame(_rows(encounters)),
        "observations": pd.DataFrame(_rows(observations)),
        "transactions": pd.DataFrame(_rows(transactions)),
    }


def save_model(model: dict[str, pd.DataFrame], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in model.items():
        frame.to_csv(directory / f"{name}.csv", index=False)
