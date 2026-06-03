#!/usr/bin/env python3
"""
strategy_stock_put_spread.py — entry/exit/trade-creation policy for
the stock put spread backtest.
Owns all market data: price history and earnings per ticker.
Engine calls identical interface as SPX strategy.

Extends BaseStrategy.  The stock backtest engine (backtest_engine_stocks.py)
calls these methods; the SPX engine is untouched.
"""

import os
from datetime import timedelta, date
import pandas as pd
from backtest_engine import run_main
from base_strategy import BaseStrategy, TradeSignal, TradeEntryReason
from CacheDailyOHLCV import CachedailyOHLCV, get_spy_ticker_list
from CacheEarning import EarningsCache
from volatility import calculate_historical_volatility
from scanner import ScannerConfig, scan
from put_spread import create_put_spread_from_scan
from config_stocks import *


class StockPutSpreadStrategy(BaseStrategy):
    """
    Entry  : day after earnings + EMA/RSI/support filters (via scanner.py)
    Exit   : handled by PutSpreadTrade.check_exit (profit target, stop, DTE)
    Reentry: no — one trade per stock per earnings cycle
    """

    def __init__(self):
        """
        price_data    : {ticker: pd.DataFrame}  from cachebt.download_list()
        earnings_data : {ticker: [date, ...]}   from CacheEarnings.get_earnings_dates()
        """
        self.price_data      = {}
        self.earnings_data   = {}
        self.used_expirations = set()
        self.sorted_dates     = {}    # {ticker: [date_str, ...]}
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

    # ── BaseStrategy: ───────────────────

    def _price(self, ticker, date_str) -> float:
        df = self.price_data[ticker]
        ts = pd.Timestamp(date_str)
        return float(df.loc[ts, 'Close']) if ts in df.index else 0.0

    def _volatility(self, ticker, date_str) -> float:
        dates = self.sorted_dates.get(ticker, [])
        if date_str not in dates:
            return 0.18
        idx = dates.index(date_str)
        if idx < 20:
            return 0.18
        df = self.price_data[ticker]
        hist = [float(df.loc[pd.Timestamp(d), 'Close']) for d in dates[idx - 20:idx + 1]]
        return calculate_historical_volatility(hist) * STOCK_VOL_SCALAR

    # ── BaseStrategy interface ────────────────────────────────────────────
    # ── inherited functions called by backtest_engine
    def load_data(self, start_date, delta_days):
        sp500_list = get_spy_ticker_list()
        sp500_list = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'JPM', 'V', 'UNH']  # TODO: expand as needed

        print("  Loading stock price data...")
        cache = CachedailyOHLCV(path=DATA_PATH, start_date=start_date, delta_days=delta_days)
        self.price_data = cache.download_list(sp500_list)
        print(f"  ✓ Loaded {len(self.price_data)} tickers")

        print("  Loading earnings data...")
        earnings_cache = EarningsCache(path=DATA_PATH)
        self.earnings_data = {t: earnings_cache.get_earnings_dates(t) for t in sp500_list}
        print(f"  ✓ Loaded earnings for {len(self.earnings_data)} tickers")

        # precompute sorted date lists per ticker for vol lookback
        for ticker, df in self.price_data.items():
            self.sorted_dates[ticker] = sorted(df.index.strftime('%Y-%m-%d').tolist())

    # ── scan all tickers for today (called by stock engine, not SPX engine) ─
    def should_enter_trades(self, current_date) -> list[TradeSignal]:
        """
        Scan every ticker in the universe for today's entry signal.
        Returns list of (ticker, strike) for all that qualify and whose
        expiration is not already in used_expirations.
        Called by backtest_engine_stocks.py instead of should_enter_trade().
        """
        date_str = current_date.strftime('%Y-%m-%d')
        current_day = current_date.date()
        signals = []
        for ticker, price_df in self.price_data.items():
            earnings_dates = self.earnings_data.get(ticker, [])
            if pd.Timestamp(date_str) not in price_df.index:
                continue
            entered, strike = scan(current_day, price_df, earnings_dates, self.cfg)
            if entered:
                exp_key = (ticker, _get_expiration(current_date).strftime('%Y-%m-%d'))
                if exp_key not in self.used_expirations:
                    signals.append(TradeSignal(reason=TradeEntryReason.SHOULD_ENTER, ticker=ticker, strike=strike))
                else:
                    signals.append(TradeSignal(reason=TradeEntryReason.SKIPPED_DUP_EXP, ticker=ticker))
            else:
                signals.append(TradeSignal(reason=TradeEntryReason.NO_SIGNAL, ticker=ticker))
        return signals  # engine iterates and creates one trade per result

    def should_reenter_after_exit(self, trade) -> TradeSignal:
        """No re-entry for stock put spreads — one trade per earnings cycle."""
        return TradeSignal(reason=TradeEntryReason.SKIPPED_VIX)

    def mark_expiration_used(self, trade):
        exp_key = (trade.ticker, trade.expiration_date.strftime('%Y-%m-%d'))
        self.used_expirations.add(exp_key)

    def mark_reentry_expiration_used(self, current_date):
        pass  # no re-entry for stocks

    def create_trade(self, current_date, trade_id, signal: TradeSignal):
        """
        Build a PutSpreadTrade from scanner-supplied strike.
        Called by backtest_engine_stocks.py after scan_all_tickers() signals.
        """
        ticker = signal.ticker
        date_str = current_date.strftime('%Y-%m-%d')
        price = self._price(ticker, date_str)
        volatility = self._volatility(ticker, date_str)
        expiration = _get_expiration(current_date)
        return create_put_spread_from_scan(
            entry_date        = current_date,
            expiration_date   = expiration,
            spx_price         = price,
            vix               = 0.0,           # not used in PutSpreadTrade
            short_strike      = signal.strike,
            volatility        = volatility,
            trade_id          = trade_id,
            wing_width        = STOCK_WING_WIDTH,
            profit_target_pct = STOCK_PROFIT_TARGET,
            num_contracts     = STOCK_NUM_CONTRACTS,
            ticker            = ticker,
        )

    def get_market_data(self, trade, date_str) -> dict:
        ticker     = trade.ticker
        df         = self.price_data[ticker]
        row        = df.loc[pd.Timestamp(date_str)] if date_str in df.index else None
        close      = float(row['Close']) if row is not None else 0.0
        volatility = self._volatility(ticker, date_str)
        return {
            'close':      close,
            'high':       float(row['High'])  if row is not None else close,
            'low':        float(row['Low'])   if row is not None else close,
            'open':       float(row['Open'])  if row is not None else close,
            'vix':        0.0,
            'volatility': volatility,
            'put_vol':    volatility * 1.10,
            'call_vol':   volatility * 0.95,
        }

    def check_expiration_used(self, current_date) -> bool:
        """stock strategy does not prevent multiple trades on same expiration date, since different tickers can have same expiration date.  Instead, check in scan_all_tickers() for each ticker + expiration combination."""
        return False   # stock strategy does not prevent multiple trades on same expiration date

    def get_trading_dates(self, start_date, end_date) -> list:
        from datetime import datetime, time
        # TODO: get rid of isinsrance
        if not isinstance(start_date, datetime):
            start_date = datetime.combine(start_date, time.min)
        if not isinstance(end_date, datetime):
            end_date = datetime.combine(end_date, time.max)
        first = next(iter(self.sorted_dates.values()))
        dates = [datetime.strptime(d, '%Y-%m-%d') for d in first]
        return [d for d in dates if start_date <= d <= end_date]

    def print_strategy_config(self):
        print(f"  Strategy:    Stock Put Spread  (wing ${STOCK_WING_WIDTH}, {STOCK_TARGET_DTE} DTE)")
        print(f"  Entry:       Day after earnings, EMA({SCAN_EMA_PERIOD}) up, RSI slope > {SCAN_RSI_SLOPE_MIN}")
        print(f"  Support:     {SCAN_SUPPORT_LOOKBACK}-day rolling low, strike increment ${SCAN_STRIKE_INCREMENT}")
        print(f"  Profit target: {int(STOCK_PROFIT_TARGET * 100)}%  Stop: {STOCK_STOP_LOSS_MULT}x credit")
        print(f"  Capital:      ")

    def print_extra_results(self, results, years):
        from reporting import print_stock_results
        print_stock_results(results, years)

    def fill_expiration_price(self, trade):
        pass
    # ── internal helpers ────────────────────────────────────────────

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


def _get_expiration(entry_date):
    """Next standard expiration approximately STOCK_TARGET_DTE days out."""
    target = entry_date + timedelta(days=STOCK_TARGET_DTE)
    # Roll to next Friday
    days_to_friday = (4 - target.weekday()) % 7
    friday = target + timedelta(days=days_to_friday)
    if friday <= entry_date:
        friday += timedelta(days=7)
    return friday


SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
DATA_PATH      = os.environ.get('YFDATA', os.path.join(SCRIPT_DIR, 'yfdatas'))


if __name__ == "__main__":
    BACKTEST_START_DATE = date.fromisoformat("2000-01-01")
    BACKTEST_START_DATE = date.today() - timedelta(days=3)
    fix_delta_days = 365*4

    strategy = StockPutSpreadStrategy()

    run_main(
        strategy      = strategy,
        title         = "PUT SPREAD ON STOCKS",
        script_name   = "Options_Using_SPX_10_NetDelta_Fixed4.py",  # for consistent naming in reports
        csv_filename  = "Stock_Put_Spread_10Year_Backtest.csv",
        start_date    = BACKTEST_START_DATE,
        delta_days    =fix_delta_days,
        extra_summary_lines = lambda r: [
            f"total trades: {r['total_trades']:^22}|",
            f"win rate:     {r['win_rate']:^22.2%}|",
        ],
    )
