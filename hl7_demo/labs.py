# labs.py

import random
from datetime import datetime
from typing import Dict, List

try:
    from utils.log_utils import get_logger
except Exception:
    from log_utils import get_logger  # type: ignore

logger = get_logger(name="MediLacra", context={"component": "labs"})

from .sdoh import get_air_quality_by_zip, get_poverty_pct_by_zcta
from .models import Patient, Encounter
from .segments import seg_msh, seg_pid, seg_pv1


# Common LOINCs + synthetic baselines. `units` is the human display; `ucum_code`
# is the machine-readable UCUM representation carried in OBX-6.
LABS_SPEC: Dict[str, Dict] = {
    "2339-0":  {"name":"Glucose",       "units":"mg/dL",    "ucum_code":"mg/dL",    "mean":92,  "sd":10,  "ref":(70,110), "poverty_beta":0.20, "aqi_beta":0.05},
    "4548-4":  {"name":"HbA1c",         "units":"%",        "ucum_code":"%",        "mean":5.3, "sd":0.4, "ref":(4.0,6.0),"poverty_beta":0.010,"aqi_beta":0.002},
    "2093-3":  {"name":"Cholesterol",   "units":"mg/dL",    "ucum_code":"mg/dL",    "mean":185, "sd":30,  "ref":(100,200),"poverty_beta":0.50,"aqi_beta":0.10},
    "13457-7": {"name":"LDL",           "units":"mg/dL",    "ucum_code":"mg/dL",    "mean":115, "sd":20,  "ref":(0,130),  "poverty_beta":0.35,"aqi_beta":0.08},
    "2085-9":  {"name":"HDL",           "units":"mg/dL",    "ucum_code":"mg/dL",    "mean":52,  "sd":10,  "ref":(40,60),  "poverty_beta":-0.10,"aqi_beta":-0.05},
    "2571-8":  {"name":"Triglycerides", "units":"mg/dL",    "ucum_code":"mg/dL",    "mean":140, "sd":40,  "ref":(0,150),  "poverty_beta":0.60,"aqi_beta":0.12},
    "1920-8":  {"name":"AST",           "units":"U/L",      "ucum_code":"U/L",      "mean":24,  "sd":6,   "ref":(10,40),  "poverty_beta":0.10,"aqi_beta":0.04},
    "1742-6":  {"name":"ALT",           "units":"U/L",      "ucum_code":"U/L",      "mean":28,  "sd":8,   "ref":(7,56),   "poverty_beta":0.12,"aqi_beta":0.04},
    "6690-2":  {"name":"WBC",           "units":"10*3/uL",  "ucum_code":"10*3/uL",  "mean":6.8, "sd":1.5, "ref":(4.0,11.0),"poverty_beta":0.01,"aqi_beta":0.02},
    "1988-5":  {"name":"CRP",           "units":"mg/L",     "ucum_code":"mg/L",     "mean":1.2, "sd":0.8, "ref":(0.0,3.0),"poverty_beta":0.02,"aqi_beta":0.03},
}


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _abnormal_flag(val: float, lo: float, hi: float) -> str:
    if val < lo:
        return "L"
    if val > hi:
        return "H"
    return "N"


def _enforce_lipid_plausibility(results: Dict[str, Dict]) -> None:
    """Keep the synthetic lipid panel internally coherent.

    Total cholesterol is derived from the generated LDL, HDL, and triglycerides using the
    familiar Friedewald-style relationship TC ~= LDL + HDL + TG/5. This is not a clinical
    diagnostic calculation; it is a synthetic-data constraint preventing impossible control
    cases such as LDL exceeding total cholesterol before PIQI mutations are introduced.
    """
    required = ("2093-3", "13457-7", "2085-9", "2571-8")
    if not all(code in results for code in required):
        return

    ldl = float(results["13457-7"]["value"])
    hdl = float(results["2085-9"]["value"])
    triglycerides = float(results["2571-8"]["value"])
    derived_total = ldl + hdl + triglycerides / 5.0

    spec = LABS_SPEC["2093-3"]
    lo, hi = spec["ref"]
    total = _clip(derived_total, lo - (hi - lo), hi + (hi - lo))
    total = round(total, 2)
    previous = results["2093-3"]["value"]
    results["2093-3"]["value"] = total
    results["2093-3"]["abnormal_flag"] = _abnormal_flag(total, lo, hi)

    logger.info(
        "Applied synthetic lipid plausibility constraint",
        extra={"extra": {
            "previous_total": previous,
            "derived_total": total,
            "ldl": ldl,
            "hdl": hdl,
            "triglycerides": triglycerides,
        }},
    )


def predict_labs_for_patient(p: Patient) -> Dict[str, Dict]:
    """Return SDOH-shifted synthetic lab values for one patient."""
    try:
        logger.info(
            "Generating lab predictions",
            extra={"extra": {"patient_uid": getattr(p, "patient_uid", None), "zip": getattr(p, "zip_code", None)}},
        )
        raw_pov = get_poverty_pct_by_zcta(p.zip_code)
        if raw_pov in (None, ""):
            logger.warning("Poverty percentage missing for ZCTA; defaulting to 0.0", extra={"extra": {"zip": getattr(p, "zip_code", None)}})
        pov = float(raw_pov or 0.0)

        aq = get_air_quality_by_zip(p.zip_code) or {}
        if "aqi" not in aq:
            logger.warning("AQI missing for ZIP; defaulting to 50.0", extra={"extra": {"zip": getattr(p, "zip_code", None)}})
        aqi = float(aq.get("aqi", 50.0))

        results: Dict[str, Dict] = {}
        for loinc, spec in LABS_SPEC.items():
            base = random.gauss(spec["mean"], spec["sd"])
            sdoh_shift = pov * spec["poverty_beta"] + aqi * spec["aqi_beta"]
            noisy = base + random.gauss(sdoh_shift, spec["sd"] * 0.05)

            lo, hi = spec["ref"]
            unclipped = noisy
            val = _clip(noisy, lo - (hi - lo), hi + (hi - lo))
            if val != unclipped:
                logger.warning(
                    "Value clipped to reasonable range",
                    extra={"extra": {
                        "loinc": loinc,
                        "name": spec["name"],
                        "unclipped": round(unclipped, 4),
                        "clipped": round(val, 4),
                        "ref_window": f"{lo}-{hi}",
                    }},
                )

            results[loinc] = {
                "loinc": loinc,
                "name": spec["name"],
                "value": round(val, 2),
                "units": spec["units"],
                "ucum_code": spec["ucum_code"],
                "ref_low": lo,
                "ref_high": hi,
                "abnormal_flag": _abnormal_flag(val, lo, hi),
                "status": "F",
            }

        _enforce_lipid_plausibility(results)
        logger.info("Finished lab predictions", extra={"extra": {"patient_uid": getattr(p, "patient_uid", None), "n_labs": len(results)}})
        return results
    except Exception as e:
        logger.error("Error generating lab predictions", extra={"extra": {"error": str(e)}})
        raise


def build_obx_labs(labs: Dict[str, Dict], start_set_id: int = 20) -> List[str]:
    """Generate numeric OBX segments with explicit UCUM coding in OBX-6."""
    try:
        logger.info("Building OBX segments for labs", extra={"extra": {"count": len(labs), "start_set_id": start_set_id}})
        if not labs:
            logger.warning("No labs provided to build_obx_labs; returning empty segment list")

        segs: List[str] = []
        sid = start_set_id
        for loinc, d in labs.items():
            for key in ("name", "value", "units", "ref_low", "ref_high", "abnormal_flag", "status"):
                if key not in d:
                    logger.warning("Missing expected field in lab record", extra={"extra": {"loinc": loinc, "missing_key": key}})

            ref = f"{d['ref_low']}-{d['ref_high']}"
            ucum_code = d.get("ucum_code") or d["units"]
            units_ce = f"{ucum_code}^{d['units']}^UCUM"
            segs.append(
                f"OBX|{sid}|NM|{loinc}^{d['name']}^LN||{d['value']}|{units_ce}|{ref}|{d['abnormal_flag']}||{d['status']}"
            )
            sid += 1

        logger.info("Completed OBX segment build", extra={"extra": {"segments": len(segs)}})
        return segs
    except Exception as e:
        logger.error("Error building OBX segments", extra={"extra": {"error": str(e)}})
        raise


def build_lab_orm(p: Patient, enc: Encounter, order_code: str = "SYN_LABS", order_text: str = "Synthetic Lab Panel") -> str:
    """Build a minimal ORM^O01 lab order."""
    try:
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        parts = [
            seg_msh("ORM^O01"),
            seg_pid(p),
            seg_pv1(enc),
            f"ORC|NW|{enc.placer_order_number}|{enc.filler_order_number}||CM|||{now}||||{enc.ordering_provider_id}^{enc.ordering_provider_name}",
            f"OBR|1|{enc.placer_order_number}|{enc.filler_order_number}|{order_code}^{order_text}^99LAB|||{now}|||||||||{enc.ordering_provider_id}^{enc.ordering_provider_name}",
        ]
        msg = "\r".join(parts)
        logger.info("ORM^O01 built", extra={"extra": {"message_length": len(msg)}})
        return msg
    except Exception as e:
        logger.error("Error building ORM^O01", extra={"extra": {"error": str(e)}})
        raise


def build_lab_oru(
    p: Patient,
    enc: Encounter,
    labs: Dict[str, Dict],
    order_code: str = "SYN_LABS",
    order_text: str = "Synthetic Lab Panel",
    start_set_id: int = 20,
) -> str:
    """Build an ORU^R01 with one OBR and OBX lines for each test."""
    try:
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        obx_lines = build_obx_labs(labs, start_set_id=start_set_id)
        parts = [
            seg_msh("ORU^R01"),
            seg_pid(p),
            seg_pv1(enc),
            f"OBR|1|{enc.placer_order_number}|{enc.filler_order_number}|{order_code}^{order_text}^99LAB|||{now}|||||||||{enc.ordering_provider_id}^{enc.ordering_provider_name}",
            *obx_lines,
        ]
        msg = "\r".join(parts)
        logger.info("ORU^R01 built", extra={"extra": {"message_length": len(msg), "obx_count": len(obx_lines)}})
        return msg
    except Exception as e:
        logger.error("Error building ORU^R01", extra={"extra": {"error": str(e)}})
        raise
