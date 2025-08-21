from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class TickerRequest(BaseModel):
    ticker: str
    include_ai_analysis: Optional[bool] = True

class TickerResponse(BaseModel):
    ticker: str
    play: bool
    tier: str  # A, B, C, or PASS
    metrics: Dict[str, Any]
    reason: str
    confidence_score: float
    confidence_source: Optional[str] = None
    estimated_credit: Optional[float] = None
    ai_analysis: Optional[Dict[str, Any]] = None

class HistoryAnalysisResponse(BaseModel):
    analysis_date: str
    total_analyzed_trades: int
    overall_win_rate: str
    tier_performance: Dict
    winner_profile: Optional[Dict]
    loser_profile: Optional[Dict]
    api_signal_performance: Dict
    key_insights: List[str]
    recommendations: List[str]
    detailed_trades_count: int

class WinnerAnalysisResponse(BaseModel):
    analysis_date: str
    total_trades: int
    winners: int
    losers: int
    win_rate: float
    profit_factor: float
    total_profit: float
    total_loss: float
    avg_win_amount: float
    avg_loss_amount: float
    avg_win_return: float
    avg_loss_return: float
    largest_win: float
    largest_loss: float
    risk_reward_ratio: float
    expectancy: float
    equity_curve: Dict
    metric_comparison: Dict
    credit_analysis: Dict
    rsi_analysis: Dict
    key_insights: List[str]
    recommendations: List[str]
    data_quality: str

class ScreenerRequest(BaseModel):
    min_market_cap: float = 10_000_000_000  # $10B default
    max_rsi: float = 40.0  # RSI below 40
    min_daily_drop: float = 5.0  # Down 5% or more
    max_results: int = 50  # Limit results
    include_analysis: bool = False  # Whether to run full analysis on each
    period: str = "1w"  # Time period: 'today', '1d', '3d', '1w', '2w', '1m', '3m', 'ytd'
    min_volume: Optional[int] = None  # Minimum daily volume
    sectors: Optional[List[str]] = None  # Sector filter (future use)
    force_refresh: bool = False  # Force refresh of cached data

class ScreenerResult(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    market_cap: Optional[float] = None  # Market cap in dollars
    market_cap_billions: Optional[float] = None  # Market cap in billions for display
    current_price: float
    daily_change_pct: float
    rsi: Optional[float] = None
    volume: Optional[int] = None
    sector: Optional[str] = None
    period_analyzed: str
    drop_period: Optional[str] = None  # Deprecated, use period_analyzed
    quick_analysis: Optional[str] = None
    previous_price: Optional[float] = None

class ScreenerResponse(BaseModel):
    total_found: int
    filters_applied: Dict[str, Any]
    results: List[ScreenerResult]
    scan_timestamp: str
    data_source: str = "Alpha Vantage"
