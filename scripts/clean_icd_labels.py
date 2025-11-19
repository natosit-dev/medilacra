# scripts/clean_icd_labels.py
import csv
import re
import argparse
from pathlib import Path

DEFAULT_IN  = Path(__file__).resolve().parents[1] / "ref" / "icd_labels.csv"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "ref" / "icd_labels_clean.csv"

# Phrases that generally indicate low-signal labels; adjust with flags
DEFAULT_EXCLUDE = {
    "unspecified", "not otherwise specified", "nos",
    "unspecified site", "unspecified location",
    "unspecified laterality", "unspecified eye", "unspecified ear",
    "other specified", "other, specified",
}

# ICD-10-CM code shape:
#   1st char: A–T,V–Z    (U reserved/rare; allow A–Z except U for safety)
#   2nd char: 0–9
#   rest: A–Z or 0–9, optional dot with up to 4 trailing chars
ICD10_PATTERN = re.compile(r"^[A-TV-Z][0-9][A-Z0-9](?:[A-Z0-9])?(?:\.[A-Z0-9]{1,4})?$", re.IGNORECASE)

def is_valid_icd(code: str) -> bool:
    code = (code or "").strip().upper()
    return bool(ICD10_PATTERN.fullmatch(code))

def significant_len(code: str) -> int:
    return len(code.replace(".", ""))

def looks_specific(desc: str, exclude_phrases: set) -> bool:
    d = (desc or "").strip().lower()
    if not d:
        return False
    return not any(p in d for p in exclude_phrases)

def clean(
    in_path: Path,
    out_path: Path,
    min_chars_no_dot: int = 4,
    drop_vague: bool = True,
    extra_exclude: list[str] = None,
) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    exclude = set(DEFAULT_EXCLUDE)
    if extra_exclude:
        exclude |= {s.lower() for s in extra_exclude}

    seen = set()
    kept = []

    with in_path.open("r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        code_field = next((c for c in rdr.fieldnames if c and c.lower() in {"code", "icd", "label"}), None)
        desc_field = next((c for c in rdr.fieldnames if c and c.lower() in {"description", "desc", "short_desc", "title"}), None)
        if not code_field or not desc_field:
            raise ValueError("Expected columns 'code' and 'description' (case-insensitive).")

        for row in rdr:
            code = (row.get(code_field) or "").strip().upper()
            desc = (row.get(desc_field) or "").strip()

            if not code or not desc:
                continue
            if not is_valid_icd(code):
                continue
            if significant_len(code) < min_chars_no_dot:
                continue
            if drop_vague and not looks_specific(desc, exclude):
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
    ap = argparse.ArgumentParser(description="Clean ICD-10-CM labels to more specific, billable-like codes.")
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_IN), help="Input CSV (code,description)")
    ap.add_argument("--out", dest="out_path", default=str(DEFAULT_OUT), help="Output cleaned CSV")
    ap.add_argument("--min-chars", dest="min_chars", type=int, default=4,
                    help="Minimum code length excluding dot (default 4). Use 3 to allow some category codes.")
    ap.add_argument("--keep-vague", action="store_true",
                    help="Keep 'unspecified/NOS/other specified' descriptions (default is to drop).")
    ap.add_argument("--extra-exclude", nargs="*", default=[],
                    help="Additional phrases to exclude (case-insensitive).")
    args = ap.parse_args()

    n = clean(
        Path(args.in_path),
        Path(args.out_path),
        min_chars_no_dot=args.min_chars,
        drop_vague=not args.keep_vague,
        extra_exclude=args.extra_exclude,
    )
    print(f"Wrote {n} cleaned ICD rows to {args.out_path}")
