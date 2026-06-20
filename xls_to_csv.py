#!/usr/bin/env python3
"""
xls_to_csv.py — one-time converter for SPX minute-bar files.

Converts each SPX_*.xlsx file matched by SPX_GLOB into a CSV with the
same columns, so load_one_file() (in the SPX loader) can read CSV
instead of XLS — same minute-bar grain, same resampling logic downstream,
just a faster file format.

Usage:
    python xls_to_csv.py --glob "SPX_*.xlsx" --out_file datas/SPX.csv
"""

import argparse
import glob
import os
import time

import pandas as pd


def convert_one_file(path):
    fname = os.path.basename(path)

    try:
        df = pd.read_excel(path)
    except Exception as e:
        print(f"  WARN: {fname}: {e}")
        return None

    # ── same column normalization as load_one_file, so the CSV is ready ──
    cols_lower = {c.lower(): c for c in df.columns}
    date_col = cols_lower.get('date') or cols_lower.get('datetime')
    if date_col is None:
        print(f"  WARN: {fname} has no Date column — skipped")
        return None

    df[date_col] = pd.to_datetime(df[date_col])
    if date_col != 'Date':
        df = df.rename(columns={date_col: 'Date'})
    df = df.set_index(date_col).between_time('09:30', '16:00')

    for needed in ('Open', 'High', 'Low', 'Close'):
        if needed not in df.columns:
            low = needed.lower()
            match = next((c for c in df.columns if c.lower() == low), None)
            if match is None:
                print(f"  WARN: {fname} missing {needed} column — skipped")
                return None
            df = df.rename(columns={match: needed})

    if df.empty:
        return None
    # ── resample to daily here, once, at conversion time ──
    daily_df = df.resample('1D').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
    }).dropna()
    daily_df.index.name = 'Date'
    daily_df = daily_df.reset_index()
    daily_df['Date'] = daily_df['Date'].dt.normalize()

    print(f"  converted {fname}: {len(df):,} bars -> {len(daily_df)} days")
    return daily_df


def main():
    parser = argparse.ArgumentParser(description='Convert minute-bar XLS files to CSV')
    parser.add_argument('--glob', type=str, default="datas/spx_*.xlsx", help='Glob pattern for source XLS files (e.g. "data/SPX_*.xlsx")')
    parser.add_argument('--out_file', type=str, default='datas/SPX.csv', help='Output file for CSV (default: datas/SPX.csv)')
    args = parser.parse_args()

    files = sorted(glob.glob(args.glob))
    if not files:
        print(f"  ERROR: no files matched {args.glob}")
        return

    start = time.time()
    count  = 0
    frames = []
    for path in files:
        df = convert_one_file(path)
        if df is None:
            continue
        frames.append(df)
        count  += 1
    if not frames:
        print("  ERROR: no files converted successfully")
        return

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values('Date')
    combined.to_csv(args.out_file, index=False)

    elapsed = time.time() - start
    print(f"\n out_file={args.out_file}, {count}/{len(files)} files processed, {len(combined):,} total rows, in {elapsed:.2f}s")


if __name__ == "__main__":
    main()
