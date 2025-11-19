# /pages/7_AI Admin.py

import os
import csv
import json
from pathlib import Path
from collections import Counter
from typing import Dict, List, Tuple

import streamlit as st

# ---- Project-relative paths (match Note Coder) ----
ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT_DIR / "models" / "Bio_ClinicalBERT"
REF_DIR   = ROOT_DIR / "ref"
DATA_DIR  = ROOT_DIR / "data"
FEEDBACK_CSV = DATA_DIR / "coder_feedback.csv"
ICD_LABELS_CSV = REF_DIR / "icd_labels.csv"
CPT_LABELS_CSV = REF_DIR / "cpt_labels.csv"

# ---- Optional: tokenizer for token length stats ----
def get_tokenizer():
    try:
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(str(MODEL_DIR))
    except Exception:
        return None

TOKENIZER = get_tokenizer()

# ---- Label maps (code -> description) ----
def read_label_map(path: Path) -> Dict[str, str]:
    m: Dict[str, str] = {}
    if not path.exists():
        return m
    with path.open("r", encoding="utf-8") as f:
        rdr = csv.reader(f)
        first = True
        for row in rdr:
            if not row:
                continue
            row = [c.strip() for c in row]
            if first and row[0].lower() in {"code", "icd", "cpt", "label"}:
                first = False
                continue
            first = False
            code = row[0] if len(row) > 0 else ""
            desc = row[1] if len(row) > 1 else ""
            if code:
                m[code] = desc
    return m

ICD_DESC = read_label_map(ICD_LABELS_CSV)
CPT_DESC = read_label_map(CPT_LABELS_CSV)

# ---- Feedback loader ----
def load_feedback(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            # Normalize pipe-separated fields to lists
            for k in ["icd_selected", "icd_suggested", "icd_rejected",
                      "cpt_selected", "cpt_suggested", "cpt_rejected"]:
                if k in r and isinstance(r[k], str):
                    r[k] = [x for x in r[k].split("|") if x]
                else:
                    r[k] = []

            # Note text was JSON-dumped
            r["report_text"] = json.loads(r.get("report_text", "\"\""))

            # Normalize service_line / coder_id to non-None strings
            r["service_line"] = (r.get("service_line") or "").strip()
            r["coder_id"] = (r.get("coder_id") or "").strip()

            # Boolean flags stored as "1"/"0" (or missing)
            def flag(col: str) -> bool:
                return str(r.get(col, "0")).strip() == "1"

            r["needs_query_flag"] = flag("needs_query")
            r["doc_missing_flag"] = flag("doc_missing")
            r["doc_insufficient_detail_flag"] = flag("doc_insufficient_detail")
            r["doc_conflicting_flag"] = flag("doc_conflicting")

            rows.append(r)
    return rows

FB_ALL = load_feedback(FEEDBACK_CSV)

# ---- Utility: text length & token length ----
def token_length(s: str) -> int:
    if not isinstance(s, str) or not s:
        return 0
    if TOKENIZER:
        # no truncation here; true raw tokenization length
        return len(TOKENIZER(s, truncation=False)["input_ids"])
    # fallback approx
    return max(1, len(s.split()))

# ========================= UI =========================

st.set_page_config(
    page_title="LLM + BERT Tuning Admin",
    page_icon="🛠️",
    layout="wide",
)
st.title("LLM + BERT Tuning Admin")

# ---- Sidebar: paths, tokenizer, filters ----
with st.sidebar:
    st.subheader("Paths & Model")
    st.caption(f"Model dir: {MODEL_DIR}")
    st.caption(f"ICD labels: {ICD_LABELS_CSV}")
    st.caption(f"CPT labels: {CPT_LABELS_CSV}")
    st.caption(f"Feedback CSV: {FEEDBACK_CSV}")
    st.divider()

    st.subheader("Tokenizer")
    if TOKENIZER:
        mdl_max = getattr(TOKENIZER, "model_max_length", None)
        st.caption(f"Tokenizer loaded: {TOKENIZER.name_or_path}")
        st.caption(f"model_max_length: {mdl_max}")
    else:
        st.warning("Transformers / tokenizer not available. Token-based stats will be approximate.")
    st.divider()

    st.subheader("Filters")

    # Available filter values from all feedback
    svc_values = sorted(
        {r["service_line"] for r in FB_ALL if r.get("service_line")}
    )
    coder_values = sorted(
        {r["coder_id"] for r in FB_ALL if r.get("coder_id")}
    )

    svc_options = ["(All)"] + svc_values
    coder_options = ["(All)"] + coder_values

    selected_service_line = st.selectbox(
        "Service line",
        options=svc_options,
        index=0,
    )
    selected_coder = st.selectbox(
        "Coder",
        options=coder_options,
        index=0,
    )

# ---- Apply filters ----
def apply_filters(rows: List[dict],
                  svc: str,
                  coder: str) -> List[dict]:
    out = []
    for r in rows:
        if svc != "(All)" and r.get("service_line") != svc:
            continue
        if coder != "(All)" and r.get("coder_id") != coder:
            continue
        out.append(r)
    return out

FB = apply_filters(FB_ALL, selected_service_line, selected_coder)

# ========================= Main panels =========================

# ---- Dataset snapshot ----
st.markdown("### Dataset Snapshot")
colA, colB, colC, colD = st.columns(4)
colA.metric("Feedback rows (filtered)", f"{len(FB)}")
n_notes = len({r.get("report_uid", "") for r in FB if r.get("report_uid")})
colB.metric("Unique report_uid", f"{n_notes}")
n_icd_labeled = sum(1 for r in FB if r["icd_selected"])
n_cpt_labeled = sum(1 for r in FB if r["cpt_selected"])
colC.metric("Rows w/ ICD labels", f"{n_icd_labeled}")
colD.metric("Rows w/ CPT labels", f"{n_cpt_labeled}")

# ---- Documentation & query signals ----
st.markdown("### Documentation & Query Signals")

if FB:
    total_rows = len(FB)
    needs_query_count = sum(1 for r in FB if r.get("needs_query_flag"))
    doc_missing_count = sum(1 for r in FB if r.get("doc_missing_flag"))
    doc_insufficient_count = sum(1 for r in FB if r.get("doc_insufficient_detail_flag"))
    doc_conflicting_count = sum(1 for r in FB if r.get("doc_conflicting_flag"))

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Labeled cases (filtered)", total_rows)

    def pct(count: int) -> str:
        return f"{(count / total_rows * 100):.1f}%" if total_rows > 0 else "0.0%"

    with col2:
        st.metric("Needs provider query", needs_query_count, pct(needs_query_count))
    with col3:
        st.metric("Documentation missing", doc_missing_count, pct(doc_missing_count))
    with col4:
        st.metric("Insufficient detail", doc_insufficient_count, pct(doc_insufficient_count))
    with col5:
        st.metric("Conflicting / ambiguous", doc_conflicting_count, pct(doc_conflicting_count))
else:
    st.caption("No feedback in the current filter selection.")

# ---- Note Length & truncation risk ----
st.markdown("### Note Length & Truncation Risk")
if FB:
    lengths = [(len(r["report_text"]), token_length(r["report_text"])) for r in FB]
    max_ctx = st.number_input(
        "Assumed BERT context length (tokens)",
        min_value=128,
        max_value=4096,
        value=512,
        step=64,
    )
    over = [t for (_, t) in lengths if t > max_ctx]
    st.caption(f"{len(over)} / {len(lengths)} notes exceed {max_ctx} tokens.")
    with st.expander("View longest notes"):
        # Show top 5 longest by tokens
        L = []
        for r in FB:
            tl = token_length(r["report_text"])
            L.append((tl, r.get("report_uid", ""), r["report_text"]))
        L.sort(reverse=True)
        for i, (tl, uid, txt) in enumerate(L[:5]):
            st.write(f"report_uid={uid or '(auto)'} — tokens≈{tl}")
            st.text_area(
                "excerpt",
                value=(txt if len(txt) < 2000 else txt[:2000] + " ..."),
                height=160,
                key=f"longest_excerpt_{i}_{uid or 'auto'}",
            )
else:
    st.info("No feedback yet. Use the Note Coder page to generate notes and save selections.")

# ---- Simple quality heuristics: selection vs suggestion ----
st.markdown("### Code Selection vs Suggestion (Precision proxy)")
st.caption("Heuristic: selection_rate = selected / suggested (per code). Higher suggests better precision.")

def tally_rates(rows: List[dict], field_sel: str, field_sug: str) -> List[Tuple[str, int, int, float]]:
    counts_sug = Counter()
    counts_sel = Counter()
    for r in rows:
        for c in r.get(field_sug, []):
            counts_sug[c] += 1
        for c in r.get(field_sel, []):
            counts_sel[c] += 1
    out: List[Tuple[str, int, int, float]] = []
    for code, s_ct in counts_sug.items():
        sel_ct = counts_sel.get(code, 0)
        rate = (sel_ct / s_ct) if s_ct else 0.0
        out.append((code, sel_ct, s_ct, rate))
    out.sort(key=lambda x: x[3], reverse=True)
    return out

if FB:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("ICD (top 25 by selection rate)")
        icd_rates = tally_rates(FB, "icd_selected", "icd_suggested")[:25]
        for code, sel, sug, rate in icd_rates:
            label = f"{code} — {ICD_DESC.get(code, '')}" if code in ICD_DESC else code
            st.write(f"- {label}: selected {sel}/{sug}  (rate {rate:.2f})")

    with col2:
        st.markdown("CPT (top 25 by selection rate)")
        cpt_rates = tally_rates(FB, "cpt_selected", "cpt_suggested")[:25]
        for code, sel, sug, rate in cpt_rates:
            label = f"{code} — {CPT_DESC.get(code, '')}" if code in CPT_DESC else code
            st.write(f"- {label}: selected {sel}/{sug}  (rate {rate:.2f})")

# ---- Misses: selected but not suggested (recall proxy) ----
st.markdown("### Missed Codes (Recall proxy)")
st.caption("Codes you selected that were NOT suggested — candidates to improve heuristics, prompts, or fine-tuned heads.")

if FB:
    missed_icd = Counter()
    missed_cpt = Counter()
    for r in FB:
        for c in r["icd_selected"]:
            if c not in r["icd_suggested"]:
                missed_icd[c] += 1
        for c in r["cpt_selected"]:
            if c not in r["cpt_suggested"]:
                missed_cpt[c] += 1
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("ICD missed")
        for code, ct in missed_icd.most_common(25):
            st.write(f"- {code} — {ICD_DESC.get(code, '')}  (count {ct})")
    with col4:
        st.markdown("CPT missed")
        for code, ct in missed_cpt.most_common(25):
            st.write(f"- {code} — {CPT_DESC.get(code, '')}  (count {ct})")

# ---- Per-run details table ----
st.markdown("### Recent Runs")
if FB:
    max_rows = max(1, len(FB))       # at least 1
    min_rows = 1                     # allow small datasets
    default_rows = min(25, max_rows) # sensible default within range

    n = st.slider(
        "Rows to show",
        min_value=min_rows,
        max_value=max_rows,
        value=default_rows,
        step=1,
    )

    for i, r in enumerate(FB[-n:]):
        uid = r.get("report_uid", "") or "auto"
        st.write(
            f"{r.get('timestamp', '')}: report_uid={uid} | backend={r.get('backend', '')} | "
            f"ICD_th={r.get('icd_threshold', '')} | CPT_th={r.get('cpt_threshold', '')} | "
            f"svc={r.get('service_line', '')} | msg={r.get('message_type', '')}"
        )
        st.write(f"ICD suggested: {', '.join(r['icd_suggested']) or '—'}")
        st.write(f"ICD selected:  {', '.join(r['icd_selected']) or '—'}")
        st.write(f"CPT suggested: {', '.join(r['cpt_suggested']) or '—'}")
        st.write(f"CPT selected:  {', '.join(r['cpt_selected']) or '—'}")
        tl = token_length(r["report_text"])
        st.caption(f"Note length: chars={len(r['report_text'])}  tokens≈{tl}")
        st.text_area(
            "report",
            value=(r["report_text"][:1500] + (" ..." if len(r["report_text"]) > 1500 else "")),
            height=120,
            key=f"run_report_{i}_{uid}",
        )
        st.divider()
else:
    st.caption("No rows to display yet.")

# ---- Recommendations block ----
st.markdown("### Recommendations")
st.write(
    """
- Long notes: If many notes exceed the BERT context, either (a) trim with section-aware summarization or (b) set a hard cap (512/768/1024) with truncation.
- Precision: Codes with low selection_rate are over-suggested → improve heuristics, add a CPT reranker, or raise their threshold.
- Recall (Missed codes): Add patterns for these in the heuristic and/or include more examples in fine-tuning.
- Documentation & queries: Use the documentation flags and query rates to drive provider education and documentation improvement by service line and coder.
- Log confidences (next step): Extend feedback rows to include per-code confidences so you can compute per-label optimal thresholds from real usage.
"""
)
