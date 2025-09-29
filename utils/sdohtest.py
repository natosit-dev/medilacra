import requests
import json

# --- Test Parameters ---
z5 = "01854"
county_fips = None # Initialize FIPS

# 1. CDC PLACES Test (Obesity Percentage)
print("--- 1. CDC PLACES Obesity ---")
# FIX: Use updated Resource ID (9umn-c3jf) and correct column name (locationid)
base_places = "https://data.cdc.gov/resource/9umn-c3jf.json"
params_places = {
    "$select": "locationid,measure,data_value",
    "$limit": "1",
    "$where": "locationid = '{}' AND measure LIKE 'Obesity among adults%'".format(z5),
}

try:
    resp_places = requests.get(base_places, params=params_places, timeout=8)
    print(f"Status: {resp_places.status_code}")
    if resp_places.status_code == 200:
        data = resp_places.json()
        if data:
            rate = data[0].get('data_value')
            print(f"Obesity Rate for 01854: {rate}%")
        else:
            print("No data found for the ZCTA and measure.")
    else:
        print(f"Failed to fetch CDC PLACES data. Response text: {resp_places.text[:100]}...")
except Exception as e:
    print(f"Error during CDC PLACES request: {e}")

# 2. Census Geocoder (ZIP to FIPS)
print("\n--- 2. Census Geocoder (Extract FIPS) ---")
# FIX: Use the /address endpoint with a full dummy address for guaranteed match.
geo_url = "https://geocoding.geo.census.gov/geocoder/geographies/address"
params_geo = {
    "zip": z5,
    "street": "1 Main St", # Generic street to force resolution
    "city": "Lowell",       # Explicitly add city
    "state": "MA",          # Explicitly add state
    "benchmark": "Public_AR_Census2020",
    "vintage": "Census2020_Census2020",
    "format": "json",
}

try:
    resp_geo = requests.get(geo_url, params=params_geo, timeout=8).json()
    
    matches = resp_geo.get("result", {}).get("addressMatches", [])
    if matches:
        county_data = matches[0].get("geographies", {}).get("Counties", [{}])[0]
        state_fp = str(county_data.get("STATE", "")).zfill(2)
        county3 = str(county_data.get("COUNTY", "")).zfill(3)
        county_fips = f"{state_fp}{county3}"
        
        print(f"Extracted County FIPS: {county_fips} ({county_data.get('NAME', 'N/A')})")
    else:
        print("Error: Census Geocoder returned no address matches for this ZIP.")
        county_fips = None

except Exception as e:
    print(f"Error during Census Geocoder request: {e}")
    county_fips = None


# 3. BLS LAUS Test (Unemployment Rate)
print("\n--- 3. BLS LAUS Unemployment ---")

if county_fips and county_fips != "00000":
    try:
        series_id = f"LAUCN{county_fips}0000000003"
        bls_url = f"https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id}"
        params_bls = {"latest": "true"}
        
        resp_bls = requests.get(bls_url, params=params_bls, timeout=8).json()
        
        series = resp_bls.get("Results", {}).get("series", [{}])
        if series and series[0].get("data"):
            data_point = series[0].get("data", [{}])[0]
            rate = data_point.get("value")
            period = data_point.get("periodName")
            year = data_point.get("year")
            print(f"Series ID: {series_id}")
            print(f"Latest Unemployment Rate ({period} {year}): {rate}%")
        else:
            print(f"Error: BLS API returned series ID, but no data points.")
    
    except Exception as e:
        print(f"Error during BLS LAUS request: {e}")
else:
    print("Skipping BLS LAUS test due to missing County FIPS.")