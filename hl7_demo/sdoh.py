import json
import time
import requests
import os
import datetime
import sys
from functools import lru_cache
from urllib.parse import quote
from typing import Dict, Optional # Keeping Dict, removing Optional

# --- Local Imports / Configuration ---
# Assuming these are defined in a local config file
try:
    from .config import AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR
except ImportError:
    # Fallback/placeholder for running standalone
    AIRNOW_API_KEY = os.environ.get("AIRNOW_API_KEY", "")
    AIRNOW_MILES_DEFAULT = 25
    ACS_YEAR = "2023"

from utils.log_utils import get_logger
logger = get_logger("SDOH")  # writes to logs/plain and logs/json

# Attempt to import refdata helper
_get_city_state_by_zip = None
try:
    from .refdata import get_city_state_by_zip as _get_city_state_by_zip
except ImportError:
    try:
        from refdata import get_city_state_by_zip as _get_city_state_by_zip
    except ImportError:
        pass # _get_city_state_by_zip remains None

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None
    logger.warning("PyYAML not installed; disk caching will be disabled.")

# --- Shared Constants ---
_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))

_AIRNOW_CACHE_PATH = os.path.join(_DATA_DIR, "airnow_cache.yaml")
_POVERTY_CACHE_PATH = os.path.join(_DATA_DIR, "acs_poverty_cache.yaml")
_GEOCODER_CACHE_PATH = os.path.join(_DATA_DIR, "geocoder_cache.yaml")
_PLACES_OBESITY_CACHE_PATH = os.path.join(_DATA_DIR, "places_obesity_cache.yaml")
_BLS_UNEMPLOYMENT_CACHE_PATH = os.path.join(_DATA_DIR, "bls_unemployment_cache.yaml")

# --- Utility Functions ---

def _city_state_for_zip(z5: str) -> tuple[str | None, str | None]:
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
        logger.exception("Error in _city_state_for_zip for %s", z5)
        pass
    return None, None

# --- Shared YAML Cache Helpers (Consolidated) ---

def _now_utc_iso() -> str:
    """Returns current UTC time in ISO format for cache metadata."""
    return datetime.datetime.utcnow().replace(microsecond=0, tzinfo=datetime.timezone.utc).isoformat()

def _ensure_data_dir():
    """Ensures the cache data directory exists."""
    if not yaml: return
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
    except Exception as e:
        logger.warning("Cache: failed to ensure data dir %s err=%s", _DATA_DIR, e)

def _load_yaml_cache(path: str, label: str) -> dict:
    """Loads cache data from a YAML file."""
    if not yaml:
        logger.debug("%s cache: PyYAML not installed; skipping disk cache.", label)
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("%s cache: read error %s err=%s", label, path, e)
        return {}

def _save_yaml_cache(path: str, label: str, cache: dict) -> None:
    """Saves cache data to a YAML file atomically."""
    if not yaml:
        return
    try:
        _ensure_data_dir()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(cache, f, sort_keys=True, allow_unicode=True)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning("%s cache: write error %s err=%s", label, path, e)

def _is_fresh(pulled_at_iso: str | None, max_age: datetime.timedelta) -> bool:
    """Checks if the pulled_at timestamp is within the max_age."""
    try:
        if not pulled_at_iso:
            return False
        # Normalize to UTC timezone awareness
        ts = datetime.datetime.fromisoformat(pulled_at_iso.replace("Z", "+00:00"))
        age = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc) - ts
        return age <= max_age
    except Exception:
        return False

def _http_get_json_with_retries(url: str, params: dict | None = None, timeout: float = 8.0, attempts: int = 3):
    """Performs an HTTP GET request with retries on server errors (429, 5xx)."""
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

# --- AirNow (File-cached) ---

def _airnow_observation(zip_code: str, miles: int) -> dict:
    """Calls AirNow and returns the 'worst' observation dict or {}."""
    if not AIRNOW_API_KEY:
        logger.error("AIRNOW_API_KEY is missing.")
        return {}

    url = "https://www.airnowapi.org/aq/observation/zipCode/current/"
    params = {"format": "application/json", "zipCode": zip_code, "distance": str(miles), "API_KEY": AIRNOW_API_KEY}
    
    # Use the general retry helper for AirNow
    data = _http_get_json_with_retries(url, params=params, timeout=6)
    
    if not data or not isinstance(data, list):
        return {}

    # Find the worst AQI reading
    worst = max(data, key=lambda x: int(x.get("AQI", -1)))
    return worst or {}

def get_air_quality_by_zip(zip_code: str, miles: int = AIRNOW_MILES_DEFAULT, ttl_hours: int = 6) -> dict:
    """
    File-cached AirNow lookup. Normalizes the data structure upon saving.
    """
    if not zip_code:
        return {}

    z5 = str(zip_code).strip()[:5]
    if not z5.isdigit() or len(z5) != 5:
        logger.warning("AirNow invalid ZIP: %s", zip_code)
        return {}

    key = f"{z5}|{int(miles)}"
    cache = _load_yaml_cache(_AIRNOW_CACHE_PATH, "AirNow")
    rec = (cache.get(key) or {}) if isinstance(cache, dict) else {}

    # --- Cache Hit Logic (Simplified by normalization on save) ---
    if rec:
        try:
            pulled_at = rec.get("pulled_at")
            if _is_fresh(pulled_at, datetime.timedelta(hours=ttl_hours)):
                val = rec.get("value") or {}
                logger.info("AirNow cache hit: key=%s aqi=%s", key, val.get("aqi"))
                return val
        except Exception:
            pass  # fall through to refresh

    # --- Cache Miss/Stale: API Call ---
    worst = _airnow_observation(z5, miles)
    
    if not worst:
        logger.info("AirNow empty result for zip=%s miles=%s", z5, miles)
        # write a minimal record to avoid hammering API
        cache[key] = {"zip": z5, "miles": int(miles), "pulled_at": _now_utc_iso(), "value": {}}
        _save_yaml_cache(_AIRNOW_CACHE_PATH, "AirNow", cache)
        return {}

    # Normalize to the desired return structure (Suggestion 1: Normalize on save)
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
    _save_yaml_cache(_AIRNOW_CACHE_PATH, "AirNow", cache)

    logger.info("AirNow refreshed: zip=%s miles=%s aqi=%s", z5, miles, value.get("aqi"))
    return value


def build_obx_air_quality(aq: Dict[str,str], set_id: int = 2) -> str:
    if not aq: return ""
    aqi, param, category = aq.get("aqi",""), aq.get("parameter",""), aq.get("category","")
    place = ", ".join([x for x in [aq.get("area",""), aq.get("state","")] if x])
    obs = aq.get("obs_time","")
    value = f"AQI={aqi}^{category}^{param}^{place} {obs}".strip()
    return f"OBX|{set_id}|TX|AIRNOW_AQI^Air Quality Index^L|1|{value}||||||F"


# --- ACS Poverty% (File-cached) ---

def get_poverty_pct_by_zcta(zcta: str, year: str = ACS_YEAR, ttl_days: int = 180) -> float | None:
    """
    File-cached ACS poverty lookup (5-year).
    Returns: float (percent, 1 decimal) or None
    """
    if not zcta:
        return None

    z5 = str(zcta).strip()[:5]
    if not z5.isdigit() or len(z5) != 5:
        logger.warning("ACS poverty invalid ZCTA: %s", zcta)
        return None

    key = f"{z5}|{year}"
    cache = _load_yaml_cache(_POVERTY_CACHE_PATH, "ACS Poverty")
    rec = (cache.get(key) or {}) if isinstance(cache, dict) else {}

    # --- Cache Hit Logic ---
    if rec:
        try:
            pulled_at = rec.get("pulled_at")
            if _is_fresh(pulled_at, datetime.timedelta(days=ttl_days)):
                val = rec.get("value") or {}
                pct = val.get("pct")
                if pct is not None:
                    logger.info("ACS poverty cache hit: key=%s pct=%.1f", key, pct)
                    return float(pct)
        except Exception:
            pass  # fall through to refresh

    # --- Cache Miss/Stale: Query Census API ---
    base = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {"get": "B17001_001E,B17001_002E,NAME", "for": f"zip code tabulation area:{z5}"}

    for attempt in range(3):
        try:
            r = requests.get(base, params=params, timeout=8)
            if r.status_code == 200:
                data = r.json() or []
                if not isinstance(data, list) or len(data) < 2:
                    break
                
                # Removed redundant inner try/except for data parsing (Suggestion 5)
                try:
                    total = float(data[1][0] or 0)
                    below = float(data[1][1] or 0)
                    if total <= 0:
                        pct = None
                    else:
                        pct = round((below / total) * 100.0, 1)
                except (ValueError, IndexError, TypeError):
                    # Catch data structure errors here.
                    pct = None
                    total = None
                    below = None
                
                # Write to YAML (even if pct None, to avoid hammering API)
                cache[key] = {
                    "zcta": z5,
                    "year": str(year),
                    "pulled_at": _now_utc_iso(),
                    "source": "US Census ACS 5-year",
                    "value": {"total": total, "below": below, "pct": pct},
                }
                _save_yaml_cache(_POVERTY_CACHE_PATH, "ACS Poverty", cache)

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
    _save_yaml_cache(_POVERTY_CACHE_PATH, "ACS Poverty", cache)
    return None


def build_obx_poverty_pct(pct: float | None, set_id: int = 3) -> str:
    if pct is None: return ""
    try: val = f"{float(pct):.1f}"
    except Exception: return ""
    return f"OBX|{set_id}|NM|ACS_POVERTY_PCT^Poverty (ACS 5-year)%^L||{val}||||||F"

# --- Census Geocoder: ZIP -> county/state/coords (File-cached) ---

def zip_to_county_fips(zip5: str) -> dict | None:
    """
    Resolve ZIP → county FIPS (SSCCC) with multiple fallbacks.
    Returns dict with keys: state_fips, county_fips, county_name, state_abbrev, lat, lon OR None.
    """
    try:
        if not zip5 or len(str(zip5)) < 5:
            logger.warning("Geocoder: invalid zip arg: %s", zip5)
            return None

        z5 = str(zip5).strip()[:5]
        cache = _load_yaml_cache(_GEOCODER_CACHE_PATH, "Geocoder")
        rec = cache.get(z5) or {}

        if rec and _is_fresh(rec.get("pulled_at"), datetime.timedelta(days=365)):
            logger.info("Geocoder cache hit: zip=%s", z5)
            return rec.get("value")

        def _save_and_return(result: dict):
            """Helper to save the cache and return the result."""
            cache[z5] = {"pulled_at": _now_utc_iso(), "value": result}
            _save_yaml_cache(_GEOCODER_CACHE_PATH, "Geocoder", cache)
            return result

        def _extract_from_census_match(am):
            """Helper to extract relevant data from a Census match dictionary."""
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
                "street": "1 Main St", "city": city, "state": state, "zip": z5,
                "benchmark": "Public_AR_Census2020", "vintage": "Census2020_Census2020",
                "format": "json",
            }
            rA = requests.get(urlA, params=pA, timeout=8)
            if rA.status_code == 200:
                matchesA = rA.json().get("result", {}).get("addressMatches", []) or []
                if matchesA:
                    out = _extract_from_census_match(matchesA[0])
                    if out.get("county_fips"):
                        logger.info("Census address (with city/state) success: %s", out.get("county_fips"))
                        return _save_and_return(out) # Early Cache Save

        # 1) Census onelineaddress (ZIP only)
        url1 = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
        p1 = {
            "address": z5, "benchmark": "Public_AR_Census2020", "vintage": "Census2020_Census2020",
            "format": "json",
        }
        r1 = requests.get(url1, params=p1, timeout=8)
        if r1.status_code == 200:
            matches1 = r1.json().get("result", {}).get("addressMatches", []) or []
            if matches1:
                out = _extract_from_census_match(matches1[0])
                if out.get("county_fips"):
                    logger.info("Census onelineaddress success: %s", out.get("county_fips"))
                    return _save_and_return(out) # Early Cache Save

        # 2) Census address (street + ZIP only)
        url2 = "https://geocoding.geo.census.gov/geocoder/geographies/address"
        p2 = {
            "street": "1 Main St", "zip": z5,
            "benchmark": "Public_AR_Census2020", "vintage": "Census2020_Census2020",
            "format": "json",
        }
        r2 = requests.get(url2, params=p2, timeout=8)
        if r2.status_code == 200:
            matches2 = r2.json().get("result", {}).get("addressMatches", []) or []
            if matches2:
                out = _extract_from_census_match(matches2[0])
                if out.get("county_fips"):
                    logger.info("Census address success: %s", out.get("county_fips"))
                    return _save_and_return(out) # Early Cache Save

        # 3) FCC Area API fallback (ZIP)
        url3 = "https://geo.fcc.gov/api/census/area"
        p3 = {"format": "json", "zip": z5}
        r3 = requests.get(url3, params=p3, timeout=8)
        if r3.status_code == 200:
            j3 = r3.json() or {}
            results = j3.get("results") or []
            if results:
                res = results[0]
                state_fips = str(res.get("state_fips", "")).zfill(2) or None
                county_fips = str(res.get("county_fips", "")).zfill(5) or None
                out = {
                    "state_fips": state_fips, "county_fips": county_fips,
                    "county_name": res.get("county_name"),
                    "state_abbrev": res.get("state_code"),
                    "lat": None, "lon": None,
                }
                if out.get("county_fips"):
                    logger.info("FCC area (zip) success: %s", out.get("county_fips"))
                    return _save_and_return(out) # Early Cache Save

        # 3b) Zippopotam.us → FCC Area (lat/lon)
        try:
            zippo_url = f"https://api.zippopotam.us/us/{z5}"
            rz = requests.get(zippo_url, timeout=8)
            if rz.status_code == 200:
                jz = rz.json() or {}
                places = jz.get("places") or []
                if places:
                    lat = float(places[0]["latitude"])
                    lon = float(places[0]["longitude"])
                    url3b = "https://geo.fcc.gov/api/census/area"
                    p3b = {"format": "json", "lat": lat, "lon": lon}
                    r3b = requests.get(url3b, params=p3b, timeout=8)
                    if r3b.status_code == 200:
                        j3b = r3b.json() or {}
                        results_b = j3b.get("results") or []
                        if results_b:
                            res = results_b[0]
                            state_fips = str(res.get("state_fips", "")).zfill(2) or None
                            county_fips = str(res.get("county_fips", "")).zfill(5) or None
                            out = {
                                "state_fips": state_fips, "county_fips": county_fips,
                                "county_name": res.get("county_name"),
                                "state_abbrev": res.get("state_code"),
                                "lat": lat, "lon": lon,
                            }
                            if out.get("county_fips"):
                                logger.info("FCC area (lat/lon) success: %s", out.get("county_fips"))
                                return _save_and_return(out) # Early Cache Save
        except Exception as e:
            logger.warning("Zippopotam/FCC latlon fallback error for zip=%s err=%s", z5, e)

        # 4) Special-case 01854 with Lowell, MA
        if z5 == "01854":
            url4 = "https://geocoding.geo.census.gov/geocoder/geographies/address"
            p4 = {
                "street": "1 Main St", "city": "Lowell", "state": "MA", "zip": z5,
                "benchmark": "Public_AR_Census2020", "vintage": "Census2020_Census2020",
                "format": "json",
            }
            r4 = requests.get(url4, params=p4, timeout=8)
            if r4.status_code == 200:
                matches4 = r4.json().get("result", {}).get("addressMatches", []) or []
                if matches4:
                    out = _extract_from_census_match(matches4[0])
                    if out.get("county_fips"):
                        logger.info("Census address (Lowell, MA) success: %s", out.get("county_fips"))
                        return _save_and_return(out) # Early Cache Save

        logger.warning("FIPS resolution failed for zip=%s (all fallbacks)", z5)
        return _save_and_return(None) # Cache negative result

    except requests.Timeout:
        logger.error("Geocoder timeout: zip=%s", zip5)
        return None
    except Exception as e:
        logger.exception("Geocoder error: zip=%s err=%s", zip5, e)
        return None


# --- CDC PLACES (ZCTA) with YAML cache ---

def get_places_measure_by_zcta(
    zcta: str,
    measure_name: str = "Obesity among adults aged >=18 years",
    ttl_days: int = 30,
    socrata_dataset: str = "cwsq-ngmh",
    app_token: str | None = None, # Used 'str | None' instead of Optional[str]
) -> float | None: # Used 'float | None' instead of Optional[float]
    """
    Return a CDC PLACES measure (default: adult obesity %) for a ZCTA (5-digit string).
    """
    try:
        if not zcta or len(str(zcta)) < 5:
            logger.warning("PLACES: invalid zcta arg: %s", zcta)
            return None

        z5 = str(zcta).strip()[:5]
        measure_prefix = measure_name.split(" aged", 1)[0] if " aged" in measure_name else measure_name
        key = f"{z5}|{measure_prefix}"

        cache = _load_yaml_cache(_PLACES_OBESITY_CACHE_PATH, "PLACES")
        rec = cache.get(key) or {}
        if rec and _is_fresh(rec.get("pulled_at"), datetime.timedelta(days=ttl_days)):
            logger.info("PLACES cache hit: key=%s", key)
            try:
                val = rec.get("value")
                return float(val) if val is not None else None
            except Exception:
                return None

        # --- HTTP attempt (Socrata) ---
        url = f"https://chronicdata.cdc.gov/resource/{socrata_dataset}.json"
        params = {
            "locationname": f"ZCTA5 {z5}",
            "measure": measure_name,
            "$select": "data_value,year",
            "$order": "year DESC",
            "$limit": 1,
        }
        headers = {}
        if app_token:
            headers["X-App-Token"] = app_token

        r = requests.get(url, params=params, headers=headers, timeout=8)
        logger.info("PLACES response: status=%s zcta=%s", r.status_code, z5)

        out_val = None
        if r.status_code == 200:
            js = r.json() or []
            if js:
                raw = js[0].get("data_value")
                out_val = float(raw) if raw not in (None, "", "NA") else None
        else:
            logger.warning("PLACES non-200 for zcta=%s: %s", z5, r.text[:300].replace("\n", " "))

        cache[key] = {"pulled_at": _now_utc_iso(), "value": out_val}
        _save_yaml_cache(_PLACES_OBESITY_CACHE_PATH, "PLACES", cache)
        return out_val

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
        # Using a fixed placeholder for when data is unavailable
        return f"OBX|{set_id}|TX|PLACES_OBESITY^Adults with Obesity (%)^L||N/A|||||F"
    logger.info("OBX obesity built for zcta=%s value=%.1f", zcta, val)
    return f"OBX|{set_id}|NM|PLACES_OBESITY^Adults with Obesity (%)^L||{val:.1f}|%||||F"

# --- BLS LAUS (File-cached) ---

def get_unemployment_rate_by_zip(zip5: str, ttl_days: int = 30) -> float | None:
    """
    Return latest county-level unemployment rate for a ZIP by mapping to county FIPS (ZIP→County)
    and querying the BLS LAUS public API. Caches results in YAML.
    """
    try:
        z5 = (str(zip5).strip()[:5] if zip5 else "")
        if len(z5) != 5 or not z5.isdigit():
            logger.warning("BLS: invalid zip=%s", zip5)
            return None

        cache = _load_yaml_cache(_BLS_UNEMPLOYMENT_CACHE_PATH, "BLS Unemployment")
        rec = cache.get(z5) or {}
        
        if rec and _is_fresh(rec.get("pulled_at"), datetime.timedelta(days=ttl_days)):
            logger.info("BLS cache hit: zip=%s", z5)
            try:
                val = rec.get("value")
                return float(val) if val is not None else None
            except Exception:
                return None

        # ZIP -> county/state FIPS
        geo = zip_to_county_fips(z5)
        if not geo or not geo.get("county_fips") or not geo.get("state_fips"):
            logger.warning("BLS: missing county FIPS for zip=%s geo=%s", z5, geo)
            # negative-cache to avoid repeated failures
            cache[z5] = {"pulled_at": _now_utc_iso(), "county_fips": None, "series_id": None, "value": None}
            _save_yaml_cache(_BLS_UNEMPLOYMENT_CACHE_PATH, "BLS Unemployment", cache)
            return None

        state_fp = geo["state_fips"]              # e.g., "06"
        county3 = geo["county_fips"][2:]          # strip state to get county 3-digit
        series_id = f"LAUCN{state_fp}{county3}0000000003"  # unemployment rate series

        url = f"https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id}"
        params = {"latest": "true"}
        
        # Using the helper for BLS API call
        data = _http_get_json_with_retries(url, params=params, timeout=8)

        out_val = None
        if data:
            series = (data.get("Results", {}) or {}).get("series", []) or []
            if series and series[0].get("data"):
                pt = series[0]["data"][0]
                val = pt.get("value")
                out_val = float(val) if val not in (None, "", "NA") else None
        else:
            logger.warning("BLS API error or non-200 for series=%s", series_id)

        cache[z5] = {
            "pulled_at": _now_utc_iso(),
            "county_fips": geo["county_fips"],
            "series_id": series_id,
            "value": out_val,
        }
        _save_yaml_cache(_BLS_UNEMPLOYMENT_CACHE_PATH, "BLS Unemployment", cache)
        return out_val

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
