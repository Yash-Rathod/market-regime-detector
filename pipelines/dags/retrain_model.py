from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

default_args = {
    "owner":            "regime-team",
    "retries":          1,
    "retry_delay":      timedelta(minutes=10),
    "email_on_failure": False,
}

with DAG(
    dag_id       = "nse_model_retrain",
    default_args = default_args,
    description  = "Weekly model retrain with drift check",
    schedule     = "0 12 * * 0",   # Every Sunday 12:00 UTC
    start_date   = datetime(2024, 1, 1),
    catchup      = False,
    tags         = ["nse", "training"],
) as dag:

    def _check_drift() -> bool:
        """
        Checks if recent feature distributions have shifted.
        Returns True if retraining is needed.
        This is a simplified check — in production use Evidently AI.
        """
        from app.db.schema import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            result = session.execute(text("""
                SELECT
                    AVG(rsi_14)        as avg_rsi,
                    STDDEV(rsi_14)     as std_rsi,
                    AVG(volatility_20) as avg_vol
                FROM features
                WHERE date >= NOW() - INTERVAL '30 days'
            """)).fetchone()
            print(f"Recent stats — RSI mean: {result[0]:.2f}, "
                  f"RSI std: {result[1]:.2f}, Vol mean: {result[2]:.4f}")
            # Simple threshold: flag if RSI std > 20 (high dispersion = regime shift)
            return float(result[1]) > 20
        finally:
            session.close()

    def _retrain():
        from training.train import train
        acc, f1 = train()
        if f1 < 0.55:
            raise ValueError(f"Model F1 {f1:.4f} below threshold 0.55. Not promoting.")
        print(f"Retrain complete — Accuracy: {acc:.4f}, F1: {f1:.4f}")

    drift_check   = PythonOperator(task_id="check_drift",    python_callable=_check_drift)
    retrain_task  = PythonOperator(task_id="retrain_model",  python_callable=_retrain)

    drift_check >> retrain_task