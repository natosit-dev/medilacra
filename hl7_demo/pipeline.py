import os, re, random
from datetime import datetime
from typing import Optional, Dict
from faker import Faker
from .reports import load_reports
from .generators import gen_patient, gen_encounter, gen_transaction, gen_observation
from .messages import build_adt, build_oru, build_dft

def run_pipeline(n_patients: int, report_glob: str, seed: Optional[int], per_encounter: bool, bulk: bool, out_dir: str, miles: int) -> Dict[str,int]:
    print(f"[INFO] Starting pipeline: {n_patients} patients, output={out_dir}, bulk={bulk}, per_encounter={per_encounter}")
    if seed is not None:
        random.seed(seed); Faker.seed(seed)
    os.makedirs(out_dir, exist_ok=True)
    reports = load_reports(report_glob)
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    count = {"ADT":0, "ORU":0, "DFT":0}
    for _ in range(n_patients):
        p = gen_patient(); e = gen_encounter(p.patient_id); t = gen_transaction(e.encounter_id)
        report_row = reports.sample(n=1).iloc[0]; o = gen_observation(e, report_row)
        print(f"[INFO] Generated patient {p.patient_id}, encounter {e.encounter_id}, ZIP={p.zip_code}")
        adt = build_adt(p, e, miles=miles, obs=o); oru = build_oru(p, e, [o]); dft = build_dft(p, e, [t], [o])
        safe_enc = re.sub(r"[^A-Za-z0-9_\-]", "_", e.encounter_id)
        if per_encounter:
            for name, msg in [("ADT", adt), ("ORU", oru), ("DFT", dft)]:
                with open(os.path.join(out_dir, f"{name}_{safe_enc}_{run_ts}.hl7"), "w", encoding="utf-8") as f: f.write(msg)
                count[name] += 1
        else:
            bulk_files = {k: os.path.join(out_dir, f"{k}_{run_ts}.hl7") for k in ["ADT","ORU","DFT"]}
            for key, msg in [("ADT", adt), ("ORU", oru), ("DFT", dft)]:
                fname = bulk_files[key]; mode = "a" if os.path.exists(fname) else "w"
                with open(fname, mode, encoding="utf-8") as f:
                    if mode == "a": f.write("\n\n")
                    f.write(msg)
                count[key] += 1
    print(f"[WRITE] Wrote encounter {safe_enc}: ADT, ORU, DFT")
    return count

# In your Streamlit "Generate" page after run_pipeline returns counts
import glob, os, re
from datetime import datetime, timezone
from storage_delta import append_bronze_messages

def log_recent_messages_to_bronze(out_dir: str, run_id: str):
    now = datetime.now(timezone.utc)
    rows = []
    for p in glob.glob(os.path.join(out_dir, "*.hl7")):
        name = os.path.basename(p)
        # infer message_type, encounter_id, control_id from filename or content as you prefer
        mtype = "ADT" if name.startswith("ADT_") else "ORU" if name.startswith("ORU_") else "DFT"
        # If you want exact control_id, read the first MSH line; otherwise store filename-based surrogate
        with open(p, "r", encoding="utf-8") as f:
            first = f.readline().strip()
        # naive control id parse (MSH-10)
        ctrl = first.split("|")[9] if first.startswith("MSH|") and len(first.split("|")) > 9 else name
        enc = re.search(r"_(VN\w+)_", name)
        encounter_id = enc.group(1) if enc else name
        rows.append({
            "run_id": run_id,
            "message_type": mtype,
            "control_id": ctrl,
            "encounter_id": encounter_id,
            "raw_hl7": open(p, "r", encoding="utf-8").read(),
            "written_path": os.path.abspath(p),
            "ingest_ts": now,
        })
    if rows:
        n = append_bronze_messages(rows)
        return n
    return 0

