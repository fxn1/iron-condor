#!/usr/bin/env python3
"""
SPX Iron Condor — Net-Delta Roll Management variant.
Capital sized to the observed peak number of concurrent trades.
See backtest_engine.py for the shared engine.
"""
from datetime import datetime
from Options_Using_SPX_10_NetDelta_Fixed4 import Fixed4Strategy
from backtest_engine import run_main
from config import *


class NetDeltaStrategy(Fixed4Strategy):
    # TODO: override create_new_trade to return IronCondorTradeOpen
    def print_strategy_config(self):
        print(f"  Underlying:    SPX (real 1-min data, resampled to daily)")
        print(f"  Strategy:      18/14 delta IC, ${WING_WIDTH} wings, Monday entry, 30 DTE")
        print(f"  Roll rule:     |net delta| > {NET_DELTA_ROLL}  (warn at +/-{NET_DELTA_WARN})")
        print(f"  Capital:       fixed assumption of {CONCURRENT_TRADES} concurrent trades")


if __name__ == "__main__":
    strategy = NetDeltaStrategy()

    run_main(
        strategy     = strategy,
        title        = "NET-DELTA ROLL MANAGEMENT",
        script_name  = "Options_Using_SPX_10_NetDelta.PY",
        csv_filename = "SPX_IronCondor_10Year_NetDelta_Backtest.csv",
        start_date   = datetime(2016, 5, 9),
        delta_days   = 365*10,
    )
