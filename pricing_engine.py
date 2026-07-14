#!/usr/bin/env python3
"""
pricing_engine.py — abstraction over Black-Scholes and real options market data.

Callers use MarketDataPricingEngine, which:
  a) reads real option prices from .gz flat files when available
  b) falls back to Black-Scholes when not, buffering synthetic rows
     in the same format for later flush to disk.

Black-Scholes is always used for delta and strike_for_delta (no delta in flat files).

Usage:
    engine = MarketDataPricingEngine(ticker='AAPL', current_date=date, cfg=gcfg)
    price  = engine.option_price(ticker, current_date, S, K, T, r, sigma, 'put', 'close')
    delta  = engine.option_delta(ticker, current_date, S, K, T, r, sigma, 'put', 'close')
    strike = engine.strike_for_delta(ticker, current_date, S, target_delta, T, r, sigma, 'put', 'close')

    # at end of each trading date in the backtest loop:
    MarketDataPricingEngine.save_all(gcfg)
"""

import gzip
from pathlib import Path

import pandas as pd

from massive_options_flatfile import _parse_raw
from pricing import black_scholes_price, black_scholes_delta, find_strike_for_delta


# ── class-level state (shared across all instances) ──────────────────────────

class MarketDataPricingEngine:
    """
    Pricing engine that reads from Massive/Polygon .gz flat files when
    available, falling back to Black-Scholes otherwise.

    Two class-level caches:
        _day_cache   : {date -> DataFrame | None}  — parsed .gz for that date
        _synth_buffer: {date -> {occ_ticker -> row_dict}}        — BS-fallback rows, flushed at end of date
    """

    _day_cache    = {}   # {date: DataFrame | None}
    _synth_buffer = {}   # {date: {occ_ticker: row_dict}}
    _file_changed = {}  # {date: bool}

    def __init__(self, cfg):
        self.data_path   = Path(cfg.options_data_path)

    # ── public interface ─────────────────────────────────────────────────────

    def option_price(self, ticker, current_date, S, K, T, r, sigma, option_type, mark) -> float:
        """Return real close price from flat file, or BS fallback (buffered for flush)."""
        date = pd.Timestamp(current_date).date()
        self._ensure_loaded(date)
        price = self._lookup(ticker.upper(), current_date, K, T, option_type, mark)
        if price is not None:
            return price
        bs_price = black_scholes_price(S, K, T, r, sigma, option_type)
        self._buffer_synthetic(ticker, current_date, K, T, option_type, mark, bs_price)
        return bs_price

    def option_delta(self, S, K, T, r, sigma, option_type) -> float:
        """Always Black-Scholes — flat files carry no delta column."""
        return black_scholes_delta(S, K, T, r, sigma, option_type)

    def strike_for_delta(self, S, target_delta, T, r, sigma, option_type) -> float:
        """Always Black-Scholes — pre-trade calculation, no file to look up."""
        return find_strike_for_delta(S, target_delta, T, r, sigma, option_type)

    @classmethod
    def save_all(cls, cfg):
        """
        Write buffered BS-fallback rows for current_date to the .gz file.
        Call once per trading date at the end of the backtest loop.
        Skips if no synthetic rows were buffered for that date.
        """
        for d, changed in cls._file_changed.items():
            if not changed:
                continue
            rows_by_ticker  = cls._synth_buffer.get(d, {})
            if not rows_by_ticker:
                continue
            rows = list(rows_by_ticker.values())
            path = _file_path(d, Path(cfg.options_data_path))
            path.parent.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame(rows, columns=['ticker', 'volume', 'open', 'close', 'high', 'low', 'window_start', 'transactions'])
            with gzip.open(path, 'wt') as f:
                df.to_csv(f, index=False)
            cls._file_changed[d] = False
            cls._synth_buffer[d] = rows_by_ticker

    # ── internal ─────────────────────────────────────────────────────────────

    def _ensure_loaded(self, date):
        if date in self.__class__._day_cache:  # Equivalent to writing MarketDataPricingEngine._day_cache.get(date). Used instead of the class name directly so subclasses would still work.
            return
        path = _file_path(date, self.data_path)
        if path.exists():
            # load raw rows into synth_buffer, day_cache
            with gzip.open(path, 'rt') as f:
                raw_df = pd.read_csv(f)  # read once
            rows = raw_df.to_dict('records')
            self.__class__._synth_buffer[date] = {
                row['ticker']: row for row in rows
            }
            self.__class__._day_cache[date] = _parse_raw(raw_df, "America/New_York")  # parse in memory
            self.__class__._file_changed[date] = False
        else:
            self.__class__._day_cache[date] = None
            self.__class__._synth_buffer[date] = {}
            self.__class__._file_changed[date] = False

    def _lookup(self, ticker, current_date, K, T, option_type, mark):
        if mark not in {'open', 'high', 'low', 'close'}:
            raise ValueError(f"Unsupported option mark: {mark}")

        df = self.__class__._day_cache.get(current_date)
        if df is None:
            return None
        # T is time-to-expiration in years (that's what Black-Scholes uses — e.g. 63 days = 0.1726 years). This converts it back to an actual calendar date
        target_exp = (pd.Timestamp(current_date) + pd.Timedelta(days=round(T * 365))).date()

        # match underlying, option_type, strike; find closest expiration within ±3 days
        mask = (
            (df['underlying'] == ticker) &
            (df['option_type'] == option_type) &
            (df['strike']     == K)
        )
        candidates = df[mask].copy()
        if candidates.empty:
            return None

        # for each candidate row, compute how many days its expiration differs from target_exp
        # candidates['exp_diff'] = abs(candidate_expiration - target_exp) in days
        candidates['exp_diff'] = (pd.to_datetime(candidates['expiration']) - pd.Timestamp(target_exp)).dt.days.abs()

        # find the 1 row with smallest exp_diff
        best = candidates.nsmallest(1, 'exp_diff').iloc[0]

        # The 3-day tolerance handles weekends/holidays where exact expiration date might be off by a day or two.
        # if even the closest is more than 3 days away, no usable match
        if best['exp_diff'] > 3:
            return None  # no close-enough expiration
        return float(best[mark])

    def _buffer_synthetic(self, ticker, current_date, K, T, option_type, mark, price):
        exp_date  = (pd.Timestamp(current_date) + pd.Timedelta(days=round(T * 365))).date()
        yymmdd    = exp_date.strftime('%y%m%d')
        cp        = 'C' if option_type == 'call' else 'P'
        occ       = f"O:{ticker}{yymmdd}{cp}{int(K * 1000):08d}"
        win_start = int(pd.Timestamp(current_date, tz='UTC').value)  # nanoseconds

        row = {
            'ticker':       occ,
            'volume':       0,
            'open':         price,
            'close':        price,
            'high':         price,
            'low':          price,
            'window_start': win_start,
            'transactions': 0,
        }
        if current_date not in self.__class__._synth_buffer:
            self.__class__._synth_buffer[current_date] = {}
        rows_by_ticker = self.__class__._synth_buffer.setdefault(current_date, {})

        if occ not in rows_by_ticker:
            rows_by_ticker[occ] = row
        else:
            existing = rows_by_ticker[occ]
            if mark == 'high':
                existing['high'] = max(float(existing['high']), price)
            elif mark == 'low':
                existing['low'] = min(float(existing['low']), price)
            else:
                existing[mark] = price

        self.__class__._file_changed[current_date] = True


# ── file path helper (reused by engine + flush) ───────────────────────────────

def _file_path(d, data_path: Path) -> Path:
    return data_path / "us_options_opra" / "day_aggs_v1" / \
           f"{d.year}" / f"{d.month:02d}" / f"{d:%Y-%m-%d}.csv.gz"
