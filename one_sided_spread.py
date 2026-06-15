from abc import abstractmethod
from trade import Trade
from pricing import black_scholes_price
from pricing import black_scholes_delta
from config import gcfg


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

    def __init__(self, ticker, entry_date, expiration_date, price, vix, short_strike, long_strike, credit, cfg, trade_id):
        super().__init__(ticker, entry_date, expiration_date, price, vix, credit, cfg, trade_id)

        self.short_strike = short_strike
        self.long_strike = long_strike
        self.credit = credit
        self.rolls = []
        self.leg_open = True
        self.leg_pnl = 0.0
        self.leg_exit_reason = None
        self.profit_target_amount = credit * cfg.profit_target

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
    def expiration_pnl(self, price):
        pass

    # ============================================================
    # CORE HELPERS
    # ============================================================

    def _spread_value(self, S, T, r, vol):
        short_price = black_scholes_price(S, self.short_strike, T, r, vol, self.option_type())
        long_price = black_scholes_price(S, self.long_strike, T, r, vol, self.option_type())
        # TODO: debug trade
        if self.trade_id <= gcfg.stocks.debug_trade_id:
            print(
                f"VAL id={self.trade_id} "
                f"S={S:.2f} "
                f"vol={vol:.3f} "
                f"short={short_price:.4f} "
                f"long={long_price:.4f} "
                f"spread={short_price - long_price:.4f}"
            )
        return short_price - long_price

    def _spread_pnl(self, S, T, r, vol):
        return self.credit - self._spread_value(S, T, r, vol)

    def net_position_delta(self, price, T, r, vol):
        if not self.leg_open:
            return 0.0

        short_delta = black_scholes_delta(price, self.short_strike, T, r, vol, self.option_type())
        long_delta = black_scholes_delta(price, self.long_strike, T, r, vol, self.option_type())
        return (-short_delta + long_delta) * 100.0

    # ============================================================
    # CLOSE
    # ============================================================

    def _close_trade(self, pnl, reason, current_date, price):
        # TODO: debug trade
        if self.trade_id <= gcfg.stocks.debug_trade_id:
            print(
                f"CLOSE {self.trade_id} "
                f"reason={reason} "
                f"days={(current_date - self.entry_date).days} "
                f"credit={self.credit:.4f} "
                f"pnl={pnl:.4f}"
            )
        self.leg_open = False
        self.leg_pnl = pnl
        self.is_open = False
        self.exit_reason = reason
        self.leg_exit_reason = reason
        self.exit_date = current_date
        self.pnl = self.banked_pnl + self.leg_pnl
        self.spx_price_at_exit = price

    # ============================================================
    # EXIT
    # ============================================================

    def check_exit(self, current_date, price, vix, volatility, day_open=None, day_high=None, day_low=None):

        if not self.is_open:
            return False
        if day_high is None: day_high = price
        if day_low  is None: day_low  = price

        dte = (self.expiration_date - current_date).days
        T = max(dte / 365.0, 0.001)
        r = gcfg.market.risk_free_rate
        vol = volatility

        pnl_high = self._spread_pnl(day_high, T, r, vol)
        pnl_low = self._spread_pnl(day_low, T, r, vol)

        # ── stop loss: check worst intraday price
        stop_hit = self.stop_trigger_hit(min(pnl_high, pnl_low))

        # ── profit target: use CLOSE only, not intraday best ─────────────
        # best_pnl = max(pnl_high, pnl_low)
        pnl_close = self._spread_pnl(price, T, r, vol)
        profit_target_hit = self.banked_pnl + pnl_close >= self.profit_target_amount

        if stop_hit and profit_target_hit:
            profit_target_hit = False  # stop wins on same-day collisions

        if stop_hit:
            self._close_trade(min(pnl_high, pnl_low), "Stop Loss", current_date, price)
            return True

        # TODO: debug trade
        if self.trade_id <= gcfg.stocks.debug_trade_id:
            print(
                f"EXITCHK id={self.trade_id} "
                f"dte={dte} "
                f"entry_credit={self.credit:.4f} "
                f"spread_value={self._spread_value(price, T, r, vol):.4f} "
                f"pnl_close={pnl_close:.4f} "
                f"target={self.profit_target_amount:.4f}"
                f"credit={self.credit:.4f} "
                f"target={self.profit_target_amount:.4f} "
            )
        if profit_target_hit:
            # TODO: debug trades
            if self.trade_id <= gcfg.stocks.debug_trade_id:
                print(
                    f"EXIT PROFIT "
                    f"id={self.trade_id} "
                    f"target={self.profit_target_amount:.4f} "
                    f"pnl_close={pnl_close:.4f} "
                    f"credit={self.credit:.4f}"
                )
            self._close_trade(pnl_close, "Profit Target", current_date, price)
            self.exited_at_profit_target = True
            return True

        if current_date >= self.expiration_date:
            expiration_pnl = self.expiration_pnl(price)
            self._close_trade(expiration_pnl, "Expiration", current_date, price)
            self.spx_price_at_expiration = price
            return True
        return False

    def _close_at_expiration(self, price):
        pass
