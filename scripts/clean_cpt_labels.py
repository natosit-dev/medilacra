# scripts/clean_cpt_labels.py
import csv
import re
import argparse
from pathlib import Path

DEFAULT_IN  = Path(__file__).resolve().parents[1] / "ref" / "cpt_labels.csv"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "ref" / "cpt_labels_clean.csv"

# Vague/administrative terms to exclude
EXCLUDE_PHRASES = {
    "unlisted", "unspecified", "not otherwise specified", "nos",
    "miscellaneous", "unclassified", "noncovered", "non covered",
    "category ii", "category iii", "temporary code", "investigational",
    "experimental", "supply", "kit", "device only", "pharmacy", "drug only"
}

# CPT numeric ranges (5-digit) by service line if you want to scope further
RANGES = {
    "all":      [(10000, 69990), (70010, 79999), (80000, 89999), (90000, 99999), (00100, 01999)],
    "radiology":[(70010, 79999)],   # imaging/IR
    "pathology":[(80000, 89999)],
    "medicine": [(90000, 99999)],
    "surgery":  [(10021, 69990)],
    "anesthesia":[(00100, 01999)],
    # add more if needed
}

def is_numeric_cpt(code: str) -> bool:
    return bool(re.fullmatch(r"\d{5}", code.strip()))

def in_ranges(code: str, ranges) -> bool:
    n = int(code)
    return any(lo <= n <= hi for lo, hi in ranges)

def looks_procedural(desc: str) -> bool:
    d = desc.lower()
    if any(p in d for p in EXCLUDE_PHRASES):
        return False
    return True

def clean(in_path: Path, out_path: Path, service_line: str = "all") -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    keep_ranges = RANGES.get(service_line.lower(), RANGES["all"])
    seen = set()
    kept = []

    with in_path.open("r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        # allow for either 'code,description' or any capitalization
        code_field = next((c for c in rdr.fieldnames if c.lower() == "code"), None)
        desc_field = next((c for c in rdr.fieldnames if c.lower() in {"description", "desc", "short_desc"}), None)
        if not code_field or not desc_field:
            raise ValueError("Expected columns 'code' and 'description' (case-insensitive)")

        for row in rdr:
            code = (row.get(code_field) or "").strip()
            desc = (row.get(desc_field) or "").strip()
            if not code or not desc:
                continue

            # Only true CPT numeric 5-digit codes
            if not is_numeric_cpt(code):
                continue

            # Optional: restrict to a service-line range
            if not in_ranges(code, keep_ranges):
                continue

            # Drop vague/admin codes
            if not looks_procedural(desc):
                continue

            key = (code, desc)
            if key in seen:
                continue
            seen.add(key)
            kept.append(key)

    kept.sort(key=lambda x: x[0])
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "description"])
        w.writerows(kept)

    return len(kept)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Clean CPT labels to clearly labeled procedures.")
    ap.add_argument("--in",  dest="in_path",  default=str(DEFAULT_IN),  help="Input CSV (code,description)")
    ap.add_argument("--out", dest="out_path", default=str(DEFAULT_OUT), help="Output cleaned CSV")
    ap.add_argument("--service-line", dest="svc", default="all",
                    choices=list(RANGES.keys()),
                    help="Optional filter to CPT ranges by service line")
    args = ap.parse_args()

    n = clean(Path(args.in_path), Path(args.out_path), args.svc)
    print(f"Wrote {n} cleaned CPT rows to {args.out_path}")
