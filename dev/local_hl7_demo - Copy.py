# local_hl7_demo.py
# Fully local patient + HL7 generator equivalent to your Databricks demo.
# - Reads CSV reports from ./input/reports/*.csv
# - Generates synthetic patients, encounters, transactions, and observations
# - Builds HL7 ADT^A01, ORU^R01, DFT^P03 messages
# - ADT includes two optional SDOH OBXs:
#     OBX-1: Police station count by ZIP (ESRI/ArcGIS)
#     OBX-2: Air quality (AirNow) by ZIP (AirNow key hardcoded)
# - Writes .hl7 files under ./output/ (bulk or per-encounter)
#
# Usage examples:
#   python local_hl7_demo.py --patients 1000 --per-encounter
#   python local_hl7_demo.py --patients 200 --bulk
#   python local_hl7_demo.py --patients 50 --seed 42 --report-glob "./input/reports/*.csv"
#
# Requirements (install once):
#   pip install faker pandas python-dateutil requests
#
# Folder layout:
#   ./input/reports/  -> put your report CSVs here (must include: report_uid,cpt_code,icd_code,procedure_description,report_text)
#   ./output/         -> generated .hl7 files land here

from __future__ import annotations
import argparse
import glob
import os
import random
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import List, Optional, Dict
import textwrap
import logging
import argparse

import json
from urllib.parse import quote

import pandas as pd
from faker import Faker
import requests

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.multioutput import MultiOutputRegressor

from hashlib import sha1



# ------------------------- Config -------------------------

# Hardcoded AirNow API key (as requested)
AIRNOW_API_KEY = "86B0C1FD-C0D8-4A01-BA10-C04A0B718B6C"
AIRNOW_MILES_DEFAULT = 75

# Census ACS release year to query for poverty %
ACS_YEAR = "2022"  # use "2023" when that 5-year release is published in the API


# ------------------------- Helpers -------------------------

def ts_hl7(dt: Optional[datetime | str]) -> str:
    if dt is None:
        return ""
    if isinstance(dt, str):
        return re.sub(r"\D", "", dt)
    return dt.strftime("%Y%m%d%H%M%S")

def one_line(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.replace("\r", " ").replace("\n", " ")).strip()

def hl7_name_from_display(patient_name: str) -> str:
    # "LAST, FIRST" -> "LAST^FIRST"
    if not patient_name:
        return "^"
    parts = [p.strip() for p in str(patient_name).split(",", 1)]
    family = parts[0] if parts else ""
    given = parts[1] if len(parts) > 1 else ""
    return f"{family}^{given}"

def hl7_name_from_full(display_name: str) -> str:
    if not display_name:
        return "^"
    s = str(display_name).strip()
    if "," in s:
        return hl7_name_from_display(s)
    parts = s.split()
    if len(parts) == 1:
        return f"{parts[0]}^"
    given = parts[0]
    family = parts[-1]
    return f"{family.upper()}^{given.upper()}"

def hl7_escape(value: Optional[str]) -> str:
    if value is None:
        return ""
    s = str(value)
    # Order matters: escape backslash first so we don't re-escape what we insert
    s = s.replace("\\", "\\E\\")
    s = s.replace("|",  "\\F\\").replace("^", "\\S\\").replace("&", "\\T\\").replace("~", "\\R\\")
    return s



# ------------------------- AI Vitals Model -------------------------

VITALS_MODEL_PATH = "vitals_model.pkl"
_vitals_model = None

def train_vitals_model(path: str = VITALS_MODEL_PATH):
    """Train a simple multi-output regression model on synthetic vitals data and save to disk."""
    X = np.array([
        [30, 20, 80],
        [50, 50, 60],
        [70, 90, 30],
        [65, 40, 70],
        [40, 80, 50],
        [75, 95, 20],
    ])
    y = np.array([
        [110, 72, 99, 20],
        [135, 78, 98, 28],
        [160, 88, 97, 32],
        [142, 75, 96, 26],
        [160, 85, 92, 31],
        [180, 96, 85, 36],
    ])

    model = MultiOutputRegressor(LinearRegression())
    model.fit(X, y)
    joblib.dump(model, path)
    return model

def load_vitals_model(path: str = VITALS_MODEL_PATH):
    global _vitals_model
    if _vitals_model is None:
        if not os.path.exists(path):
            print("[INFO] Training vitals model...")
            _vitals_model = train_vitals_model(path)
        else:
            _vitals_model = joblib.load(path)
    return _vitals_model

def predict_vitals(age: int, poverty: float, air_quality: float) -> dict:
    model = load_vitals_model()
    X = np.array([[age, poverty, air_quality]])
    systolic_bp, hr, o2sat, bmi = model.predict(X)[0]
    return {
        "systolic_bp": float(systolic_bp),
        "heart_rate": float(hr),
        "o2_sat": float(o2sat),
        "bmi": float(bmi),
    }

def build_obx_vitals(vitals: dict, start_set_id: int = 10) -> list[str]:
    segs = []
    segs.append(f"OBX|{start_set_id}|NM|8480-6^Systolic BP^LN||{vitals['systolic_bp']:.1f}|mmHg|90-140|||F")
    segs.append(f"OBX|{start_set_id+1}|NM|8867-4^Heart rate^LN||{vitals['heart_rate']:.1f}|/min|60-100|||F")
    segs.append(f"OBX|{start_set_id+2}|NM|59408-5^Oxygen saturation^LN||{vitals['o2_sat']:.1f}|%|95-100|||F")
    segs.append(f"OBX|{start_set_id+3}|NM|39156-5^Body mass index^LN||{vitals['bmi']:.1f}|kg/m2|18.5-24.9|||F")
    return segs


# ------------------------- ArcGIS Police Station Data -----------

_ARCGIS_HOST = "https://services1.arcgis.com"
_ARCGIS_PATH = "/Hp6G80Pky0om7QvQ/ArcGIS/rest/services/Local_Law_Enforcement_Locations/FeatureServer/0/query"

def _arcgis_stats_url(z5: str) -> str:
    where = f"ZIP LIKE '{z5}%'"
    stats = [
        {"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "station_count"}
    ]
    qs = (
        f"where={quote(where)}"
        f"&outStatistics={quote(json.dumps(stats, separators=(',',':')))}"
        f"&groupByFieldsForStatistics=ZIP"
        f"&returnGeometry=false"
        f"&f=json"
    )
    return f"{_ARCGIS_HOST}{_ARCGIS_PATH}?{qs}"

def _arcgis_count_url(z5: str) -> str:
    # Fallback: ask ArcGIS for just the count directly
    where = f"ZIP LIKE '{z5}%'"
    qs = (
        f"where={quote(where)}"
        f"&returnCountOnly=true"
        f"&f=json"
    )
    return f"{_ARCGIS_HOST}{_ARCGIS_PATH}?{qs}"

def get_police_station_count_by_zip(zip5: Optional[str], timeout: float = 6.0) -> int:
    """
    Returns the count of police stations for a 5-digit ZIP (tolerates ZIP+4 input).
    Strategy:
      1) outStatistics count grouped by ZIP
      2) fallback: returnCountOnly=true
    """
    if not zip5:
        return "No Data"
    z5 = str(zip5).strip()[:5]
    if not z5.isdigit() or len(z5) != 5:
        return "No Data"

    # Primary query
    url1 = _arcgis_stats_url(z5)
    for attempt in range(3):
        try:
            r = requests.get(url1, timeout=timeout)
            if r.status_code == 200:
                body = r.json()
                if isinstance(body, dict) and body.get("error"):
                    break
                feats = body.get("features") or []
                if isinstance(feats, list) and feats:
                    attrs = (feats[0] or {}).get("attributes") or {}
                    cnt = attrs.get("station_count")
                    try:
                        c = int(cnt)
                        if c > 0:
                            return c
                        break  # non-positive, try fallback
                    except Exception:
                        break
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(0.5 * (attempt + 1))
                continue
            break
        except Exception:
            time.sleep(0.5 * (attempt + 1))

    # Fallback query: direct count
    url2 = _arcgis_count_url(z5)
    for attempt in range(2):
        try:
            r = requests.get(url2, timeout=timeout)
            if r.status_code == 200:
                body = r.json()
                # ArcGIS returns {"count": N}
                if isinstance(body, dict):
                    c = int(body.get("count", 0))
                    return max(0, c)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(0.5 * (attempt + 1))
                continue
            break
        except Exception:
            time.sleep(0.5 * (attempt + 1))

    return 0

def build_obx_police_count(count: int, set_id: int = 1) -> str:
    """
    OBX|<set_id>|NM|ESRI_POLICE_COUNT^Police Station Count^L||<count>|||||F
    """
    try:
        val = max(0, int(count))
    except Exception:
        val = 0
    return f"OBX|{set_id}|NM|ESRI_POLICE_COUNT^Police Station Count^L||{val}|||||F"

# ------------------------- AirNow (Air Quality) -------------------------

@lru_cache(maxsize=512)
def get_air_quality_by_zip(zip_code: str, miles: int = AIRNOW_MILES_DEFAULT) -> Dict[str,str]:
    """
    Returns a dict with 'aqi', 'parameter', 'category', 'obs_time', 'area', 'state', 'source' for the ZIP.
    Uses hardcoded AIRNOW_API_KEY.
    """
    if not (zip_code and AIRNOW_API_KEY):
        return {}
    url = "https://www.airnowapi.org/aq/observation/zipCode/current/"
    params = {"format": "application/json", "zipCode": zip_code, "distance": str(miles), "API_KEY": AIRNOW_API_KEY}
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if not data:
                    return {}
                worst = max(data, key=lambda x: int(x.get("AQI", -1)))
                return {
                    "aqi": worst.get("AQI"),
                    "parameter": worst.get("ParameterName"),
                    "category": (worst.get("Category") or {}).get("Name"),
                    "obs_time": f"{worst.get('DateObserved','')} {worst.get('HourObserved','')} {worst.get('LocalTimeZone','')}",
                    "area": worst.get("ReportingArea"),
                    "state": worst.get("StateCode"),
                    "source": "AirNow",
                }
            elif resp.status_code in (429, 500, 502, 503):
                time.sleep(0.5 * (attempt + 1))
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return {}

def build_obx_air_quality(aq: Dict[str,str], set_id: int = 2) -> str:
    """
    Render AirNow info as a TX OBX.
      OBX|<set_id>|TX|AIRNOW_AQI^Air Quality Index^L|1|AQI=75^Moderate^PM2.5^Boston, MA 2025-08-23 EDT||||||F
    """
    if not aq:
        return ""
    aqi = aq.get("aqi", "")
    param = aq.get("parameter", "")
    category = aq.get("category", "")
    place = ", ".join([x for x in [aq.get("area",""), aq.get("state","")] if x])
    obs = aq.get("obs_time", "")
    value = f"AQI={aqi}^{category}^{param}^{place} {obs}".strip()
    ident = "AIRNOW_AQI^Air Quality Index^L"
    return f"OBX|{set_id}|TX|{ident}|1|{value}||||||F"

#------------Poverty Stats --------------
from functools import lru_cache

def _http_get_json(url: str, params: dict | None = None, timeout: float = 8.0):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(0.5 * (attempt + 1))
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None

@lru_cache(maxsize=1024)
def get_poverty_pct_by_zcta(zcta: str, year: str = ACS_YEAR) -> float | None:
    """
    Returns percent of population below poverty level for a ZCTA (ZIP-like) using Census ACS 5-year.
    % = B17001_002E / B17001_001E * 100
    """
    if not zcta:
        return None
    z5 = str(zcta).strip()[:5]
    if not z5.isdigit() or len(z5) != 5:
        return None

    base = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {
        "get": "B17001_001E,B17001_002E,NAME",
        "for": f"zip code tabulation area:{z5}",
    }
    data = _http_get_json(base, params=params, timeout=8.0)
    if not isinstance(data, list) or len(data) < 2:
        return None

    try:
        total = float(data[1][0] or 0)   # B17001_001E
        below = float(data[1][1] or 0)   # B17001_002E
        if total <= 0:
            return None
        return round((below / total) * 100.0, 1)  # one decimal place
    except Exception:
        return None

def build_obx_poverty_pct(pct: float | None, set_id: int = 3) -> str:
    """
    OBX|<set_id>|NM|ACS_POVERTY_PCT^Poverty (ACS 5-year)%^L||<percent>|||||F
    """
    if pct is None:
        return ""
    try:
        val = f"{float(pct):.1f}"
    except Exception:
        return ""
    ident = "ACS_POVERTY_PCT^Poverty (ACS 5-year)%^L"
    return f"OBX|{set_id}|NM|{ident}||{val}|||||F"


# ------------------------- Data classes -------------------------

fake = Faker()

@dataclass
class Patient:
    patient_id: str
    patient_name: str  # "LAST, FIRST"
    date_of_birth: str  # YYYY-MM-DD
    sex: str
    race: str
    ssn: str
    address: str       # one-line, as in PID-11.1 (street etc.)
    phone: str
    zip_code: str      # parsed from address

@dataclass
class Encounter:
    encounter_id: str
    patient_id: str
    visit_number: str
    patient_class: str
    assigned_patient_location: str
    admit_datetime: str
    discharge_datetime: str
    hospital_service: str
    ordering_provider_id: str
    ordering_provider_name: str
    attending_provider_id: str
    attending_provider_name: str
    placer_order_number: str
    filler_order_number: str

@dataclass
class Transaction:
    transaction_id: str
    encounter_id: str
    transaction_date: str
    transaction_amount: float
    unit_cost: float
    transaction_quantity: int
    fee_schedule: str
    insurance_plan_id: str
    billing_provider_id: str
    billing_provider_name: str

@dataclass
class Observation:
    encounter_id: str
    observation_id: str
    cpt_code: str
    icd_code: str
    placer_order_number: str
    filler_order_number: str
    procedure_description: str
    observation_text: str
    observation_sub_id: str
    result_status: str
    completed_time: str

# ------------------------- Report loading -------------------------

def load_reports(glob_path: str) -> pd.DataFrame:
    files = sorted(glob.glob(glob_path))
    if not files:
        raise FileNotFoundError(f"No report CSVs found at {glob_path}. Put files under ./input/reports/.")
    frames = []
    for f in files:
        df = pd.read_csv(f)
        missing = {c for c in ["report_uid","cpt_code","icd_code","procedure_description","report_text"] if c not in df.columns}
        if missing:
            raise ValueError(f"{f} is missing columns: {sorted(missing)}")
        frames.append(df[["report_uid","cpt_code","icd_code","procedure_description","report_text"]])
    all_df = pd.concat(frames, ignore_index=True)
    if all_df.empty:
        raise ValueError("Report dataframe is empty after load.")
    return all_df

# ------------------------- Synthetic generation -------------------------

ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")

def gen_patient() -> Patient:
    # Generate an address and PARSE ZIP from it so PID-11.5 and SDOH lookups align.
    raw_addr = one_line(fake.address())
    m = ZIP_RE.search(raw_addr)
    if m:
        zip_code = m.group(0)
    else:
        # Rare locales may not include a ZIP; fall back but also append to address for internal consistency
        zip_code = fake.postcode()
        raw_addr = f"{raw_addr} {zip_code}"

    name = fake.name().split()
    first, last = name[0], name[-1]
    formatted = f"{last.upper()}, {first.upper()}"
    dob = fake.date_of_birth(minimum_age=18, maximum_age=90)

    return Patient(
        patient_id=fake.unique.bothify("RAD#######"),
        patient_name=formatted,
        date_of_birth=dob.strftime("%Y-%m-%d"),
        sex=random.choice(["M","F"]),
        race=random.choice(["White","Black","Asian","Hispanic","Other"]),
        ssn=fake.ssn(),
        address=raw_addr,
        phone=one_line(fake.phone_number()),
        zip_code=zip_code,
    )

def gen_encounter(patient_id: str) -> Encounter:
    admit_dt = fake.date_time_between(start_date="-14d", end_date="-1d")
    disch_dt = admit_dt + timedelta(hours=random.randint(1,6))
    visit = fake.unique.bothify("VN##########")
    prov = fake.name().split(); first, last = prov[0], prov[-1]
    prov_disp = f"{last.upper()}, {first.upper()}"
    return Encounter(
        encounter_id=f"{patient_id}_{visit}",
        patient_id=patient_id,
        visit_number=visit,
        patient_class="OUTPATIENT",
        assigned_patient_location="RAD_DEPT1",
        admit_datetime=admit_dt.strftime("%Y-%m-%d %H:%M:%S"),
        discharge_datetime=disch_dt.strftime("%Y-%m-%d %H:%M:%S"),
        hospital_service="RAD",
        ordering_provider_id=fake.bothify("R######"),
        ordering_provider_name=prov_disp,
        attending_provider_id=fake.bothify("P######"),
        attending_provider_name=prov_disp,
        placer_order_number=str(uuid.uuid4()),
        filler_order_number=str(uuid.uuid4()),
    )

def gen_transaction(encounter_id: str) -> Transaction:
    prov = fake.name().split(); first, last = prov[0], prov[-1]
    prov_disp = f"{last.upper()}, {first.upper()}"
    return Transaction(
        transaction_id=str(uuid.uuid4()),
        encounter_id=encounter_id,
        transaction_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        transaction_amount=round(random.uniform(100,500),2),
        unit_cost=round(random.uniform(50,250),2),
        transaction_quantity=1,
        fee_schedule=random.choice(["TECH","PRO"]),
        insurance_plan_id=fake.unique.bothify("INS#######"),
        billing_provider_id=fake.bothify("R######"),
        billing_provider_name=prov_disp,
    )

def gen_observation(enc: Encounter, report_row: pd.Series) -> Observation:
    admit_ts = datetime.strptime(enc.admit_datetime, "%Y-%m-%d %H:%M:%S")
    disch_ts = datetime.strptime(enc.discharge_datetime, "%Y-%m-%d %H:%M:%S")
    delta_sec = int((disch_ts - admit_ts).total_seconds())
    completed = admit_ts + timedelta(seconds=random.randint(0, max(1, delta_sec)))
    return Observation(
        encounter_id=enc.encounter_id,
        observation_id=str(report_row["report_uid"]),
        cpt_code=str(report_row["cpt_code"]),
        icd_code=str(report_row["icd_code"]),
        placer_order_number=enc.placer_order_number,
        filler_order_number=enc.filler_order_number,
        procedure_description=str(report_row["procedure_description"]),
        observation_text=str(report_row["report_text"]),
        observation_sub_id="1",
        result_status="F",
        completed_time=completed.strftime("%Y-%m-%d %H:%M:%S"),
    )

# ------------------------- HL7 segments -------------------------

def seg_msh(message_type: str) -> str:
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    structures = {"ADT^A01":"ADT_A01","ORU^R01":"ORU_R01","DFT^P03":"DFT_P03"}
    if "^" in message_type and message_type.count("^") == 1:
        message_type = f"{message_type}^{structures.get(message_type, '')}"
    control_id = str(uuid.uuid4())
    return (
        f"MSH|^~\\&|FAKELAB|FAKEFACILITY|CMX|STAGE|{now}||{message_type}|{control_id}|P|2.5|||AL|NE||UNICODE UTF-8"
    )

def seg_evn(enc: Encounter, event_type: str = "A01") -> str:
    evn_ts = ts_hl7(enc.admit_datetime)
    return f"EVN|{event_type}|{evn_ts}||||{evn_ts}"

def seg_pid(p: Patient) -> str:
    # Keep simple: address (1 component) and ZIP in PID-11.5
    addr = one_line(p.address)
    phone = one_line(p.phone)
    return (
        f"PID|1||{p.patient_id}||{hl7_name_from_display(p.patient_name)}||"
        f"{ts_hl7(p.date_of_birth)}|{p.sex}||{p.race}|{addr}^^^^{p.zip_code}||{phone}||{phone}|||{p.ssn}"
    )

def seg_pv1(enc: Encounter) -> str:
    admit = ts_hl7(enc.admit_datetime)
    disch = ts_hl7(enc.discharge_datetime)
    attending_nm = hl7_name_from_full(enc.attending_provider_name)
    return (
        f"PV1|1|{enc.patient_class}|{enc.assigned_patient_location}|||"
        f"{enc.attending_provider_id}^{attending_nm}|||||||||||||{enc.visit_number}|||||||||||||||||||||||||{admit}|{disch}"
    )
    

def seg_orc(enc: Encounter) -> str:
    ordering_nm = hl7_name_from_full(enc.ordering_provider_name)
    return f"ORC|RE|{enc.placer_order_number}|{enc.filler_order_number}||CM|||||{enc.ordering_provider_id}^{ordering_nm}"

def seg_obr(enc: Encounter, obs: Optional[Observation]) -> str:
    cpt = obs.cpt_code if obs else ""
    desc = obs.procedure_description if obs else ""
    usi = f"{cpt}^{desc}^CPT" if (cpt or desc) else ""
    when = ts_hl7(obs.completed_time if obs else enc.admit_datetime)
    ordering_nm = hl7_name_from_full(enc.ordering_provider_name)
    return (
        f"OBR|1|{enc.placer_order_number}|{enc.filler_order_number}|{usi}|R|||{when}||||||||{enc.ordering_provider_id}^{ordering_nm}"
    )

def seg_obx(obs: Observation) -> str:
    ident = f"{obs.cpt_code}^{obs.procedure_description}^CPT"
    sub_id = obs.observation_sub_id or "1"
    value = one_line(obs.observation_text or "")
    status = obs.result_status or "F"
    producer = "FAKEFACILITY^RAD_DEPT1"
    return f"OBX|1|TX|{ident}|{sub_id}|{value}||||||{status}|||{producer}"

def seg_obx_lines(obs: Observation, start_set_id: int = 1, wrap_width: int = 200) -> List[str]:
    """
    Render observation_text as multiple OBX segments (one per line).
    - OBX-1 (Set ID) increments per segment, starting at start_set_id
    - OBX-3 is the CPT-based identifier used previously
    - OBX-4 (Observation Sub-ID) is the line number to preserve order
    - OBX-5 holds the (escaped) line content
    """
    ident = f"{obs.cpt_code}^{obs.procedure_description}^CPT"
    status = obs.result_status or "F"
    producer = "FAKEFACILITY^RAD_DEPT1"
    text = obs.observation_text or ""

    # Normalize newlines and wrap long lines for safer segment lengths
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = norm.split("\n")

    lines: List[str] = []
    for ln in raw_lines:
        ln = ln.strip()
        if not ln:
            # preserve blank line as an empty value
            lines.append("")
            continue
        if len(ln) > wrap_width:
            chunks = textwrap.wrap(ln, width=wrap_width, break_long_words=False, break_on_hyphens=False)
            lines.extend(chunks if chunks else [""])
        else:
            lines.append(ln)

    segs: List[str] = []
    set_id = start_set_id
    sub_id = 1
    for ln in lines:
        val = hl7_escape(ln)
        segs.append(f"OBX|{set_id}|TX|{ident}|{sub_id}|{val}||||||{status}|||{producer}")
        set_id += 1
        sub_id += 1
    return segs


def seg_ft1(tx: Transaction, obs: Optional[Observation]) -> str:
    tx_dt = ts_hl7(tx.transaction_date)
    post = tx_dt
    cpt = obs.cpt_code if obs else ""
    desc = (obs.procedure_description if obs else "CHARGE")
    qty = tx.transaction_quantity
    unit = tx.unit_cost
    amt = tx.transaction_amount
    plan = tx.insurance_plan_id
    fee = tx.fee_schedule
    dept = "RAD"
    ptype = "OUTPATIENT"
    return (
        f"FT1|1|{tx.transaction_id}| |{tx_dt}|{post}|CG|{cpt}|{desc}|{qty}|{unit}|{amt}|USD|{plan}|{fee}|{dept}|{ptype}| |{cpt}||"
    )

# ------------------------- Assemblers -------------------------

def build_adt(
    p: Patient,
    enc: Encounter,
    miles: int = AIRNOW_MILES_DEFAULT,
    add_police_obx: bool = True,
    add_air_obx: bool = True,
    add_poverty_obx: bool = True,
) -> str:
    """
    Build an ADT^A01 message and optionally append SDOH OBXs:
      - OBX-1: Police station count by ZIP (ESRI)
      - OBX-2: Air quality (AirNow) by ZIP
    """
    parts = [
        seg_msh("ADT^A01"),
        seg_evn(enc, "A01"),
        seg_pid(p),
        seg_pv1(enc),
    ]

    set_id = 1




    # SDOH: Police station count OBX
    if add_police_obx and getattr(p, "zip_code", ""):
        cnt = get_police_station_count_by_zip(getattr(p, "zip_code", ""))
        parts.append(build_obx_police_count(cnt, set_id=set_id))
        set_id += 1
        print(f"[SDOH] Police stations in ZIP {p.zip_code}: {cnt}")

    # SDOH: Air quality OBX (AirNow)
    if add_air_obx and getattr(p, "zip_code", ""):
        aq = get_air_quality_by_zip(p.zip_code, miles=miles)
        obx_aq = build_obx_air_quality(aq, set_id=set_id)
        if obx_aq:
            parts.append(obx_aq)
            set_id += 1
            print(f"[SDOH] Air quality for {p.zip_code}: {aq.get('aqi', 'NA')} ({aq.get('category', 'NA')})")
    # SDOH: Poverty % (Census ACS by ZCTA)
    if add_poverty_obx and getattr(p, "zip_code", ""):
        pov = get_poverty_pct_by_zcta(p.zip_code)
        obx_pov = build_obx_poverty_pct(pov, set_id=set_id)
        if obx_pov:
            parts.append(obx_pov)
            set_id += 1
        # AI-predicted vitals OBXs
    try:
        age = datetime.now().year - datetime.strptime(p.date_of_birth, "%Y-%m-%d").year
        pov = get_poverty_pct_by_zcta(p.zip_code) or 0.0
        aq = get_air_quality_by_zip(p.zip_code)
        aqi_val = float(aq.get("aqi", 50)) if aq else 50.0
        print(f"[SDOH] Poverty % for {p.zip_code}: {pov}")

        vitals = predict_vitals(age, pov, aqi_val)
        obx_vitals = build_obx_vitals(vitals, start_set_id=set_id)
        parts.extend(obx_vitals)
        set_id += len(obx_vitals)
        
        print(f"[AI] Predicted vitals for {p.patient_id}: {vitals}")

    except Exception as e:
        print(f"[WARN] Failed to generate vitals for {p.patient_id}: {e}")



    return "\r".join(parts)

def build_oru(p: Patient, enc: Encounter, obs_list: List[Observation]) -> str:
    obr = seg_obr(enc, obs_list[0]) if obs_list else "OBR|1||||"
    obxs: List[str] = []
    set_id = 1
    for o in obs_list:
        parts = seg_obx_lines(o, start_set_id=set_id)
        obxs.extend(parts)
        set_id += len(parts)
    return "\r".join([seg_msh("ORU^R01"), seg_pid(p), seg_pv1(enc), obr] + obxs)


def build_dft(p: Patient, enc: Encounter, txs: List[Transaction], obs_list: List[Observation]) -> str:
    ft1s = [seg_ft1(t, obs_list[0] if obs_list else None) for t in txs]
    parts = [seg_msh("DFT^P03"), seg_pid(p), seg_pv1(enc)] + ft1s
    if obs_list:
        parts.append(seg_obr(enc, obs_list[0]))
        parts.extend(seg_obx(o) for o in obs_list)
    return "\r".join(parts)

# ------------------------- Pipeline -------------------------

def run_pipeline(
    n_patients: int,
    report_glob: str,
    seed: Optional[int],
    per_encounter: bool,
    bulk: bool,
    out_dir: str,
    miles: int,
) -> Dict[str,int]:
    print(f"[INFO] Starting pipeline: {n_patients} patients, output={out_dir}, bulk={bulk}, per_encounter={per_encounter}")

    if seed is not None:
        random.seed(seed)
        Faker.seed(seed)
    os.makedirs(out_dir, exist_ok=True)
    reports = load_reports(report_glob)

    # Single run timestamp to guarantee exactly one bulk file per message type, per run
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    count = {"ADT":0, "ORU":0, "DFT":0}
    for _ in range(n_patients):
        p = gen_patient()
        e = gen_encounter(p.patient_id)
        t = gen_transaction(e.encounter_id)
        report_row = reports.sample(n=1).iloc[0]
        o = gen_observation(e, report_row)
        print(f"[INFO] Generated patient {p.patient_id}, encounter {e.encounter_id}, ZIP={p.zip_code}")


        # Assemble
        adt = build_adt(p, e, miles=miles)
        oru = build_oru(p, e, [o])
        dft = build_dft(p, e, [t], [o])

        safe_enc = re.sub(r"[^A-Za-z0-9_\-]", "_", e.encounter_id)

        if per_encounter:
            with open(os.path.join(out_dir, f"ADT_{safe_enc}_{run_ts}.hl7"), "w", encoding="utf-8") as f:
                f.write(adt)
            with open(os.path.join(out_dir, f"ORU_{safe_enc}_{run_ts}.hl7"), "w", encoding="utf-8") as f:
                f.write(oru)
            with open(os.path.join(out_dir, f"DFT_{safe_enc}_{run_ts}.hl7"), "w", encoding="utf-8") as f:
                f.write(dft)
            count["ADT"] += 1; count["ORU"] += 1; count["DFT"] += 1
        else:
            # Append to ONE bulk file per type using the fixed run_ts
            bulk_files = {
                "ADT": os.path.join(out_dir, f"ADT_{run_ts}.hl7"),
                "ORU": os.path.join(out_dir, f"ORU_{run_ts}.hl7"),
                "DFT": os.path.join(out_dir, f"DFT_{run_ts}.hl7"),
            }
            for key, msg in [("ADT", adt), ("ORU", oru), ("DFT", dft)]:
                fname = bulk_files[key]
                mode = "a" if os.path.exists(fname) else "w"
                with open(fname, mode, encoding="utf-8") as f:
                    if mode == "a":
                        f.write("\n\n")
                    f.write(msg)
                count[key] += 1
    print(f"[WRITE] Wrote encounter {safe_enc}: ADT, ORU, DFT")
    return count

# ------------------------- CLI -------------------------

def main():

    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(levelname)s: %(message)s')
    logging.getLogger("urllib3").setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser(description="Local HL7 generator (no Databricks)")
    parser.add_argument("--patients", type=int, default=100, help="Number of synthetic patients to generate")
    parser.add_argument("--report-glob", type=str, default="./input/reports/*.csv", help="Glob for report CSVs")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    out = parser.add_mutually_exclusive_group()
    out.add_argument("--per-encounter", action="store_true", help="Write one file per encounter per message type")
    out.add_argument("--bulk", action="store_true", help="Write one bulk file per message type (default)")
    parser.add_argument("--out-dir", type=str, default="./output", help="Folder to write HL7 files")
    parser.add_argument("--miles", type=int, default=AIRNOW_MILES_DEFAULT, help="Miles radius for AirNow ZIP lookup")

    args = parser.parse_args()

    # default to bulk if neither flag provided
    per_encounter = args.per_encounter
    bulk = args.bulk or (not args.per_encounter)

    counts = run_pipeline(
        n_patients=args.patients,
        report_glob=args.report_glob,
        seed=args.seed,
        per_encounter=per_encounter,
        bulk=bulk,
        out_dir=args.out_dir,
        miles=args.miles,
    )

    print(f"Generated {counts['ADT']} ADT, {counts['ORU']} ORU, {counts['DFT']} DFT messages -> {args.out_dir}")

if __name__ == "__main__":
    main()
