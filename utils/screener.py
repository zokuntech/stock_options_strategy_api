import os
import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import json
import hashlib

import numpy as np
import pandas as pd
import requests
import asyncio

from .indicators import _alpha_vantage_history, calculate_rsi, _now_utc

logger = logging.getLogger(__name__)

# ===========================
#  Configuration
# ===========================

ALPHA_VANTAGE_API_KEY = os.getenv("VANTAGE_API_KEY", "demo")

# API Tier Configuration
API_TIER = os.getenv("ALPHA_VANTAGE_TIER", "premium").lower()  # 'free' or 'premium'

if API_TIER == "premium":
    REQUESTS_PER_MINUTE = 150  # Premium tier limit
    DAILY_API_LIMIT = 10000    # Very high limit for premium (can screen thousands)
    DELAY_BETWEEN_CALLS = 0.4  # 60s / 150 = 0.4s (faster for premium)
    MAX_STOCKS_PER_SCREEN = 1000  # Screen up to 1000 stocks at once for premium
else:
    REQUESTS_PER_MINUTE = 5    # Free tier is very limited
    DAILY_API_LIMIT = 20       # Conservative limit for free tier
    DELAY_BETWEEN_CALLS = 12   # 60s / 5 = 12s delay
    MAX_STOCKS_PER_SCREEN = 20 # Limited screening for free tier

SP500_CACHE_HOURS = 24  # Cache S&P 500 list for 24 hours
SCREEN_CACHE_HOURS = 1  # Cache screening results for 1 hour (premium can refresh more often)

logger.info(f"Alpha Vantage API Tier: {API_TIER.upper()}")
logger.info(f"Rate limits: {REQUESTS_PER_MINUTE}/min, {DAILY_API_LIMIT}/day, {MAX_STOCKS_PER_SCREEN} stocks per screen")

# Simple file-based caching (in production, use Redis or database)
CACHE_DIR = "/tmp/stock_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# ===========================
#  Caching Utilities
# ===========================

def _get_cache_file(cache_key: str) -> str:
    """Get cache file path for a given key"""
    safe_key = hashlib.md5(cache_key.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{safe_key}.json")

def _get_cached_data(cache_key: str, max_age_hours: float) -> Optional[Dict[str, Any]]:
    """Get cached data if it exists and is not expired"""
    cache_file = _get_cache_file(cache_key)
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with open(cache_file, 'r') as f:
            data = json.load(f)
        
        # Check if cache is expired
        cached_time = datetime.fromisoformat(data['timestamp'])
        age_hours = (datetime.now() - cached_time).total_seconds() / 3600
        
        if age_hours < max_age_hours:
            logger.info(f"Cache hit for {cache_key} (age: {age_hours:.1f}h)")
            return data['content']
        else:
            logger.info(f"Cache expired for {cache_key} (age: {age_hours:.1f}h)")
            return None
            
    except Exception as e:
        logger.warning(f"Cache read error for {cache_key}: {e}")
        return None

def _set_cached_data(cache_key: str, data: Any) -> None:
    """Cache data with timestamp"""
    cache_file = _get_cache_file(cache_key)
    
    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'content': data
    }
    
    try:
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)
        logger.info(f"Cached data for {cache_key}")
    except Exception as e:
        logger.warning(f"Cache write error for {cache_key}: {e}")

# ===========================
#  S&P 500 Dynamic Fetching
# ===========================

def get_sp500_symbols() -> List[str]:
    """
    Get the actual S&P 500 companies list
    Loads from comprehensive JSON file with caching
    """
    cache_key = "actual_sp500_symbols"
    
    # Try to get from cache first
    cached_symbols = _get_cached_data(cache_key, SP500_CACHE_HOURS)
    if cached_symbols:
        return cached_symbols
    
    logger.info("Loading S&P 500 companies from JSON file...")
    
    try:
        # Load from JSON file
        import json
        import os
        
        # Get the path to the JSON file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(os.path.dirname(current_dir), 'data', 'sp500_companies.json')
        
        with open(json_path, 'r') as f:
            sp500_data = json.load(f)
        
        companies = sp500_data.get('companies', [])
        
        if not companies:
            raise ValueError("No companies found in JSON file")
        
        # Sort alphabetically for consistent processing
        companies.sort()
        
        logger.info(f"Loaded {len(companies)} S&P 500 companies from JSON file")
        
        # Cache the results
        _set_cached_data(cache_key, companies)
        
        return companies
        
    except Exception as e:
        logger.error(f"Failed to load S&P 500 companies from JSON: {e}")
        
        # Fallback to our static list if JSON loading fails
        logger.info("Falling back to static large-cap list")
        return LARGE_CAP_TICKERS

def get_screening_batch(all_symbols: List[str], max_stocks: int = None) -> List[str]:
    """
    Get a batch of symbols to screen, optimized for API tier
    
    For Premium: Can screen many more stocks at once
    For Free: Rotates through symbols daily to eventually cover all
    """
    if not all_symbols:
        return []
    
    if max_stocks is None:
        max_stocks = MAX_STOCKS_PER_SCREEN
    
    # For premium API, we can screen many more stocks
    if API_TIER == "premium":
        # For small requests (like streaming), use a reasonable minimum
        if max_stocks < 50:
            effective_limit = min(100, len(all_symbols))  # Use at least 100 stocks for good coverage
        else:
            effective_limit = min(max_stocks, len(all_symbols))  # Screen all available S&P 500 stocks
        
        batch = all_symbols[:effective_limit]
        logger.info(f"Premium tier: Screening {len(batch)} S&P 500 companies out of {len(all_symbols)} total")
        if len(batch) > 50:
            logger.info(f"Estimated time: {(len(batch) * 0.4) / 60:.1f} minutes at 150 calls/min")
        return batch
    
    else:
        # Free tier: Use daily rotation like before
        today = datetime.now().date()
        day_of_year = today.timetuple().tm_yday
        
        total_symbols = len(all_symbols)
        total_batches = (total_symbols + max_stocks - 1) // max_stocks  # Ceiling division
        
        # Determine which batch to use today
        batch_index = day_of_year % total_batches
        start_idx = batch_index * max_stocks
        end_idx = min(start_idx + max_stocks, total_symbols)
        
        batch = all_symbols[start_idx:end_idx]
        
        logger.info(f"Free tier: Using batch {batch_index + 1}/{total_batches} ({len(batch)} symbols)")
        logger.info(f"Today's symbols: {', '.join(batch[:10])}{'...' if len(batch) > 10 else ''}")
        
        return batch

# ===========================
#  Legacy Stock Lists (Fallback)
# ===========================

# Keep as fallback in case API fails
LARGE_CAP_TICKERS = [
    # Tech (FAANG + major tech)
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "NVDA", "NFLX", "CRM", 
    "ORCL", "ADBE", "AMD", "INTC", "CSCO", "QCOM", "AVGO", "TXN", "INTU", "MU",
    
    # Finance
    "BRK.B", "BRK.A", "JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "V", "MA", 
    "COF", "USB", "PNC", "TFC", "BLK", "SCHW", "SPGI", "CME", "ICE",
    
    # Healthcare & Pharma
    "JNJ", "UNH", "PFE", "ABBV", "TMO", "ABT", "MRK", "LLY", "MDT", "AMGN",
    "GILD", "BMY", "CVS", "CI", "HUM", "ANTM", "ISRG", "DXCM", "SYK", "BSX",
    
    # Consumer Discretionary
    "HD", "NKE", "MCD", "SBUX", "TJX", "LOW", "F", "GM",
    "DIS", "CMCSA", "VZ", "T", "TMUS", "CCI", "AMT", "EQIX", "DLR",
    
    # Consumer Staples
    "PG", "KO", "PEP", "WMT", "COST", "CL", "KMB", "GIS", "K", "HSY",
    
    # Industrial & Energy
    "BA", "CAT", "GE", "MMM", "HON", "UPS", "RTX", "LMT", "DE", "FDX",
    "XOM", "CVX", "COP", "SLB", "EOG", "KMI", "OXY", "PSX", "VLO", "MPC"
]

# ===========================
#  Date Filtering Utilities
# ===========================

def get_date_range(period: str) -> tuple[datetime, datetime]:
    """
    Get start and end dates for different time periods
    
    Args:
        period: 'today', '1d', '3d', '1w', '2w', '1m', '3m', or 'ytd'
    
    Returns:
        Tuple of (start_date, end_date)
    """
    now = _now_utc()
    end_date = now
    
    if period in ['today', '1d']:
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == '3d':
        start_date = now - timedelta(days=3)
    elif period == '1w':
        start_date = now - timedelta(weeks=1)
    elif period == '2w':
        start_date = now - timedelta(weeks=2)
    elif period == '1m':
        start_date = now - timedelta(days=30)
    elif period == '3m':
        start_date = now - timedelta(days=90)
    elif period == 'ytd':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        # Default to 1 week
        start_date = now - timedelta(weeks=1)
    
    return start_date, end_date

def filter_by_date_range(df: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """Filter DataFrame by date range"""
    if df.empty:
        return df
    
    # Ensure the index is timezone-aware
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    elif df.index.tz != timezone.utc:
        df.index = df.index.tz_convert('UTC')
    
    # Ensure start and end dates are timezone-aware
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    
    return df[(df.index >= start_date) & (df.index <= end_date)]

# ===========================
#  Stock Screener
# ===========================

def screen_stocks(
    min_market_cap: float = 10_000_000_000,
    max_rsi: float = 40.0,
    min_daily_drop: float = 5.0,
    max_results: int = 50,
    include_analysis: bool = False,
    period: str = '1w',
    min_volume: Optional[int] = None,
    sectors: Optional[List[str]] = None,
    use_dynamic_sp500: bool = True,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Screen stocks for bull put credit spread opportunities
    
    Args:
        min_market_cap: Minimum market cap in USD
        max_rsi: Maximum RSI (oversold threshold)
        min_daily_drop: Minimum daily drop percentage (positive number)
        max_results: Maximum number of results to return
        include_analysis: Whether to include full analysis for each stock
        period: Time period to look for drops ('today', '1d', '3d', '1w', '2w', '1m', '3m', 'ytd')
        min_volume: Minimum daily volume filter
        sectors: List of sectors to include (if None, include all)
        use_dynamic_sp500: Whether to use dynamic S&P 500 list or static fallback
        force_refresh: Force refresh of cached data
    
    Returns:
        Dict with screener results
    """
    # Create cache key for this specific screening request
    cache_params = {
        'min_market_cap': min_market_cap,
        'max_rsi': max_rsi,
        'min_daily_drop': min_daily_drop,
        'period': period,
        'min_volume': min_volume,
        'sectors': sectors,
        'date': datetime.now().date().isoformat()  # Include date so cache refreshes daily
    }
    cache_key = f"screening_{hashlib.md5(str(cache_params).encode()).hexdigest()}"
    
    # Try to get from cache first (unless forced refresh)
    if not force_refresh:
        cached_results = _get_cached_data(cache_key, SCREEN_CACHE_HOURS)
        if cached_results:
            logger.info("Returning cached screening results")
            return cached_results
    
    results = []
    total_checked = 0
    start_date, end_date = get_date_range(period)
    
    # Get stock symbols to screen
    if use_dynamic_sp500:
        logger.info("Getting dynamic S&P 500 symbol list...")
        all_symbols = get_sp500_symbols()
        # Get batch based on API tier
        symbols_to_screen = get_screening_batch(all_symbols, max_results)
    else:
        logger.info("Using static large-cap symbol list...")
        symbols_to_screen = LARGE_CAP_TICKERS[:max_results]  # Limit to max_results
    
    logger.info(f"Starting stock screen: RSI<{max_rsi}, Drop>{min_daily_drop}%, Period:{period}")
    logger.info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    logger.info(f"Screening {len(symbols_to_screen)} stocks (API tier: {API_TIER.upper()})")
    
    # Progress tracking for large screens
    start_time = time.time()
    api_calls_made = 0
    
    for ticker in symbols_to_screen:
        if len(results) >= max_results:
            break
            
        try:
            total_checked += 1
            api_calls_made += 1
            
            # Progress logging for large batches
            if total_checked % 25 == 0 or total_checked == len(symbols_to_screen):
                elapsed = time.time() - start_time
                rate = api_calls_made / (elapsed / 60) if elapsed > 0 else 0
                logger.info(f"Progress: {total_checked}/{len(symbols_to_screen)} stocks ({rate:.1f} calls/min) - {len(results)} matches found")
            
            # Get stock data (need more data for RSI calculation)
            df = _alpha_vantage_history(ticker, days=90)
            if df is None or df.empty:
                logger.warning(f"No data for {ticker}")
                # Still respect rate limits even on failures
                time.sleep(DELAY_BETWEEN_CALLS)
                continue
            
            # Filter data to the specified period
            period_df = filter_by_date_range(df, start_date, end_date)
            if period_df.empty:
                logger.warning(f"No data in period for {ticker}")
                time.sleep(DELAY_BETWEEN_CALLS)
                continue
            
            # Get current metrics (most recent data)
            current_price = df['Close'].iloc[-1]
            current_volume = df['Volume'].iloc[-1] if 'Volume' in df.columns else None
            
            # Calculate RSI using full dataset (need 14+ days)
            try:
                current_rsi = calculate_rsi(df['Close'])
                if current_rsi is None:
                    current_rsi = 50  # Default neutral RSI if calculation fails
            except Exception as e:
                logger.warning(f"RSI calculation failed for {ticker}: {e}")
                current_rsi = 50
            
            # Find the biggest drop in the specified period
            if len(period_df) < 2:
                # If only one day of data, compare to previous day
                if len(df) >= 2:
                    period_start_price = df['Close'].iloc[-2]
                    daily_change_pct = ((current_price - period_start_price) / period_start_price) * 100
                else:
                    time.sleep(DELAY_BETWEEN_CALLS)
                    continue
            else:
                # Find the highest price in the period and calculate drop from there
                period_high = period_df['High'].max()
                period_low = period_df['Low'].min()
                
                # Calculate the biggest single-day drop in the period
                daily_returns = period_df['Close'].pct_change().dropna()
                biggest_daily_drop = daily_returns.min() * 100 if not daily_returns.empty else 0
                
                # Calculate drop from period high to current
                drop_from_high = ((current_price - period_high) / period_high) * 100
                
                # Use the more significant drop
                daily_change_pct = min(biggest_daily_drop, drop_from_high)
            
            # Apply filters
            # 1. Daily drop filter (negative change means drop)
            if daily_change_pct > -min_daily_drop:
                time.sleep(DELAY_BETWEEN_CALLS)
                continue
                
            # 2. RSI filter  
            if current_rsi > max_rsi:
                time.sleep(DELAY_BETWEEN_CALLS)
                continue
            
            # 3. Volume filter
            if min_volume and current_volume and current_volume < min_volume:
                time.sleep(DELAY_BETWEEN_CALLS)
                continue
            
            # Note: Sector filtering would require additional API calls
            # Market cap filtering uses pre-filtered symbols
            
            # Create result
            result = {
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "daily_change_pct": round(daily_change_pct, 2),
                "rsi": round(current_rsi, 1),
                "volume": int(current_volume) if current_volume else None,
                "period_analyzed": period,
                "drop_period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "company_name": None,  # Would need additional API call
                "market_cap": None,    # Would need additional API call  
                "sector": None,        # Would need additional API call
            }
            
            # Add full analysis if requested
            if include_analysis:
                try:
                    # This would call our existing analyze_ticker function
                    # but we'll skip it for now to avoid rate limiting
                    result["quick_analysis"] = {
                        "note": "Full analysis available via /check-dip endpoint"
                    }
                except Exception as e:
                    logger.warning(f"Analysis failed for {ticker}: {e}")
                    result["quick_analysis"] = {"error": str(e)}
            
            results.append(result)
            logger.info(f"✅ {ticker}: ${current_price} ({daily_change_pct:.1f}%, RSI:{current_rsi:.1f})")
            
            # Respect rate limits
            time.sleep(DELAY_BETWEEN_CALLS)
            
        except Exception as e:
            logger.warning(f"Error screening {ticker}: {e}")
            # Still respect rate limits even on errors
            time.sleep(DELAY_BETWEEN_CALLS)
            continue
    
    # Final progress report
    total_time = time.time() - start_time
    avg_rate = api_calls_made / (total_time / 60) if total_time > 0 else 0
    logger.info(f"Screening complete: {len(results)} matches from {total_checked} stocks in {total_time:.1f}s (avg: {avg_rate:.1f} calls/min)")
    
    # Sort results by daily drop (biggest drops first)
    results.sort(key=lambda x: x['daily_change_pct'])
    
    screening_results = {
        "total_found": len(results),
        "total_checked": total_checked,
        "performance": {
            "total_time_seconds": round(total_time, 1),
            "api_calls_made": api_calls_made,
            "average_calls_per_minute": round(avg_rate, 1),
            "api_tier": API_TIER.upper()
        },
        "batch_info": {
            "using_dynamic_sp500": use_dynamic_sp500,
            "daily_api_limit": DAILY_API_LIMIT,
            "max_stocks_per_screen": MAX_STOCKS_PER_SCREEN,
            "symbols_screened_today": list(symbols_to_screen)
        },
        "filters_applied": {
            "min_market_cap": min_market_cap,
            "max_rsi": max_rsi,
            "min_daily_drop": min_daily_drop,
            "max_results": max_results,
            "period": period,
            "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            "min_volume": min_volume,
            "sectors": sectors
        },
        "results": results,
        "scan_timestamp": _now_utc().isoformat(),
        "data_source": "Alpha Vantage Premium" if API_TIER == "premium" else "Alpha Vantage Free"
    }
    
    # Cache the results
    _set_cached_data(cache_key, screening_results)
    
    return screening_results 

# ===========================
#  Async Streaming Screener
# ===========================

async def stream_screen_stocks(
    min_market_cap: float = 10_000_000_000,
    max_rsi: float = 40.0,
    min_daily_drop: float = 5.0,
    max_results: int = 50,
    include_analysis: bool = False,
    period: str = '1w',
    min_volume: Optional[int] = None,
    sectors: Optional[List[str]] = None,
    force_refresh: bool = False,
    batch_size: int = 10
):
    """
    Stream screening results in batches for real-time UI updates
    
    Yields chunks with:
    - type: "progress", "result", "batch_complete", "complete"
    - data: relevant information for each type
    """
    
    # Get symbols to screen
    all_symbols = get_sp500_symbols()
    symbols_to_screen = get_screening_batch(all_symbols, max_results)
    
    # Initial progress chunk
    yield {
        "type": "start",
        "total_symbols": len(symbols_to_screen),
        "filters": {
            "max_rsi": max_rsi,
            "min_daily_drop": min_daily_drop,
            "period": period
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    results = []
    total_checked = 0
    start_time = time.time()
    
    # Process in batches
    for i in range(0, len(symbols_to_screen), batch_size):
        batch = symbols_to_screen[i:i + batch_size]
        batch_results = []
        
        for ticker in batch:
            if len(results) >= max_results:
                break
                
            try:
                total_checked += 1
                
                # Screen individual stock
                result = await screen_single_stock(
                    ticker, max_rsi, min_daily_drop, period, min_volume
                )
                
                if result:
                    results.append(result)
                    batch_results.append(result)
                    
                    # Yield individual result immediately
                    yield {
                        "type": "result",
                        "stock": result,
                        "progress": {
                            "checked": total_checked,
                            "total": len(symbols_to_screen),
                            "found": len(results)
                        },
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
                # Small delay to respect rate limits
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.warning(f"Error screening {ticker}: {e}")
                continue
        
        # Yield batch completion
        yield {
            "type": "batch_complete",
            "batch_number": (i // batch_size) + 1,
            "batch_results": len(batch_results),
            "progress": {
                "checked": total_checked,
                "total": len(symbols_to_screen),
                "found": len(results)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if len(results) >= max_results:
            break
    
    # Final completion
    total_time = time.time() - start_time
    yield {
        "type": "complete",
        "summary": {
            "total_found": len(results),
            "total_checked": total_checked,
            "time_seconds": round(total_time, 1),
            "results": results
        },
        "timestamp": datetime.utcnow().isoformat()
    }

async def screen_single_stock(
    ticker: str, 
    max_rsi: float, 
    min_daily_drop: float, 
    period: str, 
    min_volume: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Screen a single stock asynchronously with improved filtering logic
    """
    try:
        # Get stock data
        df = _alpha_vantage_history(ticker, days=90)
        if df is None or df.empty or len(df) < 2:
            return None
        
        # Get current metrics
        current_price = df['Close'].iloc[-1]
        previous_price = df['Close'].iloc[-2]
        current_volume = df['Volume'].iloc[-1] if 'Volume' in df.columns else None
        
        # Calculate RSI
        current_rsi = calculate_rsi(df['Close'])
        if current_rsi is None:
            current_rsi = 50
        
        # Improved drop calculation based on period
        daily_change_pct = calculate_period_drop(df, period)
        
        # Apply filters with more realistic thresholds
        # 1. RSI filter (oversold)
        if current_rsi > max_rsi:
            return None
            
        # 2. Drop filter (more flexible calculation)
        if daily_change_pct > -min_daily_drop:
            return None
        
        # 3. Volume filter
        if min_volume and current_volume and current_volume < min_volume:
            return None
        
        # Get company overview data for market cap
        market_cap = _get_market_cap(ticker)
        
        # Create result
        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "daily_change_pct": round(daily_change_pct, 2),
            "rsi": round(current_rsi, 1),
            "volume": int(current_volume) if current_volume else None,
            "market_cap": market_cap,
            "market_cap_billions": round(market_cap / 1_000_000_000, 2) if market_cap else None,
            "period_analyzed": period,
            "previous_price": round(previous_price, 2)
        }
        
    except Exception as e:
        logger.warning(f"Error screening {ticker}: {e}")
        return None

def calculate_period_drop(df: pd.DataFrame, period: str) -> float:
    """
    Calculate the biggest drop in the specified period with improved logic
    """
    if df.empty or len(df) < 2:
        return 0.0
    
    current_price = df['Close'].iloc[-1]
    
    # Determine lookback based on period
    if period in ['today', '1d']:
        lookback_days = 1
    elif period == '3d':
        lookback_days = 3
    elif period == '1w':
        lookback_days = 7
    elif period == '2w':
        lookback_days = 14
    elif period == '1m':
        lookback_days = 30
    else:
        lookback_days = 7  # Default to 1 week
    
    # Get the period data (last N trading days)
    period_data = df.tail(min(lookback_days + 1, len(df)))
    
    if len(period_data) < 2:
        # Fallback: simple day-over-day change
        previous_price = df['Close'].iloc[-2]
        return ((current_price - previous_price) / previous_price) * 100
    
    # Method 1: Drop from period high
    period_high = period_data['High'].max()
    drop_from_high = ((current_price - period_high) / period_high) * 100
    
    # Method 2: Biggest single-day drop in period
    daily_returns = period_data['Close'].pct_change().dropna()
    biggest_daily_drop = daily_returns.min() * 100 if not daily_returns.empty else 0
    
    # Method 3: Drop from period start
    period_start = period_data['Close'].iloc[0]
    drop_from_start = ((current_price - period_start) / period_start) * 100
    
    # Return the most significant drop
    return min(drop_from_high, biggest_daily_drop, drop_from_start)

async def quick_screen_stocks(
    min_market_cap: float = 10_000_000_000,
    max_rsi: float = 40.0,
    min_daily_drop: float = 3.0,  # More lenient
    max_results: int = 50,
    period: str = '1w',
    min_volume: Optional[int] = None,
    sectors: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Quick screening with more lenient filters to find matches faster
    """
    # Use a smaller, high-quality subset for quick results
    quick_symbols = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX", "AMD", "INTC",
        "JPM", "BAC", "WFC", "C", "GS", "MS", "V", "MA", "PYPL", "ADBE",
        "JNJ", "PFE", "UNH", "ABBV", "LLY", "MRK", "TMO", "ABT", "BMY", "GILD",
        "XOM", "CVX", "COP", "SLB", "EOG", "KMI", "OXY", "PSX", "VLO", "MPC",
        "HD", "LOW", "NKE", "SBUX", "MCD", "DIS", "CMCSA", "VZ", "T", "NFLX"
    ]
    
    results = []
    total_checked = 0
    start_time = time.time()
    
    logger.info(f"Quick screening {len(quick_symbols)} high-cap stocks with relaxed filters")
    
    for ticker in quick_symbols[:max_results]:
        try:
            total_checked += 1
            
            result = await screen_single_stock(
                ticker, max_rsi + 10, min_daily_drop - 1, period, min_volume  # More lenient
            )
            
            if result:
                results.append(result)
                logger.info(f"✅ Quick match: {ticker} ({result['daily_change_pct']:.1f}%, RSI:{result['rsi']:.1f})")
            
            await asyncio.sleep(0.1)  # Light rate limiting
            
        except Exception as e:
            logger.warning(f"Error in quick screen for {ticker}: {e}")
            continue
    
    total_time = time.time() - start_time
    
    return {
        "total_found": len(results),
        "total_checked": total_checked,
        "performance": {
            "total_time_seconds": round(total_time, 1),
            "screening_type": "quick"
        },
        "filters_applied": {
            "max_rsi": max_rsi + 10,  # Show actual relaxed filters
            "min_daily_drop": min_daily_drop - 1,
            "period": period
        },
        "results": results,
        "scan_timestamp": datetime.utcnow().isoformat(),
        "data_source": "Alpha Vantage Premium (Quick Screen)"
    } 

def _get_market_cap(ticker: str) -> Optional[float]:
    """
    Get market cap for a ticker using Alpha Vantage Company Overview
    """
    try:
        import requests
        import time
        
        # Check cache first
        cache_key = f"market_cap_{ticker}"
        cached_data = _get_cached_data(cache_key, 24)  # Cache for 24 hours
        if cached_data:
            return cached_data
        
        # Call Alpha Vantage Company Overview API
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "OVERVIEW",
            "symbol": ticker,
            "apikey": ALPHA_VANTAGE_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        # Rate limiting
        time.sleep(DELAY_BETWEEN_CALLS)
        
        # Parse market cap
        market_cap = data.get("MarketCapitalization")
        if market_cap and market_cap != "None":
            market_cap_float = float(market_cap)
            
            # Cache the result
            _set_cached_data(cache_key, market_cap_float)
            
            return market_cap_float
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to get market cap for {ticker}: {e}")
        return None 