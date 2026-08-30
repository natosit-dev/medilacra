from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any, Mapping

import pandas as pd


Model = dict[str, pd.DataFrame]


@dataclass(frozen=True)
class CorruptionResult:
    """A cursed copy of a Beatrice model plus an exact corruption receipt."""

    model: Model
    manifest: dict[str, Any]


def copy_model(model: Mapping[str, pd.DataFrame]) -> Model:
    """Deep-copy the tabular model so ground truth is never mutated in place."""

    return {name: frame.copy(deep=True) for name, frame in model.items()}


def _require_table_field(model: Mapping[str, pd.DataFrame], table: str, field: str) -> pd.DataFrame:
    if table not in model:
        raise KeyError(f"Unknown table: {table}")
    frame = model[table]
    if field not in frame.columns:
        raise KeyError(f"Unknown field {table}.{field}")
    return frame


def _require_fraction(fraction: float) -> None:
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0.0 and 1.0 inclusive")


def _selection_count(row_count: int, fraction: float) -> int:
    return int(round(row_count * fraction))


def _record_labels(frame: pd.DataFrame, positions: list[int], identity_field: str | None) -> list[str]:
    if not positions:
        return []
    if identity_field is not None and identity_field in frame.columns:
        return [str(frame.iloc[pos][identity_field]) for pos in positions]
    return [str(pos) for pos in positions]


def control(model: Mapping[str, pd.DataFrame]) -> CorruptionResult:
    cursed = copy_model(model)
    return CorruptionResult(
        model=cursed,
        manifest={
            "operator": "control",
            "inferno_name": "Control",
            "table": None,
            "field": None,
            "fraction": 0.0,
            "source_rows": sum(len(frame) for frame in model.values()),
            "affected_rows": 0,
            "output_rows": sum(len(frame) for frame in cursed.values()),
            "affected_records": [],
        },
    )


def drop_identifier(
    model: Mapping[str, pd.DataFrame],
    table: str,
    field: str,
    *,
    identity_field: str | None = None,
) -> CorruptionResult:
    """Charon: remove an identifier/reference field from the representation."""

    source = _require_table_field(model, table, field)
    cursed = copy_model(model)
    labels = _record_labels(source, list(range(len(source))), identity_field)
    cursed[table] = cursed[table].drop(columns=[field])

    return CorruptionResult(
        model=cursed,
        manifest={
            "operator": "drop_identifier",
            "inferno_name": "Charon",
            "table": table,
            "field": field,
            "fraction": 1.0,
            "source_rows": len(source),
            "affected_rows": len(source),
            "output_rows": len(cursed[table]),
            "removed_columns": [field],
            "references_removed": int(source[field].notna().sum()),
            "affected_records": labels,
        },
    )


def null_field(
    model: Mapping[str, pd.DataFrame],
    table: str,
    field: str,
    fraction: float,
    rng: Random,
    *,
    identity_field: str | None = None,
) -> CorruptionResult:
    """Replace a deterministic fraction of existing values with NULL."""

    _require_fraction(fraction)
    source = _require_table_field(model, table, field)
    cursed = copy_model(model)

    eligible = [pos for pos in range(len(source)) if pd.notna(source.iloc[pos][field])]
    selected_count = min(_selection_count(len(source), fraction), len(eligible))
    positions = sorted(rng.sample(eligible, k=selected_count)) if selected_count else []
    labels = _record_labels(source, positions, identity_field)

    if positions:
        column_index = cursed[table].columns.get_loc(field)
        for pos in positions:
            cursed[table].iat[pos, column_index] = pd.NA

    return CorruptionResult(
        model=cursed,
        manifest={
            "operator": "null_field",
            "inferno_name": "Null",
            "table": table,
            "field": field,
            "fraction": fraction,
            "source_rows": len(source),
            "eligible_rows": len(eligible),
            "affected_rows": len(positions),
            "output_rows": len(cursed[table]),
            "affected_records": labels,
            "selected_positions": positions,
        },
    )


def duplicate_record(
    model: Mapping[str, pd.DataFrame],
    table: str,
    fraction: float,
    rng: Random,
    *,
    identity_field: str | None = None,
) -> CorruptionResult:
    """Cerberus: copy a deterministic fraction of source rows exactly."""

    _require_fraction(fraction)
    if table not in model:
        raise KeyError(f"Unknown table: {table}")
    source = model[table]
    cursed = copy_model(model)

    selected_count = _selection_count(len(source), fraction)
    positions = sorted(rng.sample(range(len(source)), k=selected_count)) if selected_count else []
    labels = _record_labels(source, positions, identity_field)

    if positions:
        copies = source.iloc[positions].copy(deep=True)
        cursed[table] = pd.concat([source.copy(deep=True), copies], ignore_index=True)

    return CorruptionResult(
        model=cursed,
        manifest={
            "operator": "duplicate_record",
            "inferno_name": "Cerberus",
            "table": table,
            "field": None,
            "fraction": fraction,
            "source_rows": len(source),
            "affected_rows": len(positions),
            "copies_introduced": len(positions),
            "output_rows": len(cursed[table]),
            "affected_records": labels,
            "selected_positions": positions,
        },
    )
