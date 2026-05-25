#!/usr/bin/env python
# coding: utf-8

import os
from CacheDailyOHLCV import CachedailyOHLCV
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(SCRIPT_DIR, 'yfdatas', ''),
START_DATE = date.fromisoformat("2025-06-01")
delta_days = 365*30

cyf = CachedailyOHLCV(path, START_DATE, delta_days)

aapl = cyf.update_ticker('SPY')
