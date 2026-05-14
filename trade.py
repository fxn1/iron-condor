from pricing import black_scholes_price
from pricing import black_scholes_delta
from pricing import find_strike_for_delta

from config import *

# ============================================================================
# IRON CONDOR TRADE WITH NET-DELTA ROLL MANAGEMENT
# ============================================================================


class IronCondorTrade:
    """
    Iron condor that supports rolling its threatened side.

    The trade tracks a *current* put spread and *current* call spread, plus
    the cumulative credit ever collected and the realized PnL banked from
    earlier (closed) instances of either spread when a roll happened.

      total_pnl_at_any_time =
          banked_pnl_from_rolls + open_put_pnl + open_call_pnl
      profit_target_amount =
          cumulative_credit_collected * PROFIT_TARGET
    """

    def __init__(self, entry_date, expiration_date, spx_price, vix,
                 put_short, put_long, put_credit,
                 call_short, call_long, call_credit,
                 num_contracts=1, trade_id=0):
        self.trade_id = trade_id
        self.entry_date = entry_date
        self.expiration_date = expiration_date
        self.spx_price_at_entry = spx_price
        self.vix_at_entry = vix
        self.num_contracts = num_contracts

        # CURRENT put spread
        self.put_short = put_short
        self.put_long  = put_long
        self.put_credit = put_credit

        # CURRENT call spread
        self.call_short = call_short
        self.call_long  = call_long
        self.call_credit = call_credit

        # Cumulative tracking across rolls
        self.cumulative_credit = put_credit + call_credit
        self.banked_pnl = 0.0
        self.put_rolls = []   # list of dicts describing each closed put spread
        self.call_rolls = []  # list of dicts describing each closed call spread

        self.total_credit = self.cumulative_credit  # used by profit target
        self.profit_target_amount = self.cumulative_credit * PROFIT_TARGET

        # Trade status
        self.is_open = True
        self.exit_date = None
        self.exit_reason = None
        self.pnl = 0.0

        # Per-leg open status
        self.put_leg_open = True
        self.call_leg_open = True
        self.put_leg_pnl  = 0.0   # PnL on the *current* open put spread
        self.call_leg_pnl = 0.0
        self.put_exit_reason = None
        self.call_exit_reason = None

        self.spx_price_at_exit = None
        self.spx_price_at_expiration = None
        self.exited_at_profit_target = False

    # ------------------------------------------------------------------ rolls

    def _refresh_profit_target(self):
        self.total_credit = self.cumulative_credit
        self.profit_target_amount = self.cumulative_credit * PROFIT_TARGET

    def roll_put_side(self, current_date, spx_price, T, r, put_vol, vol):
        """Close the current put spread, open a new one at PUT_DELTA target."""
        if len(self.put_rolls) >= MAX_ROLLS_PER_SIDE:
            return False
        # Realised PnL on the closing spread
        ps = black_scholes_price(spx_price, self.put_short, T, r, put_vol, 'put')
        pl = black_scholes_price(spx_price, self.put_long,  T, r, put_vol, 'put')
        realised = self.put_credit - (ps - pl)
        self.put_rolls.append({
            'roll_date': current_date,
            'spx_at_roll': spx_price,
            'old_short': self.put_short,
            'old_long':  self.put_long,
            'old_credit': self.put_credit,
            'realized_pnl': realised,
        })
        self.banked_pnl += realised

        # Open a new put spread at the target delta
        new_short = find_strike_for_delta(spx_price, PUT_DELTA, T, r, put_vol, 'put')
        new_long  = new_short - WING_WIDTH
        nps = black_scholes_price(spx_price, new_short, T, r, put_vol, 'put')
        npl = black_scholes_price(spx_price, new_long,  T, r, put_vol, 'put')
        new_credit = nps - npl

        self.put_short  = new_short
        self.put_long   = new_long
        self.put_credit = new_credit
        self.put_leg_pnl = 0.0
        self.cumulative_credit += new_credit
        self._refresh_profit_target()
        return True

    def roll_call_side(self, current_date, spx_price, T, r, call_vol, vol):
        """Close the current call spread, open a new one at CALL_DELTA target."""
        if len(self.call_rolls) >= MAX_ROLLS_PER_SIDE:
            return False
        cs = black_scholes_price(spx_price, self.call_short, T, r, call_vol, 'call')
        cl = black_scholes_price(spx_price, self.call_long,  T, r, call_vol, 'call')
        realised = self.call_credit - (cs - cl)
        self.call_rolls.append({
            'roll_date': current_date,
            'spx_at_roll': spx_price,
            'old_short': self.call_short,
            'old_long':  self.call_long,
            'old_credit': self.call_credit,
            'realized_pnl': realised,
        })
        self.banked_pnl += realised

        new_short = find_strike_for_delta(spx_price, CALL_DELTA, T, r, call_vol, 'call')
        new_long  = new_short + WING_WIDTH
        ncs = black_scholes_price(spx_price, new_short, T, r, call_vol, 'call')
        ncl = black_scholes_price(spx_price, new_long,  T, r, call_vol, 'call')
        new_credit = ncs - ncl

        self.call_short  = new_short
        self.call_long   = new_long
        self.call_credit = new_credit
        self.call_leg_pnl = 0.0
        self.cumulative_credit += new_credit
        self._refresh_profit_target()
        return True

    # --------------------------------------------------------- net delta

    def net_position_delta(self, spx_price, T, r, put_vol, call_vol):
        """Net delta in share-equivalent units (per 1 contract spread). +0.15 per share -> +15."""
        put_pos = 0.0
        if self.put_leg_open:
            d_ps = black_scholes_delta(spx_price, self.put_short, T, r, put_vol, 'put')
            d_pl = black_scholes_delta(spx_price, self.put_long,  T, r, put_vol, 'put')
            put_pos = -d_ps + d_pl
        call_pos = 0.0
        if self.call_leg_open:
            d_cs = black_scholes_delta(spx_price, self.call_short, T, r, call_vol, 'call')
            d_cl = black_scholes_delta(spx_price, self.call_long,  T, r, call_vol, 'call')
            call_pos = -d_cs + d_cl
        return (put_pos + call_pos) * 100.0

    # --------------------------------------------------------- exit checks

    def check_exit(self, current_date, spx_price, vix, volatility,
                   day_high=None, day_low=None):
        """Gap-aware exit logic."""
        if not self.is_open:
            return False
        if day_high is None: day_high = spx_price
        if day_low  is None: day_low  = spx_price

        dte = (self.expiration_date - current_date).days
        T = max(dte / 365.0, 0.001)
        r = RISK_FREE_RATE
        put_vol  = volatility * 1.10
        call_vol = volatility * 0.95

        def _put_pnl(S):
            ps = black_scholes_price(S, self.put_short, T, r, put_vol, 'put')
            pl = black_scholes_price(S, self.put_long,  T, r, put_vol, 'put')
            return self.put_credit - (ps - pl)

        def _call_pnl(S):
            cs = black_scholes_price(S, self.call_short, T, r, call_vol, 'call')
            cl = black_scholes_price(S, self.call_long,  T, r, call_vol, 'call')
            return self.call_credit - (cs - cl)

        if self.put_leg_open:
            current_put_pnl = _put_pnl(spx_price)
            put_pnl_low     = _put_pnl(day_low)
            put_pnl_high    = _put_pnl(day_high)
        else:
            current_put_pnl = put_pnl_low = put_pnl_high = self.put_leg_pnl

        if self.call_leg_open:
            current_call_pnl = _call_pnl(spx_price)
            call_pnl_low     = _call_pnl(day_low)
            call_pnl_high    = _call_pnl(day_high)
        else:
            current_call_pnl = call_pnl_low = call_pnl_high = self.call_leg_pnl

        put_stop_hit  = (self.put_leg_open  and put_pnl_low   < -self.put_credit  * STOP_LOSS_MULTIPLIER)
        call_stop_hit = (self.call_leg_open and call_pnl_high < -self.call_credit * STOP_LOSS_MULTIPLIER)

        best_put  = put_pnl_high if self.put_leg_open  else self.put_leg_pnl
        best_call = call_pnl_low if self.call_leg_open else self.call_leg_pnl
        best_total_with_banked = self.banked_pnl + best_put + best_call
        profit_target_hit = best_total_with_banked >= self.profit_target_amount

        if (put_stop_hit or call_stop_hit) and profit_target_hit:
            profit_target_hit = False

        if profit_target_hit:
            self.is_open = False
            self.exit_date = current_date
            self.exit_reason = "50% Profit Target"
            self.put_leg_pnl  = best_put
            self.call_leg_pnl = best_call
            self.pnl = self.banked_pnl + self.put_leg_pnl + self.call_leg_pnl
            self.put_leg_open = False
            self.call_leg_open = False
            self.spx_price_at_exit = spx_price
            self.exited_at_profit_target = True
            return True

        if self.put_leg_open:
            if vix > VIX_EXIT_PUT:
                self.put_leg_open = False
                self.put_leg_pnl = current_put_pnl
                self.put_exit_reason = "VIX Exit"
            elif put_stop_hit:
                self.put_leg_open = False
                # Record at the ACTUAL gap price, not the -2x cap.
                self.put_leg_pnl = put_pnl_low
                self.put_exit_reason = "PUT:Stop Loss"

        if self.call_leg_open and call_stop_hit:
            self.call_leg_open = False
            # Record at the ACTUAL gap price (day high for calls), not -2x cap.
            self.call_leg_pnl = call_pnl_high
            self.call_exit_reason = "CALL:Stop Loss"

        if self.is_open and dte <= EXIT_DTE:
            loss_threshold = -self.cumulative_credit * 0.50

            worst_put  = put_pnl_low   if self.put_leg_open  else self.put_leg_pnl
            worst_call = call_pnl_high if self.call_leg_open else self.call_leg_pnl
            worst_total = self.banked_pnl + worst_put + worst_call
            best_put2  = put_pnl_high if self.put_leg_open  else self.put_leg_pnl
            best_call2 = call_pnl_low if self.call_leg_open else self.call_leg_pnl
            best_total = self.banked_pnl + best_put2 + best_call2

            cut_loss_hit    = worst_total < loss_threshold
            take_profit_hit = best_total > 0
            if cut_loss_hit and take_profit_hit:
                take_profit_hit = False

            if take_profit_hit or cut_loss_hit:
                if take_profit_hit:
                    if self.put_leg_open:
                        self.put_leg_pnl = best_put2; self.put_leg_open = False
                        self.put_exit_reason = "10 DTE Exit"
                    if self.call_leg_open:
                        self.call_leg_pnl = best_call2; self.call_leg_open = False
                        self.call_exit_reason = "10 DTE Exit"
                    self.exit_reason = "10 DTE Exit (Profitable)"
                else:
                    if self.put_leg_open:
                        self.put_leg_pnl = worst_put; self.put_leg_open = False
                        self.put_exit_reason = "10 DTE Exit"
                    if self.call_leg_open:
                        self.call_leg_pnl = worst_call; self.call_leg_open = False
                        self.call_exit_reason = "10 DTE Exit"
                    self.exit_reason = "10 DTE Exit (Cut Loss)"
                self.is_open = False
                self.exit_date = current_date
                self.pnl = self.banked_pnl + self.put_leg_pnl + self.call_leg_pnl
                self.spx_price_at_exit = spx_price
                self.exited_at_profit_target = True
                return True

        if current_date >= self.expiration_date:
            self.spx_price_at_exit = spx_price
            self.spx_price_at_expiration = spx_price
            self._close_at_expiration(spx_price)
            return True

        if not self.put_leg_open and not self.call_leg_open:
            self.is_open = False
            self.exit_date = current_date
            self.exit_reason = "Both legs stopped out"
            self.pnl = self.banked_pnl + self.put_leg_pnl + self.call_leg_pnl
            self.spx_price_at_exit = spx_price
            return True

        return False

    def _close_at_expiration(self, spx_price):
        self.is_open = False
        self.exit_date = self.expiration_date
        self.spx_price_at_exit = spx_price
        self.spx_price_at_expiration = spx_price

        if self.put_leg_open:
            self.put_exit_reason = "Expiration"
            if spx_price <= self.put_long:
                self.put_leg_pnl = self.put_credit - WING_WIDTH
            elif spx_price <= self.put_short:
                self.put_leg_pnl = self.put_credit - (self.put_short - spx_price)
            else:
                self.put_leg_pnl = self.put_credit
            self.put_leg_open = False

        if self.call_leg_open:
            self.call_exit_reason = "Expiration"
            if spx_price >= self.call_long:
                self.call_leg_pnl = self.call_credit - WING_WIDTH
            elif spx_price >= self.call_short:
                self.call_leg_pnl = self.call_credit - (spx_price - self.call_short)
            else:
                self.call_leg_pnl = self.call_credit
            self.call_leg_open = False

        self.exit_reason = "Expiration"
        self.pnl = self.banked_pnl + self.put_leg_pnl + self.call_leg_pnl

