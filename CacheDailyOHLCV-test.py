#!/usr/bin/env python
# coding: utf-8

from CacheDailyOHLCV import CachedailyOHLCV
from datetime import date
from config import gcfg


START_DATE = date.fromisoformat("2025-06-01")
delta_days = 365*30

cyf = CachedailyOHLCV(gcfg.paths.yf_data_path, START_DATE, delta_days)

aapl = cyf.update_ticker('SPY')
