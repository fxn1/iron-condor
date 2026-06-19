#!/usr/bin/env python3
"""
scan_today.py — daily scanner for stock put spread paper trading.

Runs the entry scanner for today and the past N days without
executing the full backtest loop. Prints all signals with
strike, credit estimate, and expiration.

Usage:
    python scan_today.py              # scans last 5 trading days
    python scan_today.py --days 10    # scans last 10 trading days
    python scan_today.py --date 2026-06-10  # scans a specific date only
"""

import argparse
import sys
from datetime import datetime, timedelta

import pandas as pd

from base_strategy import TradeEntryReason
from config import gcfg
from strategy_stock_put_spread import StockPutSpreadStrategy


def log(msg=""):
    print(f"{datetime.now()}  {msg}")


def scan_date(strategy, current_date, cfg):
    """Scan all tickers for a single date. Returns list of signal dicts."""
    signals = []

    trade_id = 0
    for signal in strategy.should_enter_trades(current_date):
        if signal.reason != TradeEntryReason.SHOULD_ENTER:
            continue

        trade_id += 1
        new_trade = strategy.create_trade(current_date, trade_id, signal)

        if 0 <= strategy.cfg.min_credit and new_trade.credit < strategy.cfg.min_credit:
            continue

        otm_pct = (1 - new_trade.short_strike/new_trade.spx_price_at_entry) * 100
        long_strike = new_trade.spx_price_at_entry - cfg.wing_width

        signals.append({
            'Date':        current_date.strftime('%Y-%m-%d'),
            'Ticker':      new_trade.ticker,
            'Price':       round(new_trade.spx_price_at_entry, 2),
            'Short':       new_trade.short_strike,
            'Long':        long_strike,
            'OTM%':        round(otm_pct, 1),
            'Credit':      round(new_trade.credit, 2),
            'Max_Loss':    round((cfg.wing_width - new_trade.credit) * 100, 2),
            'Expiration':  new_trade.expiration_date.strftime('%Y-%m-%d'),
            'DTE':         (new_trade.expiration_date - current_date).days,
            'Vol_10d':     new_trade.volume_10med_at_entry,
        })

    return signals


def main():
    parser = argparse.ArgumentParser(description='Stock put spread daily scanner')
    parser.add_argument('--days',  type=int, default=20,    help='Number of past trading days to scan (default: 20)')
    parser.add_argument('--end_date',  type=str, default=None, help='Scan days before end_date (YYYY-MM-DD)')
    args = parser.parse_args()

    cfg = gcfg.stocks

    # ── determine dates to scan ──────────────────────────────────────────
    delta_days = 365  # 1 year of price history is enough for indicators. need at least 20 days for vol + buffer for non-trading days, earnings, etc.
    today      = datetime.today()
    # end_date   = pd.Timestamp(args.end_date) if args.end_date else pd.Timestamp(datetime.today())
    end_date = datetime(2026, 5, 9)
    # if run on a weekend, roll back to the prior Friday
    if end_date.weekday() == 5:  # Saturday
        end_date -= timedelta(days=1)
    elif end_date.weekday() == 6:  # Sunday
        end_date -= timedelta(days=2)
    # days       = args.days
    days = 3
    start_date = end_date - timedelta(days=days)  # scan start date
    load_date = end_date - timedelta(days=delta_days)  # load start date
    log(f"Scanning today={today}, delta_days={delta_days}, start_date={start_date.date()}, end_date={end_date.date()}, load_date={load_date.date()}")

    strategy = StockPutSpreadStrategy()  # for access to config parameters only
    strategy.load_data(load_date, delta_days)  # load to set up price_data and sorted_dates for volatility calculation

    # ── scan each date ───────────────────────────────────────────────────
    all_signals = []
    scan_dates = strategy.get_trading_dates(start_date, end_date)
    for d in scan_dates:
        log(f"Scanning {d.date()}...")
        day_signals = scan_date(strategy, d, cfg)
        all_signals.extend(day_signals)
        log(f"  → {len(day_signals)} signals")

    # ── print results ────────────────────────────────────────────────────
    log()
    log("=" * 90)
    log("  SCANNER SIGNALS")
    log("=" * 90)

    if not all_signals:
        log("  No signals found.")
        return

    # header
    log(f"  {'Date':<12} {'Ticker':<8} {'Price':>8} {'Short':>7} {'Long':>6} "
          f"{'OTM%':>6} {'Credit':>7} {'MaxLoss':>8} {'Expiration':<12} {'DTE':>4} {'Vol10d':>12}")
    log(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*7} {'-'*6} "
          f"{'-'*6} {'-'*7} {'-'*8} {'-'*12} {'-'*4} {'-'*12}")

    for s in sorted(all_signals, key=lambda x: (x['Date'], x['Ticker'])):
        log(f"  {s['Date']:<12} {s['Ticker']:<8} {s['Price']:>8.2f} {s['Short']:>7.0f} "
              f"{s['Long']:>6.0f} {s['OTM%']:>5.1f}% {s['Credit']:>7.2f} "
              f"{s['Max_Loss']:>8.2f} {s['Expiration']:<12} {s['DTE']:>4} "
              f"{s['Vol_10d']:>12,}")

    log()
    log(f"  Total signals: {len(all_signals)} across {len(scan_dates)} trading days")
    log()

    # ── summary by date ──────────────────────────────────────────────────
    log("  SIGNALS PER DAY")
    log(f"  {'-'*40}")
    df = pd.DataFrame(all_signals)
    by_date = df.groupby('Date').agg(
        Signals   = ('Ticker',  'count'),
        Avg_OTM   = ('OTM%',    'mean'),
        Avg_Credit= ('Credit',  'mean'),
        Tickers   = ('Ticker',  lambda x: ', '.join(sorted(x)))
    ).round(2)
    for date, row in by_date.iterrows():
        log(f"  {date}  {row['Signals']:>3} signals  "
              f"avg OTM {row['Avg_OTM']:.1f}%  avg credit ${row['Avg_Credit']:.2f}")
        log(f"    {row['Tickers']}")
    log()


if __name__ == "__main__":
    main()
