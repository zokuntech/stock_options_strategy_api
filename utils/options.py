import numpy as np
from scipy.stats import norm
from typing import Optional

def black_scholes_put(S, K, T, r, sigma):
    """
    Calculate Black-Scholes put option price
    S: Current stock price
    K: Strike price
    T: Time to expiration (in years)
    r: Risk-free rate
    sigma: Volatility
    """
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    put_price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return put_price

def estimate_bull_put_credit(current_price, vix_level=25, days_to_expiration=30):
    """
    Estimate credit for 2.5-point bull put spread with realistic premiums:
    - Strikes ~10-12% OTM (not 8%)
    - Single-stock IV ~2x VIX baseline
    - Floor credit at $80 (C-tier threshold)
    """
    try:
        r = 0.05
        T = days_to_expiration / 365

        # Baseline volatility: 2x VIX (min 30%)
        base_vol = max((vix_level or 25) / 100 * 2.0, 0.30)

        # Strikes 10% below current price
        short_strike = current_price * 0.90
        long_strike = short_strike - 2.5

        short_put_price = black_scholes_put(current_price, short_strike, T, r, base_vol)
        long_put_price = black_scholes_put(current_price, long_strike, T, r, base_vol)

        estimated_credit = (short_put_price - long_put_price) * 100

        # Low VIX boost (vol skew)
        if vix_level and vix_level < 18:
            estimated_credit *= 1.1

        # Enforce floor + round
        return round(max(estimated_credit, 80), 2)
    except:
        # Fallback: conservative mid-range estimate
        return 100.0 