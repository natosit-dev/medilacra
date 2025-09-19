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
    return f"OBX|{set_id}|NM|ACS_POVERTY_PCT^Poverty (ACS 5-year)%^L||{val}|||||F"
