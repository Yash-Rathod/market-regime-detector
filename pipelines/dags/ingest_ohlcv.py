from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

default_args = {
    "owner":            "regime-team",
    "retries":          3,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id          = "nse_daily_ingest",
    default_args    = default_args,
    description     = "Fetch NSE OHLCV data and compute features daily",
    schedule        = "30 10 * * 1-5",   # 4:00 PM IST = 10:30 UTC, weekdays
    start_date      = datetime(2024, 1, 1),
    catchup         = False,
    tags            = ["nse", "ingestion"],
) as dag:

    def _fetch():
        from pipelines.tasks.fetch_data import fetch_all_tickers
        results = fetch_all_tickers(days_back=5)  # Daily run: last 5 days
        print(f"Fetch results: {results}")

    def _features():
        from pipelines.tasks.feature_engineering import run_feature_pipeline
        run_feature_pipeline()

    fetch_task    = PythonOperator(task_id="fetch_ohlcv",       python_callable=_fetch)
    features_task = PythonOperator(task_id="compute_features",  python_callable=_features)

    fetch_task >> features_task