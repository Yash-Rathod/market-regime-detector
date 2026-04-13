import time
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from app.schemas import PredictRequest, PredictResponse, HealthResponse
from app.models.predictor import predictor
from app.metrics import (
    REQUEST_COUNT, REQUEST_LATENCY,
    PREDICTION_DIST, MODEL_CONFIDENCE
)

load_dotenv()
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load model once
    predictor.load()
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title="Market Regime Detector — NSE",
    description="Classifies Indian equity market regime: BULL / BEAR / SIDEWAYS",
    version=APP_VERSION,
    lifespan=lifespan
)


@app.get("/health", response_model=HealthResponse)
def health():
    return {
        "status":       "ok",
        "model_loaded": predictor.loaded,
        "version":      APP_VERSION
    }


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    start = time.time()
    try:
        features = request.model_dump()
        ticker   = features.pop("ticker")

        result   = predictor.predict(features)

        # Update Prometheus metrics
        PREDICTION_DIST.labels(regime=result["regime"], ticker=ticker).inc()
        MODEL_CONFIDENCE.set(result["confidence"])
        REQUEST_COUNT.labels(endpoint="/predict", status="200").inc()

        return PredictResponse(
            ticker        = ticker,
            regime        = result["regime"],
            confidence    = result["confidence"],
            probabilities = result["probabilities"]
        )
    except Exception as e:
        REQUEST_COUNT.labels(endpoint="/predict", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        latency = time.time() - start
        REQUEST_LATENCY.labels(endpoint="/predict").observe(latency)


@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/regime/latest")
def latest_regime():
    """Returns the most recently computed regime for all tracked tickers."""
    from app.db.schema import SessionLocal
    from sqlalchemy import text
    session = SessionLocal()
    try:
        rows = session.execute(text("""
            SELECT DISTINCT ON (ticker)
                ticker, date, regime_label, rsi_14, adx_14, momentum_10
            FROM features
            ORDER BY ticker, date DESC
        """)).fetchall()
        return {
            "regimes": [
                {
                    "ticker":  r[0],
                    "date":    str(r[1]),
                    "regime":  r[2],
                    "rsi_14":  r[3],
                    "adx_14":  r[4],
                    "momentum": r[5]
                } for r in rows
            ]
        }
    finally:
        session.close()