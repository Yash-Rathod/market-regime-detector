import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, f1_score, accuracy_score
from sqlalchemy import text
from app.db.schema import SessionLocal, ModelMetadata
import os, pickle, json
from dotenv import load_dotenv

load_dotenv()

FEATURE_COLS = [
    "rsi_14", "bb_width", "volatility_20",
    "momentum_10", "adx_14", "volume_ratio"
]
TARGET_COL   = "regime_label"
MODEL_PATH   = "mlartifacts/model.pkl"
ENCODER_PATH = "mlartifacts/label_encoder.pkl"

os.makedirs("mlartifacts", exist_ok=True)


def load_training_data() -> pd.DataFrame:
    session = SessionLocal()
    try:
        rows = session.execute(
            text("SELECT ticker, date, rsi_14, bb_width, volatility_20, "
                 "momentum_10, adx_14, volume_ratio, regime_label "
                 "FROM features WHERE regime_label IS NOT NULL")
        ).fetchall()
    finally:
        session.close()

    df = pd.DataFrame(rows, columns=[
        "ticker","date","rsi_14","bb_width","volatility_20",
        "momentum_10","adx_14","volume_ratio","regime_label"
    ])
    print(f"Loaded {len(df)} training samples")
    print(df["regime_label"].value_counts())
    return df


def train():
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001"))
    mlflow.set_experiment("market-regime-nse")

    df = load_training_data()
    if len(df) < 100:
        raise ValueError(f"Insufficient training data: {len(df)} rows. Run fetch + features first.")

    X = df[FEATURE_COLS].values
    le = LabelEncoder()
    y  = le.fit_transform(df[TARGET_COL].values)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    with mlflow.start_run() as run:
        params = {
            "n_estimators": 200,
            "max_depth": 8,
            "min_samples_leaf": 5,
            "class_weight": "balanced",
            "random_state": 42
        }
        mlflow.log_params(params)
        mlflow.log_param("features", FEATURE_COLS)
        mlflow.log_param("tickers", os.getenv("TICKERS"))

        model = RandomForestClassifier(**params)
        model.fit(X_train, y_train)

        # Cross-validation
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        cv_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring="f1_weighted")
        mlflow.log_metric("cv_f1_mean",  float(cv_scores.mean()))
        mlflow.log_metric("cv_f1_std",   float(cv_scores.std()))

        # Test set evaluation
        y_pred   = model.predict(X_test)
        acc      = accuracy_score(y_test, y_pred)
        f1       = f1_score(y_test, y_pred, average="weighted")
        report   = classification_report(y_test, y_pred, target_names=le.classes_)

        mlflow.log_metric("test_accuracy", acc)
        mlflow.log_metric("test_f1",       f1)

        print(f"\nTest Accuracy : {acc:.4f}")
        print(f"Test F1       : {f1:.4f}")
        print(f"\nClassification Report:\n{report}")

        # Log model + encoder to MLflow
        mlflow.sklearn.log_model(model, "random_forest_regime")
        with open(ENCODER_PATH, "wb") as f:
            pickle.dump(le, f)
        mlflow.log_artifact(ENCODER_PATH)

        # Also save locally for FastAPI to load at startup
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

        # Save class mapping
        mapping = {int(i): label for i, label in enumerate(le.classes_)}
        with open("mlartifacts/class_mapping.json", "w") as f:
            json.dump(mapping, f)
        mlflow.log_artifact("mlartifacts/class_mapping.json")

        # Record in DB
        _record_model_metadata(run.info.run_id, acc, f1)
        print(f"\nRun ID: {run.info.run_id}")
        print(f"View at: http://localhost:5001")

    return acc, f1


def _record_model_metadata(run_id: str, acc: float, f1: float):
    session = SessionLocal()
    try:
        # Deactivate old active model
        session.execute(text("UPDATE model_metadata SET is_active = 0"))
        record = ModelMetadata(
            version    = run_id,
            accuracy   = acc,
            f1_score   = f1,
            is_active  = 1
        )
        session.add(record)
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    train()