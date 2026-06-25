#!/usr/bin/env python3
"""
scanner.py — entry signal scanner for stock put spread backtest.

Single responsibility: given a date and a ticker's price history + earnings calendar, decide whether to enter a trade today and return the strike price if so.

use run_scanner to test
"""

from datetime import timedelta, date, datetime
from typing import Optional

import pandas as pd
import pandas_ta_classic as ta


# ============================================================================
# INDICATOR HELPERS
# ============================================================================
def trend_period(ema, window_len) -> float:
    window = ema.iloc[-window_len:]
    x = pd.Series(range(len(window)), index=window.index)
    return window.cov(x) / x.var()  # slope of EMA over the window


def _ema_trending_up(close: pd.Series, scanner_cfg) -> bool:
    """
    EMA is in an upward trend, allowing noise/dips inside the lookback.
    handles he case of price goes up after ema_trend_days and is now trending down but ema is still below ema_trend_days ago
    """
    ema = ta.ema(close, length=scanner_cfg.ema_period)
    if ema is None:
        return False

    ema = ema.dropna()
    window_len = scanner_cfg.ema_trend_days + 1
    if len(ema) < window_len:
        return False

    slope = ema.iloc[-1] > ema.iloc[-window_len]  # 1. overall slope over lookback period must be positive
    overall_slope = trend_period(ema, window_len)  # 2. EMA must be trending up over the lookback period, allowing for noise/dips
    recent_slope = trend_period(ema, max(3, window_len // 2))  # 3. recent slope over half the lookback period must also be positive to avoid old uptrend that's now reversing
    return slope and overall_slope > 0 and recent_slope > 0


# similar trend check as _ema_trending_up.?
def _rsi_slope(close: pd.Series, scanner_cfg) -> bool:
    """Slope of RSI(period) over last rsi_slope_days days."""
    rsi = ta.rsi(close, length=scanner_cfg.rsi_period)
    if rsi is None:
        return False
    rsi = rsi.dropna()
    window_len = scanner_cfg.rsi_slope_days + 1
    if len(rsi) < window_len:
        return False

    if len(rsi) <= scanner_cfg.rsi_period:
        return False

    if rsi.iloc[-1] < scanner_cfg.rsi_slope_min:
        return False

    slope = rsi.iloc[-1] > rsi.iloc[-1 - scanner_cfg.rsi_period]  # 1. overall slope over lookback period must be positive
    overall_slope = trend_period(rsi, window_len)  # 2. rsi must be trending up over the lookback period, allowing for noise/dips
    recent_slope = trend_period(rsi, max(3, window_len // 2))  # 3. recent slope over half the lookback period must also be positive to avoid old uptrend that's now reversing
    return slope and overall_slope > 0 and recent_slope > 0


def _find_support(close: pd.Series, scanner_cfg) -> Optional[float]:
    """Rolling N-day low as support level."""
    if len(close) < scanner_cfg.support_lookback:
        return None
    return float(close.rolling(scanner_cfg.support_lookback).min().iloc[-1])


def _nearest_strike_below(price: float, increment: float) -> float:
    """Largest strike that is a multiple of increment and <= price."""
    import math
    return math.floor(price / increment) * increment


# ============================================================================
# MAIN SCANNER FUNCTION
# ============================================================================


def scan(current_date: datetime, price_df: pd.DataFrame, earnings_dates: list[date], scanner_cfg) -> tuple[bool, Optional[float]]:
    """
    Decide whether to enter a put spread on ticker today.

    Parameters
    ----------
    current_date  : date being evaluated
    price_df      : DataFrame with DatetimeIndex and at least a 'Close' column,
                    as returned by cachebt.get_ticker()
    earnings_dates: list of past earnings dates from CacheEarnings.get_earnings_dates()
    scanner_cfg           : ScannerConfig — all tunable thresholds

    Returns
    -------
    (True, strike)  if all criteria met
    (False, None)   otherwise
    """

    # ── gate 1: yesterday was an earnings day ────────────────────────────
    if scanner_cfg.earnings_lookahead_days > 0:
        yesterday = current_date - timedelta(days=scanner_cfg.earnings_lookahead_days)
        if yesterday.date() not in earnings_dates:
            return False, None

    # ── slice history up to and including current_date ───────────────────
    history = price_df[price_df.index <= current_date]
    if history.empty:
        return False, None

    close = history['Close']
    current_price = float(close.iloc[-1])

    # ── gate 2: EMA(20) trending up ──────────────────────────────────────
    if not _ema_trending_up(close, scanner_cfg):
        return False, None

    # ── gate 3: RSI(14) slope > threshold ────────────────────────────────
    if not _rsi_slope(close, scanner_cfg):
        return False, None

    # ── gate 4: support exists and price is sufficiently above it ────────
    support = _find_support(close, scanner_cfg)
    if support is None:
        return False, None

    min_price = support * (1 + scanner_cfg.min_price_above_support_pct)
    if current_price < min_price:
        return False, None

    # ── gate 5: strike = nearest standard increment below support ────────
    strike = _nearest_strike_below(support, scanner_cfg.strike_increment)
    if strike <= 0:
        return False, None
    return True, strike
