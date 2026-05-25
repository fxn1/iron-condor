#!/usr/bin/env python
# coding: utf-8

# https://analyzingalpha.com/sp500-historical-components-and-changes
# https://github.com/marcusschiesser/intraday/blob/master/test_intraday.py
import os
import time
import pandas as pd
from datetime import datetime, date
from CacheDailyOHLCV import CachedailyOHLCV

import ssl


def get_spy(cyf):
    # disable ssl to avoid wiki download error
    ssl._create_default_https_context = ssl._create_unverified_context
    # download sp500 from wiki
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    SnPwiki = pd.read_html(url)

    # pick columns 'ticker'
    sp500 = SnPwiki[0].iloc[:, [0]]
    sp500.columns = ['ticker']
    sp500_list = sp500['ticker'].values.tolist()
    print(f"sp500 rows {type(sp500_list)} with length {len(sp500_list)}")

    get_tkr_list(cyf, sp500_list, "spy")


def get_tkr_list(cyf, tkr_list, logstr):

    print("{} start {} download".format(datetime.today(), logstr))
    cyf.download_list(tkr_list)
    print("{} end {} download".format(datetime.today(), logstr))


def get_old_files(cyf, path):
    now = time.time()
    old_files = ['SPY']

    for file in os.listdir(path):
        f = os.path.join(path, file)
        if os.stat(f).st_mtime < now - 1 * 86400:
            if os.path.isfile(f):
                ticker = file.replace('.csv', '')
                old_files.append(ticker)

    get_tkr_list(cyf, old_files, "oldfiles")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run():
    path = os.path.join(SCRIPT_DIR, 'yfdatas', ''),
    START_DATE = date.fromisoformat("2000-01-01")
    delta_days = 365*30

    cyf = CachedailyOHLCV(path, START_DATE, delta_days)
    get_spy(cyf)
    get_old_files(cyf, path)


if __name__ == '__main__':
    run()
