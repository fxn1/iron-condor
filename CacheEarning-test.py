import os
from datetime import timedelta, date

from CacheEarning import EarningsCache
STOCK_UNIVERSE = ['GOOG', 'AAPL', 'MSFT']   # list, not string
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
earnings_cache = EarningsCache(path=os.path.join(SCRIPT_DIR, 'yfdatas'))
earnings_cache.download_list(STOCK_UNIVERSE)   # run once to populate

# Then in the daily scan loop:
earnings_dates = earnings_cache.get_earnings_dates('AAPL')
today = date.today()
yesterday = today - timedelta(days=1)
if yesterday in earnings_dates:
    print(f"AAPL had earnings yesterday ({yesterday})")
