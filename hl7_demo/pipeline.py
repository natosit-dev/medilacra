# pipeline_unified.py
# One script to generate HL7 (ADT/ORU/DFT) and optionally persist to DuckDB or nowhere.

import os, re, random
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple

# Import generators / message builders (supports package or local layout)
try:
    from hl7_demo.generators import gen_patient, gen_encounter, gen_transaction, gen_observation
    from hl7_demo.reports import load_reports
    from hl7_demo.messages import build_adt, build_oru, build_dft, build_orm_labs, build_oru_labs
except ModuleNotFoundError:
    from generators import gen_patient, gen_encounter, gen_transaction, gen_observation
    from reports import load_reports
    from .messages import build_adt, build_oru, build_dft, build_orm_labs, build_oru_labs

# Optional persistence backends
DUCK_OK = True
try:
    from storage_duckdb_entities import (
        init_db as duck_init,
        upsert_patient, upsert_encounter, upsert_observation, upsert_transaction,
        append_message as duck_append_message,
        DEFAULT_DB_PATH as DUCK_DEFAULT_DB_PATH,
    )
except Exception:
    DUCK_OK = False
    DUCK_DEFAULT_DB_PATH = "medilacra.duckdb"

# Delta-related code removed

def _safe_encounter_for_filename(encounter_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", encounter_id)


def _first_msh_and_control_id(raw_msg: str) -> Tuple[str, str]:
    first = raw_msg.split("\r", 1)[0].strip()
    ctrl = ""
    if first.startswith("MSH|"):
        parts = first.split("|")
        if len(parts) > 9:
            ctrl = parts[9]
    return first, ctrl or ""


def _collect_msg_row(run_id: str, message_type: str, path: str, msg: str) -> dict:
    first, ctrl = _first_msh_and_control_id(msg)
    name = os.path.basename(path)
    m = re.search(r"_(VN[0-9A-Z]+)_", name)
    enc = m.group(1) if m else name
    return {
        "run_id": run_id,
        "message_type": message_type,
        "control_id": ctrl or name,
        "encounter_id": enc,
        "raw_hl7": msg,
        "written_path": os.path.abspath(path),
    }


def run_pipeline(n_patients: int, report_glob: str, seed: Optional[int],
                 per_encounter: bool, bulk: bool, out_dir: str, miles: int,
                 add_places_obesity_obx: bool = False, add_unemployment_obx: bool = False,
                 include_labs: bool = True,
                 persist: str = "none",
                 duckdb_path: Optional[str] = None) -> Dict[str,int]:

    """
    Generate n_patients worth of ADT/ORU/DFT messages and optionally persist entities + message log.

    per_encounter=True  -> one file per encounter per message type
    per_encounter=False -> bulk files per message type for the run (appends)
    bulk is ignored if per_encounter=True (kept for API compatibility)

    persist:
      - "duckdb": upsert entities + append message log to DuckDB (storage_duckdb_entities)
      - "none"  : filesystem only (no DB persistence)
    """
    from faker import Faker

    if seed is not None:
        random.seed(seed); Faker.seed(seed)

    os.makedirs(out_dir, exist_ok=True)
    reports = load_reports(report_glob)

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{run_ts}"

    counts: Dict[str, int] = {"ADT": 0, "ORU": 0, "DFT": 0, "ORM":0, "ORU_LABS":0}

    # Prepare DuckDB if requested
    if persist == "duckdb":
        if not DUCK_OK:
            raise RuntimeError("DuckDB persistence requested, but storage_duckdb_entities is unavailable.")
        db_path = duckdb_path or DUCK_DEFAULT_DB_PATH
        duck_init(db_path)

    for _ in range(n_patients):
        # ---- Generate synthetic entities
        p = gen_patient()
        e = gen_encounter(p.patient_id)
        t = gen_transaction(e.encounter_id)
        report_row = reports.sample(n=1).iloc[0]
        o = gen_observation(e, report_row)

        # ---- Persist entities (DuckDB only)
        if persist == "duckdb":
            payload = lambda x: x.__dict__ if hasattr(x, "__dict__") else dict(x)
            upsert_patient(payload(p), db_path=db_path)
            upsert_encounter(payload(e), db_path=db_path)
            upsert_transaction(payload(t), db_path=db_path)
            upsert_observation(payload(o), db_path=db_path)

        # ---- Build HL7 messages
        adt = build_adt(p, e, miles=miles, obs=o,
                add_places_obesity_obx=add_places_obesity_obx,
                add_unemployment_obx=add_unemployment_obx)
        oru = build_oru(p, e, [o])
        dft = build_dft(p, e, [t], [o])

        # NEW: optional labs kept separate from ADT & narrative ORU
        if include_labs:
            orm_labs = build_orm_labs(p, e)
            oru_labs = build_oru_labs(p, e, start_set_id=20)

        # ---- Write files
        safe_enc = _safe_encounter_for_filename(e.encounter_id)
        # Fix: Add lab messages to the bulk file dictionary
        bulk_files = {
            "ADT": os.path.join(out_dir, f"ADT_{run_ts}.hl7"),
            "ORU": os.path.join(out_dir, f"ORU_{run_ts}.hl7"),
            "DFT": os.path.join(out_dir, f"DFT_{run_ts}.hl7"),
            "ORM": os.path.join(out_dir, f"ORM_{run_ts}.hl7"),
            "ORU_LABS": os.path.join(out_dir, f"ORU_LABS_{run_ts}.hl7"),
        }

        msgs = {"ADT": adt, "ORU": oru, "DFT": dft}
        if include_labs:
            msgs["ORM"] = orm_labs
            msgs["ORU_LABS"] = oru_labs

        if per_encounter:
            for name, msg in msgs.items():
                path = os.path.join(out_dir, f"{name}_{safe_enc}_{run_ts}.hl7")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(msg)
                counts[name] += 1

                # Collect bronze row for DB persistence
                if persist == "duckdb":
                    row = _collect_msg_row(run_id, name, path, msg)
                    duck_append_message(row, db_path=db_path)
        else:
            for name, msg in msgs.items():
                path = bulk_files[name]
                mode = "a" if os.path.exists(path) else "w"
                with open(path, mode, encoding="utf-8") as f:
                    if mode == "a":
                        f.write("\n\n")
                    f.write(msg)
                counts[name] += 1

                if persist == "duckdb":
                    row = _collect_msg_row(run_id, name, path, msg)
                    duck_append_message(row, db_path=db_path)

    return counts


# --- Backward-compatible aliases (keeps older pages/calls working) ---

def run_and_persist(
    n_patients: int,
    report_glob: str,
    seed: Optional[int],
    per_encounter: bool,
    bulk: bool,
    out_dir: str,
    miles: int,
    db_path: Optional[str] = None,
    # New flags accepted silently by older callers
    add_places_obesity_obx: bool = False,
    add_unemployment_obx: bool = False,
) -> Dict[str, int]:
    """
    Legacy name that behaves like the old DuckDB pipeline.
    Accepts the new SDOH flags to prevent TypeError in older call sites.
    """
    return run_pipeline(
        n_patients=n_patients,
        report_glob=report_glob,
        seed=seed,
        per_encounter=per_encounter,
        bulk=bulk,
        out_dir=out_dir,
        miles=miles,
        add_places_obesity_obx=add_places_obesity_obx,
        add_unemployment_obx=add_unemployment_obx,
        persist="duckdb",
        duckdb_path=db_path,
    )


# The entire log_recent_messages_to_bronze function has been removed.


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="MediLacra unified HL7 generator")
    ap.add_argument("--n", type=int, default=10, help="Number of patients")
    ap.add_argument("--reports", type=str, default="reports/*.csv", help="Glob for report CSVs")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--per-encounter", action="store_true", help="Write one file per encounter per type")
    ap.add_argument("--bulk", action="store_true", help="Append to nightly bulk files (ignored if --per-encounter)")
    ap.add_argument("--out", type=str, default="out", help="Output folder")
    ap.add_argument("--miles", type=int, default=0, help="Distance delta for SDOH logic in ADT")
    ap.add_argument("--add-places-obesity-obx", action="store_true", help="Emit Places/Obesity OBX in ADT")
    ap.add_argument("--add-unemployment-obx", action="store_true", help="Emit Unemployment OBX in ADT")
    ap.add_argument("--persist", choices=["duckdb", "none"], default="duckdb", help="Where to persist")
    ap.add_argument("--duckdb-path", type=str, default=None, help="DuckDB database path")
    args = ap.parse_args()

    counts = run_pipeline(
        n_patients=args.n,
        report_glob=args.reports,
        seed=args.seed,
        per_encounter=args.per_encounter,
        bulk=args.bulk,
        out_dir=args.out,
        miles=args.miles,
        add_places_obesity_obx=args.add_places_obesity_obx,
        add_unemployment_obx=args.add_unemployment_obx,
        persist=args.persist,
        duckdb_path=args.duckdb_path,
    )
    print("[DONE]", counts)