import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def calculate_rsi(prices, window=14):
    """Calculate RSI for a price series - handles both pandas Series and numpy arrays"""
    try:
        # Convert numpy array to pandas Series if needed
        if isinstance(prices, np.ndarray):
            prices = pd.Series(prices)
        elif not isinstance(prices, pd.Series):
            prices = pd.Series(list(prices))
        
        if len(prices) < window + 1:
            return None
        
        # Use Wilder's smoothing method (more accurate and standard)
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        
        # Wilder's exponential smoothing (alpha = 1/period)
        avg_gain = gain.ewm(alpha=1/window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/window, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # Return the most recent RSI value
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None
        
    except Exception as e:
        logger.error(f"Error calculating RSI: {e}")
        return None

def get_real_time_rsi(ticker: str, window=14) -> Optional[float]:
    """Get real-time RSI using intraday data for more accurate readings"""
    try:
        stock = yf.Ticker(ticker)
        
        # Try to get intraday data for more accurate RSI
        # Use 2 days of hourly data to have enough points for RSI calculation
        intraday_data = stock.history(period="2d", interval="1h")
        
        if len(intraday_data) >= window + 1:
            # Use hourly data for more real-time RSI
            hourly_rsi = calculate_rsi(intraday_data['Close'], window)
            if hourly_rsi is not None:
                return hourly_rsi
        
        # Fallback to daily data if intraday fails
        daily_data = stock.history(period="30d", interval="1d")
        if len(daily_data) >= window + 1:
            return calculate_rsi(daily_data['Close'], window)
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting real-time RSI for {ticker}: {e}")
        return None

def get_vix_data():
    """Get current VIX level"""
    try:
        vix_data = yf.download('^VIX', period='1d', progress=False)
        if len(vix_data) > 0:
            return float(vix_data['Close'].iloc[-1])
        return None
    except:
        return None

def get_market_context():
    """Get broader market context for AI analysis"""
    try:
        # Get SPY data for market trend
        spy = yf.download('SPY', period='30d', progress=False)
        spy_current = float(spy['Close'].iloc[-1])
        spy_month_ago = float(spy['Close'].iloc[0])
        spy_change = ((spy_current - spy_month_ago) / spy_month_ago) * 100
        
        # Get VIX
        vix = get_vix_data()
        
        # Get DXY (Dollar Index) for macro context
        dxy = yf.download('DX-Y.NYB', period='5d', progress=False)
        dxy_change = 0
        if len(dxy) >= 2:
            dxy_current = float(dxy['Close'].iloc[-1])
            dxy_prev = float(dxy['Close'].iloc[-2])
            dxy_change = ((dxy_current - dxy_prev) / dxy_prev) * 100
        
        return {
            'spy_30d_change': round(spy_change, 1),
            'vix_level': round(vix, 1) if vix else None,
            'dxy_change': round(dxy_change, 1),
            'market_sentiment': 'bearish' if spy_change < -3 else 'bullish' if spy_change > 3 else 'neutral'
        }
    except:
        return None 