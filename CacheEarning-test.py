from datetime import timedelta, date
from config import YF_DATA_PATH

from CacheEarning import EarningsCache
STOCK_UNIVERSE = ['GOOG', 'AAPL', 'MSFT']   # list, not string
earnings_cache = EarningsCache(path=YF_DATA_PATH)
earnings_cache.download_list(STOCK_UNIVERSE)   # run once to populate

# Then in the daily scan loop:
earnings_dates = earnings_cache.get_earnings_dates('AAPL')
today = date.today()
yesterday = today - timedelta(days=1)
if yesterday in earnings_dates:
    print(f"AAPL had earnings yesterday ({yesterday})")
