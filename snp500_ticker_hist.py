#!/usr/bin/env python3
"""
snp500_ticker_hist.py — point-in-time S&P 500 membership tracker.

Source: Wikipedia "List of S&P 500 companies" page — both the current
constituents table and the "Selected changes to the list of S&P 500
components" table on the same page.

class Snp500TickerHist:
    get_spy_ticker_list()       — fetch current tickers + date_added + changes log
    universe_as_of(target_date) — compute and cache the active universe as of target_date
    update_universe(current_date) — add/remove events on current_date to active_tickers
    is_in_universe(ticker)      — True if ticker is in the cached active_tickers set

Two distinct sets are maintained:
    current_tickers — full historical superset (today's list; used by callers
                       that need every ticker ever active, e.g. price data loading)
    active_tickers  — point-in-time active set, advanced via universe_as_of()
                       then update_universe(); used by is_in_universe() to gate
                       new trade entry only — exits/other activity should use
                       current_tickers / price_data directly, not this gate.
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
        self.current_tickers = set()   # full historical superset (today's live list)
        self.active_tickers = set()    # point-in-time active set, used by is_in_universe()
        self.date_added = {}           # {ticker: date} — only for tickers active today
        self.changes = {}              # sorted list of {date: [added_tickers, removed_tickers]}

    # ── PUBLIC API ──────────────────────────────────────────────────────

    def get_spy_ticker_list(self) -> set[str]:
        """
        Fetch current S&P 500 constituents + their 'Date added', and the
        'Selected changes' table, from Wikipedia. Caches both internally.
        Returns the current ticker set.
        """
        try:
            html = requests.get(WIKI_URL, headers=HEADERS, timeout=30).text
            tables = pd.read_html(StringIO(html))
        except Exception as e:
            log(f"Failed to fetch S&P 500 page: {e}")
            return self.current_tickers  # fall back to whatever is cached

        # ── table 1: current constituents ────────────────────────────
        const_table = self._find_table(tables, required_cols=['Symbol'])
        if const_table is None:
            log("WARN: could not find current-constituents table")
            for i, t in enumerate(tables):
                log(f"table {i} cols {t.columns.tolist()}")
            return self.current_tickers

        symbol_col = self._match_col(const_table, 'Symbol')
        added_col  = self._match_col(const_table, 'Date added')

        self.current_tickers = set(const_table[symbol_col].astype(str).str.strip().tolist())

        if added_col is not None:
            for _, row in const_table.iterrows():
                t = str(row[symbol_col]).strip()
                dt = pd.to_datetime(row[added_col], errors='coerce')
                if pd.notna(dt):
                    self.date_added[t] = dt.date()

        # ── table 2: selected changes ─────────────────────────────────
        changes_table = self._find_table(tables, required_cols=['Date', 'Added', 'Removed'])
        if changes_table is None:
            log("WARN: could not find 'Selected changes' table — universe_as_of()/update_universe() will be no-ops")
        else:
            self._parse_changes_table(changes_table)
        return self.current_tickers

    def update_universe(self, input_date) -> None:
        """
        add/remove events whose date exactly matches current_date to self.active_tickers. Must be called once per date, in date order,
        from the caller's date loop, after universe_as_of() has initialized self.active_tickers to the loop's start_date.
        """
        added_tickers, removed_tickers = self.changes.get(self._to_date(input_date), ([], []))
        for t in added_tickers:
            self.active_tickers.add(t)
        for t in removed_tickers:
            self.active_tickers.discard(t)

    def universe_as_of(self, target_date: datetime = datetime.max):
        """
        Compute the active universe as of target_date.

        Primary method: roll self.current_tickers (today's superset) backward through changes, reversing each event with date > target_date.

        Fallback refinement: for tickers with a known date_added (i.e. still active today), if date_added > target_date, the ticker could not have
        been active yet — drop it even if changes didn't cover that far back.

        Caches the result in self.active_tickers and returns it.
        """
        target = self._to_date(target_date)
        self.active_tickers = set(self.current_tickers)

        for dt in sorted(self.changes.keys(), reverse=True):
            if dt <= target:
                break
            self.reverse_update_universe(dt)

        # refine using date_added where self.changes doesn't reach far enough back
        for t, dt in self.date_added.items():
            if dt > target:
                self.active_tickers.discard(t)

    def reverse_update_universe(self, input_date):
        """
        Roll self.active_tickers backward the change event, for input_date reversing add/remove.
        After this call, self.active_tickers reflects the universe just before the input_date
        recorded change event.
        """
        added_tickers, removed_tickers = self.changes[input_date]
        for t in added_tickers:
            self.active_tickers.discard(t)
        for t in removed_tickers:
            self.active_tickers.add(t)
            self.current_tickers.add(t)

    def is_in_universe(self, ticker: str) -> bool:
        """True if ticker is in the current point-in-time active set. Use only to gate new trade entry."""
        return ticker in self.active_tickers

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
        Parse the 'Selected changes' table into changes, a dict mapping date -> [added_tickers, removed_tickers]. Merges rows
        that share the same date instead of overwriting.
        Wikipedia's table typically has columns like:
        Date | Added (Ticker) | Added (Security) | Removed (Ticker) | Removed (Security) | Reason
        Column matching is done by substring, not position, to tolerate minor header changes.
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
                self.changes[key] = [added_tickers, removed_tickers]
            # log(f"date={d.date()} -> [added = {added_tickers}, removed = {removed_tickers}]")
        log(f"S&P 500 change events change events loaded: {len(self.changes)}")

    @staticmethod
    def _split_tickers(val):
        """Handle a cell that may be a single ticker string, NaN, or comma-separated."""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return []
        s = str(val).strip()
        if not s or s.lower() == 'nan':
            return []
        return [x.strip() for x in s.split(',') if x.strip()]


if __name__ == "__main__":
    # quick manual smoke test — run on a machine with internet access
    hist = Snp500TickerHist()
    sp500_list = list(hist.get_spy_ticker_list())
    log(f"Current tickers: {len(sp500_list)}")
    log(f"Current active tickers: {len(hist.active_tickers)}")

    items = list(hist.changes.items())
    for d, (added, removed) in items[:3]:
        log(f"First few events: d={d}, added {added}, removed {removed} ")
    for d, (added, removed) in items[-3:]:
        log(f"Last few events: d={d}, added {added}, removed {removed} ")

    asOfDate = datetime(2026, 6, 19)
    hist.universe_as_of(asOfDate)
    log(f"Current tickers asOfDate {asOfDate}: {len(hist.current_tickers)}")
    log(f"Current active tickers asOfDate {asOfDate}: {len(hist.active_tickers)}")
    log(f"POOL in universe after update_universe(2026-06-19): {hist.is_in_universe('POOL')}")
    log(f"MRVL in universe after update_universe(2026-06-19): {hist.is_in_universe('MRVL')}")
