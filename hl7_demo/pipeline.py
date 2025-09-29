# pipeline.py
# Unified generator for HL7 (ADT/ORU/DFT) with optional DuckDB persistence.
# Behavior unchanged; logging added for observability and easier debugging.

import os, re, random
from datetime import datetime
from typing import Optional, Dict, List, Tuple

# -----------------------------
# Logging (structured)
# -----------------------------
try:
    from utils.log_utils import get_logger  # package layout
except Exception:
    from .log_utils import get_logger  # script/local layout  # type: ignore

logger = get_logger(name="MediLacra", context={"component": "pipeline"})

# -----------------------------
# Imports: generators + builders
# Support both package and local execution layouts without changing behavior.
# -----------------------------
try:
    from hl7_demo.generators import gen_patient, gen_encounter, gen_transaction, gen_observation
    from hl7_demo.reports import load_reports
    from hl7_demo.messages import build_adt, build_oru, build_dft, build_orm_labs, build_oru_labs
except ModuleNotFoundError:
    try:
        from generators import gen_patient, gen_encounter, gen_transaction, gen_observation
        from reports import load_reports
        # Prefer local import if present; fall back to relative (package) import
        try:
            from messages import build_adt, build_oru, build_dft, build_orm_labs, build_oru_labs  # type: ignore
        except Exception:
            from .messages import build_adt, build_oru, build_dft, build_orm_labs, build_oru_labs  # type: ignore
    except Exception as e:
        logger.error("Failed to import generators/reports/messages", extra={"extra": {"error": str(e)}})
        raise

# -----------------------------
# Optional persistence backend (DuckDB)
# -----------------------------
DUCK_OK = True
try:
    from storage_duckdb_entities import (
        init_db as duck_init,
        upsert_patient, upsert_encounter, upsert_observation, upsert_transaction,
        append_message as duck_append_message,
        DEFAULT_DB_PATH as DUCK_DEFAULT_DB_PATH,
    )
    logger.info("DuckDB persistence module available", extra={"extra": {"default_db_path": "auto (module-provided)"}})
except Exception:
    DUCK_OK = False
    DUCK_DEFAULT_DB_PATH = "medilacra.duckdb"  # used only for messaging if persistence is disabled
    logger.warning("DuckDB persistence module unavailable; filesystem-only mode unless overridden")

# -----------------------------
# Small utilities (unchanged behavior)
# -----------------------------
def _safe_encounter_for_filename(encounter_id: str) -> str:
    """Sanitize encounter id for safe filename usage."""
    return re.sub(r"[^A-Za-z0-9_\-]", "_", encounter_id)

def _first_msh_and_control_id(raw_msg: str) -> Tuple[str, str]:
    """Return first MSH line and the message control ID (MSH-10) if present."""
    first = raw_msg.split("\r", 1)[0].strip()
    ctrl = ""
    if first.startswith("MSH|"):
        parts = first.split("|")
        if len(parts) > 9:
            ctrl = parts[9]
    return first, ctrl or ""

def _collect_msg_row(run_id: str, message_type: str, path: str, msg: str) -> dict:
    """Collect a row payload describing the written HL7 message for DB logging."""
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

# -----------------------------
# Core: run_pipeline
# -----------------------------
def run_pipeline(
    n_patients: int,
    report_glob: str,
    seed: Optional[int],
    per_encounter: bool,
    bulk: bool,
    out_dir: str,
    miles: int,
    add_places_obesity_obx: bool = False,
    add_unemployment_obx: bool = False,
    include_labs: bool = True,
    persist: str = "none",
    duckdb_path: Optional[str] = None
) -> Dict[str, int]:
    """
    Generate n_patients worth of ADT/ORU/DFT messages and optionally persist entities + message log.

    Modes (unchanged):
      per_encounter=True  -> one file per encounter per message type
      per_encounter=False -> bulk files per message type for the run (appends)
      bulk is ignored if per_encounter=True (kept for API compatibility)

    persist:
      - "duckdb": upsert entities + append message log using storage_duckdb_entities
      - "none"  : filesystem only (no DB persistence)
    """
    from faker import Faker  # local import to avoid module cost if unused by caller

    # ---- Seeding for reproducibility
    if seed is not None:
        random.seed(seed)
        Faker.seed(seed)
        logger.info("Randomness seeded", extra={"extra": {"seed": seed}})

    # ---- Prepare output folder + load report catalog
    os.makedirs(out_dir, exist_ok=True)
    logger.info("Output directory ready", extra={"extra": {"out_dir": os.path.abspath(out_dir)}})

    reports = load_reports(report_glob)
    logger.info("Reports loaded", extra={"extra": {"report_glob": report_glob, "report_rows": getattr(reports, 'shape', ('?', '?'))[0] if hasattr(reports, 'shape') else "unknown"}})

    # ---- Generate a run id (used in message log persistence)
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{run_ts}"

    # ---- Counters (return value)
    counts: Dict[str, int] = {"ADT": 0, "ORU": 0, "DFT": 0, "ORM": 0, "ORU_LABS": 0}

    # ---- Optional DuckDB init
    db_path = duckdb_path or DUCK_DEFAULT_DB_PATH
    if persist == "duckdb":
        if not DUCK_OK:
            logger.error("DuckDB persistence requested but module unavailable", extra={"extra": {"requested_path": db_path}})
            raise RuntimeError("DuckDB persistence requested, but storage_duckdb_entities is unavailable.")
        try:
            duck_init(db_path)
            logger.info("DuckDB initialized", extra={"extra": {"db_path": os.path.abspath(db_path)}})
        except Exception as e:
            logger.error("Failed to initialize DuckDB", extra={"extra": {"db_path": db_path, "error": str(e)}})
            raise

    # ---- Main generation loop
    logger.info("Starting pipeline run", extra={"extra": {
        "run_id": run_id,
        "n_patients": n_patients,
        "per_encounter": per_encounter,
        "bulk": bulk,
        "include_labs": include_labs,
        "persist": persist,
        "miles": miles,
        "sdoh_flags": {"places_obesity": add_places_obesity_obx, "unemployment": add_unemployment_obx},
    }})

    for idx in range(n_patients):
        try:
            # ---- Generate synthetic entities (one patient/encounter set)
            p = gen_patient()
            e = gen_encounter(p.patient_id)
            t = gen_transaction(e.encounter_id)
            report_row = reports.sample(n=1).iloc[0]
            o = gen_observation(e, report_row)

            logger.info("Entities generated", extra={"extra": {
                "i": idx + 1,
                "patient_id": getattr(p, "patient_id", None),
                "encounter_id": getattr(e, "encounter_id", None)
            }})

            # ---- Persist entities (DuckDB only)
            if persist == "duckdb":
                try:
                    payload = lambda x: x.__dict__ if hasattr(x, "__dict__") else dict(x)
                    upsert_patient(payload(p), db_path=db_path)
                    upsert_encounter(payload(e), db_path=db_path)
                    upsert_transaction(payload(t), db_path=db_path)
                    upsert_observation(payload(o), db_path=db_path)
                except Exception as pe:
                    logger.error("DuckDB entity upsert failed", extra={"extra": {"error": str(pe)}})
                    raise

            # ---- Build HL7 messages for this encounter
            adt = build_adt(
                p, e, miles=miles, obs=o,
                add_places_obesity_obx=add_places_obesity_obx,
                add_unemployment_obx=add_unemployment_obx
            )
            oru = build_oru(p, e, [o])
            dft = build_dft(p, e, [t], [o])

            # Optional separate lab messages (kept distinct from narrative ORU)
            orm_labs = None
            oru_labs = None
            if include_labs:
                orm_labs = build_orm_labs(p, e)
                oru_labs = build_oru_labs(p, e, start_set_id=20)

            # ---- File naming setup
            safe_enc = _safe_encounter_for_filename(e.encounter_id)
            bulk_files = {
                "ADT": os.path.join(out_dir, f"ADT_{run_ts}.hl7"),
                "ORU": os.path.join(out_dir, f"ORU_{run_ts}.hl7"),
                "DFT": os.path.join(out_dir, f"DFT_{run_ts}.hl7"),
                "ORM": os.path.join(out_dir, f"ORM_{run_ts}.hl7"),
                "ORU_LABS": os.path.join(out_dir, f"ORU_LABS_{run_ts}.hl7"),
            }

            # Collect messages to write for this encounter
            msgs: Dict[str, str] = {"ADT": adt, "ORU": oru, "DFT": dft}
            if include_labs and orm_labs and oru_labs:
                msgs["ORM"] = orm_labs
                msgs["ORU_LABS"] = oru_labs

            # ---- Write messages (per-encounter files or append to bulk)
            if per_encounter:
                for name, msg in msgs.items():
                    path = os.path.join(out_dir, f"{name}_{safe_enc}_{run_ts}.hl7")
                    try:
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(msg)
                        counts[name] += 1
                        logger.info("Wrote per-encounter file", extra={"extra": {"type": name, "path": path}})
                    except OSError as ioe:
                        # Common on Windows if the file is locked by another process
                        logger.error("File write failed (per-encounter)", extra={"extra": {"type": name, "path": path, "error": str(ioe)}})
                        raise

                    # Append a bronze-style message log row to DuckDB if requested
                    if persist == "duckdb":
                        try:
                            row = _collect_msg_row(run_id, name, path, msg)
                            duck_append_message(row, db_path=db_path)
                        except Exception as le:
                            logger.error("DuckDB message log append failed", extra={"extra": {"type": name, "path": path, "error": str(le)}})
                            raise
            else:
                for name, msg in msgs.items():
                    path = bulk_files[name]
                    mode = "a" if os.path.exists(path) else "w"
                    try:
                        with open(path, mode, encoding="utf-8") as f:
                            if mode == "a":
                                f.write("\n\n")  # blank lines between messages when appending
                            f.write(msg)
                        counts[name] += 1
                        logger.info("Wrote bulk file", extra={"extra": {"type": name, "path": path, "mode": mode}})
                    except OSError as ioe:
                        logger.error("File write failed (bulk)", extra={"extra": {"type": name, "path": path, "mode": mode, "error": str(ioe)}})
                        raise

                    if persist == "duckdb":
                        try:
                            row = _collect_msg_row(run_id, name, path, msg)
                            duck_append_message(row, db_path=db_path)
                        except Exception as le:
                            logger.error("DuckDB message log append failed", extra={"extra": {"type": name, "path": path, "error": str(le)}})
                            raise

        except Exception as e:
            # A single encounter failure is bubbled up (unchanged behavior),
            # but we include a detailed log entry to diagnose quickly.
            logger.error("Encounter processing failed", extra={"extra": {"i": idx + 1, "error": str(e)}})
            raise

    logger.info("Pipeline run complete", extra={"extra": {"run_id": run_id, "counts": counts}})
    return counts

# -----------------------------
# Backward-compatible alias
# -----------------------------
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
    Legacy entry point matching older callers (kept to avoid breaking pages).
    Accepts the new SDOH flags to prevent TypeError in older call sites.
    """
    logger.info("run_and_persist called (compatibility wrapper)")
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

# -----------------------------
# CLI (kept as-is except logs)
# -----------------------------
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

    logger.info("CLI invocation", extra={"extra": vars(args)})
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
    # Keep original behavior: print the final counts in CLI mode
    print("[DONE]", counts)
    logger.info("CLI run finished", extra={"extra": {"counts": counts}})
