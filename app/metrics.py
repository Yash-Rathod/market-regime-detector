from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

REQUEST_COUNT = Counter(
    "regime_api_requests_total",
    "Total prediction requests",
    ["endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "regime_api_latency_seconds",
    "Request latency",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)
PREDICTION_DIST = Counter(
    "regime_predictions_total",
    "Regime prediction distribution",
    ["regime", "ticker"]
)
MODEL_CONFIDENCE = Gauge(
    "regime_model_confidence",
    "Last prediction confidence score"
)