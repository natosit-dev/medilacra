# hl7_demo/refdata.py
import os
import pandas as pd
from functools import lru_cache
from typing import Dict

CSV_PATH = "./ref/address.csv"  # columns expected: zip, city, state

@lru_cache(maxsize=1)
def load_zip_table() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"ZIP reference not found at {CSV_PATH} (expected cols: zip, city, state)")
    df = pd.read_csv(CSV_PATH, dtype={"zip": str, "city": str, "state": str})
    need = {"zip", "city", "state"}
    missing = need - set(map(str.lower, df.columns))
    if missing:
        raise ValueError(f"{CSV_PATH} missing columns: {sorted(missing)}")
    # normalize column names
    df = df.rename(columns={c: c.lower() for c in df.columns})
    # keep only what we need, enforce 5-digit zip
    df["zip"] = df["zip"].str.strip().str[:5]
    df = df[df["zip"].str.fullmatch(r"\d{5}", na=False)]
    if df.empty:
        raise ValueError(f"{CSV_PATH} has no valid rows after cleaning")
    return df[["zip", "city", "state"]].drop_duplicates().reset_index(drop=True)

def sample_zip_city_state(rng=None) -> Dict[str, str]:
    df = load_zip_table()
    row = df.sample(1, random_state=rng).iloc[0]
    return {"zip": row["zip"], "city": row["city"], "state": row["state"]}
