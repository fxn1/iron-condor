from datetime import timedelta
from enum import Enum

from pricing import black_scholes_price
from pricing import find_strike_for_delta

from trade import IronCondorTrade

from config import *

from base_strategy import BaseStrategy

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


# ============================================================================
# TRADE CREATION
# ============================================================================

def create_new_trade(entry_date, spx_price, vix, volatility, trade_id):
    expiration = get_next_friday(entry_date, TARGET_DTE)
    dte = (expiration - entry_date).days
    T = dte / 365.0
    put_vol  = volatility * 1.10
    call_vol = volatility * 0.95

    put_short  = find_strike_for_delta(spx_price, PUT_DELTA,  T, RISK_FREE_RATE, put_vol,  'put')
    put_long   = put_short - WING_WIDTH
    call_short = find_strike_for_delta(spx_price, CALL_DELTA, T, RISK_FREE_RATE, call_vol, 'call')
    call_long  = call_short + WING_WIDTH

    ps = black_scholes_price(spx_price, put_short,  T, RISK_FREE_RATE, put_vol, 'put')
    pl = black_scholes_price(spx_price, put_long,   T, RISK_FREE_RATE, put_vol, 'put')
    put_credit  = ps - pl

    cs = black_scholes_price(spx_price, call_short, T, RISK_FREE_RATE, call_vol, 'call')
    cl = black_scholes_price(spx_price, call_long,  T, RISK_FREE_RATE, call_vol, 'call')
    call_credit = cs - cl

    return IronCondorTrade(
        entry_date=entry_date,
        expiration_date=expiration,
        spx_price=spx_price,
        vix=vix,
        put_short=put_short, put_long=put_long, put_credit=put_credit,
        call_short=call_short, call_long=call_long, call_credit=call_credit,
        num_contracts=NUM_CONTRACTS,
        trade_id=trade_id,
    )


def is_monday(d): return d.weekday() == 0


class TradeEntryReason(Enum):
    SHOULD_ENTER = "should_enter"
    SKIPPED_VIX = "skipped_vix"
    SKIPPED_DUP_EXP = "skipped_dup_exp"
    NOT_MONDAY = "not_monday"

class Fixed4Strategy(BaseStrategy):
    def should_enter_trade(self, current_date, vix, exp_key, used_expirations):
        if not is_monday(current_date):
            return TradeEntryReason.NOT_MONDAY

        if vix > VIX_NO_TRADE:
            return TradeEntryReason.SKIPPED_VIX

        if exp_key in used_expirations:
            return TradeEntryReason.SKIPPED_DUP_EXP

        return TradeEntryReason.SHOULD_ENTER


    def should_reenter_after_exit(self, trade, vix):
        return trade.exited_at_profit_target and vix <= VIX_NO_TRADE
