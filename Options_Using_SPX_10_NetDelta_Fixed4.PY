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
import os
from datetime import timedelta, datetime
import pandas as pd
from backtest_engine import run_main
from data_loader import load_spx_daily_from_minute_files, load_vix_data_from_excel
from base_strategy import BaseStrategy, get_next_friday,  TradeEntryReason, TradeSignal
from volatility import calculate_historical_volatility
from pricing import black_scholes_price, find_strike_for_delta
from trade import IronCondorTrade
from config import gcfg


def log(msg=""):
    print(f"{datetime.now()}  {msg}")

# ============================================================================
# STRATEGY
# ============================================================================


SPX_TICKER='SPX'
class Fixed4Strategy(BaseStrategy):
    """
    SPX Iron Condor — Net-Delta Roll Management, Fixed ×5 capital variant.
    See backtest_engine.py for the shared engine.
    """

    def __init__(self):
        super().__init__()
        self.cfg = gcfg.spx
        self.spx_data = {}
        self.sorted_dates = []

    # ── data injection (called by run_main after loading) ─────────────────

    # ── BaseStrategy interface ────────────────────────────────────────────

    # BaseStrategy — unified interface engine calls
    def load_data(self, start_date, delta_days):
        VIX_DATA_PATH = os.path.normpath(os.path.join(gcfg.paths.data_path, 'VIX_Daily_Data.xlsx'))
        if not os.path.exists(VIX_DATA_PATH):
            raise FileNotFoundError(VIX_DATA_PATH)

        self.vix_data = load_vix_data_from_excel(VIX_DATA_PATH)
        if self.vix_data is None:
            raise ValueError(f"Failed to load VIX data from {VIX_DATA_PATH}")
        log(f"  Loaded {len(self.vix_data)} days of VIX data")
        log()

        log("  Loading SPX minute data...")
        end_date = start_date + timedelta(days=delta_days)
        self.spx_data = load_spx_daily_from_minute_files(start_date.year, end_date.year)
        if self.spx_data is None:
            log("  ERROR: could not load SPX data")
            return
        self.sorted_dates = sorted(self.spx_data.keys())
        log(f"  Built {len(self.spx_data)} daily SPX bars")

    def should_enter_trades(self, current_date) -> list[TradeSignal]:
        if self.cfg.entry_weekday != "ALL":
            weekday = current_date.strftime("%A").upper()
            if weekday != self.cfg.entry_weekday.upper():
                return [TradeSignal(reason=TradeEntryReason.NOT_WEEKDAY, ticker=SPX_TICKER)]
        if 0 <= self.cfg.vix_no_trade < self._vix(current_date):
            return [TradeSignal(reason=TradeEntryReason.SKIPPED_VIX, ticker=SPX_TICKER)]
        if not self.check_expiration_used(current_date, SPX_TICKER):
            return [TradeSignal(reason=TradeEntryReason.SHOULD_ENTER, ticker=SPX_TICKER)]
        return [TradeSignal(reason=TradeEntryReason.SKIPPED_DUP_EXP, ticker=SPX_TICKER)]

    def should_reenter_after_exit(self, trade) -> TradeSignal:
        if trade.exited_at_profit_target and self._vix(trade.exit_date) <= self.cfg.vix_no_trade:
            return TradeSignal(reason=TradeEntryReason.SHOULD_ENTER, ticker=SPX_TICKER)
        return TradeSignal(reason=TradeEntryReason.SKIPPED_VIX, ticker=SPX_TICKER)

    def _exp_key(self, current_date, ticker):
        return ticker, get_next_friday(current_date, self.cfg.target_dte)

    def create_trade(self, current_date, trade_id, signal: TradeSignal):
        bar        = self.spx_data.get(current_date, {})
        spx_price  = bar.get('close', 0)
        volatility = self._volatility(current_date)
        expiration = get_next_friday(current_date, self.cfg.target_dte)
        dte        = (expiration - current_date).days
        T          = dte / 365.0
        put_vol    = volatility * 1.10
        call_vol   = volatility * 0.95

        put_short  = find_strike_for_delta(spx_price, self.cfg.put_delta,  T, gcfg.market.risk_free_rate, put_vol,  'put')
        put_long   = put_short - self.cfg.wing_width
        call_short = find_strike_for_delta(spx_price, self.cfg.call_delta, T, gcfg.market.risk_free_rate, call_vol, 'call')
        call_long  = call_short + self.cfg.wing_width

        ps = black_scholes_price(spx_price, put_short,  T, gcfg.market.risk_free_rate, put_vol,  'put')
        pl = black_scholes_price(spx_price, put_long,   T, gcfg.market.risk_free_rate, put_vol,  'put')

        cs = black_scholes_price(spx_price, call_short, T, gcfg.market.risk_free_rate, call_vol, 'call')
        cl = black_scholes_price(spx_price, call_long,  T, gcfg.market.risk_free_rate, call_vol, 'call')

        return IronCondorTrade(
            ticker= SPX_TICKER,
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
            cfg=self.cfg,
            trade_id=trade_id,
        )

    def get_market_data(self, trade, ts: pd.Timestamp) -> dict:
        bar        = self.spx_data.get(ts, {})
        close      = bar.get('close', 0)
        volatility = self._volatility(ts)
        return {
            'close':      close,
            'high':       bar.get('high',  close),
            'low':        bar.get('low',   close),
            'open':       bar.get('open',  close),
            'vix':        self._vix(ts),
            'volatility': volatility,
            'put_vol':    volatility * 1.10,
            'call_vol':   volatility * 0.95,
        }

    def get_trading_dates(self, start_date, end_date) -> list:
        dates = [pd.Timestamp(d) for d in self.sorted_dates]
        return [d for d in dates if start_date <= d <= end_date]

    def print_strategy_config(self):
        log("  STRATEGY")
        log("  " + "-" * 60)
        log(f"  Underlying:    SPX (real 1-min data, resampled to daily)")
        log(f"  Strategy:      18/14 delta IC, ${self.cfg.wing_width} wings, Monday entry, {self.cfg.target_dte} DTE")
        log(f"  Roll rule:     |net delta| > {self.cfg.net_delta_roll}  (warn at +/-{self.cfg.net_delta_warn})")
        log(f"    PUT/CALL Delta:    {self.cfg.put_delta} / {self.cfg.call_delta}")
        log(f"    Profit Target:     {int(self.cfg.profit_target*100)}%")
        log(f"    Stop Loss:         {self.cfg.stop_loss_multiplier}x credit per leg (worst-intraday)")
        log(f"    10 DTE Exit:       Smart exit, gap-aware")
        log(f"    VIX No-Trade:      > {self.cfg.vix_no_trade}")
        log()

    def print_extra_results(self, results, years):
        log("  NET-DELTA MANAGEMENT")
        log("  " + "-" * 60)
        log(f"    Days in Warn band ({self.cfg.net_delta_warn}-{self.cfg.net_delta_roll}):     {results['days_in_warn']}")
        log(f"    Days in Roll zone (>{self.cfg.net_delta_roll}):       {results['days_in_roll_zone']}")
        log(f"    Trades that rolled at least 1x: {results['rolled_trades']}")
        log(f"    Total PUT-side rolls:           {results['total_put_rolls']}")
        log(f"    Total CALL-side rolls:          {results['total_call_rolls']}")
        log(f"    Skipped (VIX > {self.cfg.vix_no_trade}):             {results['trades_skipped_vix']}")
        log()

    def fill_expiration_price(self, trade):
        """Look up SPX price at expiration for reporting.  Falls back to exit price."""
        if trade.spx_price_at_expiration is not None:
            return
        if self.spx_data and trade.expiration_date in self.spx_data:
            trade.spx_price_at_expiration = self.spx_data[trade.expiration_date]['close']
            return
        for offset in range(-3, 4):
            chk = trade.expiration_date + timedelta(days=offset)
            md = self.get_market_data(trade, chk)
            if md['close']:
                trade.spx_price_at_expiration = md['close']
                return
        trade.spx_price_at_expiration = trade.spx_price_at_exit

    def _volatility(self, ts: pd.Timestamp) -> float:
        if ts not in self.sorted_dates:
            return -1
        idx = self.sorted_dates.index(ts)
        if idx >= 20:
            window = self.sorted_dates[idx - 20: idx + 1]
            hist = [self.spx_data[d]['close'] for d in window]
            return calculate_historical_volatility(hist)
        return 0.18


if __name__ == "__main__":
    run_main(
        strategy      = Fixed4Strategy(),
        title         = "SPX BACKTEST NET-DELTA + FIXED *5 CAPITAL",
        script_name   = "Options_Using_SPX_10_NetDelta_Fixed4.PY",
        csv_filename  = "SPX_IronCondor_10Year_NetDelta_Fixed4_Backtest.csv",
        start_date   = datetime(2016, 5, 9),
        end_date     = datetime(2026, 5, 8),
    )
