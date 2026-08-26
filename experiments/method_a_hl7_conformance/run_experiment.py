from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from faker import Faker

from hl7_demo.generators import gen_encounter, gen_patient
from hl7_demo.segments import seg_evn, seg_msh, seg_pid, seg_pv1

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "source_registry.json"


def build_minimal_adt(patient, encounter) -> str:
    """Project existing MediLacra entities into a deliberately small ADT."""
    return "\r".join(
        [
            seg_msh("ADT^A01"),
            seg_evn(encounter, "A01"),
            seg_pid(patient),
            seg_pv1(encounter),
        ]
    ) + "\r"


def segment(message: str, name: str) -> list[str]:
    for line in message.replace("\n", "\r").split("\r"):
        if line.startswith(name + "|"):
            return line.split("|")
    return []


def field(parts: list[str], position: int) -> str | None:
    return parts[position] if len(parts) > position and parts[position] != "" else None


def parse_canonical(raw: dict) -> dict:
    msh = segment(raw["raw_payload"], "MSH")
    pid = segment(raw["raw_payload"], "PID")
    pv1 = segment(raw["raw_payload"], "PV1")
    return {
        "source_name": raw["source_name"],
        "source_record_id": raw["source_record_id"],
        "source_timestamp": raw["source_timestamp"],
        "patient_id": field(pid, 3),
        "event_type": field(msh, 8),
        "patient_class": field(pv1, 2),
        "visit_number": field(pv1, 19),
        "admit_datetime": field(pv1, 44),
        "discharge_datetime": field(pv1, 45),
    }


def write_source_surfaces(messages: list[dict], source_dir: Path) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)

    with (source_dir / "source_alpha.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["record_id", "payload", "received_at"])
        writer.writeheader()
        for i, row in enumerate(messages, 1):
            writer.writerow(
                {
                    "record_id": f"A{i:04d}",
                    "payload": row["message"],
                    "received_at": row["timestamp"],
                }
            )

    with (source_dir / "source_beta.jsonl").open("w", encoding="utf-8") as f:
        for i, row in enumerate(messages, 1):
            f.write(
                json.dumps(
                    {
                        "message_id": f"B{i:04d}",
                        "message_text": row["message"],
                        "created_at": row["timestamp"],
                    }
                )
                + "\n"
            )

    con = duckdb.connect(str(source_dir / "source_gamma.duckdb"))
    try:
        con.execute(
            "create or replace table inbound_messages(raw_id varchar, hl7 varchar, receive_ts varchar)"
        )
        con.executemany(
            "insert into inbound_messages values (?, ?, ?)",
            [
                (f"G{i:04d}", row["message"], row["timestamp"])
                for i, row in enumerate(messages, 1)
            ],
        )
    finally:
        con.close()


def load_sources(source_dir: Path) -> list[dict]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    raw_rows: list[dict] = []

    for source_name, cfg in registry.items():
        path = source_dir / cfg["path"]
        if cfg["adapter"] == "csv":
            with path.open(newline="", encoding="utf-8") as f:
                records = list(csv.DictReader(f))
        elif cfg["adapter"] == "jsonl":
            with path.open(encoding="utf-8") as f:
                records = [json.loads(line) for line in f if line.strip()]
        elif cfg["adapter"] == "duckdb":
            con = duckdb.connect(str(path), read_only=True)
            try:
                cols = [cfg["id_field"], cfg["payload_field"], cfg["timestamp_field"]]
                rows = con.execute(
                    f"select {', '.join(cols)} from {cfg['table']} order by {cfg['id_field']}"
                ).fetchall()
                records = [dict(zip(cols, row)) for row in rows]
            finally:
                con.close()
        else:
            raise ValueError(f"Unknown adapter: {cfg['adapter']}")

        for record in records:
            raw_rows.append(
                {
                    "source_name": source_name,
                    "source_record_id": record[cfg["id_field"]],
                    "source_timestamp": record[cfg["timestamp_field"]],
                    "raw_payload": record[cfg["payload_field"]],
                }
            )

    return raw_rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--output-dir", default=str(ROOT / "output"))
    args = parser.parse_args()

    random.seed(args.seed)
    Faker.seed(args.seed)
    out = Path(args.output_dir)
    source_dir = out / "sources"
    out.mkdir(parents=True, exist_ok=True)

    messages = []
    truth = []
    for _ in range(args.records):
        patient = gen_patient()
        encounter = gen_encounter(patient.patient_id)
        message = build_minimal_adt(patient, encounter)
        timestamp = datetime.now(timezone.utc).isoformat()
        messages.append({"message": message, "timestamp": timestamp})
        truth.append(
            {
                "patient_id": patient.patient_id,
                "visit_number": encounter.visit_number,
            }
        )

    write_source_surfaces(messages, source_dir)
    raw_rows = load_sources(source_dir)
    canonical = [parse_canonical(row) for row in raw_rows]

    expected_pairs = {(row["patient_id"], row["visit_number"]) for row in truth}
    actual_pairs = {(row["patient_id"], row["visit_number"]) for row in canonical}
    per_source = {}
    for row in canonical:
        per_source[row["source_name"]] = per_source.get(row["source_name"], 0) + 1

    validation = {
        "records_generated": args.records,
        "sources": 3,
        "raw_rows": len(raw_rows),
        "canonical_rows": len(canonical),
        "expected_rows": args.records * 3,
        "all_sources_complete": all(v == args.records for v in per_source.values()) and len(per_source) == 3,
        "raw_lineage_complete": all(row["source_name"] and row["source_record_id"] for row in canonical),
        "canonical_fields_populated": all(row["patient_id"] and row["visit_number"] and row["event_type"] for row in canonical),
        "reconciles_to_synthetic_truth": actual_pairs == expected_pairs,
        "unique_within_source": len({(r["source_name"], r["source_record_id"]) for r in canonical}) == len(canonical),
        "per_source_rows": per_source,
    }
    validation["pass"] = all(
        validation[key]
        for key in [
            "all_sources_complete",
            "raw_lineage_complete",
            "canonical_fields_populated",
            "reconciles_to_synthetic_truth",
            "unique_within_source",
        ]
    )

    write_csv(out / "raw_messages.csv", raw_rows)
    write_csv(out / "adt_events.csv", canonical)
    (out / "synthetic_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    (out / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
