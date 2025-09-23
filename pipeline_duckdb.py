
# pipeline_duckdb.py
import os, re
from datetime import datetime, timezone
from typing import Optional, Dict


from hl7_demo.generators import gen_patient, gen_encounter, gen_transaction, gen_observation
from hl7_demo.reports import load_reports
from hl7_demo.messages import build_adt, build_oru, build_dft
from storage_duckdb_entities import (
    init_db, upsert_patient, upsert_encounter, upsert_observation, upsert_transaction, append_message, DEFAULT_DB_PATH
)

def run_and_persist(n_patients: int,
                    report_glob: str,
                    seed: Optional[int],
                    per_encounter: bool,
                    bulk: bool,
                    out_dir: str,
                    miles: int,
                    db_path: str = DEFAULT_DB_PATH) -> Dict[str,int]:
    import random
    from faker import Faker
    if seed is not None:
        random.seed(seed); Faker.seed(seed)

    os.makedirs(out_dir, exist_ok=True)
    init_db(db_path)
    reports = load_reports(report_glob)
    run_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{run_ts}"
    counts = {"ADT":0, "ORU":0, "DFT":0}

    for _ in range(n_patients):
        p = gen_patient()
        e = gen_encounter(p.patient_id)
        t = gen_transaction(e.encounter_id)
        report_row = reports.sample(n=1).iloc[0]
        o = gen_observation(e, report_row)

        # Persist
        upsert_patient(p.__dict__ if hasattr(p, "__dict__") else dict(p), db_path=db_path)
        upsert_encounter(e.__dict__ if hasattr(e, "__dict__") else dict(e), db_path=db_path)
        upsert_transaction(t.__dict__ if hasattr(t, "__dict__") else dict(t), db_path=db_path)
        upsert_observation(o.__dict__ if hasattr(o, "__dict__") else dict(o), db_path=db_path)

        # Build messages
        adt = build_adt(p, e, miles=miles, obs=o)
        oru = build_oru(p, e, [o])
        dft = build_dft(p, e, [t], [o])

        # Write
        safe_enc = re.sub(r"[^A-Za-z0-9_\\-]", "_", e.encounter_id)
        bulk_files = {
            "ADT": os.path.join(out_dir, f"ADT_{run_ts}.hl7"),
            "ORU": os.path.join(out_dir, f"ORU_{run_ts}.hl7"),
            "DFT": os.path.join(out_dir, f"DFT_{run_ts}.hl7"),
        }
        msgs = {"ADT": adt, "ORU": oru, "DFT": dft}
        if per_encounter:
            for name, msg in msgs.items():
                path = os.path.join(out_dir, f"{name}_{safe_enc}_{run_ts}.hl7")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(msg)
                counts[name] += 1
                _append_msg_row(run_id, name, path, msg, db_path)
        else:
            for name, msg in msgs.items():
                path = bulk_files[name]
                mode = "a" if os.path.exists(path) else "w"
                with open(path, mode, encoding="utf-8") as f:
                    if mode == "a":
                        f.write("\\n\\n")
                    f.write(msg)
                counts[name] += 1
                _append_msg_row(run_id, name, path, msg, db_path)

    return counts

def _append_msg_row(run_id: str, message_type: str, path: str, msg: str, db_path: str):
    first = msg.split("\\r", 1)[0]
    control_id = ""
    if first.startswith("MSH|"):
        parts = first.split("|")
        if len(parts) > 9:
            control_id = parts[9]
    import os, re
    name = os.path.basename(path)
    m = re.search(r"_(VN[0-9A-Z]+)_", name)
    enc = m.group(1) if m else name
    append_message({
        "run_id": run_id,
        "message_type": message_type,
        "control_id": control_id or name,
        "encounter_id": enc,
        "raw_hl7": msg,
        "written_path": os.path.abspath(path),
        "ingest_ts": datetime.utcnow(),
    }, db_path=db_path)
