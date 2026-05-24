from one_sided_spread import OneSidedSpreadTrade

from config import *


class CallSpreadTrade(OneSidedSpreadTrade):

    def option_type(self):
        return 'call'

    def target_delta(self):
        return CALL_DELTA

    def long_strike_from_short(self, short_strike):
        return short_strike + WING_WIDTH

    def stop_trigger_hit(self, pnl):
        return pnl < -self.credit * STOP_LOSS_MULTIPLIER

    def expiration_pnl(self, spx_price):
        if spx_price >= self.long_strike:
            return self.credit - WING_WIDTH
        if spx_price >= self.short_strike:
            return self.credit - (spx_price - self.short_strike)
        return self.credit
