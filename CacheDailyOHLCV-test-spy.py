#!/usr/bin/env python
# coding: utf-8

# https://analyzingalpha.com/sp500-historical-components-and-changes
# https://github.com/marcusschiesser/intraday/blob/master/test_intraday.py
import os
import time
from datetime import datetime, date
from CacheDailyOHLCV import CachedailyOHLCV
from snp500_ticker_hist import Snp500TickerHist
from config import gcfg


def get_old_files(cyf, path):
    now = time.time()
    old_files = ['SPY']

    for file in os.listdir(path):
        f = os.path.join(path, file)
        if os.stat(f).st_mtime < now - 1 * 86400:
            if os.path.isfile(f):
                ticker = file.replace('.csv', '')
                old_files.append(ticker)

    print("{} start {} download".format(datetime.today(), "oldfiles"))
    cyf.download_list(old_files)


def run():
    START_DATE = date.fromisoformat("2000-01-01")
    delta_days = 365*30

    hist = Snp500TickerHist()
    sp500_list = list(hist.get_spy_ticker_list())
    print(f"Current tickers: {len(sp500_list)}")
    cyf = CachedailyOHLCV(gcfg.paths.yf_data_path, START_DATE, delta_days)
    print("{} start {} download".format(datetime.today(), "spy_list"))
    cyf.download_list(sp500_list)

    get_old_files(cyf, gcfg.paths.yf_data_path)


if __name__ == '__main__':
    run()
