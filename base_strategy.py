from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Optional

import pandas as pd

from snp500_ticker_hist import Snp500TickerHist


# ============================================================================
# DATE HELPERS
# ============================================================================


def get_next_friday(from_date, days_out=30):
    target = from_date + timedelta(days=days_out)
    days_to_friday = (4 - target.weekday()) % 7  # Roll to next Friday
    friday = target + timedelta(days=days_to_friday)
    if friday <= from_date:
        friday += timedelta(days=7)
    return friday


class TradeEntryReason(Enum):
    SHOULD_ENTER    = "should_enter"
    SKIPPED_VIX     = "skipped_vix"
    SKIPPED_DUP_EXP = "skipped_dup_exp"
    NOT_WEEKDAY      = "not_weekday"
    SKIPPED_LOW_STRIKE = "skipped_low_strike"
    NO_SIGNAL       = "no_signal"       # generic — used by stock strategy


@dataclass
class TradeSignal:
    """Carries per-signal data from should_enter_trades to the engine.
    SPX strategies leave ticker/strike as None — not needed.
    Stock strategies populate both.
    reason is always set.  ticker/strike only populated for SHOULD_ENTER signals."""
    reason: TradeEntryReason
    ticker: Optional[str] = None
    strike: Optional[float] = None


class BaseStrategy(ABC):

    def __init__(self):
        self.vix_data = None
        self.used_expirations = set()
        self.hist = Snp500TickerHist()

    @abstractmethod
    def load_data(self, start_date, delta_days):
        pass  # no-op default

    @abstractmethod
    def should_enter_trades(self, current_date) -> list[TradeSignal]:
        """Return a list of TradeSignal for each trade to enter today.
        one entry per signal or skip reason.
        Empty list means no entry.  SPX strategies return at most one item.
        Engine counts skips from signal.reason; creates trades for SHOULD_ENTER."""
        raise NotImplementedError

    @abstractmethod
    def should_reenter_after_exit(self, trade) -> TradeSignal:
        raise NotImplementedError

    @abstractmethod
    def _exp_key(self, current_date, ticker):
        raise NotImplementedError

    def mark_expiration_used(self, trade):
        self.used_expirations.add((trade.ticker, trade.expiration_date))

    def mark_reentry_expiration_used(self, current_date, ticker):
        self.used_expirations.add(self._exp_key(current_date, ticker))

    def check_expiration_used(self, current_date, ticker) -> bool:
        return self._exp_key(current_date, ticker) in self.used_expirations

    @abstractmethod
    def create_trade(self, current_date, trade_id, signal: TradeSignal):
        """Build and return a Trade from a TradeSignal.
        Strategy owns price and vol lookup — engine passes nothing extra."""
        raise NotImplementedError

    @abstractmethod
    def get_market_data(self, trade, ts: pd.Timestamp) -> dict:
        """Return market data needed by the engine for an open trade today.
        Must include: close, high, low, open, vix, volatility, put_vol, call_vol"""
        raise NotImplementedError

    def get_trading_dates(self, start_date, end_date) -> list:
        """Return sorted list of trading datetime for the backtest period.
        Default: subclass must override or engine passes dates directly."""
        raise NotImplementedError

    @abstractmethod
    def print_strategy_config(self):
        """Print strategy-specific config in the run banner."""
        raise NotImplementedError

    @abstractmethod
    def print_extra_results(self, results, years):
        """Strategy-specific report section. Default: no-op."""
        pass

    @abstractmethod
    def fill_expiration_price(self, trade):
        """fixed4 need to fill expiration price."""
        pass

    def _vix(self, current_date):
        if self.vix_data is None:
            return 18.0
        if current_date not in self.vix_data:
            return 18.0
        return self.vix_data[current_date]['close']
