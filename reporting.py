import csv
from datetime import datetime


# ============================================================================
# OUTPUT
# ============================================================================


def log(msg=""):
    print(f"{datetime.now()}  {msg}")


def print_results(cfg, results, title, years):
    print()
    print("=" * 80)
    print(f"{title} ")
    print("=" * 80)
    print()

    print("  TRADE STATISTICS")
    print("  " + "-" * 60)
    print(f"    Total Trades:           {results['total_trades']}")
    print(f"    Monday Entries:         {results['trades_entered'] - results['reentry_trades']}")
    print(f"    Re-entry Trades:        {results['reentry_trades']}")
    print(f"    Winning Trades:         {results['winning_trades']}")
    print(f"    Losing Trades:          {results['losing_trades']}")
    print(f"    Win Rate:               {results['win_rate']:.1f}%")
    print()

    print("  EXIT REASONS")
    print("  " + "-" * 60)
    for reason, count in sorted(results['exit_reasons'].items(), key=lambda x: -x[1]):
        pct = count / results['total_trades'] * 100 if results['total_trades'] else 0
        print(f"    {reason:<35} {count:>4} ({pct:>5.1f}%)")
    print()

    print("  PROFIT & LOSS")
    print("  " + "-" * 60)
    print(f"    Total P&L:              ${results['total_pnl_dollars']:,.2f}")
    print(f"    Gross Profit:           ${results['gross_profit'] * 100 * results['num_contracts']:,.2f}")
    print(f"    Gross Loss:             ${results['gross_loss']   * 100 * results['num_contracts']:,.2f}")
    print(f"    Profit Factor:          {results['profit_factor']:.2f}")
    print(f"    Avg Win:                ${results['avg_win']  * 100 * results['num_contracts']:,.2f}")
    print(f"    Avg Loss:               ${results['avg_loss'] * 100 * results['num_contracts']:,.2f}")
    print(f"    Max Drawdown:           ${results['max_drawdown_dollars']:,.2f}")
    print()

    print("  CAPITAL ANALYSIS")
    print("  " + "-" * 60)
    if not results['closed_trades']:
        print("    No closed trades. Capital, ROC, and yearly breakdown are not available.")
        print("    Check the strategy date range, loaded market data, and scanner entry filters.")
        print()
        return

    avg_credit = sum(t.cumulative_credit for t in results['closed_trades']) / len(results['closed_trades'])
    margin_per = (cfg.wing_width - avg_credit) * 100
    # Fixed capital sizing using the observed peak concurrent open trades = results['max_concurrent'].
    total_margin = margin_per * results['num_contracts'] * results['max_concurrent']
    annual_pnl = results['total_pnl_dollars'] / years

    print(f"    Avg Credit/Trade:       ${avg_credit:.2f} (incl. rolls)")
    print(f"    Margin per Contract:    ${margin_per:,.2f}")
    print(f"    Peak Observed:          {results['max_concurrent']}  ( matches observed peak)")
    print(f"    Annual P&L:             ${annual_pnl:,.2f}")
    print()

    print("")
    print("  YEARLY BREAKDOWN")
    print("  " + "-" * 60)
    by_year = {}
    for trade in results['closed_trades']:
        by_year.setdefault(trade.entry_date.year, []).append(trade)

    print(f"    {'Year':<6} {'Trades':<8} {'Wins':<6} {'Win%':<8} {'Rolls':<8} {'P&L':<14} {'ROC':<10}")
    print(f"    {'-'*6} {'-'*8} {'-'*6} {'-'*8} {'-'*8} {'-'*14} {'-'*10}")
    for year in sorted(by_year):
        ts = by_year[year]
        n = len(ts)
        w = sum(1 for x in ts if x.pnl > 0)
        rolls = sum(len(x.put_rolls) + len(x.call_rolls) for x in ts)
        wr = w / n * 100 if n else 0
        ypnl = sum(x.pnl for x in ts) * 100 * results['num_contracts']
        yroc = ypnl / total_margin * 100 if total_margin else 0
        print(f"    {year:<6} {n:<8} {w:<6} {wr:<7.1f}% {rolls:<8} ${ypnl:>11,.2f} {yroc:>8.1f}%")
        total_margin += ypnl  # assumes profits are reinvested year-over-year for ROC calculation
    print()


def export_trades_to_csv(results, filename):
    with open(filename, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            'Trade_ID', 'Ticker', 'Entry_Date', 'Expiration', 'Exit_Date', 'DTE',
            'SPX_Entry', 'SPX_Exit', 'SPX_Expiration', 'Volume_Entry', 'VIX_Entry',
            'PUT_Short_Final', 'PUT_Long_Final', 'PUT_Credit_Final', 'PUT_Rolls', 'PUT_Exit',
            'CALL_Short_Final', 'CALL_Long_Final', 'CALL_Credit_Final', 'CALL_Rolls', 'CALL_Exit',
            'Cumulative_Credit_$', 'Banked_Roll_PnL_$', 'Total_PnL_$', 'PnL_%',
            'Exit_Reason', 'Result'
        ])
        for t in results['closed_trades']:
            dte = (t.expiration_date - t.entry_date).days
            res = 'WIN' if t.pnl > 0 else 'LOSS' if t.pnl < 0 else 'BE'
            pnl_d   = t.pnl * 100 * results['num_contracts']
            credit_d = t.cumulative_credit * 100 * results['num_contracts']
            banked_d = t.banked_pnl * 100 * results['num_contracts']
            pnl_pct = (t.pnl / t.cumulative_credit * 100) if t.cumulative_credit else 0
            spx_exit = t.spx_price_at_exit or 0
            spx_exp  = t.spx_price_at_expiration or 0
            ed = t.exit_date.strftime('%Y-%m-%d') if t.exit_date else ''
            w.writerow([
                t.trade_id,
                t.ticker,
                t.entry_date.strftime('%Y-%m-%d'),
                t.expiration_date.strftime('%Y-%m-%d'),
                ed, dte,
                f"{t.spx_price_at_entry:.2f}",
                f"{spx_exit:.2f}",
                f"{spx_exp:.2f}",
                f"{t.volume_10med_at_entry:.2f}",
                f"{t.vix_at_entry:.2f}",
                t.short_strike, t.long_strike,
                f"{t.credit:.2f}",
                len(t.put_rolls),
                t.put_exit_reason or '',
                t.call_short, t.call_long,
                f"{t.call_credit:.2f}",
                len(t.call_rolls),
                t.call_exit_reason or '',
                f"{credit_d:.2f}",
                f"{banked_d:.2f}",
                f"{pnl_d:.2f}",
                f"{pnl_pct:.1f}",
                t.exit_reason or '',
                res,
            ])
    log(f"  Trades exported to: {filename}")

# ============================================================================
# STOCK-SPECIFIC REPORTING
# ============================================================================


# TODO: move to analyze_trades
def print_stock_results(results):
    """Stock put spread report — calls all 4 stock-specific sections."""
    _print_ticker_pnl(results)
    _print_earnings_hit_rate(results)
    _print_pnl_ranked(results)
    _print_stock_yearly_breakdown(results)


def _print_ticker_pnl(results):
    """Per-ticker P&L breakdown: trades, wins, win rate, total PnL."""
    print()
    print("  PER-TICKER P&L BREAKDOWN")
    print("  " + "-" * 60)
    print(f"    {'Ticker':<8} {'Trades':<8} {'Wins':<6} {'Win%':<8} {'Total P&L'}")
    print(f"    {'-'*8} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")

    by_ticker = {}
    for t in results['closed_trades']:
        ticker = getattr(t, 'ticker', 'SPX') or 'SPX'
        by_ticker.setdefault(ticker, []).append(t)

    for ticker in sorted(by_ticker):
        ts  = by_ticker[ticker]
        n   = len(ts)
        w   = sum(1 for t in ts if t.pnl > 0)
        wr  = w / n * 100 if n else 0
        pnl = sum(t.pnl for t in ts) * 100 * results['num_contracts']
        print(f"    {ticker:<8} {n:<8} {w:<6} {wr:<7.1f}% ${pnl:>10,.2f}")
    print()


def _print_earnings_hit_rate(results):
    """How often scanner fired per ticker (trades entered vs calendar days scanned).
    TODO: needs scanner_attempts per ticker passed in results to compute fully."""
    log()
    log("  EARNINGS HIT RATE")
    log("  " + "-" * 60)
    log("  [TODO: wire scanner_attempts per ticker into results dict]")
    log()

    by_ticker = {}
    for t in results['closed_trades']:
        ticker = getattr(t, 'ticker', 'SPX') or 'SPX'
        by_ticker.setdefault(ticker, 0)
        by_ticker[ticker] += 1

    for ticker in sorted(by_ticker):
        log(f"    {ticker:<8} {by_ticker[ticker]} trades entered")
    log()


def _print_pnl_ranked(results):
    """Tickers ranked by total P&L descending."""
    log()
    log("  STOCKS BY P&L (RANKED)")
    log("  " + "-" * 60)

    by_ticker = {}
    for t in results['closed_trades']:
        ticker = getattr(t, 'ticker', 'SPX') or 'SPX'
        by_ticker[ticker] = by_ticker.get(ticker, 0) + t.pnl * 100 * results['num_contracts']

    ranked = sorted(by_ticker.items(), key=lambda x: -x[1])
    for rank, (ticker, pnl) in enumerate(ranked, 1):
        log(f"    {rank:<4} {ticker:<8} ${pnl:>10,.2f}")
    log()


def _print_stock_yearly_breakdown(results):
    """Yearly breakdown per ticker — same structure as SPX yearly breakdown."""
    log()
    log("  YEARLY BREAKDOWN BY TICKER")
    log("  " + "-" * 60)

    by_year_ticker = {}
    for t in results['closed_trades']:
        ticker = getattr(t, 'ticker', 'SPX') or 'SPX'
        year   = t.entry_date.year
        by_year_ticker.setdefault(year, {}).setdefault(ticker, []).append(t)

    for year in sorted(by_year_ticker):
        log(f"    {year}")
        log(f"      {'Ticker':<8} {'Trades':<8} {'Wins':<6} {'Win%':<8} {'P&L'}")
        for ticker in sorted(by_year_ticker[year]):
            ts  = by_year_ticker[year][ticker]
            n   = len(ts)
            w   = sum(1 for t in ts if t.pnl > 0)
            wr  = w / n * 100 if n else 0
            pnl = sum(t.pnl for t in ts) * 100 * results['num_contracts']
            log(f"      {ticker:<8} {n:<8} {w:<6} {wr:<7.1f}% ${pnl:>10,.2f}")
    log()
