import json, time, requests
from functools import lru_cache
from urllib.parse import quote
from typing import Dict, Optional
from .config import AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR
# Assuming AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR are imported from config
# from .config import AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR
# from .utils import hl7_escape

from utils.log_utils import get_logger
logger = get_logger("SDOH")  # writes to logs/plain and logs/json

try:
    # any of these may exist in your project; we gracefully handle if not
    from .refdata import get_city_state_by_zip as _get_city_state_by_zip  # returns dict(city, state) or tuple
except Exception:
    try:
        from refdata import get_city_state_by_zip as _get_city_state_by_zip
    except Exception:
        _get_city_state_by_zip = None

def _city_state_for_zip(z5: str):
    """
    Returns (city, state) if known from refdata, else (None, None).
    Accepts many possible refdata return shapes.
    """
    if not _get_city_state_by_zip:
        return None, None
    try:
        res = _get_city_state_by_zip(z5)
        if isinstance(res, dict):
            return res.get("city"), res.get("state")
        if isinstance(res, (list, tuple)) and len(res) >= 2:
            return res[0], res[1]
    except Exception:
        pass
    return None, None

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

# --- AirNow (file-cached) ---
import os, time, json, requests, datetime
try:
    import yaml  # PyYAML
except Exception:
    yaml = None  # we'll log if missing

AIRNOW_MILES_DEFAULT = 25  # keep your existing defaults/constants


# Cache file location: project_root/data/airnow_cache.yaml
# Compute path relative to this file so it works from /hl7_demo
_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
_AIRNOW_CACHE_PATH = os.path.join(_DATA_DIR, "airnow_cache.yaml")

def _now_utc_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0, tzinfo=datetime.timezone.utc).isoformat()

def _ensure_data_dir():
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
    except Exception as e:
        logger.warning("AirNow cache: failed to ensure data dir %s err=%s", _DATA_DIR, e)

def _load_airnow_cache() -> dict:
    if not yaml:
        logger.warning("AirNow cache: PyYAML not installed; skipping disk cache.")
        return {}
    if not os.path.exists(_AIRNOW_CACHE_PATH):
        return {}
    try:
        with open(_AIRNOW_CACHE_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("AirNow cache: read error %s err=%s", _AIRNOW_CACHE_PATH, e)
        return {}

def _save_airnow_cache(cache: dict) -> None:
    if not yaml:
        return
    try:
        _ensure_data_dir()
        tmp = _AIRNOW_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(cache, f, sort_keys=True, allow_unicode=True)
        os.replace(tmp, _AIRNOW_CACHE_PATH)
    except Exception as e:
        logger.warning("AirNow cache: write error %s err=%s", _AIRNOW_CACHE_PATH, e)

def _airnow_observation(zip_code: str, miles: int) -> dict:
    """Calls AirNow and returns the 'worst' observation dict or {}."""
    url = "https://www.airnowapi.org/aq/observation/zipCode/current/"
    params = {"format": "application/json", "zipCode": zip_code, "distance": str(miles), "API_KEY": AIRNOW_API_KEY}
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json() or []
                if not data:
                    return {}
                worst = max(data, key=lambda x: int(x.get("AQI", -1)))
                return worst or {}
            elif resp.status_code in (429, 500, 502, 503):
                time.sleep(0.5 * (attempt + 1))
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return {}

def get_air_quality_by_zip(zip_code: str, miles: int = AIRNOW_MILES_DEFAULT, ttl_hours: int = 6) -> dict:
    """
    File-cached AirNow lookup.
    Cache key: "{ZIP}|{miles}"
    YAML record:
      { key:
          { zip, miles, pulled_at, value: {aqi, parameter, category, obs_time, area, state, source} }
      }
    """
    if not (zip_code and AIRNOW_API_KEY):
        return {}

    z5 = str(zip_code).strip()[:5]
    if not z5.isdigit() or len(z5) != 5:
        logger.warning("AirNow invalid ZIP: %s", zip_code)
        return {}

    key = f"{z5}|{int(miles)}"
    cache = _load_airnow_cache()
    rec = (cache.get(key) or {}) if isinstance(cache, dict) else {}

    # Respect TTL if present
    if rec:
        try:
            pulled_at = rec.get("pulled_at")
            if pulled_at:
                ts = datetime.datetime.fromisoformat(pulled_at.replace("Z", "+00:00"))
                if (datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc) - ts) <= datetime.timedelta(hours=ttl_hours):
                    val = rec.get("value") or {}
                    logger.info("AirNow cache hit: key=%s aqi=%s", key, (val or {}).get("AQI") or (val or {}).get("aqi"))
                    # Normalize return shape to your existing dict
                    if val:
                        return {
                            "aqi": val.get("aqi") or val.get("AQI"),
                            "parameter": val.get("parameter") or val.get("ParameterName"),
                            "category": val.get("category") or ((val.get("Category") or {}).get("Name")),
                            "obs_time": val.get("obs_time") or f"{val.get('DateObserved','')} {val.get('HourObserved','')} {val.get('LocalTimeZone','')}",
                            "area": val.get("area") or val.get("ReportingArea"),
                            "state": val.get("state") or val.get("StateCode"),
                            "source": "AirNow",
                        }
        except Exception:
            pass  # fall through to refresh

    # Miss or stale: make the API call
    worst = _airnow_observation(z5, miles)
    if not worst:
        logger.info("AirNow empty result for zip=%s miles=%s", z5, miles)
        # write a minimal record to avoid hammering API
        cache[key] = {"zip": z5, "miles": int(miles), "pulled_at": _now_utc_iso(), "value": {}}
        _save_airnow_cache(cache)
        return {}

    # Normalize to your existing return structure
    value = {
        "aqi": worst.get("AQI"),
        "parameter": worst.get("ParameterName"),
        "category": (worst.get("Category") or {}).get("Name"),
        "obs_time": f"{worst.get('DateObserved','')} {worst.get('HourObserved','')} {worst.get('LocalTimeZone','')}",
        "area": worst.get("ReportingArea"),
        "state": worst.get("StateCode"),
        "source": "AirNow",
    }

    # Persist to YAML
    cache[key] = {
        "zip": z5,
        "miles": int(miles),
        "pulled_at": _now_utc_iso(),
        "value": value,
    }
    _save_airnow_cache(cache)

    logger.info("AirNow refreshed: zip=%s miles=%s aqi=%s", z5, miles, value.get("aqi"))
    return value


def build_obx_air_quality(aq: Dict[str,str], set_id: int = 2) -> str:
    if not aq: return ""
    aqi, param, category = aq.get("aqi",""), aq.get("parameter",""), aq.get("category","")
    place = ", ".join([x for x in [aq.get("area",""), aq.get("state","")] if x])
    obs = aq.get("obs_time","")
    value = f"AQI={aqi}^{category}^{param}^{place} {obs}".strip()
    return f"OBX|{set_id}|TX|AIRNOW_AQI^Air Quality Index^L|1|{value}||||||F"


# --- ACS Poverty% (file-cached) ---
import os, time, requests, datetime
try:
    import yaml  # PyYAML
except Exception:
    yaml = None  # we'll log if missing

# Keep your existing default (can be overridden elsewhere)
ACS_YEAR = "2023"

# Cache file location: project_root/data/acs_poverty_cache.yaml
_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
_POVERTY_CACHE_PATH = os.path.join(_DATA_DIR, "acs_poverty_cache.yaml")

def _now_utc_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0, tzinfo=datetime.timezone.utc).isoformat()

def _ensure_data_dir():
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
    except Exception as e:
        logger.warning("ACS poverty cache: failed to ensure data dir %s err=%s", _DATA_DIR, e)

def _load_poverty_cache() -> dict:
    if not yaml:
        logger.warning("ACS poverty cache: PyYAML not installed; skipping disk cache.")
        return {}
    if not os.path.exists(_POVERTY_CACHE_PATH):
        return {}
    try:
        with open(_POVERTY_CACHE_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("ACS poverty cache: read error %s err=%s", _POVERTY_CACHE_PATH, e)
        return {}

def _save_poverty_cache(cache: dict) -> None:
    if not yaml:
        return
    try:
        _ensure_data_dir()
        tmp = _POVERTY_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(cache, f, sort_keys=True, allow_unicode=True)
        os.replace(tmp, _POVERTY_CACHE_PATH)
    except Exception as e:
        logger.warning("ACS poverty cache: write error %s err=%s", _POVERTY_CACHE_PATH, e)

def get_poverty_pct_by_zcta(zcta: str, year: str = ACS_YEAR, ttl_days: int = 180) -> float | None:
    """
    File-cached ACS poverty lookup (5-year).
    Cache key: "{ZCTA}|{year}"
    YAML record:
      { key:
          { zcta, year, pulled_at, source: "US Census ACS 5-year",
            value: { total, below, pct } }
      }
    Returns: float (percent, 1 decimal) or None
    """
    if not zcta:
        return None

    z5 = str(zcta).strip()[:5]
    if not z5.isdigit() or len(z5) != 5:
        logger.warning("ACS poverty invalid ZCTA: %s", zcta)
        return None

    key = f"{z5}|{year}"
    cache = _load_poverty_cache()
    rec = (cache.get(key) or {}) if isinstance(cache, dict) else {}

    # TTL: ACS is stable; 180 days default
    if rec:
        try:
            pulled_at = rec.get("pulled_at")
            if pulled_at:
                ts = datetime.datetime.fromisoformat(pulled_at.replace("Z", "+00:00"))
                if (datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc) - ts) <= datetime.timedelta(days=ttl_days):
                    val = rec.get("value") or {}
                    pct = val.get("pct")
                    if pct is not None:
                        logger.info("ACS poverty cache hit: key=%s pct=%.1f", key, pct)
                        return float(pct)
        except Exception:
            pass  # fall through to refresh

    # Miss or stale: query Census API
    base = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {"get": "B17001_001E,B17001_002E,NAME", "for": f"zip code tabulation area:{z5}"}

    for attempt in range(3):
        try:
            r = requests.get(base, params=params, timeout=8)
            if r.status_code == 200:
                data = r.json() or []
                if not isinstance(data, list) or len(data) < 2:
                    break
                try:
                    total = float(data[1][0] or 0)
                    below = float(data[1][1] or 0)
                    if total <= 0:
                        pct = None
                    else:
                        pct = round((below / total) * 100.0, 1)
                except Exception:
                    pct = None

                # Write to YAML (even if pct None, to avoid refetch storms)
                cache[key] = {
                    "zcta": z5,
                    "year": str(year),
                    "pulled_at": _now_utc_iso(),
                    "source": "US Census ACS 5-year",
                    "value": {"total": total if 'total' in locals() else None,
                              "below": below if 'below' in locals() else None,
                              "pct": pct},
                }
                _save_poverty_cache(cache)

                if pct is None:
                    logger.info("ACS poverty empty/invalid for zcta=%s year=%s", z5, year)
                    return None

                logger.info("ACS poverty refreshed: zcta=%s year=%s pct=%.1f", z5, year, pct)
                return pct

            elif r.status_code in (429, 500, 502, 503, 504):
                time.sleep(0.5 * (attempt + 1))
            else:
                logger.warning("ACS poverty HTTP %s for zcta=%s year=%s", r.status_code, z5, year)
                break
        except Exception as e:
            logger.warning("ACS poverty attempt %s error for zcta=%s err=%s", attempt + 1, z5, e)
            time.sleep(0.5 * (attempt + 1))

    # Cache a negative result to reduce hammering, with current timestamp
    cache[key] = {"zcta": z5, "year": str(year), "pulled_at": _now_utc_iso(),
                  "source": "US Census ACS 5-year", "value": {"total": None, "below": None, "pct": None}}
    _save_poverty_cache(cache)
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
    Resolve ZIP → county FIPS (SSCCC) with multiple fallbacks.
    Returns dict with keys: state_fips, county_fips, county_name, state_abbrev, lat, lon  OR None.

    Order:
      A) Census /address using (street + city + state + zip) if city/state available from refdata
      1) Census /onelineaddress (ZIP only)
      2) Census /address (street + ZIP only)
      3) FCC Area API (zip=)
      3b) Zippopotam.us (lat/lon) → FCC Area API (lat/lon)
      4) Special-case 01854 (Lowell, MA) retained for demo parity
    """
    try:
        if not zip5 or len(str(zip5)) < 5:
            logger.warning("Geocoder: invalid zip arg: %s", zip5)
            return None

        z5 = str(zip5).strip()[:5]

        def _extract_from_census_match(am):
            geos = (am or {}).get("geographies", {}) or {}
            counties = geos.get("Counties") or []
            county = counties[0] if counties else {}
            state_fips = str(county.get("STATE", "")).zfill(2) or None
            c3 = str(county.get("COUNTY", "")).zfill(3) if state_fips else None
            cfips = f"{state_fips}{c3}" if state_fips and c3 else None
            name = county.get("NAME") or None
            st = (geos.get("States") or [{}])[0].get("STUSAB") if geos.get("States") else None
            coords = (am or {}).get("coordinates") or {}
            out = {
                "state_fips": state_fips,
                "county_fips": cfips,
                "county_name": name,
                "state_abbrev": st,
                "lat": coords.get("y"),
                "lon": coords.get("x"),
            }
            return out

        # A) Use city/state from refdata if available (most precise)
        city, state = _city_state_for_zip(z5)
        if city and state:
            urlA = "https://geocoding.geo.census.gov/geocoder/geographies/address"
            pA = {
                "street": "1 Main St",
                "city": city,
                "state": state,
                "zip": z5,
                "benchmark": "Public_AR_Census2020",
                "vintage": "Census2020_Census2020",
                "format": "json",
            }
            logger.debug("Census address (with city/state) request: %s params=%s", urlA, pA)
            rA = requests.get(urlA, params=pA, timeout=8)
            logger.info("Census address (with city/state) status=%s zip=%s city=%s state=%s", rA.status_code, z5, city, state)
            if rA.status_code == 200:
                matchesA = rA.json().get("result", {}).get("addressMatches", []) or []
                logger.debug("Census address (with city/state) matches=%s", len(matchesA))
                if matchesA:
                    out = _extract_from_census_match(matchesA[0])
                    logger.info("Census address (with city/state) success: %s", out)
                    if out.get("county_fips"):
                        return out

        # 1) Census onelineaddress (ZIP only)
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
        if r1.status_code == 200:
            matches1 = r1.json().get("result", {}).get("addressMatches", []) or []
            logger.debug("Census onelineaddress matches=%s", len(matches1))
            if matches1:
                out = _extract_from_census_match(matches1[0])
                logger.info("Census onelineaddress success: %s", out)
                if out.get("county_fips"):
                    return out

        # 2) Census address (street + ZIP only)
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
            matches2 = r2.json().get("result", {}).get("addressMatches", []) or []
            logger.debug("Census address matches=%s", len(matches2))
            if matches2:
                out = _extract_from_census_match(matches2[0])
                logger.info("Census address success: %s", out)
                if out.get("county_fips"):
                    return out

        # 3) FCC Area API fallback (ZIP)
        url3 = "https://geo.fcc.gov/api/census/area"
        p3 = {"format": "json", "zip": z5}
        logger.debug("FCC area (zip) request: %s params=%s", url3, p3)
        r3 = requests.get(url3, params=p3, timeout=8)
        logger.info("FCC area (zip) status=%s zip=%s", r3.status_code, z5)
        if r3.status_code == 200:
            j3 = r3.json() or {}
            results = j3.get("results") or []
            logger.debug("FCC area (zip) results_count=%s", len(results))
            if results:
                res = results[0]
                state_fips = str(res.get("state_fips", "")).zfill(2) or None
                county_fips = str(res.get("county_fips", "")).zfill(5) or None
                out = {
                    "state_fips": state_fips,
                    "county_fips": county_fips,
                    "county_name": res.get("county_name"),
                    "state_abbrev": res.get("state_code"),
                    "lat": None,
                    "lon": None,
                }
                logger.info("FCC area (zip) success: %s", out)
                if out.get("county_fips"):
                    return out
        else:
            logger.warning("FCC area (zip) non-200: %s", r3.text[:200].replace("\n", " "))

        # 3b) Zippopotam.us → FCC Area (lat/lon)
        try:
            zippo_url = f"https://api.zippopotam.us/us/{z5}"
            logger.debug("Zippopotam request: %s", zippo_url)
            rz = requests.get(zippo_url, timeout=8)
            logger.info("Zippopotam status=%s zip=%s", rz.status_code, z5)
            if rz.status_code == 200:
                jz = rz.json() or {}
                places = jz.get("places") or []
                if places:
                    # Use first place centroid
                    lat = float(places[0]["latitude"])
                    lon = float(places[0]["longitude"])
                    url3b = "https://geo.fcc.gov/api/census/area"
                    p3b = {"format": "json", "lat": lat, "lon": lon}
                    logger.debug("FCC area (lat/lon) request: %s params=%s", url3b, p3b)
                    r3b = requests.get(url3b, params=p3b, timeout=8)
                    logger.info("FCC area (lat/lon) status=%s zip=%s", r3b.status_code, z5)
                    if r3b.status_code == 200:
                        j3b = r3b.json() or {}
                        results_b = j3b.get("results") or []
                        logger.debug("FCC area (lat/lon) results_count=%s", len(results_b))
                        if results_b:
                            res = results_b[0]
                            state_fips = str(res.get("state_fips", "")).zfill(2) or None
                            county_fips = str(res.get("county_fips", "")).zfill(5) or None
                            out = {
                                "state_fips": state_fips,
                                "county_fips": county_fips,
                                "county_name": res.get("county_name"),
                                "state_abbrev": res.get("state_code"),
                                "lat": lat,
                                "lon": lon,
                            }
                            logger.info("FCC area (lat/lon) success: %s", out)
                            if out.get("county_fips"):
                                return out
        except Exception as e:
            logger.warning("Zippopotam/FCC latlon fallback error for zip=%s err=%s", z5, e)

        # 4) Special-case 01854 with Lowell, MA (kept for your demo)
        if z5 == "01854":
            url4 = "https://geocoding.geo.census.gov/geocoder/geographies/address"
            p4 = {
                "street": "1 Main St",
                "city": "Lowell",
                "state": "MA",
                "zip": z5,
                "benchmark": "Public_AR_Census2020",
                "vintage": "Census2020_Census2020",
                "format": "json",
            }
            logger.debug("Census address fallback (Lowell, MA): %s params=%s", url4, p4)
            r4 = requests.get(url4, params=p4, timeout=8)
            logger.info("Census address (Lowell, MA) status=%s zip=%s", r4.status_code, z5)
            if r4.status_code == 200:
                matches4 = r4.json().get("result", {}).get("addressMatches", []) or []
                logger.debug("Census address (Lowell, MA) matches=%s", len(matches4))
                if matches4:
                    out = _extract_from_census_match(matches4[0])
                    logger.info("Census address (Lowell, MA) success: %s", out)
                    if out.get("county_fips"):
                        return out

        logger.warning("FIPS resolution failed for zip=%s (all fallbacks)", z5)
        return None

    except requests.Timeout:
        logger.error("Geocoder timeout: zip=%s", zip5)
        return None
    except Exception as e:
        logger.exception("Geocoder error: zip=%s err=%s", zip5, e)
        return None



# 2) CDC PLACES (SODA API): select a measure by ZCTA (no key, but rate-limited)

def get_places_measure_by_zcta(zcta: str, measure_name: str = "Obesity among adults aged >=18 years") -> float | None:
    """
    Returns the percentage Data_Value for a ZCTA, or None if not available.
    Primary: CDC PLACES ZCTA dataset 9umn-c3jf with measure LIKE 'Obesity among adults%'.
    Fallback: short_question_text = 'Obesity' (some rows omit/vary the long measure).
    """
    try:
        if not zcta or len(str(zcta)) < 5:
            logger.warning("PLACES: invalid zcta arg: %s", zcta)
            return None

        z5 = str(zcta).strip()[:5]
        base = "https://data.cdc.gov/resource/9umn-c3jf.json"

        # Attempt 1: prefix match on measure (robust to minor wording drift)
        measure_prefix = measure_name
        if " aged" in measure_name:
            measure_prefix = measure_name.split(" aged", 1)[0]  # "Obesity among adults"

        params1 = {
            "$select": "locationid,measure,short_question_text,data_value",
            "$limit": "1",
            "$where": f"locationid = '{z5}' AND measure LIKE '{measure_prefix}%'",
        }
        logger.debug("PLACES attempt1 request: %s params=%s", base, params1)
        r1 = requests.get(base, params=params1, timeout=8)
        logger.info("PLACES attempt1 response: status=%s zcta=%s", r1.status_code, z5)

        rows = []
        if r1.status_code == 200:
            rows = r1.json() or []
            logger.debug("PLACES attempt1 rows=%s preview=%s", len(rows), rows[:1])
        else:
            logger.warning("PLACES attempt1 non-200: %s", r1.text[:300].replace("\n", " "))

        # Attempt 2: short_question_text fallback ('Obesity')
        if not rows:
            params2 = {
                "$select": "locationid,measure,short_question_text,data_value",
                "$limit": "1",
                "$where": f"locationid = '{z5}' AND short_question_text = 'Obesity'",
            }
            logger.debug("PLACES attempt2 request: %s params=%s", base, params2)
            r2 = requests.get(base, params=params2, timeout=8)
            logger.info("PLACES attempt2 response: status=%s zcta=%s", r2.status_code, z5)
            if r2.status_code == 200:
                rows = r2.json() or []
                logger.debug("PLACES attempt2 rows=%s preview=%s", len(rows), rows[:1])
            else:
                logger.warning("PLACES attempt2 non-200: %s", r2.text[:300].replace("\n", " "))

        if not rows:
            logger.info("PLACES empty result for zcta=%s (after both attempts)", z5)
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