#!/usr/bin/env python3
"""
================================================================================
SPX IRON CONDOR - 10 YEAR BACKTEST

Inputs:
    * Real SPX 1-min data: spx_2016.xlsx ... spx_2026.xlsx
    * VIX_Daily_Data.xlsx from sibling SPY-DELTA folder

Output:
    * SPX_IronCondor_10Year_NetDelta_Fixed4_Backtest.csv
    * Console report with roll statistics + yearly breakdown

Author: Claude (adapted for PEC)
Date: May 2026
================================================================================
"""
import pandas as pd

from config import *
from backtest_engine import run_main
from base_strategy import BaseStrategy, get_next_friday, is_monday, TradeEntryReason
from pricing import black_scholes_price, find_strike_for_delta
from trade import IronCondorTrade


class Fixed4Strategy(BaseStrategy):
    """
    SPX Iron Condor — Net-Delta Roll Management, Fixed ×5 capital variant.
    Capital sized to a fixed assumption of CONCURRENT_TRADES (=5) concurrent trades.
    See backtest_engine.py for the shared engine.
    """

    def __init__(self):
        self.vix_data = {}
        self.used_expirations = set()

    def set_vix_data(self, vix_data):
        self.vix_data = vix_data

    def should_enter_trade(self, current_date):
        if not is_monday(current_date):                             return TradeEntryReason.NOT_MONDAY
        if self._vix(current_date) > VIX_NO_TRADE:                  return TradeEntryReason.SKIPPED_VIX
        if self._exp_key(current_date) in self.used_expirations:    return TradeEntryReason.SKIPPED_DUP_EXP
        return TradeEntryReason.SHOULD_ENTER

    def should_reenter_after_exit(self, trade):
        return trade.exited_at_profit_target and self._vix(trade.exit_date) <= VIX_NO_TRADE

    def _vix(self, current_date):
        date_str = current_date.strftime('%Y-%m-%d')
        return self.vix_data[date_str]['close'] if date_str in self.vix_data else 18.0

    @staticmethod
    def _exp_key(current_date):
        return get_next_friday(current_date, TARGET_DTE).strftime('%Y-%m-%d')

    def mark_expiration_used(self, trade):
        self.used_expirations.add(trade.expiration_date.strftime('%Y-%m-%d'))

    def check_expiration_used(self, current_date) -> bool:
        return self._exp_key(current_date) in self.used_expirations

    def create_trade(self, current_date, spx_price, volatility, trade_id):
        expiration = get_next_friday(current_date, TARGET_DTE)
        dte        = (expiration - current_date).days
        T          = dte / 365.0
        put_vol    = volatility * 1.10
        call_vol   = volatility * 0.95

        put_short  = find_strike_for_delta(spx_price, PUT_DELTA,  T, RISK_FREE_RATE, put_vol,  'put')
        put_long   = put_short - WING_WIDTH
        call_short = find_strike_for_delta(spx_price, CALL_DELTA, T, RISK_FREE_RATE, call_vol, 'call')
        call_long  = call_short + WING_WIDTH

        ps = black_scholes_price(spx_price, put_short,  T, RISK_FREE_RATE, put_vol,  'put')
        pl = black_scholes_price(spx_price, put_long,   T, RISK_FREE_RATE, put_vol,  'put')
        put_credit  = ps - pl

        cs = black_scholes_price(spx_price, call_short, T, RISK_FREE_RATE, call_vol, 'call')
        cl = black_scholes_price(spx_price, call_long,  T, RISK_FREE_RATE, call_vol, 'call')
        call_credit = cs - cl

        return IronCondorTrade(
            entry_date=current_date,
            expiration_date=expiration,
            spx_price=spx_price,
            vix=self._vix(current_date),
            put_short=put_short,
            put_long=put_long,
            put_credit=put_credit,
            call_short=call_short,
            call_long=call_long,
            call_credit=call_credit,
            num_contracts=NUM_CONTRACTS,
            trade_id=trade_id,
        )


if __name__ == "__main__":
    run_main(
        strategy      = Fixed4Strategy(),
        title         = "NET-DELTA + FIXED *5 CAPITAL",
        script_name   = "Options_Using_SPX_10_NetDelta_Fixed4.PY",
        capital_label = f"Capital:      fixed assumption of {CONCURRENT_TRADES} concurrent trades",
        csv_filename  = "SPX_IronCondor_10Year_NetDelta_Fixed4_Backtest.csv",
        extra_summary_lines = lambda r: [
            f"  |{'(fixed {} concurrent)'.format(CONCURRENT_TRADES):^30}"
            f"{'peak obs: {}'.format(r['max_concurrent']):^30}|",
        ],
    )
