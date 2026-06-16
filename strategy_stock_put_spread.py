#!/usr/bin/env python3
"""
strategy_stock_put_spread.py — entry/exit/trade-creation policy for
the stock put spread backtest.
Owns all market data: price history and earnings per ticker.
Engine calls identical interface as SPX strategy.

Extends BaseStrategy.  The stock backtest engine (backtest_engine_stocks.py)
calls these methods; the SPX engine is untouched.
"""

from datetime import datetime
import pandas as pd
from backtest_engine import run_main
from base_strategy import BaseStrategy, TradeSignal, TradeEntryReason, get_next_friday
from CacheDailyOHLCV import CachedailyOHLCV, get_spy_ticker_list
from CacheEarning import EarningsCache
from volatility import calculate_historical_volatility
from scanner import scan
from put_spread import create_put_spread_from_scan
from config import gcfg


def log(msg=""):
    print(f"{datetime.now()}  {msg}")


class StockPutSpreadStrategy(BaseStrategy):
    """
    Entry  : day after earnings + EMA/RSI/support filters (via scanner.py)
    Exit   : handled by PutSpreadTrade.check_exit (profit target, stop, DTE)
    Reentry: no — one trade per stock per earnings cycle
    """

    def __init__(self):
        """
        price_data    : {ticker: pd.DataFrame}  from cachebt.download_list()
        """
        super().__init__()
        self.cfg             = gcfg.stocks
        self.price_data      = {}
        self.earnings_cache  = None
        self.sorted_dates     = {}    # {ticker: [sorted list of dates in price_data]}
        self._vol_debug_count = 0   # TODO: debug

    # ── BaseStrategy: ───────────────────

    def _volatility(self, ticker, ts: pd.Timestamp) -> float:
        dates = self.sorted_dates.get(ticker, [])
        if ts not in dates:
            return -1
        idx = dates.index(ts)
        if idx >= 20:
            df = self.price_data[ticker]
            window = dates[idx - 20: idx + 1]
            hist = [float(df.loc[d, 'Close']) for d in window]
            hv = calculate_historical_volatility(hist)
            vol = hv * self.cfg.vol_scalar
            # TODO: debug
            if ticker in gcfg.stocks.debug_tickers:
                log(f"{ts.date()} {ticker} hv={hv:.3f}")
            if self._vol_debug_count < gcfg.stocks.debug_trade_id:
                print(
                    f"VOL {self._vol_debug_count + 1}: "
                    f"{ticker} "
                    f"{ts.date()} "
                    f"hv={hv:.3f} "
                    f"scalar={self.cfg.vol_scalar:.2f} "
                    f"vol={vol:.3f}"
                )
                self._vol_debug_count += 1
            return vol
        return 0.18

    # ── BaseStrategy interface ────────────────────────────────────────────
    # ── inherited functions called by backtest_engine
    def load_data(self, start_date, delta_days):
        sp500_list = get_spy_ticker_list()
        log(" Loading stock price data...")
        cache = CachedailyOHLCV(path=gcfg.paths.yf_data_path, start_date=start_date, delta_days=delta_days)
        self.price_data = cache.download_list(sp500_list)
        log(f"  ✓ Loaded {len(self.price_data)} tickers")

        self.earnings_cache = EarningsCache(path=gcfg.paths.yf_data_path)
        # earnings_cache.download_list(sp500_list)  # TODO: manual run for now

        # precompute sorted date lists per ticker for vol lookback
        for ticker, df in self.price_data.items():
            self.sorted_dates[ticker] = sorted(df.index.normalize().tolist())

    # ── scan all tickers for today (called by stock engine, not SPX engine) ─
    def should_enter_trades(self, current_date) -> list[TradeSignal]:
        """
        Scan every ticker in the universe for today's entry signal.
        Returns list of (ticker, strike) for all that qualify and whose
        expiration is not already used for this ticker.  Engine creates one trade per signal.
        Called by backtest_engine_stocks.py instead of should_enter_trade().
        """
        if self.cfg.entry_weekday != "ALL":
            weekday = current_date.strftime("%A").upper()
            if weekday != self.cfg.entry_weekday.upper():
                return [TradeSignal(reason=TradeEntryReason.NOT_WEEKDAY)]
        if 0 <= self.cfg.vix_no_trade < self._vix(current_date):
            return [TradeSignal(reason=TradeEntryReason.SKIPPED_VIX)]
        signals = []
        for ticker, price_df in self.price_data.items():
            earnings_dates = self.earnings_cache.get_earnings_dates(ticker)
            # log(f" Loaded  {len(earnings_dates)} earnings for ticker={ticker}")
            entered, strike = scan(current_date, price_df, earnings_dates, self.cfg)
            if entered:
                if not self.check_expiration_used(current_date, ticker):
                    if strike - self.cfg.wing_width > self.cfg.min_long_strike:
                        signals.append(TradeSignal(reason=TradeEntryReason.SHOULD_ENTER, ticker=ticker, strike=strike))
                    else:
                        signals.append(TradeSignal(reason=TradeEntryReason.SKIPPED_LOW_STRIKE, ticker=ticker))
                else:
                    signals.append(TradeSignal(reason=TradeEntryReason.SKIPPED_DUP_EXP, ticker=ticker))
            else:
                signals.append(TradeSignal(reason=TradeEntryReason.NO_SIGNAL, ticker=ticker))
        return signals  # engine iterates and creates one trade per result

    def should_reenter_after_exit(self, trade) -> TradeSignal:
        """No re-entry for stock put spreads — one trade per earnings cycle."""
        return TradeSignal(reason=TradeEntryReason.NO_SIGNAL)

    def _exp_key(self, current_date, ticker):
        return ticker, get_next_friday(current_date, self.cfg.target_dte)

    def create_trade(self, current_date, trade_id, signal: TradeSignal):
        """
        Build a PutSpreadTrade from scanner-supplied strike.
        Called by backtest_engine_stocks.py after scan_all_tickers() signals.
        """
        ticker = signal.ticker
        volatility = self._volatility(ticker, current_date)
        expiration = get_next_friday(current_date, self.cfg.target_dte)
        return create_put_spread_from_scan(
            ticker            = ticker,
            entry_date        = current_date,
            expiration_date   = expiration,
            spx_price_df      = self.price_data[ticker],
            vix               = 0.0,           # not used in PutSpreadTrade
            short_strike      = signal.strike,
            volatility        = volatility,
            trade_id          = trade_id,
            cfg               = self.cfg,
        )

    def get_market_data(self, trade, ts: pd.Timestamp) -> dict:
        ticker     = trade.ticker
        df         = self.price_data[ticker]
        row        = df.loc[ts] if ts in df.index else None
        close      = float(row['Close']) if row is not None else 0.0
        volatility = self._volatility(ticker, ts)
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

    def get_trading_dates(self, start_date, end_date) -> list:
        sorted_dates = next(iter(self.sorted_dates.values()))
        dates = [pd.Timestamp(d) for d in sorted_dates]
        return [d for d in dates if start_date <= d <= end_date]

    def print_strategy_config(self):
        log(f"  Strategy:    Stock Put Spread  (wing ${self.cfg.wing_width}, {self.cfg.target_dte} DTE)")
        log(f"  Entry:       Day after earnings, EMA({self.cfg.ema_period}) up, RSI slope > {self.cfg.rsi_slope_min}")
        log(f"  Support:     {self.cfg.support_lookback}-day rolling low, strike increment ${self.cfg.strike_increment}")
        log(f"  Profit target: {int(self.cfg.profit_target * 100)}%  Stop: {self.cfg.stop_loss_mult}x credit")
        log(f"  Capital:      ")

    def print_extra_results(self, results, years):
        pass

    def fill_expiration_price(self, trade):
        pass
    # ── internal helpers ────────────────────────────────────────────


if __name__ == "__main__":
    run_main(
        strategy      = StockPutSpreadStrategy(),
        title         = "PUT SPREAD ON STOCKS",
        script_name   = "Scanner_Put_Spread.py",  # for consistent naming in reports
        csv_filename  = "Stock_Put_Spread_Backtest.csv",
        start_date    = datetime(2022, 6, 1),
        end_date      = datetime(2026, 5, 9),
    )
