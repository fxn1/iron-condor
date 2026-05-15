from concurrent.futures import ProcessPoolExecutor as Executor
from concurrent.futures import as_completed

import pandas as pd
import glob, os
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SPX_GLOB   = os.path.join(SCRIPT_DIR, 'spx_*.xlsx')

# ============================================================================
# DATA LOADING
# ============================================================================

def load_one_file(path):
    """Load a single SPX minute file and return (daily_dict, bars, fname)."""
    fname = os.path.basename(path)

    try:
        year = int(fname.lower().replace('spx_', '').split('.')[0])
    except ValueError:
        return None

    try:
        df = pd.read_excel(path)
    except Exception as e:
        print(f"  WARN: {fname}: {e}")
        return None

    cols_lower = {c.lower(): c for c in df.columns}
    date_col = cols_lower.get('date') or cols_lower.get('datetime')
    if date_col is None:
        print(f"  WARN: {fname} has no Date column")
        return None

    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).between_time('09:30', '16:00')

    # Normalize OHLC column names
    for needed in ('Open', 'High', 'Low', 'Close'):
        if needed not in df.columns:
            low = needed.lower()
            match = next((c for c in df.columns if c.lower() == low), None)
            if match is None:
                return None
            df = df.rename(columns={match: needed})

    if df.empty:
        return None

    bars = len(df)
    daily_df = df.resample('1D').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
    }).dropna()
    daily = {}
    for idx, row in daily_df.iterrows():
        daily[idx.strftime('%Y-%m-%d')] = {
            'open': float(row['Open']), 'high': float(row['High']),
            'low': float(row['Low']), 'close': float(row['Close']),
        }
    print(f"  loaded {fname}: {bars:,} bars -> {len(daily_df)} days")

    return (daily, bars, fname)


def load_spx_daily_from_minute_files(start_year, end_year):
    start = time.time()

    files = sorted(glob.glob(SPX_GLOB))
    if not files:
        print(f"  ERROR: no files matched {SPX_GLOB}")
        return None

    # Filter by year before parallelizing
    valid_files = []
    for path in files:
        fname = os.path.basename(path)
        try:
            year = int(fname.lower().replace('spx_', '').split('.')[0])
        except ValueError:
            continue
        if start_year <= year <= end_year:
            valid_files.append(path)

    daily = {}
    total_bars = 0

    # ---- PARALLEL LOAD: 2 workers ----

    with Executor(max_workers=2) as ex:
        futures = {ex.submit(load_one_file, path): path for path in valid_files}
        for fut in as_completed(futures):
            result = fut.result()
            if result is None:
                continue

            daily_dict, bars, fname = result
            total_bars += bars
            daily.update(daily_dict)

    if not daily:
        return None

    elapsed = time.time() - start
    print(f"  TOTAL: {total_bars:,} minute bars / {len(daily)} trading days.  in {elapsed:.2f}s")

    return daily


def load_vix_data_from_excel(filepath):
    try:
        import pandas as pd
        df = pd.read_excel(filepath)
        df.columns = [c.strip().lower() for c in df.columns]
        out = {}
        for _, row in df.iterrows():
            if pd.notna(row.get('date')):
                key = pd.to_datetime(row['date']).strftime('%Y-%m-%d')
                close = row.get('close', row.get('adj close', 18.0))
                out[key] = {'close': float(close)}
        return out
    except Exception as e:
        print(f"  Error loading VIX: {e}")
        return None

