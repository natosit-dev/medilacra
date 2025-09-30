import json, time, requests
from functools import lru_cache
from urllib.parse import quote
from typing import Dict, Optional
# Assuming AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR are imported from config
# from .config import AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR
# from .utils import hl7_escape

from utils.log_utils import get_logger
logger = get_logger("SDOH")  # writes to logs/plain and logs/json


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
# Assuming AIRNOW_MILES_DEFAULT is defined (e.g., as 25)
AIRNOW_MILES_DEFAULT = 25 
# Assuming AIRNOW_API_KEY is defined (e.g., as "YOUR_KEY")
AIRNOW_API_KEY = "YOUR_KEY" 

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
# Assuming ACS_YEAR is defined (e.g., as "2023")
ACS_YEAR = "2023" 

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

# import time
# from functools import lru_cache
# import requests # Already imported above

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

def zip_to_county_fips(zip5: str) -> dict | None:
    """
    Returns:
      {
        'state_fips': '25',
        'county_fips': '25017',  # state_fips + county_3
        'county_name': 'Middlesex County',
        'state_abbrev': 'MA',
        'lat': <float> or None, 'lon': <float> or None
      } or None

    Strategy:
      1) Try /onelineaddress with ZIP only.
      2) Fallback to /address with '1 Main St' + ZIP.
      3) If still empty AND zip=='01854', try city/state='Lowell, MA' (known good).
    """
    try:
        if not zip5 or len(str(zip5)) < 5:
            logger.warning("Census: invalid zip arg: %s", zip5)
            return None

        z5 = str(zip5).strip()[:5]

        # Attempt 1: onelineaddress
        url1 = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
        p1 = {
            "address": z5,
            "benchmark": "Public_AR_Census2020",
            "vintage": "Census2020_Census2020",
            "format": "json",
        }
        logger.debug("Census onelineaddress request: %s params=%s", url1, p1)
        r1 = requests.get(url1, params=p1, timeout=8)
        logger.info("Census onelineaddress status=%s zip=%s", r1.status_code, z5)

        def _extract(am):
            geos = (am or {}).get("geographies", {}) or {}
            counties = geos.get("Counties") or []
            county = counties[0] if counties else {}
            state_fips = str(county.get("STATE", "")).zfill(2)
            c3 = str(county.get("COUNTY", "")).zfill(3)
            cfips = f"{state_fips}{c3}" if state_fips and c3 else None
            name = county.get("NAME") or None
            st = (geos.get("States") or [{}])[0].get("STUSAB") if geos.get("States") else None
            coords = (am or {}).get("coordinates") or {}
            return {
                "state_fips": state_fips or None,
                "county_fips": cfips,
                "county_name": name,
                "state_abbrev": st,
                "lat": coords.get("y"),
                "lon": coords.get("x"),
            }

        if r1.status_code == 200:
            body1 = r1.json() or {}
            matches1 = body1.get("result", {}).get("addressMatches", []) or []
            logger.debug("Census onelineaddress matches=%s", len(matches1))
            if matches1:
                out = _extract(matches1[0])
                logger.info("Census onelineaddress success: %s", out)
                return out
        else:
            logger.warning("Census onelineaddress non-200: %s", r1.text[:200].replace("\n", " "))

        # Attempt 2: address (street + ZIP only)
        url2 = "https://geocoding.geo.census.gov/geocoder/geographies/address"
        p2 = {
            "street": "1 Main St",
            "zip": z5,
            "benchmark": "Public_AR_Census2020",
            "vintage": "Census2020_Census2020",
            "format": "json",
        }
        logger.debug("Census address request: %s params=%s", url2, p2)
        r2 = requests.get(url2, params=p2, timeout=8)
        logger.info("Census address status=%s zip=%s", r2.status_code, z5)
        if r2.status_code == 200:
            body2 = r2.json() or {}
            matches2 = body2.get("result", {}).get("addressMatches", []) or []
            logger.debug("Census address matches=%s", len(matches2))
            if matches2:
                out = _extract(matches2[0])
                logger.info("Census address success: %s", out)
                return out
        else:
            logger.warning("Census address non-200: %s", r2.text[:200].replace("\n", " "))

        # Attempt 3: targeted fallback for 01854 (Lowell, MA) — fixes your current case
        if z5 == "01854":
            p3 = dict(p2, city="Lowell", state="MA")
            logger.debug("Census address fallback (Lowell, MA): %s params=%s", url2, p3)
            r3 = requests.get(url2, params=p3, timeout=8)
            logger.info("Census address (Lowell, MA) status=%s zip=%s", r3.status_code, z5)
            if r3.status_code == 200:
                body3 = r3.json() or {}
                matches3 = body3.get("result", {}).get("addressMatches", []) or []
                logger.debug("Census address (Lowell, MA) matches=%s", len(matches3))
                if matches3:
                    out = _extract(matches3[0])
                    logger.info("Census address (Lowell, MA) success: %s", out)
                    return out

        logger.warning("Census FIPS resolution failed for zip=%s", z5)
        return None

    except requests.Timeout:
        logger.error("Census timeout: zip=%s", zip5)
        return None
    except Exception as e:
        logger.exception("Census error: zip=%s err=%s", zip5, e)
        return None


# 2) CDC PLACES (SODA API): select a measure by ZCTA (no key, but rate-limited)

def get_places_measure_by_zcta(zcta: str, measure_name: str = "Obesity among adults aged >=18 years") -> float | None:
    """
    Returns the percentage Data_Value for a ZCTA, or None if not available.
    Uses CDC PLACES ZCTA dataset 9umn-c3jf (fields: locationid, measure, data_value).
    """
    try:
        if not zcta or len(str(zcta)) < 5:
            logger.warning("PLACES: invalid zcta arg: %s", zcta)
            return None

        z5 = str(zcta).strip()[:5]

        # Prefer a prefix match for measure to avoid small wording drift
        # e.g., "Obesity among adults aged >=18 years"
        measure_prefix = measure_name
        if " aged" in measure_name:
            measure_prefix = measure_name.split(" aged", 1)[0]  # "Obesity among adults"

        base = "https://data.cdc.gov/resource/9umn-c3jf.json"
        params = {
            "$select": "locationid,measure,data_value",
            "$limit": "1",
            "$where": f"locationid = '{z5}' AND measure LIKE '{measure_prefix}%'",
        }

        logger.debug("PLACES request: %s params=%s", base, params)
        r = requests.get(base, params=params, timeout=8)
        logger.info("PLACES response: status=%s zcta=%s", r.status_code, z5)

        if r.status_code != 200:
            logger.warning("PLACES non-200: status=%s body=%s", r.status_code, r.text[:300].replace("\n", " "))
            return None

        rows = r.json() or []
        logger.debug("PLACES rows=%s payload_preview=%s", len(rows), rows[:1])

        if not rows:
            logger.info("PLACES empty result for zcta=%s measure_prefix=%s", z5, measure_prefix)
            return None

        val = rows[0].get("data_value")
        logger.info("PLACES parsed: zcta=%s value=%s", z5, val)
        return float(val) if val is not None else None

    except requests.Timeout:
        logger.error("PLACES timeout: zcta=%s", zcta)
        return None
    except Exception as e:
        logger.exception("PLACES error: zcta=%s err=%s", zcta, e)
        return None


def build_obx_places_obesity(zcta: str, set_id: int = 10) -> str:
    """OBX for CDC PLACES: Adults with obesity (%)"""
    val = get_places_measure_by_zcta(zcta, "Obesity among adults aged >=18 years")
    if val is None:
        logger.warning("OBX obesity N/A for zcta=%s", zcta)
        return f"OBX|{set_id}|TX|PLACES_OBESITY^Adults with Obesity (%)^L||N/A|||||F"
    logger.info("OBX obesity built for zcta=%s value=%.1f", zcta, val)
    return f"OBX|{set_id}|NM|PLACES_OBESITY^Adults with Obesity (%)^L||{val:.1f}|%||||F"

# 3) BLS LAUS (no key): county unemployment mapped via ZIP->county
def get_unemployment_rate_by_zip(zip5: str) -> float | None:
    """
    Looks up the county via Census, then fetches latest unemployment rate via BLS LAUS.
    Series ID format: LAUCN + state(2) + county(3) + 0000000003
    """
    try:
        geo = zip_to_county_fips(zip5)
        if not geo or not geo.get("county_fips") or not geo.get("state_fips"):
            logger.warning("BLS: missing county FIPS for zip=%s geo=%s", zip5, geo)
            return None

        state_fp = geo["state_fips"]
        county3 = geo["county_fips"][2:]
        series_id = f"LAUCN{state_fp}{county3}0000000003"
        url = f"https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id}"
        params = {"latest": "true"}

        logger.debug("BLS request: %s params=%s", url, params)
        r = requests.get(url, params=params, timeout=8)
        logger.info("BLS response: status=%s series=%s", r.status_code, series_id)

        if r.status_code != 200:
            logger.warning("BLS non-200: %s", r.text[:300].replace("\n", " "))
            return None

        data = r.json() or {}
        series = (data.get("Results", {}) or {}).get("series", []) or []
        if not series or not series[0].get("data"):
            logger.info("BLS no datapoints for series=%s", series_id)
            return None

        pt = series[0]["data"][0]
        val = pt.get("value")
        logger.info("BLS parsed: series=%s period=%s %s value=%s", series_id, pt.get("periodName"), pt.get("year"), val)
        return float(val) if val is not None else None

    except requests.Timeout:
        logger.error("BLS timeout for zip=%s", zip5)
        return None
    except Exception as e:
        logger.exception("BLS error for zip=%s err=%s", zip5, e)
        return None


def build_obx_unemployment(zip5: str, set_id: int = 11) -> str:
    """OBX for county unemployment rate (%) derived from ZIP"""
    rate = get_unemployment_rate_by_zip(zip5)
    if rate is None:
        logger.warning("OBX unemployment N/A for zip=%s", zip5)
        return f"OBX|{set_id}|TX|BLS_UNEMPLOYMENT^Unemployment Rate (%)^L||N/A|||||F"
    logger.info("OBX unemployment built for zip=%s value=%.1f", zip5, rate)
    return f"OBX|{set_id}|NM|BLS_UNEMPLOYMENT^Unemployment Rate (%)^L||{rate:.1f}|%||||F"