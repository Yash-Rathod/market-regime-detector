import time
import os
import pandas as pd
from datetime import date
from sqlalchemy.dialects.postgresql import insert
from app.db.schema import SessionLocal, OHLCVRecord
from pipelines.tasks.data_sources import fetch_ohlcv
from dotenv import load_dotenv

load_dotenv()

# Internal ticker name → NSE symbol + type mapping
# Internal names use Yahoo-style naming for consistency across the codebase.
# NSE symbols are what jugaad-trader and the NSE API actually understand.
TICKER_MAP = {
    "^NSEI":       {"type": "index",  "symbol": "NIFTY 50"},
    "^NSEBANK":    {"type": "index",  "symbol": "NIFTY BANK"},
    "RELIANCE.NS": {"type": "equity", "symbol": "RELIANCE"},
    "INFY.NS":     {"type": "equity", "symbol": "INFY"},
    "HDFCBANK.NS": {"type": "equity", "symbol": "HDFCBANK"},
}


def fetch_and_store(internal_ticker: str, days_back: int = 365) -> int:
    """
    Fetches OHLCV data for a single ticker and upserts it into PostgreSQL.

    Uses the multi-source fallback chain from data_sources.py.
    Returns the number of rows stored.
    """
    config = TICKER_MAP.get(internal_ticker)
    if not config:
        print(f"[WARN] Unknown ticker: {internal_ticker}. Add it to TICKER_MAP.")
        return 0

    symbol      = config["symbol"]
    ticker_type = config["type"]

    print(f"\n── Fetching {internal_ticker} ({symbol}) ──")

    df = fetch_ohlcv(
        symbol          = symbol,
        ticker_type     = ticker_type,
        days_back       = days_back,
        allow_synthetic = True    # Set to False in production
    )

    if df.empty:
        print(f"  No data available for {internal_ticker}. Skipping.")
        return 0

    print(f"  Got {len(df)} rows. Date range: {df['date'].min().date()} → {df['date'].max().date()}")

    session = SessionLocal()
    try:
        count = 0
        for _, row in df.iterrows():
            stmt = (
                insert(OHLCVRecord)
                .values(
                    ticker = internal_ticker,
                    date   = row["date"],
                    open   = float(row["open"]),
                    high   = float(row["high"]),
                    low    = float(row["low"]),
                    close  = float(row["close"]),
                    volume = float(row["volume"]),
                )
                .on_conflict_do_nothing(
                    index_elements=["ticker", "date"]
                )
            )
            session.execute(stmt)
            count += 1

        session.commit()
        print(f"  Stored {count} rows for {internal_ticker}")
        return count

    except Exception as e:
        session.rollback()
        print(f"  [ERROR] DB write failed for {internal_ticker}: {e}")
        raise e

    finally:
        session.close()


def fetch_all_tickers(days_back: int = 365) -> dict:
    """
    Fetches and stores OHLCV for all tickers in TICKER_MAP.
    Adds a polite 1-second delay between calls to avoid hammering NSE.

    Args:
        days_back: calendar days of history to fetch

    Returns:
        dict mapping internal_ticker → rows stored
    """
    results = {}
    total   = len(TICKER_MAP)

    for idx, internal_ticker in enumerate(TICKER_MAP, start=1):
        print(f"\n[{idx}/{total}] Processing {internal_ticker}")
        try:
            rows = fetch_and_store(internal_ticker, days_back=days_back)
            results[internal_ticker] = rows
        except Exception as e:
            print(f"  [ERROR] Failed for {internal_ticker}: {e}")
            results[internal_ticker] = 0

        if idx < total:
            time.sleep(1)   # polite delay between NSE requests

    print("\n── Fetch summary ──")
    for ticker, count in results.items():
        status = "OK" if count > 0 else "FAILED"
        print(f"  [{status}] {ticker}: {count} rows")

    return results


if __name__ == "__main__":
    # When run directly, fetch 365 days of history for all tickers
    fetch_all_tickers(days_back=365)