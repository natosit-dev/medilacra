
import os
import time
from typing import Dict, List, Tuple

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.multioutput import MultiOutputRegressor

# Centralized logger (plain + JSON) comes from log_utils.get_logger
# The logger writes to logs/plain/*.log and logs/json/*.json by date.
try:
    from utils.log_utils import get_logger
    logger = get_logger(name="Vitals", context={"component": "vitals"})
except Exception as e:
    # Fallback to a no-op logger if log_utils isn't available;
    # we don't want logging failures to break the core logic.
    import logging
    logger = logging.getLogger("VitalsFallback")
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

VITALS_MODEL_PATH: str = "vitals_model.pkl"
_vitals_model: MultiOutputRegressor | None = None

# ------------------------------
# Model training / loading
# ------------------------------
def _training_data() -> Tuple[np.ndarray, np.ndarray]:
    """Return (X, y) toy training data for demo purposes.

    X columns: [age, poverty_index, air_quality_index]
    y columns: [systolic_bp, heart_rate, o2_sat, bmi]
    """
    X = np.array([[30,20,80],[50,50,60],[70,90,30],[65,40,70],[40,80,50],[75,95,20]])
    y = np.array([[110,72,99,20],[135,78,98,28],[160,88,97,32],[142,75,96,26],[160,85,92,31],[180,96,85,36]])
    return X, y

def train_vitals_model(path: str = VITALS_MODEL_PATH) -> MultiOutputRegressor:
    """Train a simple multi-output linear regression and persist it.

    Parameters
    ----------
    path : str
        Filesystem path where the trained model will be saved.

    Returns
    -------
    MultiOutputRegressor
        Fitted model.
    """
    start = time.perf_counter()
    X, y = _training_data()
    model = MultiOutputRegressor(LinearRegression())
    model.fit(X, y)
    joblib.dump(model, path)
    logger.info("Trained vitals model and saved to disk", extra={"extra": {"model_path": path}})
    logger.debug("Training set shapes", extra={"extra": {"X_shape": X.shape, "y_shape": y.shape}})
    logger.debug("Training duration seconds", extra={"extra": {"elapsed": round(time.perf_counter() - start, 6)}})
    return model

def load_vitals_model(path: str = VITALS_MODEL_PATH) -> MultiOutputRegressor:
    """Load the vitals model from disk; train it if missing (first run).

    Returns
    -------
    MultiOutputRegressor
    """
    global _vitals_model
    if _vitals_model is not None:
        return _vitals_model

    if not os.path.exists(path):
        logger.warning("Model file not found; training a fresh model", extra={"extra": {"model_path": path}})
        _vitals_model = train_vitals_model(path)
    else:
        start = time.perf_counter()
        _vitals_model = joblib.load(path)
        logger.info("Loaded vitals model from disk", extra={"extra": {"model_path": path, "elapsed": round(time.perf_counter() - start, 6)}})
    return _vitals_model

# ------------------------------
# Inference helpers
# ------------------------------
def _validate_inputs(age: int, poverty: float, air_quality: float) -> None:
    """Validate input ranges and log warnings if suspicious.

    This does *not* raise on out-of-range; instead it logs warnings so the API
    remains backward compatible.
    """
    if age < 0 or age > 120:
        logger.warning("Age appears out of realistic range", extra={"extra": {"age": age}})
    if poverty < 0 or poverty > 100:
        logger.warning("Poverty index expected 0-100", extra={"extra": {"poverty": poverty}})
    if air_quality < 0 or air_quality > 100:
        logger.warning("Air quality index expected 0-100", extra={"extra": {"air_quality": air_quality}})

def predict_vitals(age: int, poverty: float, air_quality: float) -> Dict[str, float]:
    """Predict standard vitals from demographic/environmental features.

    Parameters
    ----------
    age : int
    poverty : float
        Poverty index (0-100)
    air_quality : float
        Air quality index (0-100). Higher values represent poorer air quality
        in this toy example.

    Returns
    -------
    dict
        Keys: systolic_bp, heart_rate, o2_sat, bmi
    """
    _validate_inputs(age, poverty, air_quality)
    model = load_vitals_model()
    start = time.perf_counter()
    preds = model.predict(np.array([[age, poverty, air_quality]], dtype=float))[0]
    elapsed = round(time.perf_counter() - start, 6)
    result = {
        "systolic_bp": float(preds[0]),
        "heart_rate": float(preds[1]),
        "o2_sat": float(preds[2]),
        "bmi": float(preds[3]),
    }
    logger.info("Generated vitals prediction", extra={"extra": {"age": age, "poverty": poverty, "air_quality": air_quality, "elapsed": elapsed}})
    logger.debug("Prediction output", extra={"extra": result})
    return result

# ------------------------------
# HL7 OBX segment builder
# ------------------------------
def build_obx_vitals(vitals: Dict[str, float], start_set_id: int = 10) -> List[str]:
    """Build HL7 OBX segments from a vitals dict using LOINC codes.

    Parameters
    ----------
    vitals : dict
        Output of predict_vitals (systolic_bp, heart_rate, o2_sat, bmi).
    start_set_id : int
        OBX-1 start value; increments for each observation.

    Returns
    -------
    list[str]
        List of OBX segments (HL7 v2.5 style).
    """
    required = ("systolic_bp", "heart_rate", "o2_sat", "bmi")
    missing = [k for k in required if k not in vitals]
    if missing:
        logger.error("Missing required vitals keys for OBX build", extra={"extra": {"missing": missing}})
        # Still attempt to build with defaults to be resilient
    segs: List[str] = []
    try:
        segs.append(f"OBX|{start_set_id}|NM|8480-6^Systolic BP^LN||{vitals.get('systolic_bp', 0.0):.1f}|mmHg|90-140||||F")
        segs.append(f"OBX|{start_set_id+1}|NM|8867-4^Heart rate^LN||{vitals.get('heart_rate', 0.0):.1f}|/min|60-100||||F")
        segs.append(f"OBX|{start_set_id+2}|NM|59408-5^Oxygen saturation^LN||{vitals.get('o2_sat', 0.0):.1f}|%|95-100||||F")
        segs.append(f"OBX|{start_set_id+3}|NM|39156-5^Body mass index^LN||{vitals.get('bmi', 0.0):.1f}|kg/m2|18.5-24.9||||F")
    finally:
        logger.info("Built OBX segments", extra={"extra": {"start_set_id": start_set_id, "segment_count": len(segs)}})
    return segs

# ------------------------------
# Optional CLI for quick local testing
# ------------------------------
if __name__ == "__main__":
    sample = predict_vitals(age=55, poverty=40.0, air_quality=65.0)
    for line in build_obx_vitals(sample, start_set_id=10):
        print(line)
