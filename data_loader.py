import os
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SPX_GLOB   = os.path.join(SCRIPT_DIR, 'spx_*.xlsx')

# ============================================================================
# DATA LOADING
# ============================================================================

def load_spx_daily_from_minute_files(start_year, end_year):
    try:
        import pandas as pd
    except ImportError:
        print("  ERROR: pandas required (pip install pandas openpyxl)")
        return None

    files = sorted(glob.glob(SPX_GLOB))
    if not files:
        print(f"  ERROR: no files matched {SPX_GLOB}")
        return None

    daily = {}
    total_bars = 0
    for path in files:
        fname = os.path.basename(path)
        try:
            year = int(fname.lower().replace('spx_', '').split('.')[0])
        except ValueError:
            continue
        if year < start_year or year > end_year:
            continue

        try:
            df = pd.read_excel(path)
        except Exception as e:
            print(f"  WARN: {fname}: {e}")
            continue

        cols_lower = {c.lower(): c for c in df.columns}
        date_col = cols_lower.get('date') or cols_lower.get('datetime')
        if date_col is None:
            print(f"  WARN: {fname} has no Date column")
            continue
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.set_index(date_col).between_time('09:30', '16:00')

        for needed in ('Open', 'High', 'Low', 'Close'):
            if needed not in df.columns:
                low = needed.lower()
                match = next((c for c in df.columns if c.lower() == low), None)
                if match is None:
                    df = None
                    break
                df = df.rename(columns={match: needed})
        if df is None or df.empty:
            continue

        bars = len(df)
        total_bars += bars
        daily_df = df.resample('1D').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
        }).dropna()
        for idx, row in daily_df.iterrows():
            daily[idx.strftime('%Y-%m-%d')] = {
                'open': float(row['Open']), 'high': float(row['High']),
                'low':  float(row['Low']),  'close': float(row['Close']),
            }
        print(f"  loaded {fname}: {bars:,} bars -> {len(daily_df)} days")

    if not daily:
        return None
    print(f"  TOTAL: {total_bars:,} minute bars / {len(daily)} trading days")
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

