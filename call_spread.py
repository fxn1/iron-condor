from one_sided_spread import OneSidedSpreadTrade
from config import gcfg


class CallSpreadTrade(OneSidedSpreadTrade):

    def __init__(self, ticker, entry_date, expiration_date, spx_price, vix, short_strike, long_strike, credit, cfg, trade_id):
        super().__init__(ticker, entry_date, expiration_date, spx_price, vix, short_strike, long_strike, credit, cfg, trade_id)

    def option_type(self):
        return 'call'

    def target_delta(self):
        return gcfg.stocks.call_delta

    def long_strike_from_short(self, short_strike):
        return short_strike + gcfg.stocks.wing_width

    def stop_trigger_hit(self, pnl):
        return pnl < -self.credit * gcfg.stocks.stop_loss_mult

    def expiration_pnl(self, spx_price):
        if spx_price >= self.long_strike:
            return self.credit - gcfg.stocks.wing_width
        if spx_price >= self.short_strike:
            return self.credit - (spx_price - self.short_strike)
        return self.credit
