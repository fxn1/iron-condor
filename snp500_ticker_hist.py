#!/usr/bin/env python3
"""
snp500_ticker_hist.py — point-in-time S&P 500 membership tracker.

Source: Wikipedia "List of S&P 500 companies" page — both the current
constituents table and the "Selected changes to the list of S&P 500
components" table on the same page.

class Snp500TickerHist:
    get_spy_ticker_list()      — fetch + cache current tickers (with Date added)
    update_universe(current_date) — apply any add/remove events on/before current_date
    is_in_universe(ticker)     — True if ticker is currently in the cached set
"""

from datetime import datetime, date
from io import StringIO

import pandas as pd
import requests

WIKI_URL = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}


def log(msg=""):
    print(f"{datetime.now()}  {msg}")


class Snp500TickerHist:
    def __init__(self):
        self.current_tickers = set()        # cached active ticker set, mutated by update_universe()
        self.date_added = {}                # {ticker: date} from the current-constituents table
        self.changes = {}                   # sorted list of date --> (added:list[str], removed:list[str])

    # ── PUBLIC API ──────────────────────────────────────────────────────

    def get_spy_ticker_list(self) -> list[str]:
        """
        Fetch current S&P 500 constituents + their 'Date added', and the
        'Selected changes' table, from Wikipedia. Caches both internally.
        Returns the list of current tickers (same contract as before).
        """
        try:
            html = requests.get(WIKI_URL, headers=HEADERS, timeout=30).text
            tables = pd.read_html(StringIO(html))
        except Exception as e:
            log(f"Failed to fetch S&P 500 page: {e}")
            return list(self.current_tickers)  # fall back to whatever is cached

        # ── table 1: current constituents ────────────────────────────
        const_table = self._find_table(tables, required_cols=['Symbol'])
        if const_table is None:
            log("WARN: could not find current-constituents table")
            for i, t in enumerate(tables):
                log(f"table {i} cols {t.columns.tolist()}")
            return list(self.current_tickers)

        symbol_col = self._match_col(const_table, 'Symbol')
        added_col  = self._match_col(const_table, 'Date added')

        self.current_tickers = set(const_table[symbol_col].astype(str).str.strip().tolist())

        if added_col is not None:
            for _, row in const_table.iterrows():
                t = str(row[symbol_col]).strip()
                dt = pd.to_datetime(row[added_col], errors='coerce')
                if pd.notna(dt):
                    self.date_added[t] = dt.date()
        log(f"sp500 rows <class 'list'> with length {len(self.current_tickers)}")

        # ── table 2: selected changes ─────────────────────────────────
        changes_table = self._find_table(tables, required_cols=['Date', 'Added', 'Removed'])
        if changes_table is None:
            log("WARN: could not find 'Selected changes' table — update_universe() will be a no-op")
        else:
            self._parse_changes_table(changes_table)
        self.recreate_earliest_universe()

    def update_universe(self, current_date) -> None:
        """
        Apply any add/remove events whose date is <= current_date.
         Mutates self.current_tickers in place.
        Assumes update_universe() is called with non-decreasing current_date
        across calls (i.e. iterating forward through a backtest date loop).
        """
        added_tickers, removed_tickers = self.changes.get(self._to_date(current_date), ([], []))
        for t in added_tickers:
            self.current_tickers.add(t)
        for t in removed_tickers:
            self.current_tickers.discard(t)

    def is_in_universe(self, ticker: str) -> bool:
        return ticker in self.current_tickers

    # ── INTERNAL HELPERS ────────────────────────────────────────────────

    @staticmethod
    def _to_date(dt) -> date:
        if isinstance(dt, date) and not isinstance(dt, datetime):
            return dt
        return pd.Timestamp(dt).date()

    @staticmethod
    def _find_table(tables, required_cols):
        """Find the first table whose columns contain all required_cols (case-insensitive substring match)."""
        for t in tables:
            cols_lower = [str(c).lower() for c in t.columns]
            if all(any(req.lower() in c for c in cols_lower) for req in required_cols):
                return t
        return None

    @staticmethod
    def _match_col(df, name_substr):
        """Find the actual column name in df matching name_substr (case-insensitive)."""
        for c in df.columns:
            if name_substr.lower() in str(c).lower():
                return c
        return None

    def _parse_changes_table(self, table):
        """
        Parse the 'Selected changes' table into self.
        changes, a dict mapping date -> [added_tickers, removed_tickers].

        Wikipedia's table typically has columns like:
        Date | Added (Ticker) | Added (Security) | Removed (Ticker) | Removed (Security) | Reason
        Column matching is done by substring, not position, to tolerate
        minor header changes.
        """
        date_col    = self._match_col(table, 'Date')
        added_col   = self._match_col(table, 'Added')
        removed_col = self._match_col(table, 'Removed')

        if date_col is None:
            log(f"missing Date, Added, Removed from cols {table.columns}")
            return

        for _, row in table.iterrows():
            dt = pd.to_datetime(row[date_col], errors='coerce')
            if pd.isna(dt):
                continue
            added_val   = row[added_col]   if added_col   is not None else None
            removed_val = row[removed_col] if removed_col is not None else None
            added_tickers   = self._split_tickers(added_val)
            removed_tickers = self._split_tickers(removed_val)

            key = dt.date()
            if key in self.changes:
                self.changes[key][0].extend(added_tickers)
                self.changes[key][1].extend(removed_tickers)
            else:
                self.changes[dt.date()] = [added_tickers, removed_tickers]
            # log(f"date={d.date()} -> [added = {added_tickers}, removed = {removed_tickers}]")
        log(f"Loaded {len(self.changes)} S&P 500 change events")

    @staticmethod
    def _split_tickers(val):
        """Handle a cell that may be a single ticker string, NaN, or comma-separated."""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return []
        s = str(val).strip()
        if not s or s.lower() == 'nan':
            return []
        return [x.strip() for x in s.split(',') if x.strip()]

    def recreate_earliest_universe(self):
        """
        Roll self.current_tickers backward through every change event,
        in descending date order, reversing add/remove. After this call,
        self.current_tickers reflects the universe just before the earliest
        recorded change event.
        """
        for dt in sorted(self.changes.keys(), reverse=True):
            added_tickers, removed_tickers = self.changes[dt]
            for t in added_tickers:
                self.current_tickers.discard(t)
            for t in removed_tickers:
                self.current_tickers.add(t)


if __name__ == "__main__":
    # quick manual smoke test — run on a machine with internet access
    hist = Snp500TickerHist()
    hist.get_spy_ticker_list()
    log(f"Current tickers: {len(hist.current_tickers)}")
    log(f"Change events loaded: {len(hist.changes)}")

    items = list(hist.changes.items())
    for d, (added, removed) in items[:3]:
        log(f"First few events: d={d}, added {added}, removed {removed} ")
    for d, (added, removed) in items[-3:]:
        log(f"Last few events: d={d}, added {added}, removed {removed} ")

    for d in sorted(hist.changes.keys()):
        if d > hist._to_date(datetime(2026, 6, 19)):
            break
        hist.update_universe(d)
    log(f"POOL in universe after update_universe(2026-06-19): {hist.is_in_universe('POOL')}")
    log(f"MRVL in universe after update_universe(2026-06-19): {hist.is_in_universe('MRVL')}")
