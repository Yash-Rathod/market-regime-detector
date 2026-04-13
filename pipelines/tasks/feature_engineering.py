import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from app.db.schema import SessionLocal, FeatureRecord
import os
from dotenv import load_dotenv

load_dotenv()

TICKERS = list({
    "^NSEI", "^NSEBANK", "RELIANCE.NS", "INFY.NS", "HDFCBANK.NS"
})


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    rsi      = 100 - (100 / (1 + rs))
    return rsi


def compute_bollinger_width(series: pd.Series, period: int = 20) -> pd.Series:
    sma   = series.rolling(period).mean()
    std   = series.rolling(period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    return (upper - lower) / sma.replace(0, np.nan)


def compute_adx(
    high:  pd.Series,
    low:   pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr      = tr.ewm(span=period, min_periods=period).mean()
    plus_di  = 100 * plus_dm.ewm(span=period).mean()  / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(span=period).mean() / atr.replace(0, np.nan)
    dx       = (
        100
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    )
    adx = dx.ewm(span=period).mean()
    return adx


def assign_regime_label(row) -> str:
    """
    Rule-based regime labelling for supervised training targets.

    Thresholds are based on standard technical analysis conventions:
      - ADX > 25  indicates a trending market (Wilder's original threshold)
      - RSI > 55 / < 45  used instead of 50 to reduce noise
      - Momentum > 2%    10-day price change threshold

    In production you would validate these thresholds against
    historical NSE regime data or use unsupervised HMM labelling.
    """
    rsi = row["rsi_14"]
    adx = row["adx_14"]
    mom = row["momentum_10"]

    if pd.isna(rsi) or pd.isna(adx) or pd.isna(mom):
        return None

    if adx > 25 and mom > 0.02 and rsi > 55:
        return "BULL"
    elif adx > 25 and mom < -0.02 and rsi < 45:
        return "BEAR"
    else:
        return "SIDEWAYS"


def engineer_features_for_ticker(ticker: str) -> pd.DataFrame:
    """
    Loads raw OHLCV from DB, computes all technical features,
    assigns regime labels, and returns a clean DataFrame.
    """
    session = SessionLocal()
    try:
        rows = session.execute(
            text(
                "SELECT date, open, high, low, close, volume "
                "FROM ohlcv WHERE ticker = :t ORDER BY date"
            ),
            {"t": ticker}
        ).fetchall()
    finally:
        session.close()

    if not rows:
        print(f"  [WARN] No OHLCV data in DB for {ticker}. Run fetch_data.py first.")
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=["date", "open", "high", "low", "close", "volume"]
    )
    df["date"]  = pd.to_datetime(df["date"])
    df          = df.sort_values("date").reset_index(drop=True)

    df["rsi_14"]        = compute_rsi(df["close"])
    df["bb_width"]      = compute_bollinger_width(df["close"])
    df["volatility_20"] = (
        df["close"].pct_change().rolling(20).std() * np.sqrt(252)
    )
    df["momentum_10"]   = df["close"].pct_change(10)
    df["adx_14"]        = compute_adx(df["high"], df["low"], df["close"])
    df["volume_ratio"]  = (
        df["volume"]
        / df["volume"].rolling(20).mean().replace(0, np.nan)
    )
    df["ticker"]        = ticker
    df["regime_label"]  = df.apply(assign_regime_label, axis=1)

    before = len(df)
    df = df.dropna(subset=["rsi_14", "adx_14", "momentum_10", "bb_width"])
    print(f"  {ticker}: {before} rows → {len(df)} after dropping NaN features")

    return df


def store_features(df: pd.DataFrame, ticker: str) -> int:
    """
    Upserts feature rows into the features table.
    Skips rows where regime_label is None (insufficient data for labelling).
    Returns the number of rows stored.
    """
    session = SessionLocal()
    try:
        count = 0
        for _, row in df.iterrows():
            if row["regime_label"] is None:
                continue
            stmt = (
                insert(FeatureRecord)
                .values(
                    ticker        = ticker,
                    date          = row["date"],
                    rsi_14        = float(row["rsi_14"]),
                    bb_width      = float(row["bb_width"]),
                    volatility_20 = float(row["volatility_20"]),
                    momentum_10   = float(row["momentum_10"]),
                    adx_14        = float(row["adx_14"]),
                    volume_ratio  = float(row["volume_ratio"]),
                    regime_label  = row["regime_label"],
                )
                .on_conflict_do_nothing(
                    index_elements=["ticker", "date"]
                )
            )
            session.execute(stmt)
            count += 1

        session.commit()
        print(f"  Stored {count} feature rows for {ticker}")
        return count

    except Exception as e:
        session.rollback()
        print(f"  [ERROR] Feature store failed for {ticker}: {e}")
        raise e

    finally:
        session.close()


def run_feature_pipeline() -> dict:
    """
    Runs the full feature engineering pipeline for all tickers.
    Returns a dict mapping ticker → rows stored.
    """
    results = {}
    for ticker in TICKERS:
        print(f"\n── Engineering features for {ticker} ──")
        df = engineer_features_for_ticker(ticker)
        if df.empty:
            results[ticker] = 0
            continue
        results[ticker] = store_features(df, ticker)

    print("\n── Feature pipeline summary ──")
    for ticker, count in results.items():
        status = "OK" if count > 0 else "FAILED"
        print(f"  [{status}] {ticker}: {count} feature rows")

    return results


if __name__ == "__main__":
    run_feature_pipeline()