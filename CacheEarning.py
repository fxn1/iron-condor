#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
import yfinance as yf
from datetime import datetime


class EarningsCache:
    """
    Downloads and caches historical earnings dates per ticker.
    Modeled after cachebt — cache-first, incremental updates.

    Source: yfinance get_earnings_dates(limit=N) which returns
    historical + upcoming earnings in one call.

    CSV schema: Date (index), Ticker, EPS Estimate, Reported EPS, Surprise(%)
    """

    def __init__(self, path):
        self.path = path

    def _get_filepath(self, ticker):
        return os.path.join(self.path, ticker + '_earnings.csv')

    def _get_cache(self, ticker):
        filepath = self._get_filepath(ticker.replace(".", "-"))
        try:
            df = pd.read_csv(filepath, parse_dates=True, index_col='Date')
            df.index = df.index.tz_localize(None)   # strip tz, matches cachebt
            return df
        except FileNotFoundError:
            return pd.DataFrame()

    def _save_cache(self, ticker, df):
        filepath = self._get_filepath(ticker)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        df.to_csv(filepath)
        print(f"{datetime.today()} Saved earnings for {ticker}: {len(df)} rows to {filepath}")

    def update_ticker(self, ticker):
        """
        Fetch all available earnings dates from yfinance (up to 4 years back).
        yfinance doesn't support incremental earnings fetch, so we always
        refresh — it's a small payload (40-50 rows per ticker).
        """
        old_df = self._get_cache(ticker)

        try:
            # limit=20 gives ~5 years of quarterly earnings
            raw = yf.Ticker(ticker).get_earnings_dates(limit=20)
        except Exception as e:
            print(f"{datetime.today()} Failed to fetch earnings for {ticker}: {e}")
            return old_df

        if raw is None or raw.empty:
            print(f"{datetime.today()} No earnings data returned for {ticker}")
            return old_df

        df = raw.copy()
        df.index = df.index.tz_localize(None)   # strip tz
        df.index.name = 'Date'

        # Merge with cache — yfinance may backfill revised EPS figures
        if not old_df.empty:
            df = pd.concat([old_df, df])
            df = df.loc[~df.index.duplicated(keep='last')]  # keep latest revision

        df.sort_index(inplace=True)
        self._save_cache(ticker, df)
        return df

    def download_list(self, tickers):
        """Returns {ticker: df} where df has DatetimeIndex of earnings dates."""
        df_list = {}
        for ticker in tickers:
            if ticker.find(".") > 0:
                ticker = ticker.replace(".", "-")
            df = self.update_ticker(ticker)
            df_list[ticker] = df
        print(f"{datetime.today()} : {len(df_list)} earnings cached")
        return df_list

    def get_ticker(self, ticker):
        """Return cached earnings df for one ticker."""
        return self._get_cache(ticker)

    def get_earnings_dates(self, ticker):
        """
        Return sorted list of past earnings dates for use in the scanner.
        Filters out future dates (reported EPS is NaN for upcoming).
        """
        df = self.get_ticker(ticker)
        if df.empty:
            return []
        # Reported EPS is populated only for past earnings
        past = df[df['Reported EPS'].notna()]
        return sorted(past.index.date.tolist())
