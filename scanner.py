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
from datetime import date
from typing import Optional

import pandas as pd
import pandas_ta_classic as ta


# ============================================================================
# CONFIG — all tunable values in one place
# ============================================================================

@dataclass
class ScannerConfig:
    # Earnings gate
    earnings_lookahead_days: int = 1    # entry on day N after earnings, 1 = day immediately after

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
    if yesterday.date() not in earnings_dates:
        return False, None

    # ── slice history up to and including current_date ───────────────────
    history = price_df[price_df.index <= current_date]
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


if __name__ == "__main__":
    from CacheDailyOHLCV import CachedailyOHLCV, get_spy_ticker_list
    from CacheEarning import EarningsCache
    from config import YF_DATA_PATH
    from datetime import timedelta, date, datetime
    from config_stocks import *

    start_date = datetime(2025, 5, 1)
    delta_days = 365 * 4
    end_date = start_date + timedelta(days=delta_days + 1)  # +1 to include the last day in the loop

    sp500_list = get_spy_ticker_list()
    # sp500_list = ['MMM']  # TODO: expand as needed
    cache = CachedailyOHLCV(path=YF_DATA_PATH, start_date=start_date, delta_days=delta_days)
    sorted_dates = {}  # {ticker: [sorted list of dates in price_data]}
    for ticker in sp500_list:
        df = cache.get_cache(ticker)
        sorted_dates[ticker] = sorted(pd.to_datetime(df.index).normalize().tolist())

    sorted_dates = next(iter(sorted_dates.values()))
    dates = [pd.Timestamp(d) for d in sorted_dates]
    dates = [d for d in dates if start_date <= d <= end_date]
    dates = [datetime(2026, 4, 22)]   # hardcode for testing

    print("  Loading earnings data...")
    earnings_cache = EarningsCache(path=YF_DATA_PATH)
    # earnings_cache.download_list(sp500_list)  # TODO: update manually for now
    earnings_data = {t: earnings_cache.get_earnings_dates(t) for t in sp500_list}
    print(f"  ✓ Loaded earnings for {len(earnings_data)} tickers")

    stock_cfg = ScannerConfig(
        earnings_lookahead_days=SCAN_EARNINGS_LOOKAHEAD_DAYS,
        ema_period=SCAN_EMA_PERIOD,
        ema_trend_days=SCAN_EMA_TREND_DAYS,
        rsi_period=SCAN_RSI_PERIOD,
        rsi_slope_days=SCAN_RSI_SLOPE_DAYS,
        rsi_slope_min=SCAN_RSI_SLOPE_MIN,
        support_lookback=SCAN_SUPPORT_LOOKBACK,
        min_price_above_support_pct=SCAN_MIN_PRICE_ABOVE_SUPPORT_PCT,
        strike_increment=SCAN_STRIKE_INCREMENT,
    )
    ii = 0
    for cur_date in dates:
        for ticker in sp500_list:
            df = cache.get_cache(ticker)
            earnings_dt = earnings_cache.get_earnings_dates(ticker) # TODO: fix scanner
            entered, stk_strike = scan(cur_date, df, earnings_dt, stock_cfg)
            if entered:
                print(f"{cur_date.date()} {ticker} ENTER at strike {stk_strike}")
                ii += 1
                if ii > 10:
                    break
