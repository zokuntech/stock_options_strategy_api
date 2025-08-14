from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
from typing import Optional, Dict, Any
import time
import hashlib

from utils.models import TickerRequest, TickerResponse, HistoryAnalysisResponse, WinnerAnalysisResponse
from utils.options import estimate_bull_put_credit
from utils.indicators import (
    get_daily_history,
    calculate_rsi,
    get_market_context,
)

import openai
import os
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple in-memory cache (5 minute TTL)
_CACHE = {}
_CACHE_TTL = 300  # 5 minutes

def _cache_key(ticker: str) -> str:
    return f"analysis_{ticker.upper()}"

def _get_cached(key: str) -> Optional[Dict[str, Any]]:
    if key in _CACHE:
        data, timestamp = _CACHE[key]
        if time.time() - timestamp < _CACHE_TTL:
            return data
        else:
            del _CACHE[key]
    return None

def _set_cache(key: str, data: Dict[str, Any]):
    _CACHE[key] = (data, time.time())

app = FastAPI(
    title="Bull Put Credit Spread API",
    description="API for analyzing bull put credit spread opportunities (Yahoo with Stooq fallback)",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

def analyze_ticker(ticker: str) -> Dict[str, Any]:
    # Check cache first
    cache_key = _cache_key(ticker)
    cached = _get_cached(cache_key)
    if cached:
        logger.info(f"Cache hit for {ticker}")
        return cached
    
    try:
        start_time = time.time()
        hist_data = get_daily_history(ticker, period="60d", interval="1d", prepost=True)
        fetch_time = time.time() - start_time
        logger.info(f"Data fetch for {ticker} took {fetch_time:.2f}s")
        
        if hist_data is None or hist_data.empty:
            return {"error": f"No data available for {ticker}"}

        current_price = float(hist_data["Close"].iloc[-1])
        previous_close = float(hist_data["Close"].iloc[-2]) if len(hist_data) > 1 else current_price
        analysis_price = current_price
        current_return = ((analysis_price - previous_close) / previous_close) * 100

        rolling_5d_high = float(hist_data["Close"].rolling(window=5).max().iloc[-1])
        rolling_5d_drop = ((analysis_price - rolling_5d_high) / rolling_5d_high) * 100

        rolling_10d_high = float(hist_data["Close"].rolling(window=10).max().iloc[-1])
        rolling_10d_drop = ((analysis_price - rolling_10d_high) / rolling_10d_high) * 100

        recent_data = hist_data.tail(30)
        daily_returns = recent_data["Close"].pct_change().dropna()
        max_recent_drop = float(daily_returns.min()) * 100 if not daily_returns.empty else 0.0

        recent_low = float(hist_data["Low"].tail(10).min())
        distance_from_low = ((analysis_price - recent_low) / recent_low) * 100

        current_rsi = calculate_rsi(hist_data["Close"].values, window=14)

        if len(hist_data) >= 200:
            ma200 = float(hist_data["Close"].rolling(window=200).mean().iloc[-1])
            price_vs_200ma = ((analysis_price - ma200) / ma200) * 100
        else:
            ma200, price_vs_200ma = None, None

        market_context = get_market_context()
        vix_level = market_context.get("vix_level") if market_context else None

        metrics = {
            "RSI": round(current_rsi, 1) if current_rsi is not None else None,
            "VIX": round(vix_level, 1) if vix_level is not None else None,
            "percent_drop": round(current_return, 1),
            "rolling_5d_drop": round(rolling_5d_drop, 1),
            "rolling_10d_drop": round(rolling_10d_drop, 1),
            "max_recent_drop": round(max_recent_drop, 1),
            "days_oversold": 0,
            "distance_from_low": round(distance_from_low, 1),
            "price_vs_200ma": f"{price_vs_200ma:.1f}%" if price_vs_200ma is not None else None,
            "current_price": round(current_price, 2),
            "ma200": round(ma200, 2) if ma200 is not None else None,
        }

        # Days oversold from daily RSI
        days_oversold = 0
        if len(hist_data) >= 14:
            for i in range(min(10, len(hist_data) - 14)):
                end_idx = len(hist_data) - i
                rsi_val = calculate_rsi(hist_data["Close"].iloc[:end_idx].values, window=14)
                if rsi_val is not None and rsi_val < 30:
                    days_oversold += 1
                else:
                    break
        metrics["days_oversold"] = days_oversold

        # Cache the result
        _set_cache(cache_key, metrics)
        total_time = time.time() - start_time
        logger.info(f"Total analysis for {ticker} took {total_time:.2f}s")
        
        return metrics

    except Exception as e:
        logger.error(f"Error analyzing {ticker}: {e}")
        return {"error": f"Error analyzing {ticker}: {str(e)}"}

def evaluate_strategy(metrics: Dict[str, Any]) -> tuple[bool, str, float]:
    current_rsi = metrics.get("RSI")
    vix_level = metrics.get("VIX", 20)
    current_return = metrics.get("percent_drop", 0)
    rolling_5d_drop = metrics.get("rolling_5d_drop", 0)
    rolling_10d_drop = metrics.get("rolling_10d_drop", 0)
    max_recent_drop = metrics.get("max_recent_drop", 0)
    days_oversold = metrics.get("days_oversold", 0)
    distance_from_low = metrics.get("distance_from_low", 100)
    price_vs_200ma = metrics.get("price_vs_200ma")

    score = 0.0
    reasons = []
    signal_strength = []

    rsi_quality = "poor"
    vix_quality = "poor"
    drop_quality = "minimal"
    low_quality = "poor"
    trend_quality = "unknown"

    rsi_signal = False
    if current_rsi is not None:
        if current_rsi <= 20:
            score += 0.35; rsi_signal = True
            reasons.append(f"Extreme oversold RSI ({current_rsi:.1f})")
            signal_strength.append("extreme oversold"); rsi_quality = "excellent"
        elif current_rsi <= 25:
            score += 0.30; rsi_signal = True
            reasons.append(f"Strong oversold RSI ({current_rsi:.1f})")
            signal_strength.append("strong oversold"); rsi_quality = "excellent"
        elif current_rsi <= 30:
            score += 0.25; rsi_signal = True
            reasons.append(f"Oversold RSI ({current_rsi:.1f})")
            signal_strength.append("oversold"); rsi_quality = "strong"
        elif current_rsi <= 35:
            score += 0.15; rsi_quality = "moderate"; reasons.append(f"Near oversold RSI ({current_rsi:.1f})")
        elif current_rsi <= 40:
            score += 0.05; rsi_quality = "fair"; reasons.append(f"Weak RSI ({current_rsi:.1f})")
        else:
            rsi_quality = "poor"; reasons.append(f"RSI not oversold ({current_rsi:.1f})")
    else:
        reasons.append("RSI unavailable"); rsi_quality = "unknown"

    if vix_level is not None and vix_level >= 25:
        score += 0.30; vix_quality = "excellent"; reasons.append(f"High fear VIX ({vix_level:.1f})"); signal_strength.append("high volatility")
    elif vix_level is not None and vix_level >= 20:
        score += 0.25; vix_quality = "good"; reasons.append(f"Elevated VIX ({vix_level:.1f})")
    elif vix_level is not None and vix_level >= 18:
        score += 0.20; vix_quality = "moderate"; reasons.append(f"Moderate VIX ({vix_level:.1f})")
    elif vix_level is not None and vix_level >= 16:
        score += 0.10; vix_quality = "fair"; reasons.append(f"Low-moderate VIX ({vix_level:.1f})")
    else:
        score += 0.05; vix_quality = "poor"; reasons.append(f"Low VIX ({vix_level if vix_level is not None else 0:.1f})")

    drop_signal = False
    if abs(current_return) >= 8:
        score += 0.30; drop_signal = True; reasons.append(f"Major single-day drop ({current_return:.1f}%)"); signal_strength.append("major selloff"); drop_quality = "excellent"
    elif abs(current_return) >= 5:
        score += 0.25; drop_signal = True; reasons.append(f"Significant daily drop ({current_return:.1f}%)"); signal_strength.append("significant drop"); drop_quality = "good"
    elif abs(rolling_5d_drop) >= 10:
        score += 0.28; drop_signal = True; reasons.append(f"Major 5-day decline ({rolling_5d_drop:.1f}%)"); signal_strength.append("major multi-day drop"); drop_quality = "excellent"
    elif abs(rolling_5d_drop) >= 7:
        score += 0.23; drop_signal = True; reasons.append(f"Strong 5-day decline ({rolling_5d_drop:.1f}%)"); signal_strength.append("strong multi-day drop"); drop_quality = "good"
    elif abs(rolling_10d_drop) >= 5:
        score += 0.18; drop_signal = True; reasons.append(f"Moderate 10-day decline ({rolling_10d_drop:.1f}%)"); drop_quality = "moderate"
    elif abs(max_recent_drop) >= 8:
        score += 0.20; reasons.append(f"Recent major drop ({max_recent_drop:.1f}%)"); drop_quality = "good"
    elif abs(max_recent_drop) >= 5:
        score += 0.15; reasons.append(f"Recent significant drop ({max_recent_drop:.1f}%)"); drop_quality = "moderate"
    else:
        reasons.append(f"Minimal recent drop ({max(abs(current_return), abs(rolling_5d_drop), abs(max_recent_drop)):.1f}%)"); drop_quality = "minimal"

    if distance_from_low := metrics.get("distance_from_low", 100):
        if distance_from_low <= 1:
            score += 0.20; reasons.append(f"At recent low (+{distance_from_low:.1f}%)"); signal_strength.append("perfect timing"); low_quality = "excellent"
        elif distance_from_low <= 3:
            score += 0.18; reasons.append(f"Very near low (+{distance_from_low:.1f}%)"); signal_strength.append("excellent timing"); low_quality = "very good"
        elif distance_from_low <= 5:
            score += 0.15; reasons.append(f"Near recent low (+{distance_from_low:.1f}%)"); low_quality = "good"
        elif distance_from_low <= 8:
            score += 0.10; reasons.append(f"Moderate distance from low (+{distance_from_low:.1f}%)"); low_quality = "moderate"
        else:
            reasons.append(f"Far from recent low (+{distance_from_low:.1f}%)"); low_quality = "poor"

    if price_vs_200ma := metrics.get("price_vs_200ma"):
        pv = float(price_vs_200ma.replace("%", "")) if isinstance(price_vs_200ma, str) else float(price_vs_200ma)
        if abs(pv) <= 5:
            score += 0.15; reasons.append(f"Price near 200MA ({pv:+.1f}%)"); trend_quality = "excellent"
        elif -10 <= pv < 0:
            score += 0.12; reasons.append(f"Price below 200MA ({pv:+.1f}%)"); trend_quality = "good"
        elif pv >= -15:
            score += 0.08; reasons.append(f"Price well below 200MA ({pv:+.1f}%)"); trend_quality = "moderate"
        else:
            score += 0.02; reasons.append(f"Price far below 200MA ({pv:+.1f}%)"); trend_quality = "poor"
    else:
        reasons.append("200MA data unavailable"); trend_quality = "unknown"

    if days_oversold >= 3:
        score += 0.10; reasons.append(f"Extended oversold ({days_oversold} days)"); signal_strength.append("persistent oversold")
    elif days_oversold == 2:
        score += 0.08; reasons.append(f"Multi-day oversold ({days_oversold} days)")
    elif days_oversold == 1:
        score += 0.05; reasons.append("Recent oversold (1 day)")

    is_play = score >= 0.6 and (("oversold" in "".join(reasons)) or ("drop" in "".join(reasons)))
    main_signals = signal_strength[:3] if signal_strength else ["weak setup"]
    signal_text = ", ".join(main_signals)

    if is_play:
        reason_text = f"✅ PLAY ({signal_text}): " + " | ".join(reasons[:6])
        reason_text += f" | Quality: RSI:{rsi_quality}, VIX:{vix_quality}, Drop:{drop_quality}, Low:{low_quality}, Trend:{trend_quality}"
    else:
        reason_text = "❌ PASS: " + " | ".join(reasons[:6])

    return is_play, reason_text, min(score, 1.0)

def classify_tier(confidence_score: float, estimated_credit: Optional[float],
                  current_rsi: Optional[float], vix_level: Optional[float],
                  distance_from_low: float, is_play: bool) -> str:
    if not is_play:
        return "PASS"
    if confidence_score >= 0.8 and estimated_credit and estimated_credit >= 100:
        return "A"
    elif confidence_score >= 0.7 and estimated_credit and 80 <= estimated_credit < 100:
        return "B"
    elif confidence_score >= 0.6:
        return "C"
    return "PASS"

def get_field_tooltips() -> Dict[str, Any]:
    return {
        "RSI": {"description": "Relative Strength Index (14-day) - measures if stock is oversold", "ideal": "< 30 (oversold)", "strong_signal": "< 20 (extreme oversold)", "warning": "> 35", "emoji": "🎯"},
        "VIX": {"description": "Market fear gauge - volatility index", "ideal": "> 20", "neutral": "17–20", "warning": "< 17", "emoji": "🚀"},
        "percent_drop": {"description": "Today's price change percentage (regular session)", "ideal": "-5% or more", "neutral": "-2% to -5%", "warning": "small/positive", "emoji": "⚡"},
        "rolling_5d_drop": {"description": "Decline from highest close in last 5 days", "ideal": "-7% or more", "strong_signal": "-10%+", "warning": "> -5%", "emoji": "⚡"},
        "max_recent_drop": {"description": "Largest single-day drop in last 30 days", "ideal": "-10%+", "neutral": "-5% to -10%", "warning": "> -5%", "emoji": "🔥"},
        "days_oversold": {"description": "Consecutive days RSI < 30", "ideal": "2+ days", "strong_signal": "4+ days", "warning": "1 day", "emoji": "🎯"},
        "distance_from_low": {"description": "Above lowest close in last 10 days", "ideal": "0–3%", "neutral": "3–5%", "warning": ">5%", "emoji": "🎯"},
        "price_vs_200ma": {"description": "Price relative to 200-day MA", "ideal": "±5%", "neutral": "5–10% below", "warning": ">10% below", "emoji": "✅"},
        "current_price": {"description": "Latest available price (daily)", "emoji": "💰"},
        "ma200": {"description": "200-day moving average", "emoji": "📈"},
        "confidence_score": {"description": "Algorithm confidence (0–1)", "emoji": "💪"},
        "estimated_credit": {"description": "Est. credit for 2.5-wide bull put (~30DTE, ~10% OTM)", "emoji": "💵"},
        "tier": {"description": "Trade quality classification", "emoji": "🏆"},
        "play": {"description": "Whether it qualifies as a trade", "emoji": "🎯"},
        "reason": {"description": "Explanation for PLAY/PASS", "emoji": "📝"},
    }

def generate_ai_analysis(metrics: Dict[str, Any], is_play: bool, tier: str, confidence_score: float) -> Optional[Dict[str, Any]]:
    """
    Generate real AI-powered analysis using OpenAI/Claude API
    """
    try:
        # Get API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {
                "error": "AI analysis requires OPENAI_API_KEY environment variable",
                "fallback": "Configure API key to enable AI insights"
            }
        
        # Prepare data for AI analysis
        rsi = metrics.get("RSI")
        vix = metrics.get("VIX")
        percent_drop = metrics.get("percent_drop", 0)
        distance_from_low = metrics.get("distance_from_low", 100)
        days_oversold = metrics.get("days_oversold", 0)
        rolling_5d_drop = metrics.get("rolling_5d_drop", 0)
        rolling_10d_drop = metrics.get("rolling_10d_drop", 0)
        max_recent_drop = metrics.get("max_recent_drop", 0)
        current_price = metrics.get("current_price", 0)
        ma200 = metrics.get("ma200")
        
        # Construct prompt for AI
        prompt = f"""Analyze this bull put credit spread trading opportunity:

STOCK DATA:
- Current Price: ${current_price}
- RSI (14-day): {rsi}
- VIX Level: {vix}
- Today's Change: {percent_drop}%
- 5-day Drop: {rolling_5d_drop}%
- 10-day Drop: {rolling_10d_drop}%
- Max Recent Drop: {max_recent_drop}%
- Days Oversold (RSI<30): {days_oversold}
- Distance from Recent Low: +{distance_from_low}%
- 200-day MA: ${ma200 if ma200 else 'N/A'}

ALGORITHM ASSESSMENT:
- Trade Signal: {'PLAY' if is_play else 'PASS'}
- Tier: {tier}
- Confidence Score: {confidence_score}/1.0

As an expert options trader, provide a concise analysis including:
1. Your assessment of this bull put credit spread opportunity
2. Key risk factors to consider
3. Market timing assessment
4. Specific entry/exit recommendations
5. Position sizing suggestions

Keep response under 200 words and focus on actionable insights."""

        # Make API call to OpenAI
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use the faster, cheaper model
            messages=[
                {"role": "system", "content": "You are an expert options trader specializing in bull put credit spreads. Provide concise, actionable trading advice."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.3
        )
        
        ai_analysis = response.choices[0].message.content.strip()
        
        return {
            "analysis": ai_analysis,
            "model": "gpt-4o-mini",
            "confidence": confidence_score,
            "timestamp": pd.Timestamp.now().isoformat()
        }
        
    except Exception as e:
        logger.warning(f"AI analysis failed: {e}")
        return {
            "error": f"AI analysis unavailable: {str(e)}",
            "fallback": "Use algorithmic signals for trading decisions"
        }

@app.post("/check-dip", response_model=TickerResponse)
async def check_dip(request: TickerRequest):
    ticker = request.ticker.upper()
    try:
        metrics = analyze_ticker(ticker)
        if "error" in metrics:
            raise HTTPException(status_code=400, detail=metrics["error"])

        is_play, reason, confidence_score = evaluate_strategy(metrics)
        current_price = metrics.get("current_price", 100)
        vix_level = metrics.get("VIX", 20)
        estimated_credit = estimate_bull_put_credit(current_price, vix_level)

        tier = classify_tier(
            confidence_score=confidence_score,
            estimated_credit=estimated_credit,
            current_rsi=metrics.get("RSI"),
            vix_level=metrics.get("VIX"),
            distance_from_low=metrics.get("distance_from_low", 100),
            is_play=is_play,
        )

        response_metrics = {}
        for key, value in metrics.items():
            if value is not None:
                if isinstance(value, (int, float)):
                    if key in ["current_price", "ma200"]:
                        response_metrics[key] = round(value, 2)
                    else:
                        response_metrics[key] = round(float(value), 1)
                else:
                    response_metrics[key] = value
            else:
                response_metrics[key] = value

        response_data = {
            "ticker": ticker,
            "play": is_play,
            "tier": tier,
            "metrics": response_metrics,
            "reason": reason,
            "confidence_score": round(confidence_score, 2),
            "confidence_source": "algorithmic",
            "estimated_credit": estimated_credit,
        }
        
        # Only include ai_analysis if requested
        if request.include_ai_analysis:
            ai_analysis_result = generate_ai_analysis(metrics, is_play, tier, confidence_score)
            response_data["ai_analysis"] = ai_analysis_result
            
        # Return the response as a dict to avoid Pydantic including None fields
        from fastapi.responses import JSONResponse
        return JSONResponse(content=response_data)

    except Exception as e:
        msg = str(e)
        if any(s in msg for s in ["Too Many Requests", "Rate limited", "429"]):
            # Should be rare now, and will fall back to Stooq for price data
            raise HTTPException(status_code=429, detail=f"Rate limited: {msg}")
        raise HTTPException(status_code=500, detail=f"Error processing {ticker}: {msg}")

@app.get("/")
def root():
    return {"message": "Bull Put Credit Spread API (Yahoo with Stooq fallback)", "version": "2.2.0"}

if __name__ == "__main__":
    # Use a single worker in Docker/App Runner
    uvicorn.run(app, host="0.0.0.0", port=8000)
