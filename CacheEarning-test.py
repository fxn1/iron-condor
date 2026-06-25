from datetime import datetime
from config import gcfg

from CacheEarning import EarningsCache
from snp500_ticker_hist import Snp500TickerHist

hist = Snp500TickerHist()
hist.get_spy_ticker_list()
earnings_cache = EarningsCache(path=gcfg.paths.yf_data_path)
# earnings_cache.download_list(STOCK_UNIVERSE)   # run once to populate

ii = 0
#last_week_day = CachedailyOHLCV.last_week_day()
last_week_day = datetime(2026, 4, 21)   # hardcode for testing
hist.universe_as_of(last_week_day)
sp500_list = hist.active_tickers
# sp500_list = ['GOOG', 'AAPL', 'MSFT']   # list, not string
print(f"Current tickers: {len(sp500_list)}")
for ticker in sp500_list:
    earnings_dates = earnings_cache.get_earnings_dates(ticker)
    if last_week_day.date() in earnings_dates:
        print(f"{ticker} had earnings on : {last_week_day}")
        ii += 1
        if ii > 10:
            break
