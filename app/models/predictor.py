import pickle, json, os
import numpy as np
from dotenv import load_dotenv

load_dotenv()

MODEL_PATH   = os.getenv("MODEL_PATH",   "mlartifacts/model.pkl")
ENCODER_PATH = os.getenv("ENCODER_PATH", "mlartifacts/label_encoder.pkl")
MAPPING_PATH = os.getenv("MAPPING_PATH", "mlartifacts/class_mapping.json")


class RegimePredictor:
    def __init__(self):
        self.model         = None
        self.label_encoder = None
        self.class_mapping = None
        self.loaded        = False

    def load(self):
        with open(MODEL_PATH,   "rb") as f: self.model         = pickle.load(f)
        with open(ENCODER_PATH, "rb") as f: self.label_encoder = pickle.load(f)
        with open(MAPPING_PATH, "r")  as f: self.class_mapping = json.load(f)
        self.loaded = True
        print("Model loaded successfully")

    def predict(self, features: dict) -> dict:
        if not self.loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        feature_order = [
            "rsi_14", "bb_width", "volatility_20",
            "momentum_10", "adx_14", "volume_ratio"
        ]
        x = np.array([[features[k] for k in feature_order]])

        probs       = self.model.predict_proba(x)[0]
        pred_idx    = int(np.argmax(probs))
        confidence  = float(probs[pred_idx])
        regime      = self.class_mapping[str(pred_idx)]

        return {
            "regime":     regime,
            "confidence": round(confidence, 4),
            "probabilities": {
                self.class_mapping[str(i)]: round(float(p), 4)
                for i, p in enumerate(probs)
            }
        }


# Singleton — loaded once at startup
predictor = RegimePredictor()