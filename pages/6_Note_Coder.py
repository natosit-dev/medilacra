# /pages/6_Note_Coder.py

import os
import csv
import importlib
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Iterable

import streamlit as st

# Prefer the v2 backend if present
try:
    notecoder = importlib.import_module("hl7_demo.notecoder_v2")
except Exception:
    notecoder = importlib.import_module("hl7_demo.notecoder")

# Pull required symbols from the chosen backend
DEFAULT_KILN_URL = getattr(notecoder, "DEFAULT_KILN_URL", "http://localhost:11434/v1")
DEFAULT_MODEL = getattr(notecoder, "DEFAULT_MODEL", "qwen2.5:3b-instruct")
kiln_generate_note = notecoder.kiln_generate_note
analyze_report = notecoder.analyze_report
build_rows_for_csv = notecoder.build_rows_for_csv
write_rows_to_csv = notecoder.write_rows_to_csv

# ---------------------------
# Paths (hardcoded relative to repo root)
# ---------------------------

# Assuming this file lives at <ROOT>/pages/6_Note_Coder.py
ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT_DIR / "models" / "Bio_ClinicalBERT"
REF_DIR = ROOT_DIR / "ref"
ICD_LABELS_CSV = REF_DIR / "icd_labels.csv"
CPT_LABELS_CSV = REF_DIR / "cpt_labels.csv"

CSV_PATH_DEFAULT = "test_reports_corrected.csv"

# ---------------------------
# Logging (UI-visible)
# ---------------------------

logger = logging.getLogger("note_coder_ui")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())

def _init_runlog():
    if "run_logs" not in st.session_state:
        st.session_state["run_logs"] = []

def log(msg: str):
    logger.info(msg)
    _init_runlog()
    st.session_state["run_logs"].append(msg)

# ---------------------------
# Helpers
# ---------------------------

def transformers_available() -> bool:
    try:
        importlib.import_module("transformers")
        importlib.import_module("torch")
        return True
    except Exception:
        return False

def read_labels_csv_with_desc(path: Path) -> Tuple[List[str], Dict[str, str]]:
    """
    Read a CSV with at least two columns: code, description.
    Header is optional; we use the first two columns per line.
    Returns (codes_list, code_to_description_map).
    """
    codes: List[str] = []
    desc_map: Dict[str, str] = {}
    if not path.exists():
        return codes, desc_map

    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        first_row = True
        for row in reader:
            if not row:
                continue
            row = [col.strip() for col in row]
            # Skip header if present
            if first_row and row and (row[0].lower() in {"code", "icd", "cpt", "label"}):
                first_row = False
                continue
            first_row = False

            code = row[0] if len(row) >= 1 else ""
            desc = row[1] if len(row) >= 2 else ""
            if not code:
                continue
            codes.append(code)
            if desc:
                desc_map[code] = desc
    return codes, desc_map

def enrich_preds(preds: List[Tuple[str, float]], desc_map: Dict[str, str]) -> List[Tuple[str, str, float]]:
    """Convert [(code, conf)] -> [(code, description, conf)] using desc_map."""
    enriched: List[Tuple[str, str, float]] = []
    for code, conf in preds:
        enriched.append((code, desc_map.get(code, ""), conf))
    return enriched

def normalize_enriched(preds: Iterable) -> List[Tuple[str, str, float]]:
    """
    Normalize any of:
      - [(code, desc, conf)]
      - [(code, conf)]
    into a consistent [(code, desc, conf)] shape for the UI.
    """
    out: List[Tuple[str, str, float]] = []
    for item in preds or []:
        if not isinstance(item, (list, tuple)):
            continue
        if len(item) == 3:
            code, desc, conf = item
        elif len(item) == 2:
            code, conf = item
            desc = ""
        else:
            continue
        try:
            conf = float(conf)
        except Exception:
            continue
        out.append((str(code), str(desc), conf))
    return out

# ---------------------------
# UI
# ---------------------------

def main():
    st.set_page_config(page_title="Note Coder", page_icon="📄", layout="wide")
    st.title("Note Generator + Coder")

    _init_runlog()

    # Sidebar configs
    with st.sidebar:
        st.header("Kiln Settings")
        kiln_url = st.text_input("Kiln Base URL", value=DEFAULT_KILN_URL)
        kiln_model = st.text_input("Model", value="qwen2.5:3b-instruct")
        kiln_temp = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.4, step=0.05)
        kiln_max = st.number_input("Max tokens", min_value=256, max_value=4096, value=900, step=64)

        st.header("Coder Settings")
        coder_mode = st.selectbox("Coder backend", ["BERT (transformers)", "Heuristic (fallback)"], index=0)
        icd_thresh = st.slider("ICD threshold", 0.0, 1.0, 0.35, 0.01)
        cpt_thresh = st.slider("CPT threshold", 0.0, 1.0, 0.35, 0.01)

        st.caption(f"Model path (hardcoded): {MODEL_DIR}")
        st.caption(f"ICD labels (hardcoded): {ICD_LABELS_CSV}")
        st.caption(f"CPT labels (hardcoded): {CPT_LABELS_CSV}")

        st.header("Save")
        csv_path = st.text_input("Output CSV path", value=CSV_PATH_DEFAULT)

        with st.expander("Run log", expanded=False):
            if st.session_state["run_logs"]:
                for line in st.session_state["run_logs"][-200:]:
                    st.text(line)
            else:
                st.caption("Run logs will appear here after analysis.")

    # Case metadata inputs
    st.subheader("Case Details")
    col1, col2, col3 = st.columns(3)
    with col1:
        provider_id = st.text_input("Provider ID", value="prov-1001")
        message_type = st.text_input("Message Type", value="DFT^P03")
        service_line = st.selectbox("Service Line", ["Radiology", "Pathology", "Surgery", "Other"], index=0)
    with col2:
        provider_name = st.text_input("Provider Name", value="Leslie Miller, MD")
        procedure_description = st.text_input("Procedure Description", value="Chest X-ray 2 views")
        test_dataset_tag = st.text_input("Test Dataset Tag", value="demo")
    with col3:
        report_uid = st.text_input("Report UID (auto if blank)", value="")

    st.subheader("Note Generation Prompt")
    default_prompt = (
        "Create a concise, realistic narrative radiology report for an adult patient. "
        "Include clinical indication, technique, findings, and impression. "
        "Do not output FHIR; output only the narrative text."
    )
    case_prompt = st.text_area("Prompt to Kiln", value=default_prompt, height=140)

    # Generate note
    if st.button("Generate Note with Kiln", type="primary"):
        try:
            with st.spinner("Generating note..."):
                note = kiln_generate_note(case_prompt, kiln_url, kiln_model, kiln_temp, kiln_max)
            if not note:
                st.error("No note returned from Kiln. Check settings and server logs.")
            else:
                st.session_state["generated_note"] = note
                st.success("Note generated.")
        except Exception as e:
            st.error(f"Kiln request failed: {e}")

    note_text = st.session_state.get("generated_note", "")
    st.subheader("Generated Narrative Report")
    note_text = st.text_area("Report Text", value=note_text, height=260, key="note_text")

    # Analysis section
    st.subheader("Run Code Analysis (ICD/CPT)")
    if st.button("Run Coder Analysis"):
        log("=== Run Coder Analysis pressed ===")
        backend = "bert" if coder_mode.startswith("BERT") else "heuristic"
        log(f"Selected backend: {backend}")

        if not note_text.strip():
            st.warning("Please generate or paste a report first.")
            log("ABORT: Empty note text.")
        else:
            # Load labels and descriptions
            icd_codes, icd_desc_map = read_labels_csv_with_desc(ICD_LABELS_CSV)
            cpt_codes, cpt_desc_map = read_labels_csv_with_desc(CPT_LABELS_CSV)

            # BERT readiness
            bert_ready = transformers_available() and MODEL_DIR.is_dir()
            log(f"transformers/torch available: {transformers_available()}")
            log(f"Model dir exists: {MODEL_DIR.is_dir()} -> {MODEL_DIR}")
            log(f"ICD labels: {len(icd_codes)} from {ICD_LABELS_CSV}")
            log(f"CPT labels: {len(cpt_codes)} from {CPT_LABELS_CSV}")
            log(f"Thresholds: ICD={icd_thresh:.2f} CPT={cpt_thresh:.2f}")

            if backend == "bert" and not bert_ready:
                missing_bits = []
                if not transformers_available():
                    missing_bits.append("transformers/torch")
                if not MODEL_DIR.is_dir():
                    missing_bits.append(f"model dir {MODEL_DIR}")
                log("Forcing fallback to heuristic due to: " + ", ".join(missing_bits))
                backend = "heuristic"

            with st.spinner("Analyzing..."):
                try:
                    icd_preds_raw, cpt_preds_raw = analyze_report(
                        report_text=note_text,
                        backend=backend,
                        icd_labels=icd_codes if backend == "bert" else None,
                        cpt_labels=cpt_codes if backend == "bert" else None,
                        base_model=str(MODEL_DIR) if backend == "bert" else "emilyalsentzer/Bio_ClinicalBERT",
                        icd_threshold=icd_thresh,
                        cpt_threshold=cpt_thresh,
                    )
                    # Enrich with descriptions for display
                    icd_preds = enrich_preds(icd_preds_raw, icd_desc_map)
                    cpt_preds = enrich_preds(cpt_preds_raw, cpt_desc_map)

                    log(f"ICD predictions returned: {len(icd_preds_raw)}")
                    log(f"CPT predictions returned: {len(cpt_preds_raw)}")
                except Exception as e:
                    st.error(f"Coder analysis failed: {e}")
                    log(f"ERROR during analyze_report: {e}")
                    icd_preds, cpt_preds = [], []

            # Store enriched preds for display; still save only codes later
            st.session_state["icd_preds"] = icd_preds           # [(code, desc, conf)]
            st.session_state["cpt_preds"] = cpt_preds           # [(code, desc, conf)]

            if not icd_preds and not cpt_preds:
                st.info("No codes met the threshold. Adjust thresholds or edit the report text.")
                log("No predictions above threshold (or top-N fallback produced empty).")
            else:
                # Log top few with descriptions
                log("Top ICD: " + ", ".join([f"{c} ({d}) {p:.2f}" for c, d, p in icd_preds[:5]]) if icd_preds else "Top ICD: —")
                log("Top CPT: " + ", ".join([f"{c} ({d}) {p:.2f}" for c, d, p in cpt_preds[:5]]) if cpt_preds else "Top CPT: —")

    # Normalize session preds to 3-tuple shape to avoid unpack errors
    icd_preds_enriched: List[Tuple[str, str, float]] = normalize_enriched(st.session_state.get("icd_preds", []))
    cpt_preds_enriched: List[Tuple[str, str, float]] = normalize_enriched(st.session_state.get("cpt_preds", []))

    # Selection UI
    col_icd, col_cpt = st.columns(2)
    with col_icd:
        st.markdown("**ICD Suggestions**")
        selected_icd: List[str] = []
        if icd_preds_enriched:
            for code, desc, conf in icd_preds_enriched[:50]:
                label = f"{code} — {desc}" if desc else code
                key = f"icd_{code}"
                if st.checkbox(f"{label} (confidence {conf:.2f})", key=key):
                    selected_icd.append(code)
        else:
            st.caption("No ICD suggestions.")

    with col_cpt:
        st.markdown("**CPT Suggestions**")
        selected_cpt: List[str] = []
        if cpt_preds_enriched:
            for code, desc, conf in cpt_preds_enriched[:50]:
                label = f"{code} — {desc}" if desc else code
                key = f"cpt_{code}"
                if st.checkbox(f"{label} (confidence {conf:.2f})", key=key):
                    selected_cpt.append(code)
        else:
            st.caption("No CPT suggestions.")

    st.divider()

    # Save rows (still only codes are written to CSV schema)
    if st.button("Save Selected to CSV", type="secondary"):
        note_text = st.session_state.get("generated_note", "") if not note_text else note_text
        if not note_text.strip():
            st.warning("Report text is empty.")
        elif not selected_icd and not selected_cpt:
            st.warning("Select at least one ICD or CPT code.")
        else:
            rows = build_rows_for_csv(
                report_text=note_text,
                selected_icd=selected_icd,
                selected_cpt=selected_cpt,
                report_uid=report_uid,
                procedure_description=procedure_description,
                provider_id=provider_id,
                provider_name=provider_name,
                message_type=message_type,
                service_line=service_line,
                test_dataset_tag=test_dataset_tag,
            )
            try:
                n = write_rows_to_csv(rows, csv_path)
                uid = rows[0]["report_uid"] if rows else ""
                st.success(f"Saved {n} row(s) to {csv_path} with report_uid={uid}.")
                log(f"Wrote {n} row(s) to {csv_path} for report_uid={uid}")
            except Exception as e:
                st.error(f"Failed to write CSV: {e}")
                log(f"ERROR writing CSV: {e}")


if __name__ == "__main__":
    main()
