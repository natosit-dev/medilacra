# /pages/6_Note_Coder.py

import os
import csv
import json
import importlib
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Iterable
from datetime import datetime

# After other imports
try:
    from storage_duckdb_labels import init_db as labels_duck_init, append_label as labels_append_label, DEFAULT_DB_PATH as LABEL_DB_PATH
    LABEL_DUCK_OK = True
except Exception:
    LABEL_DUCK_OK = False
    LABEL_DB_PATH = None


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

ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT_DIR / "models" / "Bio_ClinicalBERT"
REF_DIR = ROOT_DIR / "ref"
ICD_LABELS_CSV = REF_DIR / "icd_labels.csv"
CPT_LABELS_CSV = REF_DIR / "cpt_labels.csv"

CSV_PATH_DEFAULT = "test_reports_corrected.csv"

# Feedback dataset (append-only)
DATA_DIR = ROOT_DIR / "data"
FEEDBACK_CSV = DATA_DIR / "coder_feedback.csv"
FEEDBACK_HEADERS = [
    "timestamp",
    "report_uid",
    "report_text",
    "icd_selected",
    "icd_suggested",
    "icd_rejected",
    "cpt_selected",
    "cpt_suggested",
    "cpt_rejected",
    "backend",
    "icd_threshold",
    "cpt_threshold",
    "model_path",
    "service_line",
    "message_type",
    "coder_id",
    "rationale_text",
    "needs_query",
    "doc_missing",
    "doc_insufficient_detail",
    "doc_conflicting",

]

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
    enriched: List[Tuple[str, str, float]] = []
    for code, conf in preds:
        enriched.append((code, desc_map.get(code, ""), conf))
    return enriched

def normalize_enriched(preds: Iterable) -> List[Tuple[str, str, float]]:
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

def ensure_feedback_csv():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not FEEDBACK_CSV.exists():
        with FEEDBACK_CSV.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(FEEDBACK_HEADERS)

def save_feedback_row(
    *,
    note_text: str,
    report_uid: str,
    icd_selected: List[str],
    icd_suggested: List[str],
    cpt_selected: List[str],
    cpt_suggested: List[str],
    backend: str,
    icd_threshold: float,
    cpt_threshold: float,
    model_path: Path,
    service_line: str,
    message_type: str,
    coder_id: str,
    rationale_text: str,
    needs_query: bool,
    doc_missing: bool,
    doc_insufficient_detail: bool,
    doc_conflicting: bool,
):
    ensure_feedback_csv()

    icd_selected = sorted(set(icd_selected))
    cpt_selected = sorted(set(cpt_selected))
    icd_suggested = sorted(set(icd_suggested))
    cpt_suggested = sorted(set(cpt_suggested))

    icd_rejected = sorted(set(icd_suggested) - set(icd_selected))
    cpt_rejected = sorted(set(cpt_suggested) - set(cpt_selected))

    row = [
        datetime.utcnow().isoformat(timespec="seconds"),
        report_uid or "(auto)",
        json.dumps(note_text or ""),
        "|".join(icd_selected),
        "|".join(icd_suggested),
        "|".join(icd_rejected),
        "|".join(cpt_selected),
        "|".join(cpt_suggested),
        "|".join(cpt_rejected),
        backend,
        f"{icd_threshold:.2f}",
        f"{cpt_threshold:.2f}",
        str(model_path),
        service_line,
        message_type,
        coder_id,
        rationale_text or "",
        "1" if needs_query else "0",
        "1" if doc_missing else "0",
        "1" if doc_insufficient_detail else "0",
        "1" if doc_conflicting else "0",
    ]
    with FEEDBACK_CSV.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)

# Provider options from prior CSV rows
def load_provider_pairs(csv_path: Path) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    try:
        if csv_path.exists():
            with csv_path.open("r", encoding="utf-8") as f:
                rdr = csv.DictReader(f)
                seen = set()
                for row in rdr:
                    name = (row.get("provider_name") or "").strip()
                    pid = (row.get("provider_id") or "").strip()
                    if not name and not pid:
                        continue
                    key = (name, pid)
                    if key not in seen:
                        seen.add(key)
                        pairs.append(key)
    except Exception:
        pass
    if not pairs:
        pairs = [("Leslie Miller, MD", "prov-1001")]
    return pairs

def filter_labels(query: str, desc_map: Dict[str, str], limit: int = 200) -> List[Tuple[str, str]]:
    if not query:
        return []
    q = query.lower().strip()
    results: List[Tuple[str, str]] = []
    for code, desc in desc_map.items():
        if q in code.lower() or (desc and q in desc.lower()):
            results.append((code, desc))
            if len(results) >= limit:
                break
    return results

# ---- Fuzzy search helpers (drop in near other helpers) ----
from typing import Optional
try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except Exception:
    import difflib
    _HAS_RAPIDFUZZ = False

def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def _score_pair(q: str, code: str, desc: str) -> float:
    """Return a 0..100 similarity score using RapidFuzz if present; else difflib."""
    q = _norm(q); code = _norm(code); desc = _norm(desc)
    if not q:
        return 0.0
    if _HAS_RAPIDFUZZ:
        # token-sort handles word order; partial handles substrings
        sc_code = max(
            fuzz.token_set_ratio(q, code),
            fuzz.partial_ratio(q, code),
        )
        sc_desc = max(
            fuzz.token_set_ratio(q, desc),
            fuzz.partial_ratio(q, desc),
        ) if desc else 0
        return max(sc_code, sc_desc)
    else:
        # lightweight fallback
        sc_code = difflib.SequenceMatcher(None, q, code).ratio() * 100.0
        sc_desc = (difflib.SequenceMatcher(None, q, desc).ratio() * 100.0) if desc else 0.0
        return max(sc_code, sc_desc)

def fuzzy_filter_labels(query: str, desc_map: Dict[str, str], limit: int = 50, min_score: int = 60) -> List[Tuple[str, str]]:
    """
    Fuzzy match query against code and description.
    - Multi-term: all terms must match (AND) with decent scores.
    - Returns top 'limit' (code, desc) by score desc.
    """
    q = _norm(query)
    if not q:
        return []
    terms = [t for t in q.split() if t]
    scored = []
    for code, desc in desc_map.items():
        # Require all terms to have some match; use the worst term as bottleneck
        term_scores = [_score_pair(t, code, desc) for t in terms] or [0.0]
        s = min(term_scores) if len(terms) > 1 else term_scores[0]
        if s >= min_score:
            scored.append((s, code, desc))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [(code, desc) for (s, code, desc) in scored[:limit]]


# ---------------------------
# UI
# ---------------------------

def main():
    st.set_page_config(page_title="Note Coder", page_icon="📄", layout="wide")
    st.title("Note Generator + Coder")

    _init_runlog()
    # Manual selection state (persists across reruns)
    if "manual_icd" not in st.session_state:
        st.session_state["manual_icd"] = []
    if "manual_cpt" not in st.session_state:
        st.session_state["manual_cpt"] = []

    if LABEL_DUCK_OK:
        labels_duck_init(LABEL_DB_PATH)


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
        csv_path_str = st.text_input("Output CSV path", value=CSV_PATH_DEFAULT)
        csv_path = (ROOT_DIR / csv_path_str).resolve()

        with st.expander("Run log", expanded=False):
            if st.session_state["run_logs"]:
                for line in st.session_state["run_logs"][-200:]:
                    st.text(line)
            else:
                st.caption("Run logs will appear here after analysis.")
        coder_id = st.sidebar.text_input("Coder ID / initials", value=st.session_state.get("coder_id", "NAT"))
        st.session_state["coder_id"] = coder_id

    # ---------------- Case Details ----------------
    st.subheader("Case Details")

    provider_pairs = load_provider_pairs(csv_path)
    provider_options = [f"{name} — {pid}" if pid else name for (name, pid) in provider_pairs]
    default_idx = 0

    col1, col2 = st.columns(2)
    with col1:
        service_line = st.selectbox("Service Line", ["Radiology", "Pathology", "Surgery", "Other"], index=0)
    with col2:
        test_dataset_tag = st.text_input("Test Dataset Tag", value="demo")

    st.markdown("**Provider**")
    sel = st.selectbox("Choose from prior reports", options=provider_options, index=default_idx, key="prov_choice")
    sel_name, sel_id = provider_pairs[provider_options.index(sel)]
    c1, c2 = st.columns(2)
    with c1:
        provider_name = st.text_input("Provider Name", value=sel_name, key="prov_name_edit")
    with c2:
        provider_id = st.text_input("Provider ID", value=sel_id, key="prov_id_edit")

    # ---------------- Note Generation ----------------
    st.subheader("Note Generation Prompt")
    default_prompt = (
        "Create a concise, realistic narrative radiology report for an adult patient. "
        "Include clinical indication, technique, findings, and impression. "
        "Do not output FHIR; output only the narrative text."
    )
    case_prompt = st.text_area("Prompt to Kiln", value=default_prompt, height=140)

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

    # ---------------- Analysis ----------------
    st.subheader("Run Code Analysis (ICD/CPT)")
    if st.button("Run Coder Analysis"):
        log("=== Run Coder Analysis pressed ===")
        backend = "bert" if coder_mode.startswith("BERT") else "heuristic"
        log(f"Selected backend: {backend}")

        if not note_text.strip():
            st.warning("Please generate or paste a report first.")
            log("ABORT: Empty note text.")
        else:
            icd_codes, icd_desc_map = read_labels_csv_with_desc(ICD_LABELS_CSV)
            cpt_codes, cpt_desc_map = read_labels_csv_with_desc(CPT_LABELS_CSV)

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
                    icd_preds = enrich_preds(icd_preds_raw, icd_desc_map)[:10]
                    cpt_preds = enrich_preds(cpt_preds_raw, cpt_desc_map)[:10]

                    log(f"ICD predictions returned: {len(icd_preds_raw)}; showing top 10")
                    log(f"CPT predictions returned: {len(cpt_preds_raw)}; showing top 10")
                except Exception as e:
                    st.error(f"Coder analysis failed: {e}")
                    log(f"ERROR during analyze_report: {e}")
                    icd_preds, cpt_preds = [], []

            st.session_state["icd_preds"] = icd_preds
            st.session_state["cpt_preds"] = cpt_preds

            if not icd_preds and not cpt_preds:
                st.info("No codes met the threshold. Adjust thresholds or edit the report text.")
                log("No predictions above threshold (or top-N fallback produced empty).")
            else:
                log("Top ICD: " + ", ".join([f"{c} ({d}) {p:.2f}" for c, d, p in icd_preds[:5]]) if icd_preds else "Top ICD: —")
                log("Top CPT: " + ", ".join([f"{c} ({d}) {p:.2f}" for c, d, p in cpt_preds[:5]]) if cpt_preds else "Top CPT: —")

    # Normalize session preds
    icd_preds_enriched: List[Tuple[str, str, float]] = normalize_enriched(st.session_state.get("icd_preds", []))
    cpt_preds_enriched: List[Tuple[str, str, float]] = normalize_enriched(st.session_state.get("cpt_preds", []))

    # Selection UI (BERT suggestions)
    col_icd, col_cpt = st.columns(2)
    with col_icd:
        st.markdown("ICD Suggestions")
        selected_icd_from_suggestions: List[str] = []
        if icd_preds_enriched:
            for code, desc, conf in icd_preds_enriched[:50]:
                label = f"{code} — {desc}" if desc else code
                key = f"icd_{code}"
                if st.checkbox(f"{label} (confidence {conf:.2f})", key=key):
                    selected_icd_from_suggestions.append(code)
        else:
            st.caption("No ICD suggestions.")

    with col_cpt:
        st.markdown("CPT Suggestions")
        selected_cpt_from_suggestions: List[str] = []
        if cpt_preds_enriched:
            for code, desc, conf in cpt_preds_enriched[:50]:
                label = f"{code} — {desc}" if desc else code
                key = f"cpt_{code}"
                if st.checkbox(f"{label} (confidence {conf:.2f})", key=key):
                    selected_cpt_from_suggestions.append(code)
        else:
            st.caption("No CPT suggestions.")

    st.divider()

    # ---------------- Manual search & add ----------------
    st.subheader("Add Codes by Search")

    # Load label maps once for search
    _, icd_desc_map_search = read_labels_csv_with_desc(ICD_LABELS_CSV)
    _, cpt_desc_map_search = read_labels_csv_with_desc(CPT_LABELS_CSV)

    sch_icd, sch_cpt = st.columns(2)

    with sch_icd:
        icd_query = st.text_input("Search ICD (code or description)", value="", key="icd_search")
        icd_results = fuzzy_filter_labels(icd_query, icd_desc_map_search, limit=50, min_score=60)
        icd_options = [f"{c} — {d}" if d else c for c, d in icd_results]
        icd_selection = st.multiselect("Select ICD to add", options=icd_options, default=[], key="icd_search_select")
        if st.button("Add ICD Codes", key="btn_add_icd"):
            codes_to_add = []
            for opt in icd_selection:
                code = opt.split(" — ", 1)[0]
                codes_to_add.append(code)
            st.session_state["manual_icd"] = sorted(set(st.session_state["manual_icd"]).union(codes_to_add))
            st.success(f"Added {len(codes_to_add)} ICD code(s).")

    with sch_cpt:
        cpt_query = st.text_input("Search CPT (code or description)", value="", key="cpt_search")
        cpt_results = fuzzy_filter_labels(cpt_query, cpt_desc_map_search, limit=50, min_score=60)
        cpt_options = [f"{c} — {d}" if d else c for c, d in cpt_results]
        cpt_selection = st.multiselect("Select CPT to add", options=cpt_options, default=[], key="cpt_search_select")
        if st.button("Add CPT Codes", key="btn_add_cpt"):
            codes_to_add = []
            for opt in cpt_selection:
                code = opt.split(" — ", 1)[0]
                codes_to_add.append(code)
            st.session_state["manual_cpt"] = sorted(set(st.session_state["manual_cpt"]).union(codes_to_add))
            st.success(f"Added {len(codes_to_add)} CPT code(s).")

    # Display and manage manual lists
    st.markdown("Current Manual Selections")
    mcol1, mcol2 = st.columns(2)
    with mcol1:
        if st.session_state["manual_icd"]:
            st.write(", ".join(st.session_state["manual_icd"]))
            if st.button("Clear Manual ICD", key="btn_clear_icd"):
                st.session_state["manual_icd"] = []
        else:
            st.caption("No manual ICD codes added.")
    with mcol2:
        if st.session_state["manual_cpt"]:
            st.write(", ".join(st.session_state["manual_cpt"]))
            if st.button("Clear Manual CPT", key="btn_clear_cpt"):
                st.session_state["manual_cpt"] = []
        else:
            st.caption("No manual CPT codes added.")

    st.divider()
    
    # Final selected = suggestions checked + manual added
    selected_icd = sorted(set(selected_icd_from_suggestions).union(st.session_state["manual_icd"]))
    selected_cpt = sorted(set(selected_cpt_from_suggestions).union(st.session_state["manual_cpt"]))

        # New: coder rationale and query flag
    rationale_text = st.text_area(
        "Coding rationale (why these codes?)",
        height=120,
        key="rationale_text",
    )
    needs_query = st.checkbox(
        "This case needs a provider query",
        key="needs_query",
    )

    # New: documentation quality flags
    doc_missing = st.checkbox(
        "Documentation missing key elements (cannot fully support codes)",
        key="doc_missing",
    )
    doc_insufficient_detail = st.checkbox(
        "Documentation present but lacks detail (site, acuity, laterality, etc.)",
        key="doc_insufficient_detail",
    )
    doc_conflicting = st.checkbox(
        "Documentation conflicting or ambiguous",
        key="doc_conflicting",
    )

    
    # Save rows (codes only) + log feedback
    if st.button("Save Selected to CSV", type="secondary"):
        note_text_current = st.session_state.get("generated_note", "") if not note_text else note_text
        if not note_text_current.strip():
            st.warning("Report text is empty.")
        elif not selected_icd and not selected_cpt:
            st.warning("Select at least one ICD or CPT code.")
        else:
            rows = build_rows_for_csv(
                report_text=note_text_current,
                selected_icd=selected_icd,
                selected_cpt=selected_cpt,
                report_uid="",                     # auto-generate in backend
                procedure_description="",          # dropped from UI
                provider_id=provider_id.strip(),
                provider_name=provider_name.strip(),
                message_type="",                   # message-type agnostic
                service_line=service_line.strip(),
                test_dataset_tag=test_dataset_tag.strip(),
            )

            icd_suggested_codes = [c for (c, _, _) in icd_preds_enriched]
            cpt_suggested_codes = [c for (c, _, _) in cpt_preds_enriched]

            try:
                n = write_rows_to_csv(rows, str(csv_path))
                uid = rows[0]["report_uid"] if rows else ""
                st.success(f"Saved {n} row(s) to {csv_path} with report_uid={uid}.")
                log(f"Wrote {n} row(s) to {csv_path} for report_uid={uid}")
            except Exception as e:
                st.error(f"Failed to write CSV: {e}")
                log(f"ERROR writing CSV: {e}")

            try:
                save_feedback_row(
                    note_text=note_text_current,
                    report_uid=uid,  # auto
                    icd_selected=selected_icd,
                    icd_suggested=icd_suggested_codes,
                    cpt_selected=selected_cpt,
                    cpt_suggested=cpt_suggested_codes,
                    backend="bert" if coder_mode.startswith("BERT") else "heuristic",
                    icd_threshold=icd_thresh,
                    cpt_threshold=cpt_thresh,
                    model_path=MODEL_DIR,
                    service_line=service_line,
                    message_type="",  # agnostic
                    coder_id=st.session_state.get("coder_id", ""),
                    rationale_text=rationale_text,
                    needs_query=needs_query,
                    doc_missing=doc_missing,
                    doc_insufficient_detail=doc_insufficient_detail,
                    doc_conflicting=doc_conflicting,
                )
                log(f"Appended feedback row to {FEEDBACK_CSV}")
            except Exception as e:
                log(f"ERROR writing feedback CSV: {e}")
                st.warning(f"Feedback log failed: {e}")

                # DuckDB label persistence
            if LABEL_DUCK_OK:
                try:
                    labels_append_label(
                        {
                            "case_id": uid or "",
                            "coder_id": st.session_state.get("coder_id", ""),
                            "service_line": service_line,
                            "message_type": "",
                            "backend": "bert" if coder_mode.startswith("BERT") else "heuristic",
                            "icd_threshold": icd_thresh,
                            "cpt_threshold": cpt_thresh,
                            "icd_selected": selected_icd,
                            "cpt_selected": selected_cpt,
                            "icd_suggested": icd_suggested_codes,
                            "cpt_suggested": cpt_suggested_codes,
                            "rationale_text": rationale_text,
                            "needs_query": needs_query,
                            "documentation_missing": doc_missing,
                            "insufficient_detail": doc_insufficient_detail,
                            "conflicting_information": doc_conflicting,
                            "note_text": note_text_current,
                        },
                        db_path=LABEL_DB_PATH,
                    )
                    log(f"Appended label row to DuckDB at {LABEL_DB_PATH}")
                except Exception as e:
                    log(f"ERROR writing DuckDB label row: {e}")

if __name__ == "__main__":
    main()
