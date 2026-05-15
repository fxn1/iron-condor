class BaseStrategy:

    def should_enter_trade(self, current_date, vix, exp_key, used_expirations):
        raise NotImplementedError

    def should_reenter_after_exit(self, trade, vix):
        raise NotImplementedError
