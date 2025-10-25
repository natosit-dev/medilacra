import os
import uuid
import csv
from typing import List, Dict, Tuple
from pathlib import Path

import requests

# Optional BERT/transformers backend
try:
    import torch
    from transformers import AutoTokenizer, AutoModel
    TRANSFORMERS_AVAILABLE = True
except Exception:
    TRANSFORMERS_AVAILABLE = False

DEFAULT_KILN_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5:3b-instruct"

CSV_HEADERS = [
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

# ---------------------------
# Files / CSV
# ---------------------------

def ensure_csv_exists(path: str):
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)


def write_rows_to_csv(rows: List[Dict[str, str]], path: str) -> int:
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
    return len(rows)


# ---------------------------
# Kiln / LLM integration
# ---------------------------

def kiln_generate_note(
    case_prompt: str,
    kiln_base_url: str = DEFAULT_KILN_URL,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.4,
    max_tokens: int = 900,
) -> str:
    """Generate a narrative clinical note via a Kiln/Ollama-compatible API.

    Tries, in order:
      1) OpenAI-style Chat Completions:   {base}/chat/completions
      2) OpenAI-style Text Completions:   {base}/completions
      3) Ollama native (non-/v1):         {root}/api/generate
    """
    base = kiln_base_url.rstrip("/")

    # 1) Chat Completions (OpenAI-compatible)
    try:
        url = f"{base}/chat/completions"
        payload = {
            "model": model,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "stream": False,
            "messages": [
                {"role": "system", "content": "You are a clinical documentation generator. Output ONLY a narrative report, not FHIR."},
                {"role": "user", "content": case_prompt},
            ],
        }
        r = requests.post(url, json=payload, timeout=120)
        if r.status_code == 200:
            data = r.json()
            if data.get("choices"):
                msg = data["choices"][0].get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
        elif r.status_code != 404:
            r.raise_for_status()
    except Exception:
        pass

    # 2) Text Completions (OpenAI-compatible)
    try:
        url = f"{base}/completions"
        prompt = (
            "Create a concise, realistic narrative clinical report. "
            "Include clinical indication, technique, findings, and impression. "
            "Do not output FHIR; output only the narrative text.\n\n" + case_prompt
        )
        payload = {
            "model": model,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "stream": False,
            "prompt": prompt,
        }
        r = requests.post(url, json=payload, timeout=120)
        if r.status_code == 200:
            data = r.json()
            if data.get("choices"):
                choice = data["choices"][0]
                text = choice.get("text") or choice.get("message", {}).get("content", "")
                if isinstance(text, str):
                    return text
        elif r.status_code != 404:
            r.raise_for_status()
    except Exception:
        pass

    # 3) Ollama native (strip /v1 if present)
    try:
        root = base[:-3] if base.endswith("/v1") else base
        url = f"{root}/api/generate"
        payload = {
            "model": model,
            "prompt": case_prompt,
            "stream": False,
            "options": {"temperature": float(temperature)},
        }
        r = requests.post(url, json=payload, timeout=120)
        if r.status_code == 200:
            data = r.json()
            text = data.get("response") or data.get("text") or data.get("output") or ""
            if isinstance(text, str):
                return text
        else:
            r.raise_for_status()
    except Exception:
        pass

    return ""


# ---------------------------
# Coding backends
# ---------------------------

class HeuristicCoder:
    """Rule-based fallback with regex + synonyms and section-aware boosts."""

    def __init__(self):
        import re
        self.re = re
        # ICD patterns (phrase -> (code, base_conf))
        self.icd_terms = [
            (r"\bhypertension\b|\bhtn\b", ("I10", 0.78)),
            (r"\btype\s*2\s*diabetes\b|\bt2dm\b|\bdiabetes mellitus\b", ("E11.9", 0.75)),
            (r"\bpneumonia\b|\bconsolidation\b", ("J18.9", 0.72)),
            (r"\basthma\b|\breactive airway\b", ("J45.909", 0.70)),
            (r"\bchest pain\b|\bpleuritic pain\b", ("R07.9", 0.65)),
            (r"\bshortness of breath\b|\bdyspnea\b", ("R06.02", 0.66)),
            (r"\bcopd\b|\bchronic obstructive\b", ("J44.9", 0.69)),
            (r"\bacute fracture\b|\bfracture\b", ("T14.8XXA", 0.68)),
            (r"\bheadache\b|\bcephalgia\b", ("R51.9", 0.62)),
        ]
        # CPT patterns (phrase -> (code, base_conf))
        self.cpt_terms = [
            (r"\bchest\s*x-?ray\b|\bcxr\b|\bchest radiograph\b|\bchest two views\b", ("71046", 0.80)),
            (r"\bmri\b.*\bknee\b", ("73721", 0.77)),
            (r"\bct\b.*\bhead\b|\bct\b.*\bbrain\b|\bct head\b", ("70450", 0.76)),
            (r"\babdomen\b.*\bultrasound\b|\bultrasound\b.*\babdomen\b|\bruq ultrasound\b", ("76705", 0.74)),
            (r"\bcomplete blood count\b|\bcbc\b", ("85025", 0.74)),
            (r"\bcomprehensive metabolic panel\b|\bcmp\b|\bmetabolic panel\b", ("80053", 0.73)),
            (r"\bchest\b.*\bct angiography\b|\bcta chest\b|\bpe protocol\b", ("71275", 0.78)),
            (r"\blumbar spine\b.*\bx-?ray\b|\blsxr\b", ("72110", 0.72)),
        ]
        # Section weights
        self.section_weights = {
            'impression': 1.0,
            'findings': 0.85,
            'history': 0.75,
            'indication': 0.75,
            'technique': 0.6,
            'other': 0.6,
        }

    def _split_sections(self, text: str) -> dict:
        t = text.lower()
        sections = {k: '' for k in self.section_weights}
        sections['other'] = t
        import re
        # naive splits by known labels
        for name in ['impression', 'findings', 'history', 'indication', 'technique']:
            m = re.search(rf"\b{name}\s*:\s*(.*)", t)
            if m:
                sections[name] = m.group(1)
        return sections

    def predict(self, text: str) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
        sections = self._split_sections(text)
        icd_scores: Dict[str, float] = {}
        cpt_scores: Dict[str, float] = {}

        for sec, content in sections.items():
            weight = self.section_weights.get(sec, 0.6)
            for pat, (code, base) in self.icd_terms:
                if self.re.search(pat, content):
                    icd_scores[code] = max(icd_scores.get(code, 0.0), min(1.0, base * weight + 0.1))
            for pat, (code, base) in self.cpt_terms:
                if self.re.search(pat, content):
                    cpt_scores[code] = max(cpt_scores.get(code, 0.0), min(1.0, base * weight + 0.1))

        # Modality hints from Technique
        tech = sections.get('technique', '')
        if tech:
            if 'cta' in tech and 'chest' in tech:
                cpt_scores.setdefault('71275', 0.7)
            if 'ct' in tech and 'chest' in tech:
                cpt_scores.setdefault('71250', 0.68)
            if 'mri' in tech and 'knee' in tech:
                cpt_scores.setdefault('73721', 0.70)
            if ('radiograph' in tech or 'x-ray' in tech or 'xray' in tech) and 'chest' in tech:
                cpt_scores.setdefault('71046', 0.72)

        icd = sorted(icd_scores.items(), key=lambda x: x[1], reverse=True)
        cpt = sorted(cpt_scores.items(), key=lambda x: x[1], reverse=True)
        return icd, cpt


class BertCoderTorch:
    """Multi-label coder over a clinical BERT encoder (requires fine-tuned heads)."""

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
        pooled = out.pooler_output if hasattr(out, 'pooler_output') and out.pooler_output is not None else out.last_hidden_state.mean(dim=1)
        icd_scores = torch.sigmoid(self.icd_head(pooled)).squeeze(0).tolist()
        cpt_scores = torch.sigmoid(self.cpt_head(pooled)).squeeze(0).tolist()
        icd = list(zip(self.icd_labels, icd_scores))
        cpt = list(zip(self.cpt_labels, cpt_scores))
        icd.sort(key=lambda x: x[1], reverse=True)
        cpt.sort(key=lambda x: x[1], reverse=True)
        return icd, cpt


# ---------------------------
# Label helpers
# ---------------------------

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
# High-level actions
# ---------------------------

def analyze_report(
    report_text: str,
    backend: str = "heuristic",
    icd_labels: List[str] = None,
    cpt_labels: List[str] = None,
    base_model: str = "emilyalsentzer/Bio_ClinicalBERT",
    icd_threshold: float = 0.35,
    cpt_threshold: float = 0.35,
) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
    """Return (icd_predictions, cpt_predictions) with confidences in [0,1].

    Fallbacks:
    - If BERT selected but labels are missing, use HeuristicCoder.
    - If after thresholding nothing remains, return top-5 per head.
    """
    if backend == "bert":
        if not TRANSFORMERS_AVAILABLE or not icd_labels or not cpt_labels:
            coder = HeuristicCoder()
            return coder.predict(report_text)
        coder = BertCoderTorch(base_model, icd_labels, cpt_labels)
        icd_raw, cpt_raw = coder.predict(report_text)
        icd_preds = [(code, conf) for code, conf in icd_raw if conf >= icd_threshold]
        cpt_preds = [(code, conf) for code, conf in cpt_raw if conf >= cpt_threshold]
        if not icd_preds:
            icd_preds = icd_raw[:5]
        if not cpt_preds:
            cpt_preds = cpt_raw[:5]
        return icd_preds, cpt_preds
    else:
        coder = HeuristicCoder()
        icd, cpt = coder.predict(report_text)
        return (icd[:8], cpt[:8])


def build_rows_for_csv(
    report_text: str,
    selected_icd: List[str],
    selected_cpt: List[str],
    report_uid: str,
    procedure_description: str,
    provider_id: str,
    provider_name: str,
    message_type: str,
    service_line: str,
    test_dataset_tag: str,
) -> List[Dict[str, str]]:
    uid = report_uid.strip() or str(uuid.uuid4())
    rows: List[Dict[str, str]] = []
    icd_list = selected_icd or [""]
    cpt_list = selected_cpt or [""]
    for icd in icd_list:
        for cpt in cpt_list:
            rows.append({
                "report_uid": uid,
                "cpt_code": cpt,
                "icd_code": icd,
                "procedure_description": procedure_description.strip(),
                "report_text": report_text.strip(),
                "provider_id": provider_id.strip(),
                "provider_name": provider_name.strip(),
                "message_type": message_type.strip(),
                "service_line": service_line.strip(),
                "test_dataset_tag": test_dataset_tag.strip(),
            })
    return rows
