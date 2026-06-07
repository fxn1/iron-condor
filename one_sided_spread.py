from abc import abstractmethod
from trade import Trade
from pricing import black_scholes_price
from pricing import black_scholes_delta
from pricing import find_strike_for_delta

from config import *


class OneSidedSpreadTrade(Trade):
    """
    Generic reusable engine for:
        - Put credit spreads
        - Call credit spreads

    Child classes define:
        - option_type()
        - target_delta()
        - long_strike()
        - stop_trigger()
        - expiration_pnl()
    """

    def __init__(self, entry_date, expiration_date, spx_price, vix, short_strike, long_strike, credit, num_contracts, trade_id, profit_target_pct):
        super().__init__(entry_date, expiration_date, spx_price, vix, credit, num_contracts, trade_id)

        self.short_strike = short_strike
        self.long_strike = long_strike
        self.credit = credit
        self.rolls = []
        self.leg_open = True
        self.leg_pnl = 0.0
        self.leg_exit_reason = None
        self.profit_target_amount = credit * profit_target_pct

    # ============================================================
    # ABSTRACTS
    # ============================================================

    @abstractmethod
    def option_type(self):
        pass

    @abstractmethod
    def target_delta(self):
        pass

    @abstractmethod
    def long_strike_from_short(self, short_strike):
        pass

    @abstractmethod
    def stop_trigger_hit(self, pnl):
        pass

    @abstractmethod
    def expiration_pnl(self, spx_price):
        pass

    # ============================================================
    # CORE HELPERS
    # ============================================================

    def _spread_value(self, S, T, r, vol):
        short_price = black_scholes_price(S, self.short_strike, T, r, vol, self.option_type())
        long_price = black_scholes_price(S, self.long_strike, T, r, vol, self.option_type())
        return short_price - long_price

    def _spread_pnl(self, S, T, r, vol):
        return self.credit - self._spread_value(S, T, r, vol)

    def net_position_delta(self, spx_price, T, r, vol):
        if not self.leg_open:
            return 0.0

        short_delta = black_scholes_delta(spx_price, self.short_strike, T, r, vol, self.option_type())
        long_delta = black_scholes_delta(spx_price, self.long_strike, T, r, vol, self.option_type())
        return (-short_delta + long_delta) * 100.0

    # ============================================================
    # ROLL
    # ============================================================

    def roll_side(self, current_date, spx_price, T, r, vol):
        if len(self.rolls) >= MAX_ROLLS_PER_SIDE:
            return False

        realized = self._spread_pnl(spx_price, T, r, vol)

        self.rolls.append({
            'roll_date': current_date,
            'spx_at_roll': spx_price,
            'old_short': self.short_strike,
            'old_long': self.long_strike,
            'old_credit': self.credit,
            'realized_pnl': realized,
        })

        self.banked_pnl += realized

        new_short = find_strike_for_delta(spx_price, self.target_delta(), T, r, vol, self.option_type())
        new_long = self.long_strike_from_short(new_short)

        short_price = black_scholes_price(spx_price, new_short, T, r, vol, self.option_type())
        long_price = black_scholes_price(spx_price, new_long, T, r, vol, self.option_type())

        new_credit = short_price - long_price

        self.short_strike = new_short
        self.long_strike = new_long

        self.credit = new_credit

        self.cumulative_credit += new_credit

        self.leg_pnl = 0.0

        return True

    # ============================================================
    # CLOSE
    # ============================================================

    def _close_trade(self, pnl, reason, current_date, spx_price):

        self.leg_open = False
        self.leg_pnl = pnl

        self.is_open = False

        self.exit_reason = reason
        self.leg_exit_reason = reason

        self.exit_date = current_date

        self.pnl = self.banked_pnl + self.leg_pnl

        self.spx_price_at_exit = spx_price

    # ============================================================
    # EXIT
    # ============================================================

    def check_exit(self, current_date, spx_price, vix, volatility, day_open=None, day_high=None, day_low=None):

        if not self.is_open:
            return False
        if day_high is None: day_high = spx_price
        if day_low  is None: day_low  = spx_price

        dte = (self.expiration_date - current_date).days
        T = max(dte / 365.0, 0.001)
        r = RISK_FREE_RATE
        vol = volatility

        pnl_high = self._spread_pnl(day_high, T, r, vol)
        pnl_low = self._spread_pnl(day_low, T, r, vol)

        stop_hit = self.stop_trigger_hit(min(pnl_high, pnl_low))
        best_pnl = max(pnl_high, pnl_low)
        profit_target_hit = self.banked_pnl + best_pnl >= self.profit_target_amount

        if stop_hit and profit_target_hit:
            profit_target_hit = False  # stop wins on same-day collisions

        if stop_hit:
            self._close_trade(min(pnl_high, pnl_low), "Stop Loss", current_date, spx_price)
            return True

        if profit_target_hit:
            self._close_trade(best_pnl, "Profit Target", current_date, spx_price)
            self.exited_at_profit_target = True
            return True

        if current_date >= self.expiration_date:
            expiration_pnl = self.expiration_pnl(spx_price)
            self._close_trade(expiration_pnl, "Expiration", current_date, spx_price)
            self.spx_price_at_expiration = spx_price

            return True

        return False

    def _close_at_expiration(self, spx_price):
        pass
