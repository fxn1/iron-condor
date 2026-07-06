"""
Parser for Massive.com (formerly Polygon.io) options OHLC flat files.

File layout on S3 (bucket: flatfiles):
    us_options_opra/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz
    us_options_opra/minute_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz

CSV columns (identical for day/minute aggs):
    ticker,volume,open,close,high,low,window_start,transactions

- ticker: OCC-style option symbol prefixed with "O:", e.g. O:TSLA210903C00700000
- window_start: unix timestamp in NANOSECONDS since epoch, UTC
"""

import re
import gzip
from pathlib import Path

import pandas as pd

# O:<ROOT><YYMMDD><C|P><STRIKE*1000, 8 digits>
_OCC_RE = re.compile(r"^O:([A-Z]+)(\d{6})([CP])(\d{8})$")


def parse_occ_ticker(ticker: str) -> dict:
    """Decode an OCC-style option ticker (e.g. 'O:TSLA210903C00700000')."""
    m = _OCC_RE.match(ticker)
    if not m:
        raise ValueError(f"Unrecognized option ticker format: {ticker!r}")
    root, yymmdd, cp, strike_raw = m.groups()
    expiration = pd.to_datetime(yymmdd, format="%y%m%d").date()
    strike = int(strike_raw) / 1000.0
    return {
        "underlying": root,
        "expiration": expiration,
        "option_type": "call" if cp == "C" else "put",
        "strike": strike,
    }


def read_flatfile(path: str | Path, tz: str = "America/New_York") -> pd.DataFrame:
    """
    Read a single day_aggs_v1 or minute_aggs_v1 .csv.gz file into a DataFrame,
    with the OCC ticker decoded into underlying/expiration/option_type/strike columns
    and window_start converted to a tz-aware timestamp.
    """
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as f:
        df = pd.read_csv(f)

    df = df.copy()
    return _parse_raw(df, tz)


def _parse_raw(df: pd.DataFrame, tz: str) -> pd.DataFrame:
    # nanoseconds since epoch (UTC) -> tz-aware timestamp
    df["timestamp"] = pd.to_datetime(df["window_start"], unit="ns", utc=True).dt.tz_convert(tz)
    parsed = pd.DataFrame(df["ticker"].map(parse_occ_ticker).tolist(), index=df.index)
    df = pd.concat([df, parsed], axis=1)
    cols = ["underlying", "option_type", "strike", "expiration", "timestamp", "open", "high", "low", "close", "volume",
            "transactions", "ticker", ]
    return df[cols].sort_values(["underlying", "expiration", "strike", "timestamp"]).reset_index(drop=True)

def read_flatfiles(paths, tz: str = "America/New_York") -> pd.DataFrame:
    """Read and concatenate multiple flat files (e.g. a date range) into one DataFrame."""
    frames = [read_flatfile(p, tz=tz) for p in paths]
    return pd.concat(frames, ignore_index=True)


def filter_underlying(df: pd.DataFrame, underlying: str) -> pd.DataFrame:
    """Convenience filter: all option rows for a given underlying ticker."""
    return df[df["underlying"] == underlying.upper()].reset_index(drop=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python massive_options_flatfile.py <path-to-csv.gz> [UNDERLYING]")
        sys.exit(1)

    df = read_flatfile(sys.argv[1])
    if len(sys.argv) > 2:
        df = filter_underlying(df, sys.argv[2])

    print(df.head(20).to_string(index=False))
    print(f"\n{len(df):,} rows, {df['underlying'].nunique()} underlyings")
