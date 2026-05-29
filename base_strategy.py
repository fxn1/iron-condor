from datetime import timedelta
from enum import Enum

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


class BaseStrategy:

    def set_vix_data(self, vix_data):
        pass  # no-op default; override in strategies that need vix internally

    def should_enter_trade(self, current_date) -> TradeEntryReason:
        raise NotImplementedError

    def should_reenter_after_exit(self, trade) -> bool:
        raise NotImplementedError

    def mark_expiration_used(self, trade):  # called by engine after entry
        raise NotImplementedError

    def check_expiration_used(self, current_date) -> bool:
        raise NotImplementedError

    def create_trade(self, current_date, spx_price, volatility, trade_id):
        raise NotImplementedError
