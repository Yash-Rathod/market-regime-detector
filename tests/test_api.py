import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_predictor():
    with patch("app.main.predictor") as mock:
        mock.loaded = True
        mock.predict.return_value = {
            "regime":        "BULL",
            "confidence":    0.76,
            "probabilities": {"BEAR": 0.08, "BULL": 0.76, "SIDEWAYS": 0.16}
        }
        yield mock


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_predict_valid():
    payload = {
        "ticker":        "^NSEI",
        "rsi_14":        62.5,
        "bb_width":      0.045,
        "volatility_20": 0.18,
        "momentum_10":   0.032,
        "adx_14":        28.7,
        "volume_ratio":  1.2
    }
    r = client.post("/predict", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["regime"] in ["BULL", "BEAR", "SIDEWAYS"]
    assert 0 <= data["confidence"] <= 1


def test_predict_invalid_rsi():
    payload = {
        "ticker":        "^NSEI",
        "rsi_14":        150.0,   # Invalid: RSI > 100
        "bb_width":      0.045,
        "volatility_20": 0.18,
        "momentum_10":   0.032,
        "adx_14":        28.7,
        "volume_ratio":  1.2
    }
    r = client.post("/predict", json=payload)
    assert r.status_code == 422   # Pydantic validation error


def test_metrics_endpoint():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "regime_api_requests_total" in r.text