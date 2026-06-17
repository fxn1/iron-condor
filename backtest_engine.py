#!/usr/bin/env python3
"""
backtest_engine.py — shared engine for all SPX iron condor and PutSpread backtests.

Both Options_Using_SPX_10_NetDelta.PY and Options_Using_SPX_10_NetDelta_Fixed4.PY
delegate their run_backtest() and main() logic here.  Per-script differences are
injected via parameters so this file never needs to change when a new variant is
added.
Fully generic: no price lookups, no vol calculations, no vix lookups.
All market data comes from strategy.get_market_data().
Works for both SPX iron condor and stock put spread strategies.

"""
import os
from datetime import datetime, timedelta
from config import gcfg
from base_strategy import TradeEntryReason
from reporting import print_results, export_trades_to_csv


def log(msg=""):
    print(f"{datetime.now()}  {msg}")


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

def run_backtest(start_date, delta_days, strategy, run_title):
    """
    Unified backtest loop.

    Parameters
    ----------
    start_date   : datetime of backtest start.
    delta_days   : int - backtest end date is start date + delta_days
    strategy     : BaseStrategy — provides should_enter_trade() and
                   should_reenter_after_exit().  All entry/re-entry policy
                   lives there; this function is policy-free.
    run_title    : str printed in the opening banner.
    """
    end_date = start_date + timedelta(days=delta_days + 1)  # +1 to include the last day in the loop
    today = datetime.today()
    if end_date < start_date:
        raise ValueError("End date must be after start date.")
    if start_date > today:
        raise ValueError("Start date cannot be in the future.")
    if end_date < today:
        log(f"  Backtest end date: {end_date.strftime('%Y-%m-%d')}")
    if end_date > today:
        end_date = today
    strategy.load_data(start_date, delta_days)
    log()
    log("=" * 80)
    log(f"RUNNING 10-YEAR ({run_title})")
    log("=" * 80)
    log()
    log(f"  Period:       {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    strategy.print_strategy_config()
    log(f"  Exits:       50% profit, 10 DTE smart exit, 2x stop  (gap-aware)")
    log()

    open_trades   = []
    closed_trades = []
    dates = strategy.get_trading_dates(start_date, end_date)

    trade_id              = 0
    trades_entered        = 0
    trades_skipped_vix    = 0
    skipped_duplicate_exp = 0
    skipped_low_credit    = 0
    profit_target_exits   = 0
    reentry_trades        = 0
    total_put_rolls       = 0
    total_call_rolls      = 0
    days_in_warn          = 0
    days_in_roll_zone     = 0
    max_concurrent        = 0

    log("  Running backtest...")

    for current_date in dates:
        trades_to_close = []
        for trade in open_trades:
            md = strategy.get_market_data(trade, current_date)
            close       = md['close']
            day_high    = md['high']
            day_low     = md['low']
            day_open    = md['open']
            vix         = md['vix']
            volatility = md['volatility']
            # 1) Exit checks (gap-aware)
            if trade.check_exit(current_date, close, vix, volatility, day_open=day_open, day_high=day_high, day_low=day_low):
                trades_to_close.append(trade)

        for trade in open_trades:
            # 2) Position management — delegated to trade type (IC rolls; others no-op)
            # 2) Net-delta roll management for trades that survived the exits
            if not trade.is_open:
                continue
            md = strategy.get_market_data(trade, current_date)
            close       = md['close']
            put_vol     = md['put_vol']
            call_vol    = md['call_vol']
            stats       = trade.manage_position(current_date, close, gcfg.market.risk_free_rate, put_vol, call_vol)
            days_in_warn      += stats.get('days_in_warn',      0)
            days_in_roll_zone += stats.get('days_in_roll_zone', 0)
            total_put_rolls   += stats.get('put_rolls',         0)
            total_call_rolls  += stats.get('call_rolls',        0)

        # 3) Process closed trades and queue re-entries
        potential_reentries = []
        for trade in trades_to_close:
            ticker = trade.ticker
            strategy.fill_expiration_price(trade)
            open_trades.remove(trade)
            closed_trades.append(trade)
            signal = strategy.should_reenter_after_exit(trade)
            # only one reentry per day
            if signal.reason == TradeEntryReason.SHOULD_ENTER and not strategy.check_expiration_used(current_date, ticker):
                potential_reentries.append(signal)
                strategy.mark_reentry_expiration_used(current_date, ticker)  # ← marks today, not trade expiration date
                profit_target_exits += 1

        # Re-entries
        if potential_reentries:
            # Re-entry: ask strategy — it checks dup exp internally
            for signal in potential_reentries:
                trade_id += 1
                new_trade = strategy.create_trade(current_date, trade_id, signal)
                open_trades.append(new_trade)
                trades_entered  += 1
                reentry_trades  += 1
        else:
            skipped_duplicate_exp += 1

        # Regular entries
        for signal in strategy.should_enter_trades(current_date):
            if signal.reason == TradeEntryReason.SHOULD_ENTER:
                trade_id += 1
                new_trade = strategy.create_trade(current_date, trade_id, signal)

                if 0 <= strategy.cfg.min_credit and new_trade.credit < strategy.cfg.min_credit:
                    skipped_low_credit += 1
                    continue

                open_trades.append(new_trade)
                strategy.mark_expiration_used(new_trade)
                trades_entered += 1
            elif signal.reason == TradeEntryReason.SKIPPED_VIX:
                trades_skipped_vix += 1
            elif signal.reason == TradeEntryReason.SKIPPED_DUP_EXP:
                skipped_duplicate_exp += 1

        # Track peak concurrent for INFORMATIONAL output. Capital sizing
        max_concurrent = max(max_concurrent, len(open_trades))

    # Force-close anything still open at end of period
    for trade in open_trades:
        md = strategy.get_market_data(trade, dates[-1])
        spx_price = md['close']
        trade._close_at_expiration(spx_price)
        closed_trades.append(trade)

    # ── stats — single pass ───────────────────────────────────────────────
    n = winning = losing = total_pnl = gp = gl = rolled_trades = peak = mdd = 0
    exit_reasons = {}
    for t in closed_trades:
        n           += 1
        pnl         = t.pnl
        total_pnl   += pnl

        if pnl > 0:
            winning += 1
            gp += pnl
        elif pnl < 0:
            losing += 1
            gl += pnl

        if t.roll_stats()['rolled']:
            rolled_trades += 1

        peak = max(peak, total_pnl)
        mdd = max(mdd, peak - total_pnl)

        r = t.exit_reason or "Unknown"
        exit_reasons[r] = exit_reasons.get(r, 0) + 1

    # derived — computed once after the loop
    total_pnl_dollars = total_pnl * 100 * strategy.cfg.num_contracts
    avg_win = gp / winning if winning else 0
    avg_loss = gl / losing if losing else 0
    win_rate = winning / n * 100 if n else 0
    pf = abs(gp / gl) if gl else float('inf')
    log("  Complete!\n")
    return {
        'total_trades':         n,
        'trades_entered':       trades_entered,
        'trades_skipped_vix':    trades_skipped_vix,
        'skipped_duplicate_exp': skipped_duplicate_exp,
        'skipped_low_credit':    skipped_low_credit,
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
        'max_drawdown_dollars': mdd * 100 * strategy.cfg.num_contracts,
        'exit_reasons':         exit_reasons,
        'closed_trades':        closed_trades,
        'num_contracts':        strategy.cfg.num_contracts,
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

def run_main(*, strategy, title, script_name, csv_filename, start_date, end_date, extra_summary_lines=None):
    """
    Shared main() body.  Callers supply only what differs between variants.

    Parameters
    ----------
    strategy            : BaseStrategy instance
    title               : str  — banner title, e.g. "NET-DELTA ROLL MANAGEMENT"
    script_name         : str  — printed under the banner
    csv_filename        : str  — output CSV filename (no path)
    start_date         : datetime or None — if provided, overrides default backtest start date
    end_date   : datetime — backtest end date (will be capped to today if in future)
    extra_summary_lines : callable(results) -> list[str] | None — extra lines
                          inserted after the CAPITAL INVESTED row in the final
                          summary box.  Receives results so lines can reference
                          runtime values like max_concurrent.
    """
    log()
    log("=" * 80)
    log(script_name)
    log("=" * 80)
    log()

    today = datetime.today()
    if end_date > today:
        end_date = today
    end_date = end_date + timedelta(days=1)  # +1 to include the last day in the loop
    delta_days = (end_date - start_date).days
    years   = delta_days / 365.25
    results = run_backtest(start_date, delta_days, strategy, title)

    strategy.print_extra_results(results, years)  # ← stock sections; no-op for SPX
    print_results(strategy.cfg, results, title, years)

    log()
    # TODO: move below to reporting, and make it more generic (not SPX-specific) by passing in the wing width or other relevant parameters via results or strategy.
    if not results['closed_trades']:
        log("=" * 80)
        log(f"FINAL SUMMARY -  ({title})")
        log("=" * 80)
        log()
        log("  No trades were generated for this run.")
        log("  Check the strategy date range, loaded market data, and entry filters.")
        log()
        return results

    avg_credit = sum(t.cumulative_credit for t in results['closed_trades']) / len(results['closed_trades'])
    margin = (strategy.cfg.wing_width - avg_credit) * 100 * results['max_concurrent']  # peak concurrent open trades, not total trades
    annual_pnl = results['total_pnl_dollars'] / years
    total_return = results['total_pnl_dollars']/margin
    roc = ((1 + total_return) ** (1 / years) - 1) * 100 if margin and years > 0 else 0

    log("=" * 80)
    log(f"FINAL SUMMARY - BACKTEST  ({title})")
    log("=" * 80)
    log()
    log(f"  +{'-'*60}+")
    log(f"  |{'CAPITAL INVESTED:':^30}{'${:,.0f}'.format(margin):^30}|")
    for line in (extra_summary_lines(results) if extra_summary_lines else []):
        log(line)
    log(f"  |{'TOTAL P&L :':^30}{'${:,.0f}'.format(results['total_pnl_dollars']):^30}|")
    if margin:
        log(f"  |{'TOTAL RETURN ({:.0f} yrs):'.format(years):^30}{'{:.1f}%'.format(total_return*100):^30}|")
    log(f"  |{'ANNUAL P&L:':^30}{'${:,.0f}'.format(annual_pnl):^30}|")
    log(f"  |{'ANNUAL ROC:':^30}{'{:.1f}%'.format(roc):^30}|")
    log(f"  |{'WIN RATE:':^30}{'{:.1f}%'.format(results['win_rate']):^30}|")
    log(f"  |{'PROFIT FACTOR:':^30}{'{:.2f}'.format(results['profit_factor']):^30}|")
    log(f"  |{'TOTAL ROLLS (PUT/CALL):':^30}{'{}/{}'.format(results['total_put_rolls'], results['total_call_rolls']):^30}|")
    log(f"  +{'-'*60}+")
    log()
    csv_path = os.path.join(gcfg.paths.output_path, csv_filename)
    export_trades_to_csv(results, csv_path)
