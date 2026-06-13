from datetime import datetime
from config import gcfg

from CacheEarning import EarningsCache
from CacheDailyOHLCV import get_spy_ticker_list

STOCK_UNIVERSE = get_spy_ticker_list()
# STOCK_UNIVERSE = ['GOOG', 'AAPL', 'MSFT']   # list, not string
earnings_cache = EarningsCache(path=gcfg.paths.yf_data_path)
# earnings_cache.download_list(STOCK_UNIVERSE)   # run once to populate

ii = 0
#last_week_day = CachedailyOHLCV.last_week_day()
last_week_day = datetime(2026, 4, 21)   # hardcode for testing
for ticker in STOCK_UNIVERSE:
    earnings_dates = earnings_cache.get_earnings_dates(ticker)
    if last_week_day.date() in earnings_dates:
        print(f"{ticker} had earnings on : {last_week_day}")
        ii += 1
        if ii > 10:
            break
