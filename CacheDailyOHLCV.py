#!/usr/bin/env python
# coding: utf-8


# https://github.com/marcusschiesser/intraday/blob/master/test_intraday.py
import pandas as pd
import yfinance as yf
import os
from datetime import datetime, date, timedelta


class CachedailyOHLCV:
    def __init__(self, path, start_date, delta_days):
        self.path = path
        self.start_date = start_date
        self.delta_days = delta_days
        # yf.pdr_override()
        
    @staticmethod
    def strip_tz(d):
        return d.tz_localize(None)

    def df_to_utc(self, df):
        df.index = df.index.map(self.strip_tz)

    def get_tickerfile(self, ticker):
        return os.path.join(self.path, ticker + '.csv')

    def get_cache(self, ticker):
        filename = self.get_tickerfile(ticker.replace(".", "-"))
        try:
            return pd.read_csv(filename, parse_dates=True, index_col='Date')
        except FileNotFoundError:
            print("{} Ticker cache file '{}' not found.".format(datetime.today(), filename))
            # return empty data frame on error
            return pd.DataFrame()

    def get_lastday(self, df):
        if len(df) == 0:
            return self.start_date
        return df.index.max().to_pydatetime()

    # Creating a Function
    @staticmethod
    def check_weekday(wkdate):
        # computing the parameter date with len function
        res = len(pd.bdate_range(wkdate, wkdate))
        return res != 0

    @staticmethod
    def last_week_day():
        today = date.today()
        if CachedailyOHLCV.check_weekday(today):
            return datetime.combine(today, datetime.min.time())
        today = today - timedelta(days=1)
        if CachedailyOHLCV.check_weekday(today):
            return datetime.combine(today, datetime.min.time())
        today = today - timedelta(days=1)
        return datetime.combine(today, datetime.min.time())

    def update_ticker(self, ticker):
        old_df = self.get_cache(ticker)
        last_date = self.get_lastday(old_df)
        start_date = last_date + timedelta(days=1)
        last_week_day = self.last_week_day()
        if start_date > last_week_day:
            return old_df
        end_date = start_date + timedelta(days=self.delta_days)  
        if end_date > last_week_day:
            end_date = last_week_day
        if end_date <= start_date:
            end_date = start_date + timedelta(days=1)
        print("{} getting ticker {} from {} to {}. last date={}, old_df len={}".format(datetime.today(), ticker, start_date, end_date, last_date, len(old_df)))

        # get yahoo finance data
        try:
            # yf_data = pdata.get_data_yahoo(ticker, start=start_date, end=end_date)
            yf_data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
            # Fix for yfinance 0.2.x MultiIndex columns
            if isinstance(yf_data.columns, pd.MultiIndex):
                # Single ticker: drop the ticker level, keep price fields
                yf_data.columns = yf_data.columns.get_level_values(0)
            print("{} got ticker {} from {} to {}. last date={}, yf_data len={}".format(datetime.today(), ticker, start_date, end_date, last_date, len(yf_data)))
        except ValueError:
            print("{} ignoring unknown ticker {}.".format(datetime.today(), ticker))
            return old_df

        df = yf_data
        if df.empty:
            print("{} returned data for ticker is empty - do not update cache".format(datetime.today()))
        else: 
            # append new data
            old_df = pd.concat([old_df, df], sort=False)
            last_date = self.get_lastday(old_df)
            filename = self.get_tickerfile(ticker)
            print("{} updating ticker {} to file {}, last_date={}".format(datetime.today(), ticker, filename, last_date))
            # serialize to CSV
            old_df.to_csv(filename)
        return old_df

    def download_list(self, tickers):
        df_list = {}
        for ticker in tickers:
            if ticker.find(".") > 0:
                ticker = ticker.replace(".", "-")
            df = self.update_ticker(ticker)
            df = df.loc[~df.index.duplicated(keep='first')]
            df_list[ticker] = df
        print("{} {} end download".format(datetime.today(), len(df_list)))
        return df_list

    def get_ticker(self, ticker):
        df = self.get_cache(ticker)
        # return latest data as UTC
        self.df_to_utc(df)
        return df


def get_spy_ticker_list():
    from io import StringIO
    import requests
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        html = requests.get(url, headers=headers).text
        SnPwiki = pd.read_html(StringIO(html))
        # pick columns 'ticker'
        sp500 = SnPwiki[0].iloc[:, [0]]
        sp500.columns = ['ticker']
        sp500_list = sp500['ticker'].values.tolist()
        print(f"sp500 rows {type(sp500_list)} with length {len(sp500_list)}")
        return sp500_list
    except Exception as e:
        print(f"{datetime.today()} Failed to fetch S&P 500 list: {e}")
        return []
