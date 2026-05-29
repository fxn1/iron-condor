#!/usr/bin/env python3
"""
strategy_stock_put_spread.py — entry/exit/trade-creation policy for
the stock put spread backtest.

Extends BaseStrategy.  The stock backtest engine (backtest_engine_stocks.py)
calls these methods; the SPX engine is untouched.
"""

from datetime import timedelta
from base_strategy import BaseStrategy, TradeEntryReason
from scanner import ScannerConfig, scan
from put_spread import create_put_spread_from_scan
from config_stocks import *


class StockPutSpreadStrategy(BaseStrategy):
    """
    Entry  : day after earnings + EMA/RSI/support filters (via scanner.py)
    Exit   : handled by PutSpreadTrade.check_exit (profit target, stop, DTE)
    Reentry: no — one trade per stock per earnings cycle
    """

    def __init__(self, price_data, earnings_data):
        """
        price_data    : {ticker: pd.DataFrame}  from cachebt.download_list()
        earnings_data : {ticker: [date, ...]}   from CacheEarnings.get_earnings_dates()
        """
        self.price_data    = price_data
        self.earnings_data = earnings_data
        self.used_expirations = set()
        self.cfg           = ScannerConfig(
            earnings_lookahead_days        = SCAN_EARNINGS_LOOKAHEAD_DAYS,
            ema_period                     = SCAN_EMA_PERIOD,
            ema_trend_days                 = SCAN_EMA_TREND_DAYS,
            rsi_period                     = SCAN_RSI_PERIOD,
            rsi_slope_days                 = SCAN_RSI_SLOPE_DAYS,
            rsi_slope_min                  = SCAN_RSI_SLOPE_MIN,
            support_lookback               = SCAN_SUPPORT_LOOKBACK,
            min_price_above_support_pct    = SCAN_MIN_PRICE_ABOVE_SUPPORT_PCT,
            strike_increment               = SCAN_STRIKE_INCREMENT,
        )

    # ── BaseStrategy: vix not needed for stock strategy ───────────────────

    def set_vix_data(self, vix_data):
        pass   # stock strategy does not use VIX for entry/exit decisions

    # ── scan all tickers for today (called by stock engine, not SPX engine) ─
    def scan_all_tickers(self, current_date):
        """
        Scan every ticker in the universe for today's entry signal.
        Returns list of (ticker, strike) for all that qualify and whose
        expiration is not already in used_expirations.
        Called by backtest_engine_stocks.py instead of should_enter_trade().
        """
        signals = []
        for ticker, price_df in self.price_data.items():
            earnings_dates = self.earnings_data.get(ticker, [])
            if price_df is None or price_df.empty:
                continue
            entered, strike = scan(current_date, price_df, earnings_dates, self.cfg)
            if entered:
                exp_key = (ticker, _get_expiration(current_date).strftime('%Y-%m-%d'))
                if exp_key not in self.used_expirations:
                    signals.append((ticker, strike))
        return signals  # engine iterates and creates one trade per result

    # ── BaseStrategy interface ────────────────────────────────────────────

    def should_enter_trade(self, current_date) -> TradeEntryReason:
        """
        Not used by the stock engine — stock engine calls scan_all_tickers()
        which returns per-ticker signals.  Implemented here to satisfy the
        abstract base; raises clearly if called by mistake.
        """
        raise NotImplementedError(
            "StockPutSpreadStrategy uses scan_all_tickers(). "
            "should_enter_trade() is for the SPX engine only."
        )

    def should_reenter_after_exit(self, trade):
        """No re-entry for stock put spreads — one trade per earnings cycle."""
        return False   # one trade per stock per earnings cycle

    def mark_expiration_used(self, trade):
        exp_key = (trade.ticker, trade.expiration_date.strftime('%Y-%m-%d'))
        self.used_expirations.add(exp_key)

    def check_expiration_used(self, current_date) -> bool:
        '''stock strategy does not prevent multiple trades on same expiration date, since different tickers can have same expiration date.  Instead, check in scan_all_tickers() for each ticker + expiration combination.'''
        return False   # stock strategy does not prevent multiple trades on same expiration date

    # ── trade creation ────────────────────────────────────────────────────

    def create_trade(self, current_date, spx_price, volatility, trade_id):
        """
        Not used by the stock engine — stock engine calls create_stock_trade()
        which takes ticker + strike.  Implemented here to satisfy the abstract
        base; raises clearly if called by mistake.
        """
        raise NotImplementedError(
            "StockPutSpreadStrategy uses create_stock_trade(). "
            "create_trade() is for the SPX engine only."
        )

    @staticmethod
    def create_stock_trade(ticker, current_date, price, volatility, strike, trade_id):
        """
        Build a PutSpreadTrade from scanner-supplied strike.
        Called by backtest_engine_stocks.py after scan_all_tickers() signals.
        """
        expiration = _get_expiration(current_date)
        return create_put_spread_from_scan(
            entry_date        = current_date,
            expiration_date   = expiration,
            spx_price         = price,
            vix               = 0.0,           # not used in PutSpreadTrade
            short_strike      = strike,
            volatility        = volatility,
            trade_id          = trade_id,
            wing_width        = STOCK_WING_WIDTH,
            profit_target_pct = STOCK_PROFIT_TARGET,
            num_contracts     = STOCK_NUM_CONTRACTS
        )


# ── expiration helper ─────────────────────────────────────────────────────

def _get_expiration(entry_date):
    """Next standard expiration approximately STOCK_TARGET_DTE days out."""
    target = entry_date + timedelta(days=STOCK_TARGET_DTE)
    # Roll to next Friday
    days_to_friday = (4 - target.weekday()) % 7
    friday = target + timedelta(days=days_to_friday)
    if friday <= entry_date:
        friday += timedelta(days=7)
    return friday
