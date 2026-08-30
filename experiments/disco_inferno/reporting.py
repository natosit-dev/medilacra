from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    if not columns:
        return "(no metrics)"
    header = "| " + " | ".join(str(c) for c in columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    rows = []
    for _, row in frame.iterrows():
        rows.append("| " + " | ".join(str(row[c]) for c in columns) + " |")
    return "\n".join([header, divider, *rows])


def _comparison_table(metrics: pd.DataFrame) -> str:
    focus = metrics[(metrics["delta"] != 0) | (metrics["metric"] == "rows")].copy()
    if focus.empty:
        focus = metrics.copy()
    return _markdown_table(focus)


def render_arm_report(name: str, manifest: Mapping[str, Any], metrics: pd.DataFrame) -> str:
    table = manifest.get("table") or "—"
    field = manifest.get("field") or "—"
    fraction = float(manifest.get("fraction", 0.0))
    return (
        f"## {name}\n\n"
        f"- Operator: `{manifest.get('operator')}`\n"
        f"- Target table: `{table}`\n"
        f"- Target field: `{field}`\n"
        f"- Intensity: {fraction:.1%}\n"
        f"- Affected rows: {int(manifest.get('affected_rows', 0))}\n\n"
        f"{_comparison_table(metrics)}\n"
    )


def render_report(
    *,
    run_id: str,
    reality_seed: int,
    inferno_seed: int,
    counts: Mapping[str, int],
    arms: Mapping[str, tuple[Mapping[str, Any], pd.DataFrame]],
) -> str:
    sections = [
        "# Disco Inferno — Beatrice vs Inferno",
        "",
        f"**Run ID:** `{run_id}`  ",
        f"**Reality seed:** `{reality_seed}`  ",
        f"**Inferno seed:** `{inferno_seed}`  ",
        "**Judge:** Minos",
        "",
        "## Source Reality",
        "",
        "| Entity | Count |",
        "|---|---:|",
    ]
    sections.extend(f"| {name} | {count:,} |" for name, count in counts.items())
    sections.extend(
        [
            "",
            "> Beatrice is the untouched faithful representation of the generated MediLacra reality. Inferno is a corrupted copy of that same model.",
            "",
        ]
    )
    for name, (manifest, metrics) in arms.items():
        sections.append(render_arm_report(name, manifest, metrics))
    sections.extend(
        [
            "## Interpretation Boundary",
            "",
            "This MVP reports direct representational damage only. It does **not** assign a universal entropy score or claim that the measured deltas exhaust what can be inferred from the cursed representation.",
            "",
        ]
    )
    return "\n".join(sections)


def write_report(path: Path, report: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
