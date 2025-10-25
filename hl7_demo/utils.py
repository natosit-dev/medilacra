# utils.py
# Lightweight helpers for HL7 string and name formatting.
# Behavior unchanged; added structured logging and explanatory comments.

import re
from datetime import datetime
from typing import Optional

# --- Logging (structured) ---
try:
    from utils.log_utils import get_logger
except Exception:
    from log_utils import get_logger  # type: ignore

logger = get_logger(name="MediLacra", context={"component": "utils"})
logger.info("utils module loaded")

import os

COUNTER_FILE = "control_id_counter.txt"

def get_next_control_id():
    """
    Returns the next integer control ID, incrementing and persisting between sessions.
    Starts at 1 if the counter file does not exist.
    """
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r") as f:
            current = int(f.read().strip())
    else:
        current = 0

    next_id = current + 1
    with open(COUNTER_FILE, "w") as f:
        f.write(str(next_id))
    return next_id


def ts_hl7(dt: Optional[datetime | str]) -> str:
    """
    Convert to HL7 TS (YYYYMMDDHHMMSS), preserving original semantics:
      - None  -> "" (allowed for optional TS fields)
      - str   -> strip all non-digits (e.g., "2025-09-29 14:25:36" -> "20250929142536")
      - datetime -> format with "%Y%m%d%H%M%S"
    Note: HL7 permits reduced precision (e.g., YYYYMMDD); we warn on atypical lengths.
    """
    try:
        if dt is None:
            logger.info("ts_hl7 called with None; returning empty TS")
            return ""
        if isinstance(dt, str):
            raw = dt
            digits = re.sub(r"\D", "", raw)
            if digits != raw:
                logger.info(
                    "ts_hl7 sanitized non-digit characters from string",
                    extra={"extra": {"input_len": len(raw), "digits_len": len(digits)}},
                )
            # Common lengths: 8 (date), 12/14 (date+time); allow others but warn
            if len(digits) not in (4, 6, 8, 10, 12, 14):
                logger.warning(
                    "Atypical HL7 TS length after sanitization",
                    extra={"extra": {"length": len(digits), "value": digits}},
                )
            return digits
        # datetime path
        out = dt.strftime("%Y%m%d%H%M%S")
        return out
    except Exception as e:
        logger.error("ts_hl7 failed", extra={"extra": {"error": str(e), "type": str(type(dt))}})
        raise


def one_line(s: Optional[str]) -> str:
    """
    Collapse any newlines/tabs/multiple spaces to a single space.
    Preserves original return behavior, returning "" for falsy input.
    """
    try:
        if not s:
            return ""
        # Replace CR/LF with space, then collapse all whitespace runs.
        # This is intentionally lossy for readability in HL7 textual fields.
        original = s
        out = re.sub(r"\s+", " ", original.replace("\r", " ").replace("\n", " ")).strip()
        if out != original:
            logger.info(
                "one_line normalized whitespace",
                extra={"extra": {"input_len": len(original), "output_len": len(out)}},
            )
        return out
    except Exception as e:
        logger.error("one_line failed", extra={"extra": {"error": str(e)}})
        raise


def hl7_name_from_display(patient_name: str) -> str:
    """
    Convert 'Family, Given' display to HL7 XPN 'FAMILY^GIVEN' (case preserved).
    If empty, return caret separator per original implementation.
    """
    try:
        if not patient_name:
            logger.info("hl7_name_from_display received empty name; returning '^'")
            return "^"
        parts = [p.strip() for p in str(patient_name).split(",", 1)]
        family = parts[0] if parts else ""
        given = parts[1] if len(parts) > 1 else ""
        return f"{family}^{given}"
    except Exception as e:
        logger.error("hl7_name_from_display failed", extra={"extra": {"error": str(e)}})
        raise


def hl7_name_from_full(display_name: str) -> str:
    """
    Convert free-text full name to HL7 XPN 'FAMILY^GIVEN'.
    Rules (unchanged):
      - If a comma is present, delegate to hl7_name_from_display().
      - If single token, return 'TOKEN^'.
      - Else, use first token as given, last as family; both uppercased.
    """
    try:
        if not display_name:
            logger.info("hl7_name_from_full received empty name; returning '^'")
            return "^"
        s = str(display_name).strip()
        if "," in s:
            return hl7_name_from_display(s)
        parts = s.split()
        if len(parts) == 1:
            logger.info("hl7_name_from_full single-token input", extra={"extra": {"token": parts[0]}})
            return f"{parts[0]}^"
        given, family = parts[0], parts[-1]
        return f"{family.upper()}^{given.upper()}"
    except Exception as e:
        logger.error("hl7_name_from_full failed", extra={"extra": {"error": str(e)}})
        raise


def hl7_escape(value: Optional[str]) -> str:
    """
    Escape HL7 special characters in a value per v2 encoding rules.
    Mapping (unchanged):
      \  -> \\E\\
      |  -> \\F\\
      ^  -> \\S\\
      &  -> \\T\\
      ~  -> \\R\\
    """
    try:
        if value is None:
            return ""
        s = str(value)
        had_specials = any(ch in s for ch in ("\\", "|", "^", "&", "~"))
        s = s.replace("\\", "\\E\\")
        s = s.replace("|", "\\F\\").replace("^", "\\S\\").replace("&", "\\T\\").replace("~", "\\R\\")
        if had_specials:
            logger.info("hl7_escape applied", extra={"extra": {"original_len": len(value), "escaped_len": len(s)}})
        return s
    except Exception as e:
        logger.error("hl7_escape failed", extra={"extra": {"error": str(e)}})
        raise
