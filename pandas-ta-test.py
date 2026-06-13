from datetime import date
import pandas as pd
import pandas_ta_classic as ta
from CacheDailyOHLCV import CachedailyOHLCV
from config import gcfg


# support
# find support/resistance with pivots
# Option A — rolling N-day low (simplest, good enough for backtesting)
def find_support(close: pd.Series, lookback=20) -> float:
    return close.rolling(lookback).min().iloc[-1]

# Option B — swing low (local minimum, more meaningful)
# def find_support(close: pd.Series, lookback=20, window=3) -> float:
#     lows = close.rolling(window, center=True).min()
#     swing_lows = close[(close == lows) & (close == close.rolling(lookback).min())]
#     return swing_lows.iloc[-1] if len(swing_lows) else close.rolling(lookback).min().iloc[-1]


# Option C — pandas-ta has pivot points (PDLP) which is closest to support
# df.ta.pivots(append=True)   # adds S1, S2, S3 support columns

START_DATE = date.fromisoformat("2025-06-01")
delta_days = 365*30
cache = CachedailyOHLCV(gcfg.paths.yf_data_path, START_DATE, delta_days)  # instantiate first
df = cache.update_ticker('AAPL')
# df = cache.get_ticker('AAPL')

print(df.columns)
print(df.head(2))

# EMA-20 trending up
df['EMA20'] = ta.ema(df['Close'], length=20)
ema_trending_up = df['EMA20'].iloc[-1] > df['EMA20'].iloc[-5]
print(f"EMA20 trending up: {ema_trending_up}")

# RSI(14) slope
df['RSI14'] = ta.rsi(df['Close'], length=14)
rsi_slope = (df['RSI14'].iloc[-1] - df['RSI14'].iloc[-3]) / 3  # slope over 3 days
rsi_slope_ok = rsi_slope > 0.5
print(f"RSI14 slope: {rsi_slope:.2f}, ok: {rsi_slope_ok}")

# Or append all to df at once
df.ta.ema(length=20, append=True)      # adds column EMA_20
df.ta.rsi(length=14, append=True)      # adds column RSI_14
print(df.tail())

print(f"Support (rolling 20-day low): {find_support(df['Close'], lookback=20):.2f}")
