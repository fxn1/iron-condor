from one_sided_spread import OneSidedSpreadTrade

from config import *


class PutSpreadTrade(OneSidedSpreadTrade):

    def option_type(self):
        return 'put'

    def target_delta(self):
        return PUT_DELTA

    def long_strike_from_short(self, short_strike):
        return short_strike - WING_WIDTH

    def stop_trigger_hit(self, pnl):
        return pnl < -self.credit * STOP_LOSS_MULTIPLIER

    def expiration_pnl(self, spx_price):
        if spx_price <= self.long_strike:
            return self.credit - WING_WIDTH
        if spx_price <= self.short_strike:
            return self.credit - (self.short_strike - spx_price)
        return self.credit
