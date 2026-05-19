#!/usr/bin/env python3
"""
SPX Iron Condor — Net-Delta Roll Management variant.
Capital sized to the observed peak number of concurrent trades.
See backtest_engine.py for the shared engine.
"""
from config import *
from strategy_fixed4 import Fixed4Strategy
from backtest_engine import run_main

class NetDeltaStrategy(Fixed4Strategy):
    # TODO: override create_new_trade to return IronCondorTradeOpen
    pass

if __name__ == "__main__":
    run_main(
        strategy     = NetDeltaStrategy(),
        title        = "NET-DELTA ROLL MANAGEMENT",
        script_name  = "Options_Using_SPX_10_NetDelta.PY",
        capital_label= "Roll action: close threatened side, re-enter at fresh 18/14 delta",
        csv_filename = "SPX_IronCondor_10Year_NetDelta_Backtest.csv",
    )
