import csv

from config import *

# ============================================================================
# OUTPUT
# ============================================================================

def print_results(results, years):
    print()
    print("=" * 80)
    print("10-YEAR SPX BACKTEST RESULTS  (NET-DELTA + FIXED *5 CAPITAL)")
    print("=" * 80)
    print()

    print("  STRATEGY")
    print("  " + "-" * 60)
    print(f"    Underlying:        SPX")
    print(f"    PUT/CALL Delta:    {PUT_DELTA} / {CALL_DELTA}")
    print(f"    Wing Width:        ${WING_WIDTH}")
    print(f"    Roll Threshold:    |net delta| > {NET_DELTA_ROLL}")
    print(f"    Profit Target:     {int(PROFIT_TARGET*100)}%")
    print(f"    Stop Loss:         {STOP_LOSS_MULTIPLIER}x credit per leg (worst-intraday)")
    print(f"    10 DTE Exit:       Smart exit, gap-aware")
    print(f"    VIX No-Trade:      > {VIX_NO_TRADE}")
    print(f"    Capital Sizing:    fixed {CONCURRENT_TRADES} concurrent")
    print()

    print("  TRADE STATISTICS")
    print("  " + "-" * 60)
    print(f"    Total Trades:           {results['total_trades']}")
    print(f"    Monday Entries:         {results['trades_entered'] - results['reentry_trades']}")
    print(f"    Re-entry Trades:        {results['reentry_trades']}")
    print(f"    Skipped (VIX > {VIX_NO_TRADE}):     {results['trades_skipped_vix']}")
    print(f"    Winning Trades:         {results['winning_trades']}")
    print(f"    Losing Trades:          {results['losing_trades']}")
    print(f"    Win Rate:               {results['win_rate']:.1f}%")
    print()

    print("  NET-DELTA MANAGEMENT")
    print("  " + "-" * 60)
    print(f"    Days in Warn band ({NET_DELTA_WARN}-{NET_DELTA_ROLL}):     {results['days_in_warn']}")
    print(f"    Days in Roll zone (>{NET_DELTA_ROLL}):       {results['days_in_roll_zone']}")
    print(f"    Trades that rolled at least 1x:    {results['rolled_trades']}")
    print(f"    Total PUT-side rolls:              {results['total_put_rolls']}")
    print(f"    Total CALL-side rolls:             {results['total_call_rolls']}")
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
    avg_credit = sum(t.cumulative_credit for t in results['closed_trades']) / len(results['closed_trades'])
    margin_per = (WING_WIDTH - avg_credit) * 100
    # Fixed capital sizing using the observed peak concurrent open trades = 5.
    # (Reviewer originally asked for * 4, but tracking showed peak = 5.)
    total_margin = margin_per * results['num_contracts'] * 5
    annual_pnl = results['total_pnl_dollars'] / years
    roc = annual_pnl / total_margin * 100 if total_margin else 0
    print(f"    Avg Credit/Trade:       ${avg_credit:.2f} (incl. rolls)")
    print(f"    Margin per Contract:    ${margin_per:,.2f}")
    print(f"    Concurrent Trades:      5  (fixed - matches observed peak)")
    print(f"    Peak Observed:          {results['max_concurrent']}  (informational)")
    print(f"    Total Capital Required: ${total_margin:,.2f}")
    print(f"    Annual P&L:             ${annual_pnl:,.2f}")
    print(f"    Annual ROC:             {roc:.1f}%")
    if total_margin:
        print(f"    Total Return ({years:.0f} yrs):    {results['total_pnl_dollars']/total_margin*100:.1f}%")
    print()

    print("  YEARLY BREAKDOWN")
    print("  " + "-" * 60)
    by_year = {}
    for t in results['closed_trades']:
        by_year.setdefault(t.entry_date.year, []).append(t)
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
    print()


def export_trades_to_csv(results, filename):
    with open(filename, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            'Trade_ID', 'Entry_Date', 'Expiration', 'Exit_Date', 'DTE',
            'SPX_Entry', 'SPX_Exit', 'SPX_Expiration', 'VIX_Entry',
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
                t.entry_date.strftime('%Y-%m-%d'),
                t.expiration_date.strftime('%Y-%m-%d'),
                ed, dte,
                f"{t.spx_price_at_entry:.2f}",
                f"{spx_exit:.2f}",
                f"{spx_exp:.2f}",
                f"{t.vix_at_entry:.2f}",
                t.put_short, t.put_long,
                f"{t.put_credit:.2f}",
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
    print(f"  Trades exported to: {filename}")

