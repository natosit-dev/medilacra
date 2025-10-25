import glob
import pandas as pd

def load_reports(glob_path: str) -> pd.DataFrame:
    files = sorted(glob.glob(glob_path))
    if not files:
        raise FileNotFoundError(f"No report CSVs found at {glob_path}. Put files under ./input/reports/.")
    frames = []
    for f in files:
        df = pd.read_csv(f)
        req = ["report_uid","cpt_code","cpt_description","icd_code","icd_description","procedure_description","report_text"]
        missing = {c for c in req if c not in df.columns}
        if missing:
            raise ValueError(f"{f} is missing columns: {sorted(missing)}")
        frames.append(df[req])
    all_df = pd.concat(frames, ignore_index=True)
    if all_df.empty:
        raise ValueError("Report dataframe is empty after load.")
    return all_df
