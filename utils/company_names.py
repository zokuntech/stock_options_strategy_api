"""
Utility module for retrieving company names from ticker symbols.
Includes caching to minimize API calls.
"""
import logging
import time
import yfinance as yf
from typing import Dict, Optional
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# In-memory cache for company names
_COMPANY_NAME_CACHE = {}
_CACHE_TTL = 7 * 24 * 60 * 60  # 7 days in seconds

# File cache path for persistence
CACHE_FILE = Path(__file__).parent.parent / "data" / "company_names_cache.json"

def _load_cache() -> None:
    """Load company names cache from file if it exists."""
    global _COMPANY_NAME_CACHE
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
                _COMPANY_NAME_CACHE = cache_data.get("names", {})
                logger.info(f"Loaded {len(_COMPANY_NAME_CACHE)} company names from cache")
    except Exception as e:
        logger.warning(f"Failed to load company names cache: {e}")
        _COMPANY_NAME_CACHE = {}

def _save_cache() -> None:
    """Save company names cache to file."""
    try:
        # Ensure data directory exists
        os.makedirs(CACHE_FILE.parent, exist_ok=True)
        
        cache_data = {
            "last_updated": time.time(),
            "names": _COMPANY_NAME_CACHE
        }
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
            
        logger.debug(f"Saved {len(_COMPANY_NAME_CACHE)} company names to cache")
    except Exception as e:
        logger.warning(f"Failed to save company names cache: {e}")

def _is_cache_valid(timestamp: float) -> bool:
    """Check if cached data is still valid."""
    return time.time() - timestamp < _CACHE_TTL

def get_company_name(ticker: str) -> Optional[str]:
    """
    Get company name for a given ticker symbol.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
        
    Returns:
        Company name if found, None otherwise
    """
    ticker = ticker.upper().strip()
    
    # Check in-memory cache first
    if ticker in _COMPANY_NAME_CACHE:
        cached_data = _COMPANY_NAME_CACHE[ticker]
        if isinstance(cached_data, dict) and _is_cache_valid(cached_data.get("timestamp", 0)):
            return cached_data.get("name")
        elif isinstance(cached_data, str):  # Legacy cache format
            return cached_data
    
    # Try to fetch from yfinance
    try:
        logger.debug(f"Fetching company name for {ticker}")
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Try different fields for company name
        company_name = (
            info.get('longName') or 
            info.get('shortName') or 
            info.get('displayName') or
            info.get('companyName')
        )
        
        if company_name:
            # Cache the result with timestamp
            _COMPANY_NAME_CACHE[ticker] = {
                "name": company_name,
                "timestamp": time.time()
            }
            
            # Save to file cache periodically (every 10 new entries)
            if len(_COMPANY_NAME_CACHE) % 10 == 0:
                _save_cache()
                
            logger.debug(f"Found company name for {ticker}: {company_name}")
            return company_name
        else:
            logger.warning(f"No company name found for {ticker}")
            return None
            
    except Exception as e:
        logger.warning(f"Error fetching company name for {ticker}: {e}")
        return None

def get_company_names_batch(tickers: list) -> Dict[str, Optional[str]]:
    """
    Get company names for multiple tickers efficiently.
    
    Args:
        tickers: List of ticker symbols
        
    Returns:
        Dictionary mapping ticker to company name
    """
    results = {}
    
    for ticker in tickers:
        results[ticker] = get_company_name(ticker)
        
        # Small delay to avoid rate limiting
        time.sleep(0.1)
    
    # Save cache after batch operation
    _save_cache()
    
    return results

def preload_sp500_companies():
    """
    Preload company names for S&P 500 companies.
    This can be run periodically to warm the cache.
    """
    try:
        # Load S&P 500 tickers
        sp500_file = Path(__file__).parent.parent / "data" / "sp500_companies.json"
        if sp500_file.exists():
            with open(sp500_file, 'r') as f:
                data = json.load(f)
                tickers = data.get("companies", [])
                
            logger.info(f"Preloading company names for {len(tickers)} S&P 500 companies")
            get_company_names_batch(tickers)
            logger.info("S&P 500 company names preload complete")
        else:
            logger.warning("S&P 500 companies file not found")
    except Exception as e:
        logger.error(f"Error preloading S&P 500 company names: {e}")

# Initialize cache on import
_load_cache()

# Manual mappings for common tickers that might have issues
MANUAL_MAPPINGS = {
    "BRK.B": "Berkshire Hathaway Inc.",
    "BF.B": "Brown-Forman Corporation",
    "GOOGL": "Alphabet Inc.",
    "GOOG": "Alphabet Inc.", 
    "META": "Meta Platforms, Inc.",
    "TSLA": "Tesla, Inc."
}

def get_company_name_with_fallback(ticker: str) -> str:
    """
    Get company name with manual fallback for problematic tickers.
    Always returns a string (falls back to ticker if no name found).
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Company name or ticker symbol as fallback
    """
    ticker = ticker.upper().strip()
    
    # Check manual mappings first
    if ticker in MANUAL_MAPPINGS:
        return MANUAL_MAPPINGS[ticker]
    
    # Try to get from our main function
    company_name = get_company_name(ticker)
    
    # Return company name if found, otherwise return ticker
    return company_name if company_name else ticker
