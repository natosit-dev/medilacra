import os, joblib, numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.multioutput import MultiOutputRegressor

VITALS_MODEL_PATH = "vitals_model.pkl"
_vitals_model = None

def train_vitals_model(path: str = VITALS_MODEL_PATH):
    X = np.array([[30,20,80],[50,50,60],[70,90,30],[65,40,70],[40,80,50],[75,95,20]])
    y = np.array([[110,72,99,20],[135,78,98,28],[160,88,97,32],[142,75,96,26],[160,85,92,31],[180,96,85,36]])
    model = MultiOutputRegressor(LinearRegression()); model.fit(X, y); joblib.dump(model, path); return model

def load_vitals_model(path: str = VITALS_MODEL_PATH):
    global _vitals_model
    if _vitals_model is None:
        _vitals_model = train_vitals_model(path) if not os.path.exists(path) else joblib.load(path)
    return _vitals_model

def predict_vitals(age: int, poverty: float, air_quality: float) -> dict:
    model = load_vitals_model()
    systolic_bp, hr, o2sat, bmi = model.predict(np.array([[age, poverty, air_quality]]))[0]
    return {"systolic_bp": float(systolic_bp), "heart_rate": float(hr), "o2_sat": float(o2sat), "bmi": float(bmi)}

def build_obx_vitals(vitals: dict, start_set_id: int = 10) -> list[str]:
    segs = []
    segs.append(f"OBX|{start_set_id}|NM|8480-6^Systolic BP^LN||{vitals['systolic_bp']:.1f}|mmHg|90-140||||F")
    segs.append(f"OBX|{start_set_id+1}|NM|8867-4^Heart rate^LN||{vitals['heart_rate']:.1f}|/min|60-100||||F")
    segs.append(f"OBX|{start_set_id+2}|NM|59408-5^Oxygen saturation^LN||{vitals['o2_sat']:.1f}|%|95-100||||F")
    segs.append(f"OBX|{start_set_id+3}|NM|39156-5^Body mass index^LN||{vitals['bmi']:.1f}|kg/m2|18.5-24.9||||F")
    return segs
