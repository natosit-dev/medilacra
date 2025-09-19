#utils.py

import re
from datetime import datetime
from typing import Optional

def ts_hl7(dt: Optional[datetime | str]) -> str:
    if dt is None: return ""
    if isinstance(dt, str): return re.sub(r"\D", "", dt)
    return dt.strftime("%Y%m%d%H%M%S")

def one_line(s: Optional[str]) -> str:
    if not s: return ""
    return re.sub(r"\s+", " ", s.replace("\r", " ").replace("\n", " ")).strip()

def hl7_name_from_display(patient_name: str) -> str:
    if not patient_name: return "^"
    parts = [p.strip() for p in str(patient_name).split(",", 1)]
    family = parts[0] if parts else ""
    given = parts[1] if len(parts) > 1 else ""
    return f"{family}^{given}"

def hl7_name_from_full(display_name: str) -> str:
    if not display_name: return "^"
    s = str(display_name).strip()
    if "," in s: return hl7_name_from_display(s)
    parts = s.split()
    if len(parts) == 1: return f"{parts[0]}^"
    given, family = parts[0], parts[-1]
    return f"{family.upper()}^{given.upper()}"

def hl7_escape(value: Optional[str]) -> str:
    if value is None: return ""
    s = str(value)
    s = s.replace("\\", "\\E\\")
    s = s.replace("|","\\F\\").replace("^","\\S\\").replace("&","\\T\\").replace("~","\\R\\")
    return s
