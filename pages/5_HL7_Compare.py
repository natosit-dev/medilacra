import os, re
import streamlit as st
import pandas as pd
import duckdb, pyodbc
from dotenv import load_dotenv

# ---------- Load env ----------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "medilacra.duckdb")

IRIS_DSN = os.getenv("IRIS_DSN", "iris")
IRIS_USER = os.getenv("IRIS_USER", "demoapp")
IRIS_PASSWORD = os.getenv("IRIS_PASSWORD", "demo")

# IRIS tables
MSH_TABLE = os.getenv("IRIS_MSH_TABLE", "Demo_HL7.MsgHeader")
PID_TABLE = os.getenv("IRIS_PID_TABLE", "Demo_HL7.PatientIdentification")
OBX_TABLE = os.getenv("IRIS_OBX_TABLE", "Demo_HL7.Observation")

# IRIS join columns (message id / MSH-10)
MSH_MSGID = os.getenv("IRIS_MSH_MSGID_COL", "MSH10")
PID_MSGID = os.getenv("IRIS_PID_MSGID_COL", "MSH10")
OBX_MSGID = os.getenv("IRIS_OBX_MSGID_COL", "MSH10")

# IRIS field columns
MSH_DT = os.getenv("IRIS_MSH_DT_COL", "MSH7")
PID_ID = os.getenv("IRIS_PID_ID_COL", "PatientID")
PID_DOB = os.getenv("IRIS_PID_DOB_COL", "BirthDateTime")
PID_SEX = os.getenv("IRIS_PID_SEX_COL", "Sex")

# IRIS OBX columns (for preview)
OBX_SETID = os.getenv("IRIS_OBX_SETID_COL", "SetID")
OBX_VALUETYPE = os.getenv("IRIS_OBX_VALUETYPE_COL", "ValueType")
OBX_ID = os.getenv("IRIS_OBX_ID_COL", "ObservationIdentifier")
OBX_VALUE = os.getenv("IRIS_OBX_VALUE_COL", "ObservationValue")
OBX_UNITS = os.getenv("IRIS_OBX_UNITS_COL", "Units")
OBX_STATUS = os.getenv("IRIS_OBX_STATUS_COL", "ObservationResultStatus")
OBX_DT = os.getenv("IRIS_OBX_DT_COL", "DateTimeOfTheObservation")

# ---------- Connections ----------
@st.cache_resource
def get_duck():
    return duckdb.connect(os.path.join(ROOT, DUCKDB_PATH))

@st.cache_resource
def get_iris():
    return pyodbc.connect(f"DSN={IRIS_DSN};UID={IRIS_USER};PWD={IRIS_PASSWORD};", autocommit=True)

# ---------- Helpers ----------
def find_duck_table(conn) -> str:
    """
    Autodetect the DuckDB table that has the columns we need:
    control_id (MSH-10), raw_hl7 (text), and ingest_ts (for recency).
    """
    q = """
    SELECT table_schema, table_name
    FROM information_schema.columns
    WHERE lower(column_name) IN ('control_id','raw_hl7','ingest_ts')
    GROUP BY table_schema, table_name
    HAVING COUNT(*) >= 2  -- must have at least control_id + raw_hl7
    ORDER BY table_schema, table_name
    """
    df = conn.execute(q).df()
    if df.empty:
        raise RuntimeError("No DuckDB table with required columns (control_id, raw_hl7) was found.")
    # Prefer tables that also have ingest_ts
    for _, r in df.iterrows():
        cols = conn.execute(f"""
            SELECT lower(column_name) AS c
            FROM information_schema.columns
            WHERE table_schema=? AND table_name=?
        """, [r.table_schema, r.table_name]).df()["c"].tolist()
        if "ingest_ts" in cols:
            return f'{r.table_schema}."{r.table_name}"' if r.table_schema != "main" else f'"{r.table_name}"'
    r = df.iloc[0]
    return f'{r.table_schema}."{r.table_name}"' if r.table_schema != "main" else f'"{r.table_name}"'

def parse_hl7_minimal(raw_msg: str) -> dict:
    """Minimal parser for fields we compare."""
    out = {}
    if not raw_msg:
        return out
    lines = [ln.strip() for ln in re.split(r'\r?\n', raw_msg) if ln.strip()]
    for ln in lines:
        parts = ln.split('|')
        seg = parts[0] if parts else ""
        if seg == "MSH":
            if len(parts) > 7:  out["MSH-7"]  = parts[7]
            if len(parts) > 10: out["MSH-10"] = parts[10]
        elif seg == "PID":
            if len(parts) > 3:  out["PID-3"] = parts[3]
            if len(parts) > 7:  out["PID-7"] = parts[7]
            if len(parts) > 8:  out["PID-8"] = parts[8]
    return out

def df_from_iris(sql: str, params=()):
    conn = get_iris()
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    return pd.DataFrame.from_records(rows, columns=cols)

def norm_ts14(s):
    if s is None: return None
    s = str(s).strip()
    return s[:14] if re.fullmatch(r"\d{14,}", s) else s

# ---------- UI ----------
st.title("HL7 Compare: DuckDB Raw vs IRIS SQL (by MSH-10 / control_id)")

duck = get_duck()
duck_table = find_duck_table(duck)

# Pull recent message ids from DuckDB (by ingest_ts if present)
recent_sql = f"""
SELECT control_id, message_type, ingest_ts
FROM {duck_table}
ORDER BY ingest_ts DESC NULLS LAST
LIMIT 250
"""
recent = duck.execute(recent_sql).df()

if recent.empty:
    st.warning("No rows found in DuckDB.")
    st.stop()

left, right = st.columns([2,1])
with left:
    st.subheader("Pick a message (control_id)")
    msg_id = st.selectbox("control_id (MSH-10)", recent["control_id"].tolist())
with right:
    st.caption("Recent (DuckDB)")
    st.dataframe(recent, use_container_width=True, hide_index=True)

# Fetch raw HL7 for the chosen control_id
raw_row = duck.execute(
    f'SELECT raw_hl7 FROM {duck_table} WHERE control_id = ? LIMIT 1', [msg_id]
).df()
if raw_row.empty:
    st.error("Selected message not found in DuckDB.")
    st.stop()
raw_hl7 = raw_row.iloc[0]["raw_hl7"]
parsed = parse_hl7_minimal(raw_hl7)

st.subheader("Raw HL7 (DuckDB)")
st.code(raw_hl7, language="hl7")

# IRIS queries using configured tables/columns
IRIS_MSH_SQL = f"""
SELECT TOP 1
  {MSH_MSGID} AS message_id,
  {MSH_DT}    AS msg_datetime
FROM {MSH_TABLE}
WHERE {MSH_MSGID} = ?
"""

IRIS_PID_SQL = f"""
SELECT TOP 1
  {PID_MSGID} AS message_id,
  {PID_ID}    AS pid3,
  {PID_DOB}   AS pid7,
  {PID_SEX}   AS pid8
FROM {PID_TABLE}
WHERE {PID_MSGID} = ?
"""

IRIS_OBX_SQL = f"""
SELECT
  {OBX_MSGID}         AS message_id,
  {OBX_SETID}         AS obx1,
  {OBX_VALUETYPE}     AS obx2,
  {OBX_ID}            AS obx3,
  {OBX_VALUE}         AS obx5,
  {OBX_UNITS}         AS obx6,
  {OBX_STATUS}        AS obx11,
  {OBX_DT}            AS obx14
FROM {OBX_TABLE}
WHERE {OBX_MSGID} = ?
ORDER BY obx1
"""

st.subheader("IRIS Segment Rows")
iris_msh = df_from_iris(IRIS_MSH_SQL, (msg_id,))
iris_pid = df_from_iris(IRIS_PID_SQL, (msg_id,))
iris_obx = df_from_iris(IRIS_OBX_SQL, (msg_id,))

lv, rv = st.columns(2)
with lv:
    st.markdown("**MSH** (IRIS)")
    st.dataframe(iris_msh, use_container_width=True, hide_index=True)
    st.markdown("**PID** (IRIS)")
    st.dataframe(iris_pid, use_container_width=True, hide_index=True)
with rv:
    st.markdown("**OBX** (IRIS)")
    st.dataframe(iris_obx, use_container_width=True, hide_index=True)

# ---------- Comparison ----------
st.subheader("Field Comparison")

# Build a single-row dict from IRIS
iris_row = {}
if not iris_msh.empty: iris_row.update({k.lower(): iris_msh.iloc[0][k] for k in iris_msh.columns})
if not iris_pid.empty: iris_row.update({k.lower(): iris_pid.iloc[0][k] for k in iris_pid.columns})

comparisons = [
    ("Message Control ID (MSH-10)", parsed.get("MSH-10"), iris_row.get("message_id")),
    ("Message DateTime (MSH-7)"   , norm_ts14(parsed.get("MSH-7")), norm_ts14(iris_row.get("msg_datetime"))),
    ("Patient ID (PID-3)"         , parsed.get("PID-3"), iris_row.get("pid3")),
    ("DOB (PID-7)"                , parsed.get("PID-7"), iris_row.get("pid7")),
    ("Sex (PID-8)"                , parsed.get("PID-8"), iris_row.get("pid8")),
]
cmp_df = pd.DataFrame(
    [{"Field": f, "Raw (DuckDB)": a, "IRIS SQL": b, "Match": "✓" if (str(a).strip()==str(b).strip()) else "✗"}
     for (f,a,b) in comparisons]
)
st.dataframe(cmp_df, use_container_width=True, hide_index=True)

# OBX count sanity check
raw_obx_count = sum(1 for ln in raw_hl7.splitlines() if ln.startswith("OBX|"))
iris_obx_count = len(iris_obx)
st.markdown(
    f"**OBX count** — Raw: `{raw_obx_count}` vs IRIS: `{iris_obx_count}` "
    + ("✓" if raw_obx_count == iris_obx_count else "✗")
)

if not iris_obx.empty:
    with st.expander("OBX Quick Preview (first 10)"):
        st.dataframe(iris_obx.head(10), use_container_width=True, hide_index=True)
