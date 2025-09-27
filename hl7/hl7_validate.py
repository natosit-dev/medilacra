# hl7/hl7_validate.py
from __future__ import annotations
from typing import List, Tuple, Dict
from dataclasses import dataclass
import re
from schemas.xml_to_registry import HL7Registry, SegmentDef, FieldDef

SEP_FIELD = '|'
SEP_COMP = '^'
SEP_REP = '~'
SEP_SUB = '&'

@dataclass
class ValIssue:
    segment: str
    field_pos: int
    level: str   # ERROR/WARN
    message: str

def _is_empty(val: str) -> bool:
    return val == "" or val is None

def _looks_ts(val: str) -> bool:
    # YYYY[MM[DD[HH[MM[SS[.SSSS]]]]]]
    return bool(re.match(r"^\d{4}(\d{2}(\d{2}(\d{2}(\d{2}(\d{2}(\.\d{1,4})?)?)?)?)?)?$", val))

def _looks_nm(val: str) -> bool:
    return bool(re.match(r"^[+-]?\d+(\.\d+)?$", val))

def _validate_datatype(raw: str, f: FieldDef, registry: HL7Registry) -> List[str]:
    msgs = []
    dt = f.datatype.upper()
    if dt in ("TS", "DTM", "DT"):  # simple TS/DT check
        if raw and not _looks_ts(raw):
            msgs.append(f"Datatype {dt} expected; got '{raw}'.")
    elif dt in ("NM", "SI"):
        if raw and not _looks_nm(raw):
            msgs.append(f"Datatype {dt} expected numeric; got '{raw}'.")
    elif dt in ("CWE", "CE", "CX", "XCN", "XAD", "XPN"):
        # Basic shape check: components separated by ^
        # We won't recursively validate subcomponents here; keep it lightweight.
        pass
    # Else: leave as pass-through
    return msgs

def _validate_table(raw: str, f: FieldDef, registry: HL7Registry) -> List[str]:
    if not f.table or not raw:
        return []
    tbl = registry.tables.get(f.table)
    if not tbl or not tbl.values:
        return []  # table known but values not populated — skip strictness
    # For CWE/CE, the code is comp[0]
    code = raw.split(SEP_COMP, 1)[0]
    if code and code not in tbl.values:
        return [f"Value '{code}' not in table {f.table}."]
    return []

# ... imports omitted for brevity ...

def validate_message(message_text: str, registry: HL7Registry) -> List[ValIssue]:
    issues: List[ValIssue] = []
    lines = [ln.rstrip("\r\n") for ln in message_text.splitlines() if ln.strip()]
    for ln in lines:
        parts = ln.split(SEP_FIELD)
        seg = parts[0]
        segdef: SegmentDef = registry.segments.get(seg)
        if not segdef:
            issues.append(ValIssue(seg, 0, "ERROR", f"Unknown segment '{seg}' for HL7 {registry.version}."))
            continue

        values = parts[1:]  # data fields after segment tag

        # --- special-case MSH: skip the "Field Separator" definition if present ---
        fields_def = segdef.fields
        if seg == "MSH" and fields_def:
            # Most exports list MSH-1 ("Field Separator") first; data starts at MSH-2
            fields_def = fields_def[1:]

        for idx, fdef in enumerate(fields_def, start=1):
            raw = values[idx - 1] if idx - 1 < len(values) else ""
            # Required?
            if fdef.required and (raw is None or raw == ""):
                issues.append(ValIssue(seg, idx, "ERROR", f"Required field '{fdef.name}' (#{idx}) empty."))
            # Datatype + Table checks (your existing helpers)
            for msg in _validate_datatype(raw, fdef, registry):
                issues.append(ValIssue(seg, idx, "ERROR", msg))
            for msg in _validate_table(raw, fdef, registry):
                issues.append(ValIssue(seg, idx, "WARN", msg))

        if len(values) > len(fields_def):
            issues.append(ValIssue(seg, 0, "WARN", f"{len(values)} fields present; {len(fields_def)} defined."))

    return issues

