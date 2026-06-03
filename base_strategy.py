from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Optional


# ============================================================================
# DATE HELPERS
# ============================================================================


def get_next_friday(from_date, days_out=30):
    target = from_date + timedelta(days=days_out)
    days_to_friday = (4 - target.weekday()) % 7
    if days_to_friday == 0 and target.weekday() != 4:
        days_to_friday = 7
    friday = target + timedelta(days=days_to_friday)
    if friday <= from_date:
        friday += timedelta(days=7)
    return friday


def is_monday(d): return d.weekday() == 0


class TradeEntryReason(Enum):
    SHOULD_ENTER    = "should_enter"
    SKIPPED_VIX     = "skipped_vix"
    SKIPPED_DUP_EXP = "skipped_dup_exp"
    NOT_MONDAY      = "not_monday"
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
    def mark_expiration_used(self, trade):
        raise NotImplementedError

    def mark_reentry_expiration_used(self, current_date):
        raise NotImplementedError

    @abstractmethod
    def create_trade(self, current_date, trade_id, signal: TradeSignal):
        """Build and return a Trade from a TradeSignal.
        Strategy owns price and vol lookup — engine passes nothing extra."""
        raise NotImplementedError

    @abstractmethod
    def get_market_data(self, trade, date_str) -> dict:
        """Return market data needed by the engine for an open trade today.
        Must include: close, high, low, open, vix, volatility, put_vol, call_vol"""
        raise NotImplementedError

    @abstractmethod
    def check_expiration_used(self, current_date) -> bool:
        raise NotImplementedError

    def get_trading_dates(self, start_date, end_date) -> list:
        """Return sorted list of trading datetimes for the backtest period.
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
