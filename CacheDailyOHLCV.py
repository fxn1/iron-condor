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
        dirname = os.path.dirname(self.path)
        return os.path.join(dirname, ticker + '.csv')

    def get_cache(self, ticker):
        filename = self.get_tickerfile(ticker)
        try:
            return pd.read_csv(filename, parse_dates=True, index_col='Date')
        except FileNotFoundError:
            print("{} Ticker cache file '{}' not found.".format(datetime.today(), filename))
            # return empty data frame on error
            return pd.DataFrame()

    def get_lastday(self, df):
        if len(df) == 0:
            return self.start_date
        return df.index.max().date()

    # Creating a Function
    @staticmethod
    def check_weekday(date):
        # computing the parameter date with len function
        res = len(pd.bdate_range(date, date))
        return res != 0

    def last_week_day(self):
        today = date.today()
        if self.check_weekday(today):
            return today
        today = today - timedelta(days=1)
        if self.check_weekday(today):
            return today
        today = today - timedelta(days=1)
        return today
 
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
        df_list = []
        ii = 0
        for ticker in tickers:
            if ticker.find(".") > 0:
                ticker = ticker.replace(".", "-")
            df = self.update_ticker(ticker)
            df = df.loc[~df.index.duplicated(keep='first')]
            df_list.append(df)
            ii += 1
        all_df = pd.concat(df_list, axis=1)
        print("{} {} {} end download".format(datetime.today(), ii, len(all_df)))
        return all_df

    def get_ticker(self, ticker):
        df = self.get_cache(ticker)
        # return latest data as UTC
        self.df_to_utc(df)
        return df
