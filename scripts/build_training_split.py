# scripts/build_training_split.py
import csv, json, random, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FB = ROOT / "data" / "coder_feedback.csv"
OUT = ROOT / "data" / "notes_with_labels.csv"

random.seed(42)

def main():
    rows = []
    with FB.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            text = json.loads(r["report_text"]) if r["report_text"] else ""
            icd = [c for c in r["icd_selected"].split("|") if c]
            cpt = [c for c in r["cpt_selected"].split("|") if c]
            if not text.strip():
                continue
            rows.append({
                "report_text": text,
                "icd_codes": "|".join(icd),
                "cpt_codes": "|".join(cpt),
                "service_line": r.get("service_line",""),
                "message_type": r.get("message_type","")
            })
    # simple encounter-level split: 80/10/10
    random.shuffle(rows)
    n = len(rows); n_train = int(0.8*n); n_dev = int(0.1*n)
    for i, r in enumerate(rows):
        r["split"] = "train" if i < n_train else ("dev" if i < n_train+n_dev else "test")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["report_text","icd_codes","cpt_codes","split","service_line","message_type"])
        w.writeheader(); w.writerows(rows)

if __name__ == "__main__":
    main()
