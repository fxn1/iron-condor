#!/usr/bin/env python
# coding: utf-8

from CacheDailyOHLCV import CachedailyOHLCV
from datetime import date
from config import YF_DATA_PATH

START_DATE = date.fromisoformat("2025-06-01")
delta_days = 365*30

cyf = CachedailyOHLCV(YF_DATA_PATH, START_DATE, delta_days)

aapl = cyf.update_ticker('SPY')
