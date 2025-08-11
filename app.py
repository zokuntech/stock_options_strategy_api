from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import yfinance as yf
import pandas as pd
import numpy as np
import pytz

# Import our custom modules
from utils.models import TickerRequest, TickerResponse, HistoryAnalysisResponse, WinnerAnalysisResponse
from utils.indicators import get_real_time_rsi, calculate_rsi, get_vix_data, get_market_context
from utils.options import estimate_bull_put_credit

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Bull Put Credit Spread API",
    description="Enhanced API for analyzing bull put credit spread opportunities with after-hours support",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def analyze_ticker(ticker: str) -> Dict[str, Any]:
    """
    Analyze a ticker for bull put spread opportunities with after-hours support
    """
    try:
        stock = yf.Ticker(ticker)
        
        # Get extended market data (includes pre-market and after-hours)
        hist_data = stock.history(period="60d", interval="1d", prepost=True)
        
        if hist_data.empty:
            return {"error": f"No data available for {ticker}"}
        
        # Get current/latest price (includes after-hours if available)
        current_info = stock.info
        current_price = None
        price_source = "Regular Hours"
        
        # Try to get the most recent price (could be after-hours)
        try:
            # Get intraday data to check for after-hours pricing
            intraday_data = stock.history(period="1d", interval="1m", prepost=True)
            if not intraday_data.empty:
                latest_price = intraday_data['Close'].iloc[-1]
                latest_time = intraday_data.index[-1]
                
                # Check if this is after-hours data
                market_tz = pytz.timezone('America/New_York')
                latest_time_et = latest_time.tz_convert(market_tz) if latest_time.tz else latest_time.replace(tzinfo=market_tz)
                
                # Market hours: 9:30 AM - 4:00 PM ET
                market_open = latest_time_et.replace(hour=9, minute=30, second=0, microsecond=0)
                market_close = latest_time_et.replace(hour=16, minute=0, second=0, microsecond=0)
                
                if latest_time_et < market_open:
                    price_source = "Pre-Market"
                elif latest_time_et > market_close:
                    price_source = "After-Hours"
                else:
                    price_source = "Regular Hours"
                
                current_price = float(latest_price)
            else:
                # Fallback to daily close
                current_price = float(hist_data['Close'].iloc[-1])
        except:
            # Final fallback to regular market data
            if 'regularMarketPrice' in current_info:
                current_price = current_info['regularMarketPrice']
            elif 'currentPrice' in current_info:
                current_price = current_info['currentPrice']
            else:
                current_price = float(hist_data['Close'].iloc[-1])
        
        # Get after-hours change if available
        after_hours_change = 0.0
        after_hours_change_pct = 0.0
        
        try:
            regular_close = float(hist_data['Close'].iloc[-1])
            if price_source in ["Pre-Market", "After-Hours"] and current_price != regular_close:
                after_hours_change = current_price - regular_close
                after_hours_change_pct = (after_hours_change / regular_close) * 100
        except:
            pass
        
        # Calculate metrics using the regular session data for consistency
        closes = hist_data['Close'].values
        
        # RSI calculation - use real-time intraday RSI for more accurate readings
        current_rsi = get_real_time_rsi(ticker)
        if current_rsi is None:
            # Fallback to daily RSI if real-time fails
            current_rsi = calculate_rsi(closes)
        
        # Calculate recent drops and metrics
        previous_close = float(hist_data['Close'].iloc[-2]) if len(hist_data) > 1 else current_price
        regular_close = float(hist_data['Close'].iloc[-1])  # Use regular session close for calculations
        
        # Use regular session close for drop calculations (more consistent)
        analysis_price = regular_close
        current_return = ((analysis_price - previous_close) / previous_close) * 100
        
        # Rolling drops - use DataFrame operations properly
        rolling_5d_high = float(hist_data['Close'].rolling(window=5).max().iloc[-1])
        rolling_5d_drop = ((analysis_price - rolling_5d_high) / rolling_5d_high) * 100
        
        rolling_10d_high = float(hist_data['Close'].rolling(window=10).max().iloc[-1])
        rolling_10d_drop = ((analysis_price - rolling_10d_high) / rolling_10d_high) * 100
        
        # Max recent drop (largest single-day drop in last 30 days)
        recent_data = hist_data.tail(30)
        daily_returns = recent_data['Close'].pct_change().dropna()
        max_recent_drop = float(daily_returns.min()) * 100 if not daily_returns.empty else 0.0
        
        # Distance from recent low
        recent_low = float(hist_data['Low'].tail(10).min())
        distance_from_low = ((analysis_price - recent_low) / recent_low) * 100
        
        # Days oversold (RSI < 30) - calculate using historical data properly
        days_oversold = 0
        if len(hist_data) >= 14:  # Need at least 14 days for RSI
            # Calculate RSI for each of the last 10 days
            for i in range(min(10, len(hist_data) - 14)):
                end_idx = len(hist_data) - i
                rsi_data = hist_data['Close'].iloc[:end_idx].values
                rsi_val = calculate_rsi(rsi_data)
                
                if rsi_val and rsi_val < 30:
                    days_oversold += 1
                else:
                    break
        
        # 200-day moving average
        if len(hist_data) >= 200:
            ma200 = float(hist_data['Close'].rolling(window=200).mean().iloc[-1])
            price_vs_200ma = ((analysis_price - ma200) / ma200) * 100
        else:
            ma200 = None
            price_vs_200ma = None
        
        # Get market context (VIX, etc.)
        market_context = get_market_context()
        vix_level = market_context.get('vix_level') if market_context else None
        
        # Compile metrics (using regular session price for calculations, but include current price info)
        metrics = {
            'RSI': round(current_rsi, 1) if current_rsi else None,
            'VIX': round(vix_level, 1) if vix_level else None,
            'percent_drop': round(current_return, 1),
            'rolling_5d_drop': round(rolling_5d_drop, 1),
            'rolling_10d_drop': round(rolling_10d_drop, 1),
            'max_recent_drop': round(max_recent_drop, 1),
            'days_oversold': days_oversold,
            'distance_from_low': round(distance_from_low, 1),
            'price_vs_200ma': f"{price_vs_200ma:.1f}%" if price_vs_200ma is not None else None,
            'current_price': round(current_price, 2),
            'regular_close': round(regular_close, 2) if price_source in ["Pre-Market", "After-Hours"] else None,
            'price_source': price_source,
            'after_hours_change': round(after_hours_change, 2) if price_source in ["Pre-Market", "After-Hours"] else None,
            'after_hours_change_pct': round(after_hours_change_pct, 1) if price_source in ["Pre-Market", "After-Hours"] else None,
            'ma200': round(ma200, 2) if ma200 is not None else None
        }
        
        return metrics
        
    except Exception as e:
        logger.error(f"Error analyzing {ticker}: {e}")
        return {"error": f"Error analyzing {ticker}: {str(e)}"}

def evaluate_strategy(metrics: Dict[str, Any]) -> tuple[bool, str, float]:
    """Enhanced strategy evaluation with detailed scoring"""
    
    # Extract metrics with None checking
    current_rsi = metrics.get('RSI')
    vix_level = metrics.get('VIX', 20)  # Default to moderate VIX if unavailable
    current_return = metrics.get('percent_drop', 0)
    rolling_5d_drop = metrics.get('rolling_5d_drop', 0)
    rolling_10d_drop = metrics.get('rolling_10d_drop', 0)
    max_recent_drop = metrics.get('max_recent_drop', 0)
    days_oversold = metrics.get('days_oversold', 0)
    distance_from_low = metrics.get('distance_from_low', 100)
    price_vs_200ma = metrics.get('price_vs_200ma')
    
    # Initialize scoring
    score = 0.0
    reasons = []
    signal_strength = []
    
    # Quality indicators for detailed feedback
    rsi_quality = "poor"
    vix_quality = "poor"
    drop_quality = "minimal"
    low_quality = "poor"
    trend_quality = "unknown"
    
    # 1. RSI SCORING (Enhanced - up to 0.35 points)
    rsi_signal = False
    if current_rsi is not None:
        if current_rsi <= 20:
            score += 0.35
            rsi_signal = True
            reasons.append(f"Extreme oversold RSI ({current_rsi:.1f})")
            signal_strength.append("extreme oversold")
            rsi_quality = "excellent"
        elif current_rsi <= 25:
            score += 0.3
            rsi_signal = True
            reasons.append(f"Strong oversold RSI ({current_rsi:.1f})")
            signal_strength.append("strong oversold")
            rsi_quality = "excellent"
        elif current_rsi <= 30:
            score += 0.25
            rsi_signal = True
            reasons.append(f"Oversold RSI ({current_rsi:.1f})")
            signal_strength.append("oversold")
            rsi_quality = "strong"
        elif current_rsi <= 35:
            score += 0.15
            reasons.append(f"Near oversold RSI ({current_rsi:.1f})")
            rsi_quality = "moderate"
        elif current_rsi <= 40:
            score += 0.05
            reasons.append(f"Weak RSI ({current_rsi:.1f})")
            rsi_quality = "fair"
        else:
            reasons.append(f"RSI not oversold ({current_rsi:.1f})")
            rsi_quality = "poor"
    else:
        reasons.append("RSI unavailable")
        rsi_quality = "unknown"
    
    # 2. VIX SCORING (Market fear component - up to 0.3 points)
    if vix_level >= 25:
        score += 0.3
        reasons.append(f"High fear VIX ({vix_level:.1f})")
        signal_strength.append("high volatility")
        vix_quality = "excellent"
    elif vix_level >= 20:
        score += 0.25
        reasons.append(f"Elevated VIX ({vix_level:.1f})")
        vix_quality = "good"
    elif vix_level >= 18:
        score += 0.2
        reasons.append(f"Moderate VIX ({vix_level:.1f})")
        vix_quality = "moderate"
    elif vix_level >= 16:
        score += 0.1
        reasons.append(f"Low-moderate VIX ({vix_level:.1f})")
        vix_quality = "fair"
    else:
        score += 0.05
        reasons.append(f"Low VIX ({vix_level:.1f})")
        vix_quality = "poor"
    
    # 3. DROP MAGNITUDE SCORING (Enhanced - up to 0.3 points)
    drop_quality = "minimal"
    drop_signal = False
    
    # Check for major single-day drops
    if abs(current_return) >= 8:
        score += 0.3
        drop_signal = True
        reasons.append(f"Major single-day drop ({current_return:.1f}%)")
        signal_strength.append("major selloff")
        drop_quality = "excellent"
    elif abs(current_return) >= 5:
        score += 0.25
        drop_signal = True
        reasons.append(f"Significant daily drop ({current_return:.1f}%)")
        signal_strength.append("significant drop")
        drop_quality = "good"
    
    # Check for multi-day drops
    elif abs(rolling_5d_drop) >= 10:
        score += 0.28
        drop_signal = True
        reasons.append(f"Major 5-day decline ({rolling_5d_drop:.1f}%)")
        signal_strength.append("major multi-day drop")
        drop_quality = "excellent"
    elif abs(rolling_5d_drop) >= 7:
        score += 0.23
        drop_signal = True
        reasons.append(f"Strong 5-day decline ({rolling_5d_drop:.1f}%)")
        signal_strength.append("strong multi-day drop")
        drop_quality = "good"
    elif abs(rolling_5d_drop) >= 5:
        score += 0.18
        drop_signal = True
        reasons.append(f"Moderate 5-day decline ({rolling_5d_drop:.1f}%)")
        drop_quality = "moderate"
    
    # Check for recent sharp declines
    elif abs(max_recent_drop) >= 8:
        score += 0.2
        reasons.append(f"Recent major drop ({max_recent_drop:.1f}%)")
        drop_quality = "good"
    elif abs(max_recent_drop) >= 5:
        score += 0.15
        reasons.append(f"Recent significant drop ({max_recent_drop:.1f}%)")
        drop_quality = "moderate"
    else:
        reasons.append(f"Minimal recent drop ({max(abs(current_return), abs(rolling_5d_drop), abs(max_recent_drop)):.1f}%)")
        drop_quality = "minimal"
    
    # 4. DISTANCE FROM LOW SCORING (Timing component - up to 0.2 points)
    if distance_from_low <= 1:
        score += 0.2
        reasons.append(f"At recent low (+{distance_from_low:.1f}%)")
        signal_strength.append("perfect timing")
        low_quality = "excellent"
    elif distance_from_low <= 3:
        score += 0.18
        reasons.append(f"Very near low (+{distance_from_low:.1f}%)")
        signal_strength.append("excellent timing")
        low_quality = "very good"
    elif distance_from_low <= 5:
        score += 0.15
        reasons.append(f"Near recent low (+{distance_from_low:.1f}%)")
        low_quality = "good"
    elif distance_from_low <= 8:
        score += 0.1
        reasons.append(f"Moderate distance from low (+{distance_from_low:.1f}%)")
        low_quality = "moderate"
    else:
        reasons.append(f"Far from recent low (+{distance_from_low:.1f}%)")
        low_quality = "poor"
    
    # 5. TREND ANALYSIS (200MA component - up to 0.15 points)
    if price_vs_200ma is not None:
        price_vs_200ma_float = float(price_vs_200ma.replace('%', '')) if isinstance(price_vs_200ma, str) else price_vs_200ma
        
        if abs(price_vs_200ma_float) <= 5:
            score += 0.15
            reasons.append(f"Price near 200MA ({price_vs_200ma_float:+.1f}%)")
            trend_quality = "excellent"
        elif price_vs_200ma_float >= -10 and price_vs_200ma_float < 0:
            score += 0.12
            reasons.append(f"Price below 200MA ({price_vs_200ma_float:+.1f}%)")
            trend_quality = "good"
        elif price_vs_200ma_float >= -15:
            score += 0.08
            reasons.append(f"Price well below 200MA ({price_vs_200ma_float:+.1f}%)")
            trend_quality = "moderate"
        else:
            score += 0.02
            reasons.append(f"Price far below 200MA ({price_vs_200ma_float:+.1f}%)")
            trend_quality = "poor"
    else:
        reasons.append("200MA data unavailable")
        trend_quality = "unknown"
    
    # 6. OVERSOLD PERSISTENCE BONUS (up to 0.1 points)
    if days_oversold >= 3:
        score += 0.1
        reasons.append(f"Extended oversold ({days_oversold} days)")
        signal_strength.append("persistent oversold")
    elif days_oversold >= 2:
        score += 0.08
        reasons.append(f"Multi-day oversold ({days_oversold} days)")
    elif days_oversold >= 1:
        score += 0.05
        reasons.append(f"Recent oversold ({days_oversold} day)")
    
    # Determine if it's a PLAY or PASS
    is_play = score >= 0.6 and (rsi_signal or drop_signal)
    
    # Create detailed reason
    main_signals = signal_strength[:3] if signal_strength else ["weak setup"]
    signal_text = ", ".join(main_signals)
    
    if is_play:
        reason_text = f"✅ PLAY ({signal_text}): " + " | ".join(reasons[:6])
        reason_text += f" | Quality: RSI:{rsi_quality}, VIX:{vix_quality}, Drop:{drop_quality}, Low:{low_quality}, Trend:{trend_quality}"
    else:
        reason_text = f"❌ PASS: " + " | ".join(reasons[:6])
        
    return is_play, reason_text, min(score, 1.0)

def classify_tier(confidence_score: float, estimated_credit: Optional[float], 
                 current_rsi: Optional[float], vix_level: Optional[float], 
                 distance_from_low: float, is_play: bool) -> str:
    """Classify trade tier based on multiple factors"""
    
    if not is_play:
        return "PASS"
    
    # A-Tier: $100+ credit + strong setup
    if confidence_score >= 0.8 and estimated_credit and estimated_credit >= 100:
        return "A"
    
    # B-Tier: $80–99 credit + good setup
    elif confidence_score >= 0.7 and estimated_credit and 80 <= estimated_credit < 100:
        return "B"
    
    # C-Tier: < $80 credit but playable
    elif confidence_score >= 0.6:
        return "C"
    
    # Otherwise PASS
    return "PASS"

def get_field_tooltips() -> Dict[str, Any]:
    """Get comprehensive field descriptions and tooltips"""
    return {
        "RSI": {
            "description": "Relative Strength Index (14-day) - measures if stock is oversold",
            "ideal": "< 30 (oversold)",
            "strong_signal": "< 20 (extreme oversold)",
            "warning": "> 35 (already rebounding; entry riskier)",
            "emoji": "🎯"
        },
        "VIX": {
            "description": "Market fear gauge - volatility index (same for all stocks as it measures overall market sentiment)",
            "ideal": "> 20 (panic conditions = better rebounds)",
            "neutral": "17–20 (okay but not tailwind)",
            "warning": "< 17 (calm market = stock-level oversold must be strong)",
            "emoji": "🚀"
        },
        "percent_drop": {
            "description": "Today's price change percentage (regular session)",
            "ideal": "-5% or more in 1 day",
            "neutral": "-2% to -5% (check multi-day instead)",
            "warning": "Positive or small drop (no fresh selloff)",
            "emoji": "⚡"
        },
        "rolling_5d_drop": {
            "description": "Price decline from highest close in last 5 days to current price",
            "ideal": "-7% or more over 5 days",
            "strong_signal": "-10%+ (deep multi-day capitulation)",
            "warning": "Less than -5% (no real decline)",
            "emoji": "⚡"
        },
        "max_recent_drop": {
            "description": "Largest single-day drop in the last 30 days",
            "ideal": "-10% or deeper within 30 days",
            "neutral": "-5% to -10% (moderate pullback)",
            "warning": "Less than -5% (no significant event)",
            "emoji": "🔥"
        },
        "days_oversold": {
            "description": "Number of consecutive days RSI has been below 30",
            "ideal": "2+ consecutive days RSI < 30",
            "strong_signal": "4+ days oversold (capitulation)",
            "warning": "1 day oversold (weak confirmation)",
            "emoji": "🎯"
        },
        "distance_from_low": {
            "description": "How far current price is above the lowest close in last 10 days",
            "ideal": "0–3% above recent low (still hugging bottom)",
            "neutral": "3–5% above low (minor rebound started)",
            "warning": ">5% above low (late entry; wait for next dip)",
            "emoji": "🎯"
        },
        "price_vs_200ma": {
            "description": "Current price relative to 200-day moving average",
            "ideal": "±5% of 200MA (healthy pullback)",
            "neutral": "5–10% below 200MA (watch for trend confirmation)",
            "warning": ">10% below 200MA (falling knife risk)",
            "emoji": "✅"
        },
        "current_price": {
            "description": "Latest available price (may include pre-market or after-hours data)",
            "note": "Check price_source field to see if this is regular, pre-market, or after-hours pricing",
            "emoji": "💰"
        },
        "regular_close": {
            "description": "Regular session closing price (shown when current_price is from pre-market or after-hours)",
            "note": "Analysis is based on regular session data for consistency",
            "emoji": "📊"
        },
        "price_source": {
            "description": "Indicates whether current_price is from regular hours, pre-market, or after-hours trading",
            "values": {
                "Regular Hours": "Price is from normal trading session (9:30 AM - 4:00 PM ET)",
                "Pre-Market": "Price is from pre-market trading (before 9:30 AM ET)",
                "After-Hours": "Price is from after-hours trading (after 4:00 PM ET)"
            },
            "emoji": "🕐"
        },
        "after_hours_change": {
            "description": "Dollar change from regular session close to current after-hours/pre-market price",
            "note": "Only shown when trading outside regular hours",
            "emoji": "🌙"
        },
        "after_hours_change_pct": {
            "description": "Percentage change from regular session close to current after-hours/pre-market price",
            "note": "Only shown when trading outside regular hours",
            "emoji": "🌙"
        },
        "ma200": {
            "description": "200-day moving average price - used to determine long-term trend",
            "emoji": "📈"
        },
        "confidence_score": {
            "description": "Enhanced algorithm confidence level for trade recommendation (0.0-1.0 scale)",
            "ideal": "≥ 0.85 (Exceptional Setup)",
            "neutral": "0.7 – 0.84 (Good Setup)",
            "warning": "< 0.7 (Avoid / Small Probe)",
            "emoji": "💪"
        },
        "estimated_credit": {
            "description": "Estimated credit received for 2.5-point bull put spread (30-day expiration, ~10% OTM strikes)",
            "ideal": "≥ $100 (High premium)",
            "neutral": "$80-99 (Moderate premium)",
            "warning": "< $80 (Low premium)",
            "note": "Based on regular session price for consistency",
            "emoji": "💵"
        },
        "tier": {
            "description": "Trade quality classification based on multiple criteria",
            "tiers": {
                "A": "🟢 Strongest setups - Full position size (up to 70% allocation)",
                "B": "🟡 Moderate setups - Half position size (~35% allocation)",
                "C": "🔴 Weak setups - Avoid or very small probe",
                "PASS": "⚫ Does not meet minimum criteria"
            },
            "emoji": "🏆"
        },
        "play": {
            "description": "Whether the stock qualifies for a bull put spread trade based on regular session analysis",
            "note": "After-hours movement doesn't change the fundamental analysis",
            "emoji": "🎯"
        },
        "reason": {
            "description": "Detailed explanation of why the stock is flagged as PLAY or PASS, including quality assessment",
            "emoji": "📝"
        },
        "ai_analysis": {
            "description": "AI-powered market analysis and trading insights",
            "emoji": "🤖"
        }
    }

@app.post("/check-dip", response_model=TickerResponse)
async def check_dip(request: TickerRequest):
    """Main endpoint for bull put spread analysis"""
    ticker = request.ticker.upper()
    
    try:
        # Analyze the ticker
        metrics = analyze_ticker(ticker)
        
        if "error" in metrics:
            raise HTTPException(status_code=400, detail=metrics["error"])
        
        # Evaluate strategy
        is_play, reason, confidence_score = evaluate_strategy(metrics)
        
        # Estimate credit for tier classification
        current_price = metrics.get('current_price', 100)
        vix_level = metrics.get('VIX', 20)
        estimated_credit = estimate_bull_put_credit(current_price, vix_level)
        
        # Classify tier
        tier = classify_tier(
            confidence_score=confidence_score,
            estimated_credit=estimated_credit,
            current_rsi=metrics.get('RSI'),
            vix_level=metrics.get('VIX'),
            distance_from_low=metrics.get('distance_from_low', 100),
            is_play=is_play
        )
        
        # Get tooltips
        tooltips = get_field_tooltips()
        
        # Create formatted response metrics
        response_metrics = {}
        for key, value in metrics.items():
            if value is not None:
                if isinstance(value, (int, float)):
                    # Round numeric values appropriately
                    if key in ['current_price', 'regular_close', 'ma200']:
                        response_metrics[key] = round(value, 2)
                    elif key in ['after_hours_change']:
                        response_metrics[key] = round(value, 2)
                    else:
                        response_metrics[key] = round(value, 1) if isinstance(value, float) else value
                else:
                    response_metrics[key] = value
            else:
                response_metrics[key] = value
        
        return TickerResponse(
            ticker=ticker,
            play=is_play,
            tier=tier,
            metrics=response_metrics,
            reason=reason,
            confidence_score=round(confidence_score, 2),
            confidence_source="algorithmic",
            estimated_credit=estimated_credit,
            ai_analysis=None,  # Simplified for now
            tooltips=tooltips
        )
        
    except Exception as e:
        logger.error(f"Error processing {ticker}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing {ticker}: {str(e)}")

@app.get("/tooltips")
async def get_tooltips():
    """Get field descriptions and tooltips"""
    return get_field_tooltips()

@app.get("/")
def read_root():
    """API root endpoint"""
    return {
        "message": "Bull Put Credit Spread Analysis API",
        "version": "2.0.0",
        "description": "Clean, modular API for analyzing bull put spread opportunities",
        "features": [
            "Real-time RSI calculation using intraday data",
            "After-hours price support",
            "Advanced tier classification (A/B/C/PASS)",
            "Market context integration (VIX, SPY trend)",
            "Modular codebase for easy maintenance"
        ],
        "endpoints": {
            "POST /check-dip": "Analyze a ticker for bull put spread opportunities",
            "GET /tooltips": "Get field descriptions and usage guidelines",
            "GET /": "This information page"
        },
        "examples": {
            "check_ticker": {
                "url": "/check-dip",
                "method": "POST",
                "body": {"ticker": "AAPL", "include_ai_analysis": true}
            }
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 