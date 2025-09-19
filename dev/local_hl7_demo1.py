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

import json
from urllib.parse import quote

import pandas as pd
from faker import Faker
import requests

# ------------------------- Config -------------------------

# Hardcoded AirNow API key (as requested)
AIRNOW_API_KEY = "86B0C1FD-C0D8-4A01-BA10-C04A0B718B6C"
AIRNOW_MILES_DEFAULT = 25

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
        return 0
    z5 = str(zip5).strip()[:5]
    if not z5.isdigit() or len(z5) != 5:
        return 0

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

    # SDOH: Air quality OBX (AirNow)
    if add_air_obx and getattr(p, "zip_code", ""):
        aq = get_air_quality_by_zip(p.zip_code, miles=miles)
        obx_aq = build_obx_air_quality(aq, set_id=set_id)
        if obx_aq:
            parts.append(obx_aq)
            set_id += 1

    return "\r".join(parts)

def build_oru(p: Patient, enc: Encounter, obs_list: List[Observation]) -> str:
    obr = seg_obr(enc, obs_list[0]) if obs_list else "OBR|1||||"
    obxs = [seg_obx(o) for o in obs_list]
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

    return count

# ------------------------- CLI -------------------------

def main():
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
