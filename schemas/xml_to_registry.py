# schemas/xml_to_registry.py
from __future__ import annotations
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ----------------------------
# Data structures
# ----------------------------
@dataclass
class TableDef:
    id: str
    name: Optional[str]
    values: List[str] = field(default_factory=list)

@dataclass
class DataTypeComp:
    name: str
    datatype: Optional[str]  # sub-datatype for components (may be None)
    table: Optional[str]

@dataclass
class DataTypeDef:
    name: str
    components: List[DataTypeComp] = field(default_factory=list)

@dataclass
class FieldDef:
    position: int
    name: str
    datatype: str
    required: bool
    repeating: bool
    table: Optional[str] = None

@dataclass
class SegmentDef:
    name: str
    fields: List[FieldDef] = field(default_factory=list)

@dataclass
class MessageSeg:
    segment: str
    usage: str   # R, RE, O, X (if present)
    repeating: bool

@dataclass
class MessageDef:
    name: str              # e.g., ORU_R01
    structure: List[MessageSeg]

@dataclass
class HL7Registry:
    version: str
    segments: Dict[str, SegmentDef]
    messages: Dict[str, MessageDef]
    datatypes: Dict[str, DataTypeDef]
    tables: Dict[str, TableDef]

# ----------------------------
# Helpers
# ----------------------------
def _lname(tag: str) -> str:
    """Return the local part of an XML tag, stripping any namespace."""
    return tag.split('}')[-1] if '}' in tag else tag

def _text(node: Optional[ET.Element]) -> Optional[str]:
    return node.text.strip() if (node is not None and node.text) else None

def _boolish(s: Optional[str], default=False) -> bool:
    if s is None:
        return default
    s = s.strip().lower()
    return s in ("true", "t", "1", "y", "yes", "r", "required")

def _first_attr(e: ET.Element, *names: str) -> Optional[str]:
    for n in names:
        v = e.get(n)
        if v:
            return v
    return None

def _first_child_text(e: ET.Element, *local_names: str) -> Optional[str]:
    for c in e.iter():
        if _lname(c.tag) in local_names:
            txt = _text(c)
            if txt:
                return txt
    return None

def _gather(root: ET.Element, *local_names: str) -> List[ET.Element]:
    """Collect all descendants whose local tag name matches any in local_names."""
    keep = set(local_names)
    return [el for el in root.iter() if _lname(el.tag) in keep]

# ----------------------------
# Loader
# ----------------------------
def load_iris_schema(xml_path: str, version_hint: str = "2.5") -> HL7Registry:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Gather likely nodes by LOCAL tag name (no XPath predicates/functions)
    msg_nodes = _gather(root, "MessageType", "Message", "MessageStructure")
    seg_nodes = _gather(root, "Segment")
    dt_nodes  = _gather(root, "DataType")
    tbl_nodes = _gather(root, "Table", "HL7Table")

    # If nothing found, raise with a friendly hint listing the available tag names
    if not (msg_nodes or seg_nodes or dt_nodes or tbl_nodes):
        seen = sorted({ _lname(e.tag) for e in root.iter() })
        raise ValueError(
            "Could not detect HL7 schema elements in XML. "
            f"Top-level local tag names seen: {', '.join(seen[:40])} ..."
        )

    # --- Tables (value sets) ---
    tables: Dict[str, TableDef] = {}
    for t in tbl_nodes:
        tid = (_first_attr(t, "ID", "Id", "Number") or "").strip()
        name = _first_attr(t, "Name", "Description") or _first_child_text(t, "Name", "Description")
        values: List[str] = []
        # Common child names for enumerations: Value, Item, Enum, Enumeration
        for v in t.iter():
            if _lname(v.tag) in ("Value", "Item", "Enum", "Enumeration"):
                code = _first_attr(v, "Code", "Value", "Id") or _text(v)
                if code:
                    values.append(code.strip())
        if tid:
            tables[tid] = TableDef(id=tid, name=name, values=values)

    # --- Datatypes (components) ---
    datatypes: Dict[str, DataTypeDef] = {}
    for d in dt_nodes:
        dname = _first_attr(d, "Name") or _first_child_text(d, "Name")
        if not dname:
            continue
        comps: List[DataTypeComp] = []
        for c in d.iter():
            if _lname(c.tag) == "Component":
                cname = _first_attr(c, "Name") or _first_child_text(c, "Name") or ""
                cdt   = _first_attr(c, "Datatype", "DataType") or _first_child_text(c, "Datatype", "DataType")
                ctbl  = _first_attr(c, "Table", "TableId") or _first_child_text(c, "Table", "TableId")
                comps.append(DataTypeComp(name=cname.strip(), datatype=cdt, table=ctbl))
        datatypes[dname] = DataTypeDef(name=dname, components=comps)

    # --- Segments (ordered fields) ---
    segments: Dict[str, SegmentDef] = {}
    for s in seg_nodes:
        sname = _first_attr(s, "Name") or _first_child_text(s, "Name")
        if not sname:
            continue
        fields: List[FieldDef] = []
        for f in s.iter():
            if _lname(f.tag) != "Field":
                continue
            pos_raw = _first_attr(f, "Position", "Seq")
            try:
                pos = int(pos_raw) if pos_raw else len(fields) + 1
            except ValueError:
                pos = len(fields) + 1
            fname = _first_attr(f, "Name") or _first_child_text(f, "Name") or f"Field{pos}"
            fdt   = _first_attr(f, "Datatype", "DataType") or _first_child_text(f, "Datatype", "DataType") or "ST"
            freq  = _boolish(_first_attr(f, "Required", "Req"), default=False)
            frep  = _boolish(_first_attr(f, "Repeating", "Repeats"), default=False)
            ftbl  = _first_attr(f, "Table", "TableId") or _first_child_text(f, "Table", "TableId")
            fields.append(FieldDef(position=pos, name=fname, datatype=fdt, required=freq, repeating=frep, table=ftbl))
        fields.sort(key=lambda x: x.position)
        segments[sname] = SegmentDef(name=sname, fields=fields)

    # --- Messages (segment order + usage) ---
    def _norm_usage(u: Optional[str]) -> str:
        if not u:
            return "R"
        u = u.upper()
        return u if u in ("R", "RE", "O", "X") else "R"

    messages: Dict[str, MessageDef] = {}
    for m in msg_nodes:
        mname = _first_attr(m, "Name", "Structure", "Struct") or _first_child_text(m, "Name", "Structure", "Struct")
        if not mname:
            continue
        struct: List[MessageSeg] = []
        for r in m.iter():
            if _lname(r.tag) in ("SegmentRef", "SegmentReference"):
                sg = _first_attr(r, "Seg", "Segment", "Name")
                if not sg:
                    continue
                usage = _norm_usage(_first_attr(r, "Usage"))
                rep = _boolish(_first_attr(r, "Repeating", "Repeats"), default=False)
                struct.append(MessageSeg(segment=sg, usage=usage, repeating=rep))
        messages[mname] = MessageDef(name=mname, structure=struct)

    return HL7Registry(
        version=version_hint,
        segments=segments,
        messages=messages,
        datatypes=datatypes,
        tables=tables,
    )
