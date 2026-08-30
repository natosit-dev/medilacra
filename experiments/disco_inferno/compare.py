from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


Model = Mapping[str, pd.DataFrame]


def model_summary(model: Model, label: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for table, frame in model.items():
        rows.append(
            {
                "model": label,
                "table": table,
                "rows": len(frame),
                "columns": len(frame.columns),
                "null_cells": int(frame.isna().sum().sum()),
                "exact_duplicate_rows": int(frame.duplicated(keep=False).sum()),
            }
        )
    return pd.DataFrame(rows)


def compare_models(beatrice: Model, inferno: Model, manifest: Mapping[str, Any]) -> pd.DataFrame:
    """Report direct, defensible damage measurements for one corruption arm."""

    table = manifest.get("table")
    operator = str(manifest.get("operator"))
    metrics: list[dict[str, Any]] = []

    for name in beatrice:
        if name not in inferno:
            raise KeyError(f"Inferno model is missing table: {name}")
        clean = beatrice[name]
        cursed = inferno[name]
        metrics.extend(
            [
                {"table": name, "metric": "rows", "beatrice": len(clean), "inferno": len(cursed), "delta": len(cursed) - len(clean)},
                {"table": name, "metric": "columns", "beatrice": len(clean.columns), "inferno": len(cursed.columns), "delta": len(cursed.columns) - len(clean.columns)},
                {"table": name, "metric": "null_cells", "beatrice": int(clean.isna().sum().sum()), "inferno": int(cursed.isna().sum().sum()), "delta": int(cursed.isna().sum().sum() - clean.isna().sum().sum())},
            ]
        )

    if table is not None:
        clean = beatrice[str(table)]
        cursed = inferno[str(table)]
        if operator == "drop_identifier":
            metrics.append(
                {
                    "table": table,
                    "metric": "explicit_references_removed",
                    "beatrice": int(manifest.get("references_removed", 0)),
                    "inferno": 0,
                    "delta": -int(manifest.get("references_removed", 0)),
                }
            )
        elif operator == "null_field":
            field = str(manifest["field"])
            clean_present = int(clean[field].notna().sum())
            cursed_present = int(cursed[field].notna().sum())
            metrics.append(
                {
                    "table": table,
                    "metric": f"{field}_values_present",
                    "beatrice": clean_present,
                    "inferno": cursed_present,
                    "delta": cursed_present - clean_present,
                }
            )
        elif operator == "duplicate_record":
            copies = int(manifest.get("copies_introduced", 0))
            metrics.append(
                {
                    "table": table,
                    "metric": "represented_rows_added",
                    "beatrice": 0,
                    "inferno": copies,
                    "delta": copies,
                }
            )

    return pd.DataFrame(metrics)


def control_is_zero(metrics: pd.DataFrame) -> bool:
    return bool((metrics["delta"] == 0).all())
