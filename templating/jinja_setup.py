# templating/jinja_setup.py
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from jinja2 import Environment, FileSystemLoader, StrictUndefined

def hl7_escape(s: str) -> str:
    if s is None:
        return ""
    # Escape the HL7 special chars in a naive/default way
    return (
        s.replace("\\", "\\E\\")
         .replace("|", "\\F\\")
         .replace("^", "\\S\\")
         .replace("&", "\\T\\")
         .replace("~", "\\R\\")
    )

def ts_fmt(dt: datetime | str) -> str:
    if isinstance(dt, str):
        # assume already HL7 formatted, passthrough
        return dt
    return dt.strftime("%Y%m%d%H%M%S")

def build_env(templates_dir: str | Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    env.filters["hl7_escape"] = hl7_escape
    env.filters["ts"] = ts_fmt
    return env

def render(env: Environment, template_name: str, payload: Dict[str, Any], flavor: Dict[str, Any] | None = None) -> str:
    tpl = env.get_template(template_name)
    ctx = {**payload, "rules": (flavor or {})}
    out = tpl.render(**ctx)
    return out if out.endswith("\n") else out + "\n"
