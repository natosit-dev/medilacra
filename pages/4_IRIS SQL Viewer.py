import streamlit as st
import pyodbc
import os
import sys
import platform
from dotenv import load_dotenv

# Load variables from .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

st.write(f"Python: {sys.version.split()[0]}  |  Arch: {platform.architecture()[0]}")
st.write("ODBC drivers:", pyodbc.drivers())  # should list "InterSystems ODBC" or similar

@st.cache_resource
def get_conn():
    dsn = os.getenv("IRIS_DSN", "iris")
    user = os.getenv("IRIS_USER", "demoapp")
    pwd = os.getenv("IRIS_PASSWORD", "demo")

    conn_str = f"DSN={dsn};UID={user};PWD={pwd};"
    return pyodbc.connect(conn_str, autocommit=True)

def run_sql(sql, params=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        try:
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description]
            return cols, rows
        except pyodbc.ProgrammingError:
            return [], []


st.subheader("IRIS Demo.PatientMsg")
cols, rows = run_sql("SELECT TOP 5 * FROM Demo.PatientMsg")
st.write(f"Rows returned: {len(rows)}")
if rows:
    st.dataframe([{cols[i]: r[i] for i in range(len(cols))} for r in rows])

st.subheader("IRIS Demo.Observation")
cols, rows = run_sql("SELECT TOP 5 * FROM Demo.Observation")
st.write(f"Rows returned: {len(rows)}")
if rows:
    st.dataframe([{cols[i]: r[i] for i in range(len(cols))} for r in rows])