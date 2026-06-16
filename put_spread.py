from one_sided_spread import OneSidedSpreadTrade
from pricing import black_scholes_price
from config import gcfg


class PutSpreadTrade(OneSidedSpreadTrade):

    def __init__(self, ticker, entry_date, expiration_date, spx_price, vix, short_strike, long_strike, credit, cfg, trade_id):
        super().__init__(ticker, entry_date, expiration_date, spx_price, vix, short_strike, long_strike, credit, cfg, trade_id)

    def option_type(self):
        return 'put'

    # TODO: if some derived classes don't need target_delta, consider refactoring to avoid forcing them to implement it.
    def target_delta(self):
        # Stock put spreads use support-based strikes, not delta targeting.
        # This is only reached if roll_side is ever called — not expected
        # for stock strategy but required by the abstract interface.
        raise NotImplementedError("PutSpreadTrade (stock) does not support rolling")

    def long_strike_from_short(self, short_strike):
        return short_strike - self.cfg.wing_width

    def stop_trigger_hit(self, pnl):
        return pnl < -self.credit * gcfg.stocks.stop_loss_mult

    def expiration_pnl(self, spx_price):
        if spx_price <= self.long_strike:
            return self.credit - self.cfg.wing_width
        if spx_price <= self.short_strike:
            return self.credit - (self.short_strike - spx_price)
        return self.credit


def create_put_spread_from_scan(ticker, entry_date, expiration_date, spx_price, vix, short_strike, volatility, trade_id, cfg):
    """
    Construct a PutSpreadTrade from scanner output.
    short_strike comes from scanner.scan(); long_strike derived here.
    """
    long_strike = short_strike - cfg.wing_width
    dte = (expiration_date - entry_date).days
    T   = max(dte / 365.0, 0.001)
    vol = volatility * 1.10   # matches IC put vol convention

    # print(f"create_put_spread_from_scan: spx_price={spx_price}, short_strike={short_strike}, long_strike={long_strike}. wing_width={wing_width}, T={T:.4f}, dte={dte}, r={gcfg.market.risk_free_rate:.4f}, sigma={vol:.4f}, put")
    ps = black_scholes_price(spx_price, short_strike, T, gcfg.market.risk_free_rate, vol, 'put')
    pl = black_scholes_price(spx_price, long_strike,  T, gcfg.market.risk_free_rate, vol, 'put')
    credit = ps - pl

    return PutSpreadTrade(
        ticker=ticker,
        entry_date=entry_date,
        expiration_date=expiration_date,
        spx_price=spx_price,
        vix=vix,
        short_strike=short_strike,
        long_strike=long_strike,
        credit=credit,
        cfg=cfg,
        trade_id=trade_id,
    )
