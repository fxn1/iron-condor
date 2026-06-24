
import pandas as pd
import os
import time

SPX_CSV_PATH = "datas/SPX.csv"

# ============================================================================
# DATA LOADING
# ============================================================================


def load_spx_daily_from_csv(start_year, end_year):
    start = time.time()

    path = SPX_CSV_PATH  # e.g. "datas/SPX.csv" — set this constant near SPX_GLOB
    if not os.path.exists(path):
        print(f"  ERROR: {path} not found")
        return None

    # Filter by year before parallelizing
    df = pd.read_csv(path, parse_dates=['Date'])
    df = df[(df['Date'].dt.year >= start_year) & (df['Date'].dt.year <= end_year)]

    if df.empty:
        return None

    daily = {}
    for _, row in df.iterrows():
        daily[row['Date'].normalize()] = {
            'open': float(row['Open']), 'high': float(row['High']),
            'low': float(row['Low']), 'close': float(row['Close']),
        }

    elapsed = time.time() - start
    print(f"  {len(daily)} trading days.  in {elapsed:.2f}s")

    return daily


def load_vix_data_from_excel(filepath):
    try:
        df = pd.read_excel(filepath)
        df.columns = [c.strip().lower() for c in df.columns]
        out = {}
        for _, row in df.iterrows():
            if pd.notna(row.get('date')):
                key = pd.Timestamp(row['date']).normalize()
                close = row.get('close', row.get('adj close', 18.0))
                out[key] = {'close': float(close)}
        return out
    except Exception as e:
        print(f"  Error loading VIX: {e}")
        return None
