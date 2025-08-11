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
    tooltips: Dict[str, Any]

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
