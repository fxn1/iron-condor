#!/usr/bin/env python3
"""
analyze_trades.py — post-run analysis tool for put spread backtest CSV.reads CSV output directly.

Usage:
    python analyze_trades.py path/to/Stock_Put_Spread_Backtest.csv
"""

import sys
import pandas as pd


# ── load ─────────────────────────────────────────────────────────────────────

def prepare_data(df):
    df['Entry_Date'] = pd.to_datetime(df['Entry_Date'])
    df['Exit_Date'] = pd.to_datetime(df['Exit_Date'])
    df['Year'] = df['Entry_Date'].dt.year
    df['Hold_Days'] = (df['Exit_Date'] - df['Entry_Date']).dt.days
    df['Credit'] = df['PUT_Credit_Final'].astype(float)
    df['Short'] = df['PUT_Short_Final'].astype(float)
    df['OTM_Pct'] = (df['SPX_Entry'].astype(float) - df['Short']) / df['SPX_Entry'].astype(float) * 100
    df['Is_Win'] = df['Result'] == 'WIN'
    print(f"Loaded {len(df)} trades  ({df['Entry_Date'].min()}–{df['Entry_Date'].max()})")


# ── analyses ──────────────────────────────────────────────────────────────────

def otm_analysis(df: pd.DataFrame):
    print("\n── STRIKE / OTM ANALYSIS ───────────────────────────────────────")
    print(f"  Avg OTM%    : {df['OTM_Pct'].mean():.1f}%")
    print(f"  Median OTM% : {df['OTM_Pct'].median():.1f}%")
    print(f"  Min OTM%    : {df['OTM_Pct'].min():.1f}%")
    print(f"  Max OTM%    : {df['OTM_Pct'].max():.1f}%")

    bins   = [0, 5, 10, 15, 20, 25, 30, 100]
    labels = ['0-5%', '5-10%', '10-15%', '15-20%', '20-25%', '25-30%', '>30%']
    df['OTM_Bucket'] = pd.cut(df['OTM_Pct'], bins=bins, labels=labels)
    dist = df.groupby('OTM_Bucket', observed=True).agg(
        Trades   = ('Trade_ID', 'count'),
        Win_Rate = ('Result',   lambda x: (x == 'WIN').mean() * 100),
        Avg_PnL  = ('Total_PnL_$', 'mean'),
    ).round(2)
    print("\n  OTM% distribution:")
    print(dist.to_string())


def hold_time_analysis(df: pd.DataFrame):
    print("\n── HOLD TIME ANALYSIS ──────────────────────────────────────────")
    print(f"  Avg hold days  : {df['Hold_Days'].mean():.1f}")
    print(f"  Median         : {df['Hold_Days'].median():.1f}")
    print(f"  % closed day 1 : {(df['Hold_Days'] <= 1).mean()*100:.1f}%")
    print(f"  % closed <= 3d : {(df['Hold_Days'] <= 3).mean()*100:.1f}%")
    print(f"  % closed <= 5d : {(df['Hold_Days'] <= 5).mean()*100:.1f}%")
    print(f"  % held > 10d   : {(df['Hold_Days'] > 10).mean()*100:.1f}%")

    bins   = [0, 1, 3, 5, 10, 20, 40, 200]
    labels = ['1d', '2-3d', '4-5d', '6-10d', '11-20d', '21-40d', '>40d']
    df['Hold_Bucket'] = pd.cut(df['Hold_Days'], bins=bins, labels=labels)
    dist = df.groupby('Hold_Bucket', observed=True).agg(
        Trades   = ('Trade_ID', 'count'),
        Win_Rate = ('Result',   lambda x: (x == 'WIN').mean() * 100),
        Avg_PnL  = ('Total_PnL_$', 'mean'),
    ).round(2)
    print("\n  Hold time distribution:")
    print(dist.to_string())


def credit_analysis(df: pd.DataFrame):
    print("\n── CREDIT ANALYSIS ─────────────────────────────────────────────")
    print(f"  Avg credit       : ${df['Credit'].mean():.2f}")
    print(f"  Median credit    : ${df['Credit'].median():.2f}")
    print(f"  Min credit       : ${df['Credit'].min():.4f}")
    print(f"  Max credit       : ${df['Credit'].max():.2f}")
    print(f"  % credit < $0.10 : {(df['Credit'] < 0.10).mean()*100:.1f}%")
    print(f"  % credit < $0.50 : {(df['Credit'] < 0.50).mean()*100:.1f}%")

    bins   = [0, 0.10, 0.25, 0.50, 1.0, 2.0, 5.0, 999]
    labels = ['<0.10', '0.10-0.25', '0.25-0.50', '0.50-1.00', '1.00-2.00', '2.00-5.00', '>5.00']
    df['Credit_Bucket'] = pd.cut(df['Credit'], bins=bins, labels=labels)
    dist = df.groupby('Credit_Bucket', observed=True).agg(
        Trades   = ('Trade_ID', 'count'),
        Win_Rate = ('Result',   lambda x: (x == 'WIN').mean() * 100),
        Avg_PnL  = ('Total_PnL_$', 'mean'),
    ).round(2)
    print("\n  Credit size distribution:")
    print(dist.to_string())


def yearly_analysis(df: pd.DataFrame):
    print("\n── YEARLY BREAKDOWN ────────────────────────────────────────────")
    yearly = df.groupby('Year').agg(
        Trades     = ('Trade_ID',    'count'),
        Win_Rate   = ('Result',      lambda x: (x == 'WIN').mean() * 100),
        Total_PnL  = ('Total_PnL_$', 'sum'),
        Avg_Hold   = ('Hold_Days',   'mean'),
        Avg_OTM    = ('OTM_Pct',     'mean'),
        Avg_Credit = ('Credit',      'mean'),
    ).round(2)
    print(yearly.to_string())


def exit_reason_analysis(df: pd.DataFrame):
    print("\n── EXIT REASON BREAKDOWN ───────────────────────────────────────")
    exits = df.groupby('Exit_Reason').agg(
        Trades   = ('Trade_ID',    'count'),
        Avg_PnL  = ('Total_PnL_$', 'mean'),
        Tot_PnL  = ('Total_PnL_$', 'sum'),
        Avg_Hold = ('Hold_Days',   'mean'),
        Avg_OTM  = ('OTM_Pct',    'mean'),
    ).round(2)
    print(exits.to_string())


def worst_trades(df: pd.DataFrame, n=10):
    print(f"\n── TOP {n} WORST TRADES ─────────────────────────────────────────")
    cols = ['Trade_ID', 'Ticker', 'Entry_Date', 'Exit_Date', 'Hold_Days',
            'SPX_Entry', 'Short', 'OTM_Pct', 'Credit', 'Total_PnL_$', 'Exit_Reason']
    print(df.nsmallest(n, 'Total_PnL_$')[cols].to_string(index=False))


def best_trades(df: pd.DataFrame, n=10):
    print(f"\n── TOP {n} BEST TRADES ──────────────────────────────────────────")
    cols = ['Trade_ID', 'Ticker', 'Entry_Date', 'Exit_Date', 'Hold_Days',
            'SPX_Entry', 'Short', 'OTM_Pct', 'Credit', 'Total_PnL_$', 'Exit_Reason']
    print(df.nlargest(n, 'Total_PnL_$')[cols].to_string(index=False))


def ticker_summary(df: pd.DataFrame):
    print("\n── PER-TICKER SUMMARY (losers first) ───────────────────────────")
    t = df.groupby('Ticker').agg(
        Trades     = ('Trade_ID',    'count'),
        Win_Rate   = ('Result',      lambda x: (x == 'WIN').mean() * 100),
        Total_PnL  = ('Total_PnL_$', 'sum'),
        Avg_OTM    = ('OTM_Pct',     'mean'),
        Avg_Credit = ('Credit',      'mean'),
        Avg_Hold   = ('Hold_Days',   'mean'),
    ).sort_values('Total_PnL').round(2)
    print(t.to_string())


def volume_analysis(df: pd.DataFrame):
    print("\n── VOLUME ANALYSIS (10d Median at Entry) ───────────────────────")
    volume_col = 'Volume_Entry'
    if volume_col not in df.columns or df[volume_col].isna().all():
        print("  ⚠  Volume_Entry column missing — rerun backtest to populate.")
        return

    print(f"  Avg volume     : {df[volume_col].mean():,.0f}")
    print(f"  Median volume  : {df[volume_col].median():,.0f}")
    print(f"  Min volume     : {df[volume_col].min():,.0f}")
    print(f"  Max volume     : {df[volume_col].max():,.0f}")
    print(f"  % under 100K   : {(df[volume_col] < 100_000).mean() * 100:.1f}%")
    print(f"  % under 500K   : {(df[volume_col] < 500_000).mean() * 100:.1f}%")
    print(f"  % under 1M     : {(df[volume_col] < 1_000_000).mean() * 100:.1f}%")
    print(f"  % under 10M    : {(df[volume_col] < 10_000_000).mean() * 100:.1f}%")
    print(f"  % over 10M     : {(df[volume_col] > 10_000_000).mean() * 100:.1f}%")

    bins = [0, 100_000, 500_000, 1_000_000, 5_000_000, 10_000_000, float('inf')]
    labels = ['<100K', '100K-500K', '500K-1M', '1M-5M', '5M-10M', '>10M']
    df['Vol_Bucket'] = pd.cut(df[volume_col], bins=bins, labels=labels)
    dist = df.groupby('Vol_Bucket', observed=True).agg(
        Trades=('Trade_ID', 'count'),
        Win_Rate=('Is_Win', lambda x: x.mean() * 100),
        Avg_PnL=('Total_PnL_$', 'mean'),
        Avg_OTM=('OTM_Pct', 'mean'),
        Avg_Credit=('Credit', 'mean'),
    ).round(2)
    print("\n  Volume bucket distribution:")
    print(dist.to_string())

    # worst trades by volume bucket
    print("\n  Avg loss by volume bucket (losing trades only):")
    losses = df[~df['Is_Win']].groupby('Vol_Bucket', observed=True).agg(
        Trades=('Trade_ID', 'count'),
        Avg_Loss=('Total_PnL_$', 'mean'),
        Max_Loss=('Total_PnL_$', 'min'),
    ).round(2)
    print(losses.to_string())


def all_analysis(df):
    prepare_data(df)
    otm_analysis(df)
    hold_time_analysis(df)
    credit_analysis(df)
    yearly_analysis(df)
    exit_reason_analysis(df)
    worst_trades(df)
    best_trades(df)
    ticker_summary(df)
    volume_analysis(df)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "outputs/Stock_Put_Spread_Backtest.csv"
    print(f"Loading: {path}")
    df = pd.read_csv(path)
    all_analysis(df)


if __name__ == "__main__":
    main()
