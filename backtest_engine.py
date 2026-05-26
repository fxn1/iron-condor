#!/usr/bin/env python3
"""
backtest_engine.py — shared engine for all SPX iron condor backtests.

Both Options_Using_SPX_10_NetDelta.PY and Options_Using_SPX_10_NetDelta_Fixed4.PY
delegate their run_backtest() and main() logic here.  Per-script differences are
injected via parameters so this file never needs to change when a new variant is
added.
"""

import os
from datetime import timedelta

from config import *
from data_loader import load_spx_daily_from_minute_files, load_vix_data_from_excel
from volatility import calculate_historical_volatility
from base_strategy import get_next_friday, create_new_trade, TradeEntryReason
from reporting import print_results, export_trades_to_csv


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

def run_backtest(spx_data, vix_data, start_date, end_date, strategy, run_title, capital_label):
    """
    Unified backtest loop.

    Parameters
    ----------
    spx_data     : dict of daily SPX bars, keyed by 'YYYY-MM-DD' string.
    vix_data     : dict of daily VIX bars, keyed by 'YYYY-MM-DD' string.
    start_date   : datetime of backtest start.
    end_date     : datetime of backtest end.
    strategy     : BaseStrategy — provides should_enter_trade() and
                   should_reenter_after_exit().  All entry/re-entry policy
                   lives there; this function is policy-free.
    run_title    : str printed in the opening banner.
    capital_label: str printed as the "Capital:" line in the banner.
    """
    print()
    print("=" * 80)
    print(f"RUNNING 10-YEAR SPX BACKTEST  ({run_title})")
    print("=" * 80)
    print()
    print(f"  Period:      {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"  Strategy:    18/14 Delta Iron Condor on SPX  (wing ${WING_WIDTH})")
    print(f"  Roll rule:   |net delta| > {NET_DELTA_ROLL}  (warn at +/-{NET_DELTA_WARN})")
    print(f"  {capital_label}")
    print(f"  Exits:       50% profit, 10 DTE smart exit, 2x stop  (gap-aware)")
    print()

    open_trades   = []
    closed_trades = []
    used_expirations = set()

    sorted_dates = sorted(spx_data.keys())
    dates = [datetime.strptime(d, '%Y-%m-%d') for d in sorted_dates]
    dates = [d for d in dates if start_date <= d <= end_date]

    trade_id = 0
    trades_entered       = 0
    trades_skipped_vix   = 0
    skipped_duplicate_exp = 0
    profit_target_exits  = 0
    reentry_trades       = 0
    total_put_rolls      = 0
    total_call_rolls     = 0
    days_in_warn         = 0
    days_in_roll_zone    = 0
    max_concurrent       = 0  # Still tracked for INFORMATIONAL output

    print("  Running backtest...")

    for current_date in dates:
        date_str = current_date.strftime('%Y-%m-%d')
        if date_str not in spx_data:
            continue

        spx_price = spx_data[date_str]['close']
        day_high  = spx_data[date_str].get('high',  spx_price)
        day_low   = spx_data[date_str].get('low',   spx_price)
        day_open  = spx_data[date_str].get('open',  spx_price)
        vix = vix_data[date_str]['close'] if date_str in vix_data else 18.0

        idx = sorted_dates.index(date_str)  # TODO: optimize by tracking index in loop instead of .index() lookup  (O(n^2))
        if idx >= 20:
            hist = [spx_data[d]['close'] for d in sorted_dates[idx - 20:idx + 1]]
            volatility = calculate_historical_volatility(hist)
        else:
            volatility = 0.18
        put_vol  = volatility * 1.10
        call_vol = volatility * 0.95

        # 1) Exit checks (gap-aware)
        trades_to_close = []
        for trade in open_trades:
            if trade.check_exit(current_date, spx_price, vix, volatility,
                                day_open=day_open, day_high=day_high, day_low=day_low):
                trades_to_close.append(trade)

        # 2) Net-delta roll management for trades that survived the exits
        for trade in open_trades:
            if not trade.is_open:
                continue
            if not trade.can_roll():
                continue  # only roll true iron condors (both sides still on)
            rolled, stats = trade.manage_position(current_date, spx_price,
                                          RISK_FREE_RATE, put_vol, call_vol, volatility)
            if not rolled:
                continue
            days_in_warn += stats.get('days_in_warn', 0)
            days_in_roll_zone += stats.get('days_in_roll_zone', 0)
            total_put_rolls += stats.get('put_rolls', 0)
            total_call_rolls += stats.get('call_rolls', 0)

        # 3) Process closed trades and queue re-entries
        potential_reentries = []
        for trade in trades_to_close:
            exp_str = trade.expiration_date.strftime('%Y-%m-%d')
            if exp_str in spx_data:
                trade.spx_price_at_expiration = spx_data[exp_str]['close']
            else:
                for offset in range(-3, 4):
                    chk = (trade.expiration_date + timedelta(days=offset)).strftime('%Y-%m-%d')
                    if chk in spx_data:
                        trade.spx_price_at_expiration = spx_data[chk]['close']
                        break
            if trade.spx_price_at_expiration is None:
                trade.spx_price_at_expiration = trade.spx_price_at_exit

            open_trades.remove(trade)
            closed_trades.append(trade)
            if strategy.should_reenter_after_exit(trade, vix):
                potential_reentries.append(True)
                profit_target_exits += 1

        potential_expiration = get_next_friday(current_date, TARGET_DTE)
        exp_key = potential_expiration.strftime('%Y-%m-%d')

        if potential_reentries and exp_key not in used_expirations:
            trade_id += 1
            new_trade = create_new_trade(current_date, spx_price, vix, volatility, trade_id)
            open_trades.append(new_trade)
            used_expirations.add(exp_key)
            trades_entered  += 1
            reentry_trades  += 1
        elif potential_reentries:
            skipped_duplicate_exp += 1

        trade_reason = strategy.should_enter_trade(current_date, vix, exp_key, used_expirations)
        if trade_reason == TradeEntryReason.SHOULD_ENTER:
            trade_id += 1
            new_trade = create_new_trade(current_date, spx_price, vix, volatility, trade_id)
            open_trades.append(new_trade)
            used_expirations.add(exp_key)
            trades_entered += 1
        elif trade_reason == TradeEntryReason.SKIPPED_VIX:
            trades_skipped_vix += 1
        elif trade_reason == TradeEntryReason.SKIPPED_DUP_EXP:
            skipped_duplicate_exp += 1

        # Track peak concurrent for INFORMATIONAL output. Capital sizing
        # in this variant uses the fixed CONCURRENT_TRADES constant instead.
        max_concurrent = max(max_concurrent, len(open_trades))

    # Force-close anything still open at end of period
    for trade in open_trades:
        last_str  = dates[-1].strftime('%Y-%m-%d')
        spx_price = spx_data[last_str]['close']
        trade._close_at_expiration(spx_price)
        closed_trades.append(trade)

    # ── stats ──────────────────────────────────────────────────────────────
    n      = len(closed_trades)
    winning = sum(1 for t in closed_trades if t.pnl > 0)
    losing  = sum(1 for t in closed_trades if t.pnl < 0)
    total_pnl         = sum(t.pnl for t in closed_trades)
    total_pnl_dollars = total_pnl * 100 * NUM_CONTRACTS
    gp = sum(t.pnl for t in closed_trades if t.pnl > 0)
    gl = sum(t.pnl for t in closed_trades if t.pnl < 0)
    avg_win  = gp / winning if winning else 0
    avg_loss = gl / losing  if losing  else 0
    win_rate = winning / n * 100 if n else 0
    pf       = abs(gp / gl) if gl else float('inf')

    cum, peak, mdd = 0, 0, 0
    for t in closed_trades:
        cum  += t.pnl
        peak  = max(peak, cum)
        mdd   = max(mdd,  peak - cum)

    exit_reasons = {}
    for t in closed_trades:
        r = t.exit_reason or "Unknown"
        exit_reasons[r] = exit_reasons.get(r, 0) + 1

    rolled_trades = sum(1 for t in closed_trades if t.roll_stats()['rolled'])
    print("  Complete!\n")
    return {
        'total_trades':         n,
        'trades_entered':       trades_entered,
        'trades_skipped_vix':   trades_skipped_vix,
        'skipped_duplicate_exp': skipped_duplicate_exp,
        'profit_target_exits':  profit_target_exits,
        'reentry_trades':       reentry_trades,
        'winning_trades':       winning,
        'losing_trades':        losing,
        'win_rate':             win_rate,
        'total_pnl':            total_pnl,
        'total_pnl_dollars':    total_pnl_dollars,
        'gross_profit':         gp,
        'gross_loss':           gl,
        'avg_win':              avg_win,
        'avg_loss':             avg_loss,
        'profit_factor':        pf,
        'max_drawdown':         mdd,
        'max_drawdown_dollars': mdd * 100 * NUM_CONTRACTS,
        'exit_reasons':         exit_reasons,
        'closed_trades':        closed_trades,
        'num_contracts':        NUM_CONTRACTS,
        'total_put_rolls':      total_put_rolls,
        'total_call_rolls':     total_call_rolls,
        'rolled_trades':        rolled_trades,
        'days_in_warn':         days_in_warn,
        'days_in_roll_zone':    days_in_roll_zone,
        'max_concurrent':       max_concurrent,
    }


# ============================================================================
# SHARED MAIN HELPER
# ============================================================================

def run_main(*, strategy, title, script_name, capital_label, csv_filename, extra_summary_lines=None):
    """
    Shared main() body.  Callers supply only what differs between variants.

    Parameters
    ----------
    strategy            : BaseStrategy instance
    title               : str  — banner title, e.g. "NET-DELTA ROLL MANAGEMENT"
    script_name         : str  — printed under the banner
    capital_label       : str  — printed as the "Capital:" line in run_backtest banner
    csv_filename        : str  — output CSV filename (no path)
    extra_summary_lines : callable(results) -> list[str] | None — extra lines
                          inserted after the CAPITAL INVESTED row in the final
                          summary box.  Receives results so lines can reference
                          runtime values like max_concurrent.
    """
    print()
    print("=" * 80)
    print(f"SPX IRON CONDOR - 10 YEAR BACKTEST  ({title})")
    print(script_name)
    print("=" * 80)
    print()
    print(f"  Underlying:    SPX (real 1-min data, resampled to daily)")
    print(f"  Strategy:      18/14 delta IC, ${WING_WIDTH} wings, Monday entry, {TARGET_DTE} DTE")
    print(f"  Roll rule:     |net delta| > {NET_DELTA_ROLL}  (warn at +/-{NET_DELTA_WARN})")
    print(f"  {capital_label}")
    print()

    SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
    VIX_DATA_PATH= os.path.normpath(os.path.join(SCRIPT_DIR, 'VIX_Daily_Data.xlsx'))
    output_path  = SCRIPT_DIR

    vix_data = None
    if os.path.exists(VIX_DATA_PATH):
        vix_data = load_vix_data_from_excel(VIX_DATA_PATH)
        if vix_data:
            print(f"  Loaded {len(vix_data)} days of VIX data")
    if vix_data is None:
        print("  ERROR: VIX data not found")
        return
    print()

    print("  Loading SPX minute data...")
    spx_data = load_spx_daily_from_minute_files(START_YEAR, END_YEAR)
    if spx_data is None:
        print("  ERROR: could not load SPX data")
        return
    print(f"  Built {len(spx_data)} daily SPX bars")

    years   = (END_DATE - START_DATE).days / 365.25
    results = run_backtest(spx_data, vix_data, START_DATE, END_DATE, strategy, title, capital_label)

    print_results(results, years)

    csv_path = os.path.join(output_path, csv_filename)
    export_trades_to_csv(results, csv_path)
    print()

    avg_credit = sum(t.cumulative_credit for t in results['closed_trades']) / len(results['closed_trades'])
    # Fixed capital sizing using the observed peak concurrent open trades = 5.
    # (Original reviewer request was * 4, but tracking showed peak = 5, so
    # using 4 understates capital ~20% and overstates ROC ~25%.)
    margin = (WING_WIDTH - avg_credit) * 100 * 5
    annual_pnl = results['total_pnl_dollars'] / years
    roc        = annual_pnl / margin * 100 if margin else 0

    print("=" * 80)
    print(f"FINAL SUMMARY - 10 YEAR SPX BACKTEST  ({title})")
    print("=" * 80)
    print()
    print(f"  +{'-'*60}+")
    print(f"  |{'CAPITAL INVESTED:':^30}{'${:,.0f}'.format(margin):^30}|")
    for line in (extra_summary_lines(results) if extra_summary_lines else []):
        print(line)
    print(f"  |{'TOTAL P&L (10 years):':^30}{'${:,.0f}'.format(results['total_pnl_dollars']):^30}|")
    if margin:
        print(f"  |{'TOTAL RETURN:':^30}{'{:.0f}%'.format(results['total_pnl_dollars']/margin*100):^30}|")
    print(f"  |{'ANNUAL P&L:':^30}{'${:,.0f}'.format(annual_pnl):^30}|")
    print(f"  |{'ANNUAL ROC:':^30}{'{:.1f}%'.format(roc):^30}|")
    print(f"  |{'WIN RATE:':^30}{'{:.1f}%'.format(results['win_rate']):^30}|")
    print(f"  |{'PROFIT FACTOR:':^30}{'{:.2f}'.format(results['profit_factor']):^30}|")
    print(f"  |{'TOTAL ROLLS (PUT/CALL):':^30}{'{}/{}'.format(results['total_put_rolls'], results['total_call_rolls']):^30}|")
    print(f"  +{'-'*60}+")
    print()
