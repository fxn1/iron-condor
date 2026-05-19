#!/usr/bin/env python3
"""
================================================================================
SPX IRON CONDOR - 10 YEAR BACKTEST

Inputs:
    * Real SPX 1-min data: spx_2016.xlsx ... spx_2026.xlsx
    * VIX_Daily_Data.xlsx from sibling SPY-DELTA folder

Output:
    * SPX_IronCondor_10Year_NetDelta_Fixed4_Backtest.csv
    * Console report with roll statistics + yearly breakdown

Author: Claude (adapted for PEC)
Date: May 2026
================================================================================
"""
#!/usr/bin/env python3
"""
SPX Iron Condor — Net-Delta Roll Management, Fixed ×5 capital variant.
Capital sized to a fixed assumption of CONCURRENT_TRADES (=5) concurrent trades.
See backtest_engine.py for the shared engine.
"""
from config import *
from strategy_fixed4 import Fixed4Strategy
from backtest_engine import run_main

if __name__ == "__main__":
    run_main(
        strategy      = Fixed4Strategy(),
        title         = "NET-DELTA + FIXED *5 CAPITAL",
        script_name   = "Options_Using_SPX_10_NetDelta_Fixed4.PY",
        capital_label = f"Capital:      fixed assumption of {CONCURRENT_TRADES} concurrent trades",
        csv_filename  = "SPX_IronCondor_10Year_NetDelta_Fixed4_Backtest.csv",
        extra_summary_lines = lambda r: [
            f"  |{'(fixed {} concurrent)'.format(CONCURRENT_TRADES):^30}"
            f"{'peak obs: {}'.format(r['max_concurrent']):^30}|",
        ],
    )
