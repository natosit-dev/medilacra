# scripts/icd_xml_to_csv.py
import argparse, csv, re
from pathlib import Path
import xml.etree.ElementTree as ET

def text_clean(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def is_leaf(diag_el: ET.Element) -> bool:
    # A billable code in the tabular structure typically has no child <diag>
    return not any(child.tag.lower() == "diag" for child in diag_el)

def iter_diags(root: ET.Element):
    # Walk all <diag> nodes anywhere under the doc
    for el in root.iter():
        if el.tag.lower() == "diag":
            yield el

def extract_pairs(xml_path: Path, leaf_only: bool):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    out = []
    seen = set()
    for d in iter_diags(root):
        # Pull code + short description
        name_el = d.find("./name")
        desc_el = d.find("./desc")
        if name_el is None or desc_el is None:
            continue
        code = text_clean(name_el.text)
        desc = text_clean(desc_el.text)

        if not code or not desc:
            continue
        if leaf_only and not is_leaf(d):
            continue

        key = (code, desc)
        if key in seen:
            continue
        seen.add(key)
        out.append((code, desc))
    # stable sort by code
    out.sort(key=lambda x: x[0])
    return out

def main():
    p = argparse.ArgumentParser(description="Convert ICD-10-CM tabular XML to code,description CSV.")
    p.add_argument("--in", dest="in_path", default="icd-10-cm-tabular-2025.xml", help="Input XML path")
    p.add_argument("--out", dest="out_path", default=str(Path(__file__).resolve().parents[1] / "ref" / "icd_labels.csv"),
                   help="Output CSV path")
    p.add_argument("--all-codes", action="store_true", help="Include non-leaf parent codes too (default: leaf/billable only)")
    args = p.parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pairs = extract_pairs(in_path, leaf_only=not args.all_codes)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "description"])
        w.writerows(pairs)

    print(f"Wrote {len(pairs):,} rows to {out_path}")

if __name__ == "__main__":
    main()
