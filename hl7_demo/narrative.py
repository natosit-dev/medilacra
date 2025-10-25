import os
import uuid
import csv
from typing import List, Dict, Tuple
import torch
import streamlit as st
import requests

# Optional: lightweight BERT coder (falls back to heuristic rules if no labels/model)
try:
    
    from transformers import AutoTokenizer, AutoModel
    TRANSFORMERS_AVAILABLE = True
except Exception:
    TRANSFORMERS_AVAILABLE = False

CSV_PATH = "test_reports_corrected.csv"
DEFAULT_KILN_URL = "http://localhost:3500"
DEFAULT_MODEL = "qwen2.5:3b-instruct"

# ---------------------------
# Utilities
# ---------------------------

def ensure_csv_exists(path: str):
    headers = [
        "report_uid",
        "cpt_code",
        "icd_code",
        "procedure_description",
        "report_text",
        "provider_id",
        "provider_name",
        "message_type",
        "service_line",
        "test_dataset_tag",
    ]
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)


def write_rows_to_csv(rows: List[Dict[str, str]], path: str):
    ensure_csv_exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for r in rows:
            writer.writerow([
                r.get("report_uid", ""),
                r.get("cpt_code", ""),
                r.get("icd_code", ""),
                r.get("procedure_description", ""),
                r.get("report_text", ""),
                r.get("provider_id", ""),
                r.get("provider_name", ""),
                r.get("message_type", ""),
                r.get("service_line", ""),
                r.get("test_dataset_tag", ""),
            ])


# ---------------------------
# Kiln integration
# ---------------------------

def kiln_generate_note(
    case_prompt: str,
    kiln_base_url: str = DEFAULT_KILN_URL,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.4,
    max_tokens: int = 900,
) -> str:
    """Call Kiln (local orchestrator) to generate a narrative clinical note.

    This function assumes a simple POST endpoint `${kiln_base_url}/generate` that accepts:
    {
      "model": "qwen2.5:3b-instruct",
      "prompt": "...",
      "temperature": 0.4,
      "max_tokens": 900,
      "stream": false
    }
    and returns JSON with a top-level "text" or "response" field containing the note.

    Adjust keys as needed for your Kiln instance.
    """
    url = kiln_base_url.rstrip("/") + "/generate"
    payload = {
        "model": model,
        "prompt": case_prompt,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        # Try common fields
        for key in ("text", "response", "output", "content"):
            if key in data and isinstance(data[key], str):
                return data[key]
        # Some servers return a list of choices
        if "choices" in data and data["choices"]:
            c = data["choices"][0]
            if isinstance(c, dict):
                for key in ("text", "message", "content"):
                    if key in c:
                        val = c[key]
                        if isinstance(val, dict):
                            # OpenAI-style
                            return val.get("content", "")
                        if isinstance(val, str):
                            return val
        return ""
    except Exception as e:
        st.error(f"Kiln request failed: {e}")
        return ""


# ---------------------------
# Coder models
# ---------------------------

class HeuristicCoder:
    """Very small rule-based fallback with confidence scores.
    Replace/extend with your own dictionaries if BERT weights are not available.
    """

    def __init__(self):
        # Minimal demo maps. Extend as needed.
        self.icd_map = {
            "hypertension": ("I10", 0.78),
            "diabetes": ("E11.9", 0.75),
            "pneumonia": ("J18.9", 0.72),
            "asthma": ("J45.909", 0.70),
            "chest pain": ("R07.9", 0.65),
        }
        self.cpt_map = {
            "chest x-ray": ("71046", 0.80),
            "mri knee": ("73721", 0.77),
            "ct head": ("70450", 0.76),
            "cbc": ("85025", 0.74),
            "metabolic panel": ("80053", 0.73),
        }

    def predict(self, text: str) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
        t = text.lower()
        icd = []
        cpt = []
        for k, (code, conf) in self.icd_map.items():
            if k in t:
                icd.append((code, conf))
        for k, (code, conf) in self.cpt_map.items():
            if k in t:
                cpt.append((code, conf))
        return icd, cpt


class BertCoderTorch:
    """Tiny multi-label head over a clinical BERT encoder.
    This class expects label lists for ICD and CPT and uses sigmoid outputs as confidences.
    Provide your fine-tuned heads via state_dict() if available; otherwise, results will be random.
    """

    def __init__(self, base_model: str, icd_labels: List[str], cpt_labels: List[str]):
        if not TRANSFORMERS_AVAILABLE:
            raise RuntimeError("transformers/torch not installed")
        self.encoder = AutoModel.from_pretrained(base_model)
        self.tokenizer = AutoTokenizer.from_pretrained(base_model)
        hidden = self.encoder.config.hidden_size
        self.icd_labels = icd_labels
        self.cpt_labels = cpt_labels
        self.icd_head = torch.nn.Linear(hidden, len(self.icd_labels))
        self.cpt_head = torch.nn.Linear(hidden, len(self.cpt_labels))
        self.encoder.eval(); self.icd_head.eval(); self.cpt_head.eval()

    @torch.no_grad()
    def predict(self, text: str) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
        toks = self.tokenizer([text], padding=True, truncation=True, return_tensors="pt")
        out = self.encoder(**toks)
        if hasattr(out, "pooler_output") and out.pooler_output is not None:
            pooled = out.pooler_output
        else:
            pooled = out.last_hidden_state.mean(dim=1)
        icd_scores = torch.sigmoid(self.icd_head(pooled)).squeeze(0).tolist()
        cpt_scores = torch.sigmoid(self.cpt_head(pooled)).squeeze(0).tolist()
        icd = list(zip(self.icd_labels, icd_scores))
        cpt = list(zip(self.cpt_labels, cpt_scores))
        # Sort by confidence desc
        icd.sort(key=lambda x: x[1], reverse=True)
        cpt.sort(key=lambda x: x[1], reverse=True)
        return icd, cpt


def load_labels_from_text(path: str) -> List[str]:
    labels = []
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s:
                    labels.append(s)
    return labels


# ---------------------------
# Streamlit UI
# ---------------------------

def main():
    st.set_page_config(page_title="Note Coder", page_icon="📄", layout="wide")
    st.title("Note Generator + BERT Coder")

    with st.sidebar:
        st.header("Kiln Settings")
        kiln_url = st.text_input("Kiln Base URL", value=DEFAULT_KILN_URL)
        kiln_model = st.text_input("Model", value=DEFAULT_MODEL)
        kiln_temp = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.4, step=0.05)
        kiln_max = st.number_input("Max tokens", min_value=256, max_value=4096, value=900, step=64)

        st.header("Coder Settings")
        coder_mode = st.selectbox("Coder backend", ["Heuristic (fallback)", "BERT (transformers)"])
        icd_thresh = st.slider("ICD threshold", 0.0, 1.0, 0.35, 0.01)
        cpt_thresh = st.slider("CPT threshold", 0.0, 1.0, 0.35, 0.01)
        base_model = st.text_input("BERT base model", value="emilyalsentzer/Bio_ClinicalBERT")
        icd_labels_path = st.text_input("ICD labels file (one per line)", value="")
        cpt_labels_path = st.text_input("CPT labels file (one per line)", value="")

        st.header("Save")
        csv_path = st.text_input("Output CSV path", value=CSV_PATH)

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
        "Include clinical indication, technique, findings, and impression. Do not output FHIR; output only the narrative text."
    )
    case_prompt = st.text_area("Prompt to Kiln", value=default_prompt, height=140)

    # Generate note
    if st.button("Generate Note with Kiln", type="primary"):
        with st.spinner("Contacting Kiln and generating note..."):
            note = kiln_generate_note(case_prompt, kiln_url, kiln_model, kiln_temp, kiln_max)
        if not note:
            st.error("No note returned from Kiln. Check settings and server logs.")
        else:
            st.session_state["generated_note"] = note
            st.success("Note generated.")

    note_text = st.session_state.get("generated_note", "")
    st.subheader("Generated Narrative Report")
    note_text = st.text_area("Report Text", value=note_text, height=260, key="note_text")

    # Analysis section
    st.subheader("Run Code Analysis (ICD/CPT)")
    analyze = st.button("Run Coder Analysis")

    if analyze:
        if not note_text.strip():
            st.warning("Please generate or paste a report first.")
        else:
            with st.spinner("Analyzing with selected coder backend..."):
                icd_preds: List[Tuple[str, float]] = []
                cpt_preds: List[Tuple[str, float]] = []
                if coder_mode.startswith("Heuristic"):
                    coder = HeuristicCoder()
                    icd_preds, cpt_preds = coder.predict(note_text)
                else:
                    if not TRANSFORMERS_AVAILABLE:
                        st.error("transformers/torch not installed. Use heuristic mode or install dependencies.")
                    else:
                        icd_labels = load_labels_from_text(icd_labels_path)
                        cpt_labels = load_labels_from_text(cpt_labels_path)
                        if not icd_labels or not cpt_labels:
                            st.warning("ICD/CPT label files not provided or empty. Falling back to heuristic coder.")
                            coder = HeuristicCoder()
                            icd_preds, cpt_preds = coder.predict(note_text)
                        else:
                            coder = BertCoderTorch(base_model, icd_labels, cpt_labels)
                            icd_raw, cpt_raw = coder.predict(note_text)
                            # Apply thresholds
                            icd_preds = [(code, conf) for code, conf in icd_raw if conf >= icd_thresh]
                            cpt_preds = [(code, conf) for code, conf in cpt_raw if conf >= cpt_thresh]

            st.session_state["icd_preds"] = icd_preds
            st.session_state["cpt_preds"] = cpt_preds
            if not icd_preds and not cpt_preds:
                st.info("No codes met the threshold. Adjust thresholds or edit the report text.")

    icd_preds = st.session_state.get("icd_preds", [])
    cpt_preds = st.session_state.get("cpt_preds", [])

    # Selection UI
    col_icd, col_cpt = st.columns(2)
    with col_icd:
        st.markdown("**ICD Suggestions**")
        selected_icd = []
        if icd_preds:
            for code, conf in icd_preds[:50]:
                key = f"icd_{code}"
                chk = st.checkbox(f"{code} (confidence {conf:.2f})", key=key)
                if chk:
                    selected_icd.append(code)
        else:
            st.caption("No ICD suggestions.")

    with col_cpt:
        st.markdown("**CPT Suggestions**")
        selected_cpt = []
        if cpt_preds:
            for code, conf in cpt_preds[:50]:
                key = f"cpt_{code}"
                chk = st.checkbox(f"{code} (confidence {conf:.2f})", key=key)
                if chk:
                    selected_cpt.append(code)
        else:
            st.caption("No CPT suggestions.")

    st.divider()

    # Save rows
    if st.button("Save Selected to CSV", type="secondary"):
        if not note_text.strip():
            st.warning("Report text is empty.")
        elif not selected_icd and not selected_cpt:
            st.warning("Select at least one ICD or CPT code.")
        else:
            uid = report_uid.strip() or str(uuid.uuid4())
            rows = []
            # If one of the lists is empty, still produce rows for the other (with blank counterpart)
            icd_list = selected_icd or [""]
            cpt_list = selected_cpt or [""]
            for icd in icd_list:
                for cpt in cpt_list:
                    rows.append({
                        "report_uid": uid,
                        "cpt_code": cpt,
                        "icd_code": icd,
                        "procedure_description": procedure_description.strip(),
                        "report_text": note_text.strip(),
                        "provider_id": provider_id.strip(),
                        "provider_name": provider_name.strip(),
                        "message_type": message_type.strip(),
                        "service_line": service_line.strip(),
                        "test_dataset_tag": test_dataset_tag.strip(),
                    })
            try:
                write_rows_to_csv(rows, csv_path)
                st.success(f"Saved {len(rows)} row(s) to {csv_path} with report_uid={uid}.")
            except Exception as e:
                st.error(f"Failed to write CSV: {e}")


if __name__ == "__main__":
    main()
