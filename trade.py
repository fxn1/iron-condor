from abc import ABC, abstractmethod

from pricing import black_scholes_price
from pricing import black_scholes_delta
from pricing import find_strike_for_delta

from config import *

'''
Trade
    |
    +-- OneSidedSpreadTrade
    |       |
    |       +-- PutSpreadTrade
    |       +-- CallSpreadTrade
    |
    +-- IronCondorTrade
            |
            +-- IronCondorTradeOpen
'''

# ============================================================================
# ABSTRACT BASE
# ============================================================================


class Trade(ABC):
    """
    Abstract base for all option spread trades.

    Owns every attribute the backtest engine and reporting layer touch
    without knowing the trade type.  Subclasses implement the three
    abstract methods and optionally override manage_position / roll_stats.
    """

    def __init__(self, entry_date, expiration_date, spx_price, vix, cumulative_credit, num_contracts=1, trade_id=0):
        self.trade_id           = trade_id
        self.entry_date         = entry_date
        self.expiration_date    = expiration_date
        self.spx_price_at_entry = spx_price
        self.vix_at_entry       = vix
        self.num_contracts      = num_contracts

        # Credit / profit target — subclass __init__ passes initial credit;
        # rolls update cumulative_credit
        self.cumulative_credit    = cumulative_credit
        self.banked_pnl           = 0.0

        # Universal trade status
        self.is_open                 = True
        self.exit_date               = None
        self.exit_reason             = None
        self.pnl                     = 0.0
        self.exited_at_profit_target = False
        self.spx_price_at_exit       = None
        self.spx_price_at_expiration = None

    # ── must implement ────────────────────────────────────────────────────

    @abstractmethod
    def check_exit(self, current_date, spx_price, vix, volatility,
                   day_open=None, day_high=None, day_low=None) -> bool:
        """Return True and update state if the trade closes today."""
        ...

    @abstractmethod
    def _close_at_expiration(self, spx_price):
        """Set final pnl/status when expiration is reached."""
        ...

    # ── generic interface (IC overrides; others inherit no-ops) ──────────

    def manage_position(self, current_date, spx_price, r, put_vol, call_vol, volatility) -> tuple[bool, dict]:
        """
        Intraday position management (rolling, hedging, etc.).
        Called by the backtest engine after exit checks each day.
        Returns a dict of stat increments understood by the engine:
            { 'put_rolls', 'call_rolls', 'days_in_warn', 'days_in_roll_zone' }
        Default: no-op — spreads that don't roll just return zeros.
        """
        return False, {}

    def can_roll(self) -> bool:
        """Whether the trade can still roll (if it has a rolling plan)."""
        return False

    def roll_stats(self) -> dict:
        """
        Lifetime roll counters for reporting.
        Default: no rolls.
        """
        return {'put_rolls': 0, 'call_rolls': 0, 'rolled': False}

    # ── shared helper ─────────────────────────────────────────────────────
    def _finalize_trade_close(self, current_date, spx_price, reason):
        self.is_open = False
        self.exit_date = current_date
        if reason:
            self.exit_reason = reason
        self.spx_price_at_exit = spx_price

# ============================================================================
# IRON CONDOR TRADE WITH NET-DELTA ROLL MANAGEMENT
# ============================================================================


class IronCondorTrade(Trade):
    """
    Iron condor with net-delta roll management that supports rolling its threatened side.

    The trade tracks a *current* put spread and *current* call spread, plus
    the cumulative credit ever collected and the realized PnL banked from
    earlier (closed) instances of either spread when a roll happened.

      total_pnl = banked_pnl_from_rolls + open_put_pnl + open_call_pnl
    """

    def __init__(self, entry_date, expiration_date, spx_price, vix,
                 put_short, put_long, put_credit,
                 call_short, call_long, call_credit,
                 num_contracts=1, trade_id=0):
        super().__init__(
            entry_date, expiration_date, spx_price, vix,
            cumulative_credit = put_credit + call_credit,
            num_contracts     = num_contracts,
            trade_id          = trade_id,
        )

        # Current put spread
        self.put_short = put_short
        self.put_long  = put_long
        self.put_credit = put_credit

        # Current call spread
        self.call_short = call_short
        self.call_long  = call_long
        self.call_credit = call_credit

        # Cumulative tracking across rolls
        self.cumulative_credit = put_credit + call_credit
        self.banked_pnl = 0.0
        self.put_rolls = []   # list of dicts describing each closed put spread
        self.call_rolls = []  # list of dicts describing each closed call spread

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
        return True

    # --------------------------------------------------------- net delta

    def net_position_delta(self, spx_price, T, r, put_vol, call_vol):
        """Net delta in share-equivalent units (per 1 contract spread).
        +0.15 per share -> +15.

        Positive net delta -> position profits when SPX rises (typical when SPX
        has fallen and put side is now at-the-money / short).
        Negative net delta -> position profits when SPX falls (typical when SPX
        has rallied and call side is now at-the-money / short).
        """
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
    def _put_pnl(self, S, T, r, put_vol):
        ps = black_scholes_price(S, self.put_short, T, r, put_vol, 'put')
        pl = black_scholes_price(S, self.put_long, T, r, put_vol, 'put')
        return self.put_credit - (ps - pl)

    def _call_pnl(self, S, T, r, call_vol):
        cs = black_scholes_price(S, self.call_short, T, r, call_vol, 'call')
        cl = black_scholes_price(S, self.call_long, T, r, call_vol, 'call')
        return self.call_credit - (cs - cl)

    def _close_leg(self, side, pnl, reason):
        if side == 'put':
            self.put_leg_open = False
            self.put_leg_pnl = pnl
            self.put_exit_reason = reason
        else:
            self.call_leg_open = False
            self.call_leg_pnl = pnl
            self.call_exit_reason = reason

    def _adjust_open_pnl(self, day_open, T, r, put_vol, call_vol,
                         current_put_pnl, put_pnl_high, put_pnl_low,
                         current_call_pnl, call_pnl_low, call_pnl_high):
        """Return (stop_fill_put, stop_fill_call, profit_fill_put, profit_fill_call).
        Base: no open-price adjustment."""
        put_pnl = put_pnl_high if self.put_leg_open else self.put_leg_pnl
        call_pnl = call_pnl_low if self.call_leg_open else self.call_leg_pnl
        return put_pnl_low, call_pnl_high, put_pnl, call_pnl

    def check_exit(self, current_date, spx_price, vix, volatility, day_open=None, day_high=None, day_low=None):
        """Gap-aware exit logic."""
        if not self.is_open:
            return False
        if day_high is None: day_high = spx_price
        if day_low  is None: day_low  = spx_price
        if day_open is None: day_open = spx_price

        dte = (self.expiration_date - current_date).days
        T = max(dte / 365.0, 0.001)
        r = RISK_FREE_RATE
        put_vol  = volatility * 1.10
        call_vol = volatility * 0.95

        if self.put_leg_open:
            current_put_pnl = self._put_pnl(spx_price, T, r, put_vol)
            put_pnl_low     = self._put_pnl(day_low, T, r, put_vol)
            put_pnl_high    = self._put_pnl(day_high, T, r, put_vol)
        else:
            current_put_pnl = put_pnl_low = put_pnl_high = self.put_leg_pnl

        if self.call_leg_open:
            current_call_pnl = self._call_pnl(spx_price, T, r, call_vol)
            call_pnl_low     = self._call_pnl(day_low, T, r, call_vol)
            call_pnl_high    = self._call_pnl(day_high, T, r, call_vol)
        else:
            current_call_pnl = call_pnl_low = call_pnl_high = self.call_leg_pnl

        # Stop loss = worst-case intraday
        put_stop_hit  = (self.put_leg_open  and put_pnl_low   < -self.put_credit  * STOP_LOSS_MULTIPLIER)
        call_stop_hit = (self.call_leg_open and call_pnl_high < -self.call_credit * STOP_LOSS_MULTIPLIER)

        # Profit target = best-case intraday + banked PnL from rolls
        put_pnl  = put_pnl_high if self.put_leg_open  else self.put_leg_pnl
        call_pnl = call_pnl_low if self.call_leg_open else self.call_leg_pnl
        best_total_with_banked = self.banked_pnl + put_pnl + call_pnl
        profit_target_hit = best_total_with_banked >= self.cumulative_credit * PROFIT_TARGET

        if (put_stop_hit or call_stop_hit) and profit_target_hit:
            profit_target_hit = False  # stop wins on same-day collisions

        # save originals for 10 DTE before open-adjustment overwrites them
        put_pnl_low_raw = put_pnl_low
        call_pnl_high_raw = call_pnl_high

        put_pnl_low, call_pnl_high, put_pnl, call_pnl = (
            self._adjust_open_pnl(day_open, T, r, put_vol, call_vol,
                     current_put_pnl, put_pnl_high, put_pnl_low,
                     current_call_pnl, call_pnl_low, call_pnl_high))

        if profit_target_hit:
            self._finalize_trade_close(current_date, spx_price, "50% Profit Target")
            self._close_leg('put', put_pnl, "")
            self._close_leg('call', call_pnl, "")
            self.pnl = self.banked_pnl + self.put_leg_pnl + self.call_leg_pnl
            self.exited_at_profit_target = True
            return True

        if self.put_leg_open:
            if vix > VIX_EXIT_PUT:
                self._close_leg('put', current_put_pnl, "VIX Exit")
            elif put_stop_hit:
                self._close_leg('put', put_pnl_low, "PUT:Stop Loss")

        if self.call_leg_open and call_stop_hit:
            self._close_leg('call', call_pnl_high, "CALL:Stop Loss")

        # 10 DTE smart exit
        if self.is_open and dte <= EXIT_DTE:
            loss_threshold = -self.cumulative_credit * 0.50

            worst_put  = put_pnl_low_raw   if self.put_leg_open  else self.put_leg_pnl
            worst_call = call_pnl_high_raw if self.call_leg_open else self.call_leg_pnl
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
                        self._close_leg('put', best_put2, "10 DTE Exit")
                    if self.call_leg_open:
                        self._close_leg('call', best_call2, "10 DTE Exit")
                    self.exit_reason = "10 DTE Exit (Profitable)"
                else:
                    if self.put_leg_open:
                        self._close_leg('put', worst_put, "10 DTE Exit")
                    if self.call_leg_open:
                        self._close_leg('call', worst_call, "10 DTE Exit")
                    self.exit_reason = "10 DTE Exit (Cut Loss)"
                self._finalize_trade_close(current_date, spx_price, None)
                self.pnl = self.banked_pnl + self.put_leg_pnl + self.call_leg_pnl
                self.exited_at_profit_target = True
                return True

        # Expiration
        if current_date >= self.expiration_date:
            self.spx_price_at_exit = spx_price
            self.spx_price_at_expiration = spx_price
            self._close_at_expiration(spx_price)
            return True

        if not self.put_leg_open and not self.call_leg_open:
            self._finalize_trade_close(current_date, spx_price, "Both legs stopped out")
            self.pnl = self.banked_pnl + self.put_leg_pnl + self.call_leg_pnl
            return True

        return False

    def _close_at_expiration(self, spx_price):
        self._finalize_trade_close(self.expiration_date, spx_price, None)
        self.spx_price_at_expiration = spx_price

        if self.put_leg_open:
            if spx_price <= self.put_long:
                self._close_leg('put', self.put_credit - WING_WIDTH, "Expiration")
            elif spx_price <= self.put_short:
                self._close_leg('put', self.put_credit - (self.put_short - spx_price), "Expiration")
            else:
                self._close_leg('put', self.put_credit, "Expiration")

        if self.call_leg_open:
            if spx_price >= self.call_long:
                self._close_leg('call', self.call_credit - WING_WIDTH, "Expiration")
            elif spx_price >= self.call_short:
                self._close_leg('call', self.call_credit - (spx_price - self.call_short), "Expiration")
            else:
                self._close_leg('call', self.call_credit, "Expiration")

        self.exit_reason = "Expiration"
        self.pnl = self.banked_pnl + self.put_leg_pnl + self.call_leg_pnl

    def manage_position(self, current_date, spx_price, r, put_vol, call_vol, volatility) -> tuple[bool, dict]:
        stats = {'days_in_warn': 0, 'days_in_roll_zone': 0, 'put_rolls': 0, 'call_rolls': 0}
        dte = (self.expiration_date - current_date).days
        if dte <= EXIT_DTE:
            return False, stats  # near expiration -> let smart-exit handle it
        T = max(dte / 365.0, 0.001)
        net_delta = self.net_position_delta(spx_price, T, r, put_vol, call_vol)

        if NET_DELTA_WARN < abs(net_delta) <= NET_DELTA_ROLL:
            stats['days_in_warn'] = 1
        elif abs(net_delta) > NET_DELTA_ROLL:
            stats['days_in_roll_zone'] = 1
            if net_delta > 0:
                if self.roll_put_side(current_date, spx_price, T, RISK_FREE_RATE, put_vol, volatility):
                    stats['put_rolls'] = 1
            else:
                if self.roll_call_side(current_date, spx_price, T, RISK_FREE_RATE, call_vol, volatility):
                    stats['call_rolls'] = 1
        return True, stats

    def can_roll(self) -> bool:
        """Whether the trade can still roll (if it has a rolling plan)."""
        return self.put_leg_open and self.call_leg_open

    def roll_stats(self) -> dict:
        return {
            'put_rolls':  len(self.put_rolls),
            'call_rolls': len(self.call_rolls),
            'rolled':     bool(self.put_rolls or self.call_rolls),
        }


class IronCondorTradeOpen(IronCondorTrade):
    # --------------------------------------------------------- exit checks

    def _adjust_open_pnl(self, day_open, T, r, put_vol, call_vol,
                     current_put_pnl, put_pnl_high, put_pnl_low,
                     current_call_pnl, call_pnl_low, call_pnl_high):
        # 1. conservative pnl
        if self.put_leg_open:
            put_pnl_low = min(self._put_pnl(day_open, T, r, put_vol), put_pnl_low)
        if self.call_leg_open:
            call_pnl_high = min(self._call_pnl(day_open, T, r, call_vol), call_pnl_high)
        put_pnl = min(current_put_pnl, put_pnl_high) if self.put_leg_open else self.put_leg_pnl
        call_pnl = min(current_call_pnl, call_pnl_low) if self.call_leg_open else self.call_leg_pnl
        return put_pnl_low, call_pnl_high, put_pnl, call_pnl
