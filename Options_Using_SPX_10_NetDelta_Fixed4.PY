#!/usr/bin/env python3
"""
================================================================================
SPX IRON CONDOR - 10 YEAR BACKTEST
Owns all market data lookups: price, vol, vix.  Engine is data-free.
SPX iron condor, net-delta rolls, fixed ×5 capital sizing.

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
from backtest_engine import run_main
from base_strategy import BaseStrategy, get_next_friday, is_monday, TradeEntryReason, TradeSignal
from volatility import calculate_historical_volatility
from pricing import black_scholes_price, find_strike_for_delta
from trade import IronCondorTrade
from config import *


# ============================================================================
# STRATEGY
# ============================================================================

class Fixed4Strategy(BaseStrategy):
    """
    SPX Iron Condor — Net-Delta Roll Management, Fixed ×5 capital variant.
    Capital sized to a fixed assumption of CONCURRENT_TRADES (=5) concurrent trades.
    See backtest_engine.py for the shared engine.
    """

    def __init__(self):
        self.vix_data = {}
        self.spx_data = {}
        self.sorted_dates = []
        self.used_expirations = set()

    # ── data injection (called by run_main after loading) ─────────────────

    def set_vix_data(self, vix_data):
        self.vix_data = vix_data

    def set_spx_data(self, spx_data):
        self.spx_data     = spx_data
        self.sorted_dates = sorted(spx_data.keys())

    # ── internal helpers ──────────────────────────────────────────────────

    # ── BaseStrategy interface ────────────────────────────────────────────

    # BaseStrategy — unified interface engine calls
    def should_enter_trades(self, current_date) -> list[TradeSignal]:
        return [self.should_enter_trade(current_date)]

    def should_reenter_after_exit(self, trade) -> TradeSignal:
        if trade.exited_at_profit_target and self._vix(trade.exit_date) <= VIX_NO_TRADE:
            return TradeSignal(reason=TradeEntryReason.SHOULD_ENTER)
        return TradeSignal(reason=TradeEntryReason.SKIPPED_VIX)

    def should_enter_trade(self, current_date) -> TradeSignal:
        if not is_monday(current_date):
            return TradeSignal(reason=TradeEntryReason.NOT_MONDAY)
        if self._vix(current_date) > VIX_NO_TRADE:
            return TradeSignal(reason=TradeEntryReason.SKIPPED_VIX)
        if self._exp_key(current_date) in self.used_expirations:
            return TradeSignal(reason=TradeEntryReason.SKIPPED_DUP_EXP)
        return TradeSignal(reason=TradeEntryReason.SHOULD_ENTER)

    def _vix(self, current_date):
        # TODO: fix caller
        date_str = current_date if isinstance(current_date, str) else current_date.strftime('%Y-%m-%d')
        return self.vix_data[date_str]['close'] if date_str in self.vix_data else 18.0

    @staticmethod
    def _exp_key(current_date):
        return get_next_friday(current_date, TARGET_DTE).strftime('%Y-%m-%d')

    def mark_expiration_used(self, trade):
        self.used_expirations.add(trade.expiration_date.strftime('%Y-%m-%d'))

    def mark_reentry_expiration_used(self, current_date):
        self.used_expirations.add(self._exp_key(current_date))

    def check_expiration_used(self, current_date) -> bool:
        return self._exp_key(current_date) in self.used_expirations

    def _volatility(self, date_str) -> float:
        idx = self.sorted_dates.index(date_str) if date_str in self.sorted_dates else -1
        if idx >= 20:
            hist = [self.spx_data[d]['close'] for d in self.sorted_dates[idx - 20:idx + 1]]
            return calculate_historical_volatility(hist)
        return 0.18

    def get_trading_dates(self, start_date, end_date) -> list:
        from datetime import datetime
        dates = [datetime.strptime(d, '%Y-%m-%d') for d in self.sorted_dates]
        return [d for d in dates if start_date <= d <= end_date]

    def print_strategy_config(self):
        print(f"  Strategy:    18/14 Delta Iron Condor on SPX  (wing ${WING_WIDTH})")
        print(f"  Roll rule:   |net delta| > {NET_DELTA_ROLL}  (warn at +/-{NET_DELTA_WARN})")

    def get_market_data(self, trade, date_str) -> dict:
        bar        = self.spx_data.get(date_str, {})
        close      = bar.get('close', 0)
        volatility = self._volatility(date_str)
        return {
            'close':      close,
            'high':       bar.get('high',  close),
            'low':        bar.get('low',   close),
            'open':       bar.get('open',  close),
            'vix':        self._vix(date_str),
            'volatility': volatility,
            'put_vol':    volatility * 1.10,
            'call_vol':   volatility * 0.95,
        }

    def create_trade(self, current_date, trade_id, signal: TradeSignal):
        date_str   = current_date.strftime('%Y-%m-%d')
        bar        = self.spx_data.get(date_str, {})
        spx_price  = bar.get('close', 0)
        volatility = self._volatility(date_str)
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

        cs = black_scholes_price(spx_price, call_short, T, RISK_FREE_RATE, call_vol, 'call')
        cl = black_scholes_price(spx_price, call_long,  T, RISK_FREE_RATE, call_vol, 'call')

        return IronCondorTrade(
            entry_date=current_date,
            expiration_date=expiration,
            spx_price=spx_price,
            vix=self._vix(current_date),
            put_short=put_short,
            put_long=put_long,
            put_credit=ps - pl,
            call_short=call_short,
            call_long=call_long,
            call_credit=cs - cl,
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
