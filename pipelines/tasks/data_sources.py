import pandas as pd
import numpy as np
import requests
from datetime import date, timedelta
from typing import Optional


def _try_jugaad(
    symbol: str,
    ticker_type: str,
    from_date: date,
    to_date: date
) -> Optional[pd.DataFrame]:
    try:
        from jugaad_trader.nse import NSEHistory
        nse = NSEHistory()

        if ticker_type == "index":
            # Try new API name first, fall back to old
            if hasattr(nse, "index_history"):
                df = nse.index_history(symbol=symbol, start=from_date, end=to_date)
            elif hasattr(nse, "get_history"):
                df = nse.get_history(symbol=symbol, start=from_date,
                                     end=to_date, index=True)
            else:
                raise AttributeError("No known index history method on NSEHistory")
        else:
            if hasattr(nse, "equity_history"):
                df = nse.equity_history(symbol=symbol, series="EQ",
                                        start=from_date, end=to_date)
            elif hasattr(nse, "get_history"):
                df = nse.get_history(symbol=symbol, start=from_date,
                                     end=to_date, index=False)
            else:
                raise AttributeError("No known equity history method on NSEHistory")

        if df is not None and not df.empty:
            print(f"  [jugaad] OK for {symbol}")
            return df
        return None

    except Exception as e:
        print(f"  [jugaad] failed for {symbol}: {e}")
        return None

def _try_nse_direct(
    symbol: str,
    from_date: date,
    to_date: date
) -> Optional[pd.DataFrame]:
    try:
        session = requests.Session()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer":         "https://www.nseindia.com",
        }
        session.get("https://www.nseindia.com", timeout=10, headers=headers)
        session.get(
            "https://www.nseindia.com/get-quotes/equity",
            timeout=10, headers=headers
        )
        url = (
            f"https://www.nseindia.com/api/historical/cm/equity"
            f"?symbol={symbol}"
            f"&series=[%22EQ%22]"
            f"&from={from_date.strftime('%d-%m-%Y')}"
            f"&to={to_date.strftime('%d-%m-%Y')}"
        )
        resp = session.get(url, timeout=15, headers=headers)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data:
                df = pd.DataFrame(data)
                print(f"  [nse-direct] OK for {symbol}")
                return df
    except Exception as e:
        print(f"  [nse-direct] failed for {symbol}: {e}")
    return None


def _synthetic_fallback(symbol: str, days_back: int) -> pd.DataFrame:
    """
    Generates realistic OHLCV using geometric Brownian motion.
    ONLY for development and testing — never for production.
    """
    print(
        f"  [SYNTHETIC FALLBACK] Generating fake data for {symbol}. "
        f"NOT for production use."
    )
    np.random.seed(42)
    dates   = pd.bdate_range(end=date.today(), periods=days_back)
    price   = 20000.0 if "NIFTY" in symbol.upper() else 2000.0
    returns = np.random.normal(0.0003, 0.012, len(dates))
    prices  = price * np.exp(np.cumsum(returns))
    noise   = np.random.uniform(0.005, 0.015, len(dates))

    df = pd.DataFrame({
        "date":   dates,
        "open":   prices * (1 - noise / 2),
        "high":   prices * (1 + noise),
        "low":    prices * (1 - noise),
        "close":  prices,
        "volume": np.random.randint(
            1_000_000, 50_000_000, len(dates)
        ).astype(float),
    })
    return df


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps any source's column schema to the standard schema:
    date, open, high, low, close, volume
    """
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    # Resolve date column
    for cname in ["date", "ch_timestamp", "timestamp", "tradingdate", "tdate"]:
        if cname in df.columns:
            df["date"] = pd.to_datetime(df[cname], errors="coerce")
            break

    # Resolve price and volume columns by trying known aliases
    patterns = {
        "open":   [
            "open", "ch_opening_price", "open_price", "openprice"
        ],
        "high":   [
            "high", "ch_trade_high_price", "high_price", "highprice"
        ],
        "low":    [
            "low",  "ch_trade_low_price",  "low_price",  "lowprice"
        ],
        "close":  [
            "close", "ch_closing_price", "close_price",
            "closeprice", "last", "ltp"
        ],
        "volume": [
            "volume", "ch_tot_traded_qty", "tottrdqty",
            "quantity", "traded_quantity", "tradedquantity"
        ],
    }
    for target, candidates in patterns.items():
        if target not in df.columns:
            for candidate in candidates:
                if candidate in df.columns:
                    df[target] = df[candidate]
                    break

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "open", "high", "low", "close"])

    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["volume"] = df["volume"].fillna(0.0)

    df = df.sort_values("date").reset_index(drop=True)

    return df[["date", "open", "high", "low", "close", "volume"]]


def fetch_ohlcv(
    symbol: str,
    ticker_type: str = "equity",
    days_back: int = 365,
    allow_synthetic: bool = True
) -> pd.DataFrame:
    """
    Main entry point for all data fetching.

    Tries sources in order:
      1. jugaad-trader  (NSE official endpoints)
      2. NSE direct API (browser-mimicking requests)
      3. Synthetic GBM  (only if allow_synthetic=True)

    Returns a normalised DataFrame with columns:
      date, open, high, low, close, volume

    Args:
        symbol:          NSE symbol e.g. "NIFTY 50", "RELIANCE", "INFY"
        ticker_type:     "index" or "equity"
        days_back:       how many calendar days of history to fetch
        allow_synthetic: if True, returns synthetic data when all sources fail
    """
    from_date = date.today() - timedelta(days=days_back)
    to_date   = date.today()

    raw = (
        _try_jugaad(symbol, ticker_type, from_date, to_date)
        or _try_nse_direct(symbol, from_date, to_date)
        or (
            _synthetic_fallback(symbol, days_back)
            if allow_synthetic
            else None
        )
    )

    if raw is None:
        print(f"  [ERROR] All sources failed for {symbol} and synthetic is disabled.")
        return pd.DataFrame()

    if isinstance(raw, pd.DataFrame) and raw.empty:
        return pd.DataFrame()

    return _normalise(raw)