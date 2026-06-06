#!/usr/bin/env python3
"""
scanner.py — entry signal scanner for stock put spread backtest.

Single responsibility: given a date and a ticker's price history +
earnings calendar, decide whether to enter a trade today and return
the strike price if so.

All tunable parameters are in ScannerConfig — change values there,
not in the logic below.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import pandas_ta_classic as ta


# ============================================================================
# CONFIG — all tunable values in one place
# ============================================================================

@dataclass
class ScannerConfig:
    # Earnings gate
    earnings_lookahead_days: int = 1    # entry on day N after earnings
                                        # 1 = day immediately after

    # EMA trend
    ema_period: int   = 20              # EMA(20)
    ema_trend_days: int = 5             # EMA today must be > EMA N days ago

    # RSI slope
    rsi_period: int   = 14              # RSI(14)
    rsi_slope_days: int = 3             # slope measured over last N days
    rsi_slope_min: float = 0.5          # minimum slope threshold

    # Support
    support_lookback: int = 20          # rolling low over N days
    min_price_above_support_pct: float = 0.02   # price must be >= 2% above support

    # Strike
    strike_increment: float = 5.0       # nearest standard strike below support


# Default instance — import and override individual fields as needed:
#   from scanner import DEFAULT_CONFIG
#   cfg = ScannerConfig(**vars(DEFAULT_CONFIG), ema_period=50)
DEFAULT_CONFIG = ScannerConfig()


# ============================================================================
# INDICATOR HELPERS
# ============================================================================
def trend_period(ema, window_len) -> float:
    window = ema.iloc[-window_len:]
    x = pd.Series(range(len(window)), index=window.index)
    return window.cov(x) / x.var()  # slope of EMA over the window


def _ema_trending_up(close: pd.Series, cfg: ScannerConfig) -> float:
    """
    EMA is in an upward trend, allowing noise/dips inside the lookback.
    handles he case of price goes up after ema_trend_days and is now trending down but ema is still below ema_trend_days ago
    """
    ema = ta.ema(close, length=cfg.ema_period)
    if ema is None:
        return 0.0

    ema = ema.dropna()
    window_len = cfg.ema_trend_days + 1
    if len(ema) < window_len:
        return 0.0

    # 1. overall slope over lookback period must be positive
    slope = ema.iloc[-1] > ema.iloc[-1 - cfg.ema_trend_days]

    # 2. EMA must be trending up over the lookback period, allowing for noise/dips
    overall_slope = trend_period(ema, window_len)

    # 3. recent slope over half the lookback period must also be positive to avoid old uptrend that's now reversing
    recent_slope = trend_period(ema, max(3, window_len // 2))
    return slope and overall_slope > 0 and recent_slope > 0


# similar trend check as _ema_trending_up.?
def _rsi_slope(close: pd.Series, cfg: ScannerConfig) -> float:
    """Slope of RSI(period) over last rsi_slope_days days."""
    rsi = ta.rsi(close, length=cfg.rsi_period)
    if rsi is None:
        return 0.0
    rsi = rsi.dropna()
    window_len = cfg.rsi_slope_days + 1
    if len(rsi) < window_len:
        return 0.0

    if rsi.iloc[-1] < cfg.rsi_slope_min:
        return 0.0

    # 1. overall slope over lookback period must be positive
    slope = rsi.iloc[-1] > rsi.iloc[-1 - cfg.rsi_period]

    # 2. rsi must be trending up over the lookback period, allowing for noise/dips
    overall_slope = trend_period(rsi, window_len)

    # 3. recent slope over half the lookback period must also be positive to avoid old uptrend that's now reversing
    recent_slope = trend_period(rsi, max(3, window_len // 2))
    return slope and overall_slope > 0 and recent_slope > 0


def _find_support(close: pd.Series, cfg: ScannerConfig) -> Optional[float]:
    """Rolling N-day low as support level."""
    if len(close) < cfg.support_lookback:
        return None
    return float(close.rolling(cfg.support_lookback).min().iloc[-1])


# TODO : use the pricing functions to get strike for a given delta instead of this. this is just a rough approximation and may not be accurate enough for backtesting.
def _nearest_strike_below(price: float, increment: float) -> float:
    """Largest strike that is a multiple of increment and <= price."""
    import math
    return math.floor(price / increment) * increment


# ============================================================================
# MAIN SCANNER FUNCTION
# ============================================================================


def scan(current_date: date, price_df: pd.DataFrame, earnings_dates: list[date], cfg: ScannerConfig = DEFAULT_CONFIG) -> tuple[bool, Optional[float]]:
    """
    Decide whether to enter a put spread on ticker today.

    Parameters
    ----------
    current_date  : date being evaluated
    price_df      : DataFrame with DatetimeIndex and at least a 'Close' column,
                    as returned by cachebt.get_ticker()
    earnings_dates: list of past earnings dates from CacheEarnings.get_earnings_dates()
    cfg           : ScannerConfig — all tunable thresholds

    Returns
    -------
    (True, strike)  if all criteria met
    (False, None)   otherwise
    """

    # ── gate 1: yesterday was an earnings day ────────────────────────────
    yesterday = current_date - timedelta(days=cfg.earnings_lookahead_days)
    if yesterday not in earnings_dates:
        return False, None

    # ── slice history up to and including current_date ───────────────────
    history = price_df[price_df.index.date <= current_date]
    if history.empty:
        return False, None

    close = history['Close']
    current_price = float(close.iloc[-1])

    # ── gate 2: EMA(20) trending up ──────────────────────────────────────
    if _ema_trending_up(close, cfg) > 0.0:
        return False, None

    # ── gate 3: RSI(14) slope > threshold ────────────────────────────────
    if _rsi_slope(close, cfg) > 0.0:
        return False, None

    # ── gate 4: support exists and price is sufficiently above it ────────
    support = _find_support(close, cfg)
    if support is None:
        return False, None

    min_price = support * (1 + cfg.min_price_above_support_pct)
    if current_price < min_price:
        return False, None

    # ── gate 5: strike = nearest standard increment below support ────────
    strike = _nearest_strike_below(support, cfg.strike_increment)
    if strike <= 0:
        return False, None

    return True, strike
