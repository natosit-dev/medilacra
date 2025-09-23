import json, time, requests
from functools import lru_cache
from urllib.parse import quote
from typing import Dict, Optional
from .config import AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR
from .utils import hl7_escape

# --- ArcGIS police station count ---
_ARCGIS_HOST = "https://services1.arcgis.com"
_ARCGIS_PATH = "/Hp6G80Pky0om7QvQ/ArcGIS/rest/services/Local_Law_Enforcement_Locations/FeatureServer/0/query"

def _arcgis_stats_url(z5: str) -> str:
    where = f"ZIP LIKE '{z5}%'"
    stats = [{"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "station_count"}]
    qs = f"where={quote(where)}&outStatistics={quote(json.dumps(stats,separators=(',',':')))}&groupByFieldsForStatistics=ZIP&returnGeometry=false&f=json"
    return f"{_ARCGIS_HOST}{_ARCGIS_PATH}?{qs}"

def _arcgis_count_url(z5: str) -> str:
    where = f"ZIP LIKE '{z5}%'"
    return f"{_ARCGIS_HOST}{_ARCGIS_PATH}?where={quote(where)}&returnCountOnly=true&f=json"

def get_police_station_count_by_zip(zip5: Optional[str], timeout: float = 6.0) -> int | str:
    if not zip5: return "No Data"
    z5 = str(zip5).strip()[:5]
    if not z5.isdigit() or len(z5) != 5: return "No Data"
    for attempt in range(3):
        try:
            r = requests.get(_arcgis_stats_url(z5), timeout=timeout)
            if r.status_code == 200:
                body = r.json(); feats = body.get("features") or []
                if feats:
                    cnt = int((feats[0] or {}).get("attributes",{}).get("station_count", 0))
                    if cnt > 0: return cnt
            if r.status_code in (429,500,502,503,504): time.sleep(0.5*(attempt+1)); continue
            break
        except Exception: time.sleep(0.5*(attempt+1))
    for attempt in range(2):
        try:
            r = requests.get(_arcgis_count_url(z5), timeout=timeout)
            if r.status_code == 200:
                return max(0, int((r.json() or {}).get("count", 0)))
            if r.status_code in (429,500,502,503,504): time.sleep(0.5*(attempt+1)); continue
            break
        except Exception: time.sleep(0.5*(attempt+1))
    return 0

def build_obx_police_count(count: int | str, set_id: int = 1) -> str:
    try: val = max(0, int(count))
    except Exception: val = 0
    return f"OBX|{set_id}|NM|ESRI_POLICE_COUNT^Police Station Count^L||{val}|||||F"

# --- AirNow ---
@lru_cache(maxsize=512)
def get_air_quality_by_zip(zip_code: str, miles: int = AIRNOW_MILES_DEFAULT) -> Dict[str,str]:
    if not (zip_code and AIRNOW_API_KEY): return {}
    url = "https://www.airnowapi.org/aq/observation/zipCode/current/"
    params = {"format":"application/json","zipCode":zip_code,"distance":str(miles),"API_KEY":AIRNOW_API_KEY}
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json() or []
                if not data: return {}
                worst = max(data, key=lambda x: int(x.get("AQI", -1)))
                return {
                    "aqi": worst.get("AQI"),
                    "parameter": worst.get("ParameterName"),
                    "category": (worst.get("Category") or {}).get("Name"),
                    "obs_time": f"{worst.get('DateObserved','')} {worst.get('HourObserved','')} {worst.get('LocalTimeZone','')}",
                    "area": worst.get("ReportingArea"), "state": worst.get("StateCode"), "source": "AirNow",
                }
            elif resp.status_code in (429,500,502,503): time.sleep(0.5*(attempt+1))
        except Exception: time.sleep(0.5*(attempt+1))
    return {}

def build_obx_air_quality(aq: Dict[str,str], set_id: int = 2) -> str:
    if not aq: return ""
    aqi, param, category = aq.get("aqi",""), aq.get("parameter",""), aq.get("category","")
    place = ", ".join([x for x in [aq.get("area",""), aq.get("state","")] if x])
    obs = aq.get("obs_time","")
    value = f"AQI={aqi}^{category}^{param}^{place} {obs}".strip()
    return f"OBX|{set_id}|TX|AIRNOW_AQI^Air Quality Index^L|1|{value}||||||F"

# --- Census ACS Poverty% ---
def _http_get_json(url: str, params: dict | None = None, timeout: float = 8.0):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200: return r.json()
            if r.status_code in (429,500,502,503,504): time.sleep(0.5*(attempt+1))
        except Exception: time.sleep(0.5*(attempt+1))
    return None

@lru_cache(maxsize=1024)
def get_poverty_pct_by_zcta(zcta: str, year: str = ACS_YEAR) -> float | None:
    if not zcta: return None
    z5 = str(zcta).strip()[:5]
    if not z5.isdigit() or len(z5) != 5: return None
    base = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {"get":"B17001_001E,B17001_002E,NAME","for": f"zip code tabulation area:{z5}"}
    data = _http_get_json(base, params=params, timeout=8.0)
    if not isinstance(data, list) or len(data) < 2: return None
    try:
        total = float(data[1][0] or 0); below = float(data[1][1] or 0)
        if total <= 0: return None
        return round((below / total) * 100.0, 1)
    except Exception:
        return None

def build_obx_poverty_pct(pct: float | None, set_id: int = 3) -> str:
    if pct is None: return ""
    try: val = f"{float(pct):.1f}"
    except Exception: return ""
    return f"OBX|{set_id}|NM|ACS_POVERTY_PCT^Poverty (ACS 5-year)%^L||{val}||||||F"

# Adding More APIs/SDOH Data


# --- Additions: keyless public APIs for SDOH ---

import time
from functools import lru_cache
import requests

# Reuse your existing _http_get_json if present; if not, keep this local helper
def _http_get_json_with_retries(url: str, params: dict | None = None, timeout: float = 8.0, attempts: int = 3):
    for attempt in range(attempts):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(0.5 * (attempt + 1))
                continue
            break
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None

# 1) Census Geocoder: ZIP -> county/state/coords (no key)
@lru_cache(maxsize=2048)
def zip_to_county_fips(zip5: str) -> dict | None:
    """
    Returns:
      {
        'state_fips': '25',
        'county_fips': '25025' (state_fips + county_3),
        'county_name': 'Suffolk County',
        'state_abbrev': 'MA',
        'lat': 42.36, 'lon': -71.06
      } or None
    """
    if not zip5 or len(str(zip5)) < 5:
        return None
    z5 = str(zip5).strip()[:5]
    url = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
    params = {
        "address": z5,
        "benchmark": "Public_AR_Census2020",
        "vintage": "Census2020_Census2020",
        "format": "json",
    }
    data = _http_get_json_with_retries(url, params=params, timeout=8)
    try:
        am = (data or {}).get("result", {}).get("addressMatches", [])[0]
        geos = am.get("geographies", {})
        counties = geos.get("Counties") or []
        county = counties[0] if counties else {}
        state_fips = str(county.get("STATE", "")).zfill(2)
        c3 = str(county.get("COUNTY", "")).zfill(3)
        county_fips = f"{state_fips}{c3}" if state_fips and c3 else None
        return {
            "state_fips": state_fips or None,
            "county_fips": county_fips,
            "county_name": county.get("NAME") or county.get("COUNTY_NAME"),
            "state_abbrev": county.get("USPS"),
            "lat": am.get("coordinates", {}).get("y"),
            "lon": am.get("coordinates", {}).get("x"),
        }
    except Exception:
        return None

# 2) CDC PLACES (SODA API): select a measure by ZCTA (no key, but rate-limited)
@lru_cache(maxsize=2048)
def get_places_measure_by_zcta(zcta: str, measure_name: str = "Obesity among adults aged >=18 years") -> float | None:
    """
    Returns the Data_Value for the requested measure (percentage) for a ZCTA, or None if not available.
    """
    if not zcta or len(str(zcta)) < 5:
        return None
    z5 = str(zcta).strip()[:5]
    # 2022 PLACES ZCTA resource id: as of writing often 'gd4x-jyhw'; SODA is stable but ids can change over time.
    # Keep both measure and zcta in the query to avoid downloading the world.
    base = "https://data.cdc.gov/resource/gd4x-jyhw.json"
    params = {
        "$select": "zcta5,measure,Data_Value",
        "$limit": "1",
        "$where": "zcta5 = '{}' AND measure = '{}'".format(z5.replace("'", "''"), measure_name.replace("'", "''")),
    }
    data = _http_get_json_with_retries(base, params=params, timeout=8)
    if isinstance(data, list) and data:
        try:
            return float(data[0].get("data_value"))
        except Exception:
            return None
    return None

def build_obx_places_obesity(zcta: str, set_id: int = 10) -> str:
    """OBX for CDC PLACES: Adults with obesity (%)"""
    from .utils import hl7_escape  # reuse your existing utility
    val = get_places_measure_by_zcta(zcta, "Obesity among adults aged >=18 years")
    if val is None:
        return f"OBX|{set_id}|TX|PLACES_OBESITY^Adults with Obesity (%)^L||N/A|||||F"
    return f"OBX|{set_id}|NM|PLACES_OBESITY^Adults with Obesity (%)^L||{val:.1f}|%||||F"

# 3) BLS LAUS (no key): county unemployment mapped via ZIP->county
@lru_cache(maxsize=4096)
def get_unemployment_rate_by_zip(zip5: str) -> float | None:
    """
    Looks up the county via Census, then fetches latest unemployment rate via BLS LAUS.
    Series ID format: LAUCN + state(2) + county(3) + 0000000003
    """
    geo = zip_to_county_fips(zip5)
    if not geo or not geo.get("county_fips"):
        return None
    state_fp = geo["state_fips"]
    county3 = geo["county_fips"][2:]
    series_id = f"LAUCN{state_fp}{county3}0000000003"
    url = f"https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id}"
    params = {"latest": "true"}
    data = _http_get_json_with_retries(url, params=params, timeout=8)
    try:
        series = (data or {}).get("Results", {}).get("series", [])
        pts = series[0].get("data", []) if series else []
        if not pts:
            return None
        return float(pts[0]["value"])
    except Exception:
        return None

def build_obx_unemployment(zip5: str, set_id: int = 11) -> str:
    """OBX for county unemployment rate (%) derived from ZIP"""
    rate = get_unemployment_rate_by_zip(zip5)
    if rate is None:
        return f"OBX|{set_id}|TX|BLS_UNEMPLOYMENT^Unemployment Rate (%)^L||N/A|||||F"
    return f"OBX|{set_id}|NM|BLS_UNEMPLOYMENT^Unemployment Rate (%)^L||{rate:.1f}|%||||F"
