# scripts/augment_negatives.py
import re, csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data" / "notes_with_labels.csv"
OUT = ROOT / "data" / "notes_with_labels_aug.csv"

SWAPS = [
    (r"\bCT\b", "MRI"), (r"\bMRI\b", "CT"),
    (r"\bchest\b", "knee"), (r"\bknee\b", "chest"),
    (r"\bhead\b", "abdomen"), (r"\babdomen\b", "head"),
    (r"\bx-?ray\b", "ultrasound"), (r"\bultrasound\b", "x-ray"),
]

def make_negatives(text, max_aug=2):
    outs = []
    t = text
    cnt = 0
    for pat, repl in SWAPS:
        t2 = re.sub(pat, repl, t, flags=re.IGNORECASE)
        if t2 != t:
            outs.append(t2); cnt += 1
            if cnt >= max_aug: break
    return outs

def main():
    with IN.open("r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)

    aug_rows = []
    for r in rows:
        # positives: keep as-is
        aug_rows.append(r)
        # negatives: same text but **empty CPT/ICD** (or subset), signals “don’t fire those”
        for neg in make_negatives(r["report_text"], max_aug=2):
            aug_rows.append({
                **r, "report_text": neg, "icd_codes": "", "cpt_codes": "", "split": r["split"]
            })

    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader(); w.writerows(aug_rows)

if __name__ == "__main__":
    main()
