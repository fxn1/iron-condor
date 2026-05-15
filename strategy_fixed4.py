"""
WITH NET-DELTA ROLL MANAGEMENT
CAPITAL SIZING: FIXED * 5 CONCURRENT (matches observed peak)
================================================================================

This is a sibling of Options_Using_SPX_10_NetDelta.PY with ONE change:
capital sizing uses a fixed multiplier instead of the observed peak.

History of this multiplier:
  1. Original code:  * 4   (reviewer-preferred fixed assumption)
  2. After tracking: peak observed was 5, not 4 -> using 4 understates
     capital ~20% and overstates ROC ~25%.
  3. Current:        * 5   (fixed, matches observed peak so capital is
                            sized for the true worst case the strategy
                            actually demanded)

Keeping the multiplier fixed (rather than data-driven) preserves
comparability across runs - the capital figure won't shift just because
one run happens to hit a busier peak day.

The peak number actually observed each run is still tracked and printed
in the CAPITAL ANALYSIS block so you can verify the * 5 assumption still
holds for the latest run.

Everything else is identical to Options_Using_SPX_10_NetDelta.PY:
    * Net-delta rolls when |net delta| > 15
    * Gap-aware stops (actual gap price) and profit targets (best intraday)
    * Same-day stop-wins-over-profit-target rule
    * 18/14 delta entry, $50 wings, Monday entry, 30 DTE
    * 50% profit target, 10 DTE smart exit, 2x stop loss
    * VIX > 25 skip entry, VIX > 30 close puts
    * Max 3 rolls per side per trade
"""
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
