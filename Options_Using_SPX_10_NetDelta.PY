#!/usr/bin/env python3
"""
================================================================================
SPX IRON CONDOR - 10 YEAR BACKTEST
WITH NET-DELTA ROLL MANAGEMENT (PER UPLOADED RULES)
================================================================================

This program extends Options_Using_SPX_10.PY by adding net-delta-driven
position management.

Net Delta Rules Applied (from uploaded screenshot):
    Net Delta Range          Status     Action
    -10 to +10               OK         Hold position
    -15 to -10 / +10 to +15  Warning    Monitor closely
    Beyond +/-15             Roll       Close & re-enter

What "net delta" means here:
    For each open iron condor we compute the position delta in
    share-equivalent units per 1 contract spread:

        put_pos_delta  = -delta(put_short)  + delta(put_long)
        call_pos_delta = -delta(call_short) + delta(call_long)
        net_delta_$    = (put_pos_delta + call_pos_delta) * 100

    A 1-contract spread that controls 100 shares with a per-share delta of
    +0.15 has a position delta of +15 share-equivalents.

What "roll the threatened side" means:
    A NET POSITIVE delta beyond +15 means the index has dropped enough that
    the short PUT side has grown deep - the put side is THREATENED. We close
    the entire put spread (locking in its current loss) and re-open a new
    put spread on the SAME expiration whose short strike sits at the
    PUT_DELTA target (18). Wing width unchanged.

    A NET NEGATIVE delta beyond -15 means the index has rallied enough that
    the short CALL side is THREATENED. We close the call spread and re-open
    at the CALL_DELTA target (14).

    The other (un-threatened) side is left alone.

What carries over to the new spread:
    * Same expiration (DTE keeps ticking down)
    * Stops on the new spread are 2x its NEW credit
    * Profit target stays at 50% of CUMULATIVE credit collected on this
      trade (so collecting more credit by rolling raises the bar)
    * The realized loss from the closed spread is "banked" against the trade
      so the running PnL accounts for it

Other behaviour preserved from Options_Using_SPX_10.PY:
    * 18 / 14 delta entry, $50 wings on SPX, Monday entry, 30 DTE
    * 50% profit target -> close & re-enter immediately
    * 10 DTE smart exit
    * Per-leg stop loss = 2x credit, gap-aware (worst intraday)
    * VIX > 25 skip entry, VIX > 30 close puts
    * Profit target uses each leg's BEST intraday price; stops use WORST
      intraday price; if both fire same day, STOP wins (conservative)

Inputs:
    * Real SPX 1-min data: spx_2016.xlsx ... spx_2026.xlsx
    * VIX_Daily_Data.xlsx from sibling SPY-DELTA folder

Output:
    * SPX_IronCondor_10Year_NetDelta_Backtest.csv
    * Console report with roll statistics + yearly breakdown

Author: Claude (adapted for PEC)
Date: May 2026
================================================================================
"""

import os
from datetime import timedelta
from typing import List

from config import *

from data_loader import load_spx_daily_from_minute_files, load_vix_data_from_excel
from volatility import calculate_historical_volatility
from strategy_fixed4 import get_next_friday, create_new_trade
from strategy_fixed4 import Fixed4Strategy
# TODO: compare IronCondorTradeOpen vs IronCondorTrade and consolidate if possible
from trade import IronCondorTradeOpen
from reporting import print_results
from reporting import export_trades_to_csv

STRIKE_INCREMENT = 5

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VIX_DATA_PATH = os.path.normpath(
    os.path.join(SCRIPT_DIR, 'VIX_Daily_Data.xlsx')
    # os.path.join(SCRIPT_DIR, '..', '..', 'SPY-DELTA', 'VIX_Daily_Data.xlsx')
)
OUTPUT_PATH = SCRIPT_DIR


class NetDeltaStrategy(Fixed4Strategy):
    pass


strategy = NetDeltaStrategy()
def is_monday(d): return d.weekday() == 0


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

def run_backtest(spx_data, vix_data, start_date, end_date):
    print()
    print("=" * 80)
    print("RUNNING 10-YEAR SPX BACKTEST  (NET-DELTA ROLL MANAGEMENT)")
    print("=" * 80)
    print()
    print(f"  Period:      {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"  Strategy:    18/14 Delta Iron Condor on SPX  (wing ${WING_WIDTH})")
    print(f"  Roll rule:   |net delta| > {NET_DELTA_ROLL}  (warn at +/-{NET_DELTA_WARN})")
    print(f"  Roll action: close threatened side, re-enter at fresh 18/14 delta")
    print(f"  Cap:         max {MAX_ROLLS_PER_SIDE} rolls per side per trade")
    print(f"  Exits:       50% profit, 10 DTE smart exit, 2x stop  (gap-aware)")
    print()

    open_trades: List[IronCondorTradeOpen] = []
    closed_trades: List[IronCondorTradeOpen] = []
    used_expirations = set()

    sorted_dates = sorted(spx_data.keys())
    dates = [datetime.strptime(d, '%Y-%m-%d') for d in sorted_dates]
    dates = [d for d in dates if start_date <= d <= end_date]

    trade_id = 0
    trades_entered = 0
    trades_skipped_vix = 0
    skipped_duplicate_exp = 0
    profit_target_exits = 0
    reentry_trades = 0
    total_put_rolls = 0
    total_call_rolls = 0
    days_in_warn = 0
    days_in_roll_zone = 0
    max_concurrent = 0  # 2. Track max concurrent open trades for capital analysis

    print("  Running backtest...")

    for current_date in dates:
        date_str = current_date.strftime('%Y-%m-%d')
        if date_str not in spx_data:
            continue

        spx_price = spx_data[date_str]['close']
        day_high  = spx_data[date_str].get('high', spx_price)
        day_low   = spx_data[date_str].get('low',  spx_price)
        day_open = spx_data[date_str].get('open',  spx_price)
        vix = vix_data[date_str]['close'] if date_str in vix_data else 18.0

        idx = sorted_dates.index(date_str)
        if idx >= 20:
            hist = [spx_data[d]['close'] for d in sorted_dates[idx - 20:idx + 1]]
            volatility = calculate_historical_volatility(hist)
        else:
            volatility = 0.18
        put_vol  = volatility * 1.10
        call_vol = volatility * 0.95

        # 1) Existing exit checks (gap-aware)
        trades_to_close = []
        for trade in open_trades:
            if trade.check_exit(current_date, spx_price, vix, volatility, day_open=day_open, day_high=day_high, day_low=day_low):
                trades_to_close.append(trade)

        # 2) Net-delta roll management for trades that survived the exits
        for trade in open_trades:
            if not trade.is_open:
                continue
            if not (trade.put_leg_open and trade.call_leg_open):
                continue  # only roll true iron condors (both sides still on)

            dte = (trade.expiration_date - current_date).days
            if dte <= EXIT_DTE:
                continue  # near expiration -> let smart-exit handle it
            T = max(dte / 365.0, 0.001)
            net_delta = trade.net_position_delta(spx_price, T, RISK_FREE_RATE, put_vol, call_vol)

            if NET_DELTA_WARN < abs(net_delta) <= NET_DELTA_ROLL:
                days_in_warn += 1
            elif abs(net_delta) > NET_DELTA_ROLL:
                days_in_roll_zone += 1
                if net_delta > 0:
                    if trade.roll_put_side(current_date, spx_price, T, RISK_FREE_RATE, put_vol, volatility):
                        total_put_rolls += 1
                else:
                    if trade.roll_call_side(current_date, spx_price, T, RISK_FREE_RATE, call_vol, volatility):
                        total_call_rolls += 1

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
            if trade.exited_at_profit_target and vix <= VIX_NO_TRADE:
                potential_reentries.append(True)
                profit_target_exits += 1

        potential_expiration = get_next_friday(current_date, TARGET_DTE)
        exp_key = potential_expiration.strftime('%Y-%m-%d')

        if potential_reentries and exp_key not in used_expirations:
            trade_id += 1
            new_trade = create_new_trade(current_date, spx_price, vix, volatility, trade_id)
            open_trades.append(new_trade)
            used_expirations.add(exp_key)
            trades_entered += 1
            reentry_trades += 1
        elif potential_reentries:
            skipped_duplicate_exp += 1

        if is_monday(current_date):
            if vix > VIX_NO_TRADE:
                trades_skipped_vix += 1
            elif exp_key in used_expirations:
                skipped_duplicate_exp += 1
            else:
                trade_id += 1
                new_trade = create_new_trade(current_date, spx_price, vix, volatility, trade_id)
                open_trades.append(new_trade)
                used_expirations.add(exp_key)
                trades_entered += 1

        # Track peak concurrent for INFORMATIONAL output. Capital sizing
        # in this variant uses the fixed CONCURRENT_TRADES constant instead.
        max_concurrent = max(max_concurrent, len(open_trades))

    for trade in open_trades:
        last_str = dates[-1].strftime('%Y-%m-%d')
        spx_price = spx_data[last_str]['close']
        trade._close_at_expiration(spx_price)
        closed_trades.append(trade)

    # Stats
    n = len(closed_trades)
    winning = sum(1 for t in closed_trades if t.pnl > 0)
    losing  = sum(1 for t in closed_trades if t.pnl < 0)
    total_pnl = sum(t.pnl for t in closed_trades)
    total_pnl_dollars = total_pnl * 100 * NUM_CONTRACTS
    gp = sum(t.pnl for t in closed_trades if t.pnl > 0)
    gl = sum(t.pnl for t in closed_trades if t.pnl < 0)
    avg_win  = gp / winning if winning else 0
    avg_loss = gl / losing  if losing  else 0
    win_rate = winning / n * 100 if n else 0
    pf = abs(gp / gl) if gl else float('inf')
    cum, peak, mdd = 0, 0, 0
    for t in closed_trades:
        cum += t.pnl
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)

    exit_reasons = {}
    for t in closed_trades:
        r = t.exit_reason or "Unknown"
        exit_reasons[r] = exit_reasons.get(r, 0) + 1

    rolled_trades = sum(1 for t in closed_trades if t.put_rolls or t.call_rolls)

    print("  Complete!\n")

    return {
        'total_trades': n, 'trades_entered': trades_entered,
        'trades_skipped_vix': trades_skipped_vix,
        'skipped_duplicate_exp': skipped_duplicate_exp,
        'profit_target_exits': profit_target_exits,
        'reentry_trades': reentry_trades,
        'winning_trades': winning, 'losing_trades': losing,
        'win_rate': win_rate,
        'total_pnl': total_pnl, 'total_pnl_dollars': total_pnl_dollars,
        'gross_profit': gp, 'gross_loss': gl,
        'avg_win': avg_win, 'avg_loss': avg_loss,
        'profit_factor': pf,
        'max_drawdown': mdd, 'max_drawdown_dollars': mdd * 100 * NUM_CONTRACTS,
        'exit_reasons': exit_reasons,
        'closed_trades': closed_trades,
        'num_contracts': NUM_CONTRACTS,
        'total_put_rolls': total_put_rolls,
        'total_call_rolls': total_call_rolls,
        'rolled_trades': rolled_trades,
        'days_in_warn': days_in_warn,
        'days_in_roll_zone': days_in_roll_zone,
        'max_concurrent': max_concurrent,
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    print()
    print("=" * 80)
    print("SPX IRON CONDOR - 10 YEAR BACKTEST  (NET-DELTA ROLL MANAGEMENT)")
    print("Options_Using_SPX_10_NetDelta.PY")
    print("=" * 80)
    print()
    print(f"  Underlying:    SPX (real 1-min data, resampled to daily)")
    print(f"  Strategy:      18/14 delta IC, ${WING_WIDTH} wings, Monday entry, {TARGET_DTE} DTE")
    print(f"  Roll rule:     |net delta| > {NET_DELTA_ROLL}  (warn at +/-{NET_DELTA_WARN})")
    print(f"  Roll action:   close threatened side, re-enter at fresh 18/14 delta")
    print()

    vix_data = None
    if os.path.exists(VIX_DATA_PATH):
        vix_data = load_vix_data_from_excel(VIX_DATA_PATH)
        if vix_data:
            print(f"  ✓ Loaded {len(vix_data)} days of VIX data")
    if vix_data is None:
        print("  ERROR: VIX data not found")
        # print("  ⚠ VIX data not found, defaulting VIX=18")
        # vix_data = {d: {'close': 18.0} for d in spx_data.keys()}
    print()

    print("  Loading SPX minute data...")
    spx_data = load_spx_daily_from_minute_files(START_YEAR, END_YEAR)
    if spx_data is None:
        print("  ERROR: could not load SPX data")
        return
    print(f"  ✓ Built {len(spx_data)} daily SPX bars")

    years = (END_DATE - START_DATE).days / 365.25
    results = run_backtest(spx_data, vix_data, START_DATE, END_DATE)

    print_results(results, years)

    csv_path = os.path.join(OUTPUT_PATH, 'SPX_IronCondor_10Year_NetDelta_Backtest.csv')
    export_trades_to_csv(results, csv_path)
    print()

    avg_credit = sum(t.cumulative_credit for t in results['closed_trades']) / len(results['closed_trades'])
    margin = (WING_WIDTH - avg_credit) * 100 * results['max_concurrent']
    annual_pnl = results['total_pnl_dollars'] / years
    roc = annual_pnl / margin * 100 if margin else 0

    print("=" * 80)
    print("FINAL SUMMARY - 10 YEAR SPX BACKTEST  (NET-DELTA ROLL MANAGEMENT)")
    print("=" * 80)
    print()
    print(f"  +{'-'*60}+")
    print(f"  |{'CAPITAL INVESTED:':^30}{'${:,.0f}'.format(margin):^30}|")
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


if __name__ == "__main__":
    main()
