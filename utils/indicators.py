import os
import time
import logging
import threading
from typing import Optional, Tuple, Dict

import numpy as np
import pandas as pd

# --- Yahoo stack
import yfinance as yf
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Stooq fallback
from pandas_datareader import data as pdr
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# ===========================
#  Config via env
# ===========================
YF_MIN_INTERVAL = float(os.getenv("YF_MIN_INTERVAL", "3.0"))          # seconds between Yahoo calls
MARKET_CACHE_TTL = float(os.getenv("MARKET_CACHE_TTL", "600"))        # seconds for SPY/VIX cache (increased from 300)
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "auto").lower()            # "auto" | "yahoo" | "stooq"
ENABLE_MARKET_CONTEXT = os.getenv("ENABLE_MARKET_CONTEXT", "true").lower() == "true"  # disable to reduce API calls

# ===========================
#  Shared Yahoo session
# ===========================
def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": os.getenv(
            "YF_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4_1) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
    })
    retry = Retry(
        total=5,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD", "OPTIONS"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.trust_env = False  # ignore any proxy env that might trip Yahoo
    return s

_YF_SESSION = _make_session()

# ===========================
#  Container-wide rate limit
# ===========================
_LAST_CALL_TS = 0.0
_RATE_LOCK = threading.Lock()

def _respect_rate_limit():
    global _LAST_CALL_TS
    with _RATE_LOCK:
        now = time.time()
        delay = YF_MIN_INTERVAL - (now - _LAST_CALL_TS)
        if delay > 0:
            time.sleep(delay)
        _LAST_CALL_TS = time.time()

# ===========================
#  Helpers
# ===========================
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _stooq_symbol(t: str) -> Optional[str]:
    """
    Map a plain US ticker to Stooq format.
    Stooq expects e.g. 'PANW.US', 'AAPL.US', 'SPY.US'.
    Indices like ^VIX generally aren't available; return None for those.
    """
    t = t.strip().upper()
    if t.startswith("^"):
        # Stooq doesn't provide ^VIX; return None so we skip it
        return None
    if t.endswith(".US"):
        return t
    return f"{t}.US"

def _stooq_history(ticker: str, days: int = 90) -> Optional[pd.DataFrame]:
    try:
        sym = _stooq_symbol(ticker)
        if sym is None:
            return None
        end = _now_utc().date()
        start = end - timedelta(days=days + 10)  # a bit extra for business days
        df = pdr.DataReader(sym, "stooq", start, end)  # returns DESC order
        if df is None or df.empty:
            return None
        df = df.sort_index()  # ASC
        # Normalize columns to Yahoo-like capitalization if needed
        cols = {c: c.capitalize() for c in df.columns}
        df = df.rename(columns=cols)
        return df
    except Exception as e:
        logger.warning(f"Stooq fetch failed for {ticker}: {e}")
        return None

def _yahoo_history(ticker: str, period: str = "60d", interval: str = "1d", prepost: bool = True) -> Optional[pd.DataFrame]:
    try:
        _respect_rate_limit()
        t = yf.Ticker(ticker, session=_YF_SESSION)
        df = t.history(period=period, interval=interval, prepost=prepost, auto_adjust=False)
        if df is not None and not df.empty:
            return df
        return None
    except Exception as e:
        logger.warning(f"Yahoo history failed for {ticker}: {e}")
        return None

def _yahoo_download(symbol: str, period: str = "30d", interval: str = "1d") -> Optional[pd.DataFrame]:
    try:
        _respect_rate_limit()
        df = yf.download(symbol, session=_YF_SESSION, progress=False, auto_adjust=False, period=period, interval=interval)
        if df is not None and not df.empty:
            return df
        return None
    except Exception as e:
        logger.warning(f"Yahoo download failed for {symbol}: {e}")
        return None

# ===========================
#  Public API
# ===========================
def get_daily_history(ticker: str, period: str = "60d", interval: str = "1d", prepost: bool = True) -> pd.DataFrame:
    """
    Fetch daily history with provider selection:
    - If DATA_PROVIDER=yahoo → Yahoo only
    - If DATA_PROVIDER=stooq → Stooq only
    - If DATA_PROVIDER=auto → Try Yahoo, fallback to Stooq
    """
    provider = DATA_PROVIDER
    if provider == "yahoo":
        df = _yahoo_history(ticker, period=period, interval=interval, prepost=prepost)
        if df is None or df.empty:
            raise RuntimeError("Yahoo returned no data")
        return df

    if provider == "stooq":
        df = _stooq_history(ticker, days=90 if period.endswith("60d") else 120)
        if df is None or df.empty:
            raise RuntimeError("Stooq returned no data")
        return df

    # auto
    df = _yahoo_history(ticker, period=period, interval=interval, prepost=prepost)
    if df is None or df.empty:
        logger.info(f"Yahoo empty/429 for {ticker}; falling back to Stooq")
        df = _stooq_history(ticker, days=90 if period.endswith("60d") else 120)
    if df is None or df.empty:
        raise RuntimeError("No data from Yahoo or Stooq")
    return df

# ---- RSI ----
def calculate_rsi(prices, window: int = 14) -> Optional[float]:
    try:
        if isinstance(prices, np.ndarray):
            series = pd.Series(prices)
        elif isinstance(prices, pd.Series):
            series = prices
        else:
            series = pd.Series(list(prices))
        if len(series) < window + 1:
            return None
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        last = rsi.iloc[-1]
        return float(last) if not pd.isna(last) else None
    except Exception as e:
        logger.error(f"RSI calc error: {e}")
        return None

# ---- Market context (SPY/VIX with cache) ----
_MARKET_CACHE: Dict = {"data": None, "ts": 0.0}

def get_market_context() -> Optional[Dict]:
    # Skip market context if disabled
    if not ENABLE_MARKET_CONTEXT:
        return None
        
    global _MARKET_CACHE
    now = time.time()
    cached = _MARKET_CACHE.get("data")
    ts = _MARKET_CACHE.get("ts", 0.0)
    if cached and (now - ts) < MARKET_CACHE_TTL:
        return cached

    # Try SPY with provider-aware fallback
    try:
        spy = None
        if DATA_PROVIDER == "stooq":
            # Use Stooq only
            spy = _stooq_history("SPY", days=35)
        elif DATA_PROVIDER == "yahoo":
            # Use Yahoo only
            spy = _yahoo_download("SPY", period="30d", interval="1d")
        else:
            # auto: Try Yahoo first, fallback to Stooq
            spy = _yahoo_download("SPY", period="30d", interval="1d")
            if spy is None or spy.empty:
                logger.info("SPY Yahoo failed, falling back to Stooq")
                spy = _stooq_history("SPY", days=35)

        if spy is None or spy.empty:
            logger.warning("Failed to get SPY from both Yahoo and Stooq")
            return cached

        spy = spy.sort_index()
        spy_current = float(spy["Close"].iloc[-1])
        spy_month_ago = float(spy["Close"].iloc[0])
        spy_change = ((spy_current - spy_month_ago) / spy_month_ago) * 100

        # VIX: Only attempt if not using Stooq-only mode (Stooq doesn't have VIX)
        vix_level = None
        if DATA_PROVIDER != "stooq":
            vix = _yahoo_download("^VIX", period="5d", interval="1d")
            vix_level = float(vix["Close"].iloc[-1]) if (vix is not None and not vix.empty) else None

        data = {
            "spy_30d_change": round(spy_change, 1),
            "vix_level": round(vix_level, 1) if vix_level is not None else None,
            "dxy_change": None,
            "market_sentiment": "bearish" if spy_change < -3 else "bullish" if spy_change > 3 else "neutral",
        }
        _MARKET_CACHE = {"data": data, "ts": now}
        return data
    except Exception as e:
        logger.warning(f"Market context fetch fail: {e}")
        return cached
