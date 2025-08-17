import os
import time
import logging
from typing import Optional, Dict, Any

import numpy as np
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# ===========================
#  Config via env
# ===========================
ALPHA_VANTAGE_API_KEY = os.getenv("VANTAGE_API_KEY", "demo")     # Alpha Vantage API key

# ===========================
#  Helpers
# ===========================
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _alpha_vantage_history(ticker: str, days: int = 90) -> Optional[pd.DataFrame]:
    """
    Fetch historical data from Alpha Vantage API
    """
    try:
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "apikey": ALPHA_VANTAGE_API_KEY,
            "outputsize": "compact"  # Last 100 data points
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Debug logging - remove after fixing
        logger.info(f"Alpha Vantage response for {ticker}: {str(data)[:500]}...")
        
        if "Error Message" in data:
            logger.warning(f"Alpha Vantage error for {ticker}: {data['Error Message']}")
            return None
            
        if "Note" in data:
            logger.warning(f"Alpha Vantage rate limit for {ticker}: {data['Note']}")
            return None
            
        time_series = data.get("Time Series (Daily)", {})
        if not time_series:
            logger.warning(f"No time series data for {ticker}")
            return None
            
        # Convert to DataFrame
        df_data = []
        for date_str, values in time_series.items():
            df_data.append({
                "Date": pd.to_datetime(date_str),
                "Open": float(values["1. open"]),
                "High": float(values["2. high"]),
                "Low": float(values["3. low"]),
                "Close": float(values["4. close"]),
                "Volume": int(values["5. volume"])
            })
        
        df = pd.DataFrame(df_data)
        df.set_index("Date", inplace=True)
        df.sort_index(inplace=True)
        
        # Filter to requested days
        cutoff_date = _now_utc().date() - timedelta(days=days)
        df = df[df.index.date >= cutoff_date]
        
        return df if not df.empty else None
        
    except Exception as e:
        logger.warning(f"Alpha Vantage fetch failed for {ticker}: {e}")
        return None

# ===========================
#  Public API
# ===========================
def get_daily_history(ticker: str, period: str = "60d", interval: str = "1d", prepost: bool = True) -> pd.DataFrame:
    """
    Fetch daily history using Alpha Vantage API
    """
    df = _alpha_vantage_history(ticker, days=90 if period.endswith("60d") else 120)
    if df is None or df.empty:
        raise RuntimeError(f"Alpha Vantage returned no data for {ticker}")
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

# ---- No market context - removed to save API calls ----
def get_market_context() -> None:
    """
    Market context removed - will be separate endpoint later
    """
    return None
