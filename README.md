# Iron Condor Project Review

## Purpose

This repository is a Python backtesting workspace for options strategies. The main completed path is a 10-year SPX iron condor backtest with net-delta roll management. There is also an in-progress stock put-spread workflow that uses cached Yahoo Finance OHLCV data, cached earnings dates, and a technical scanner.

The existing `README.md` is only a placeholder, so this document captures the current structure, data dependencies, execution flow, and notable implementation notes.

## Main Strategy: SPX Iron Condor Backtest

The SPX backtest models an 18-delta put side and 14-delta call side iron condor using fixed-width wings. It enters on Mondays, skips entries when VIX is above the configured threshold, avoids duplicate expirations, and optionally re-enters after a profit-target exit.

Core assumptions live in `config.py`:

| Setting | Current value | Meaning |
| --- | ---: | --- |
| `WING_WIDTH` | 50 | Width of each option spread wing |
| `TARGET_DTE` | 30 | Target days to expiration |
| `PUT_DELTA` | 18 | Short put target delta |
| `CALL_DELTA` | 14 | Short call target delta |
| `VIX_NO_TRADE` | 25 | Skip new entries above this VIX level |
| `VIX_EXIT_PUT` | 30 | Close put leg above this VIX level |
| `PROFIT_TARGET` | 0.50 | Exit at 50% of cumulative credit |
| `STOP_LOSS_MULTIPLIER` | 2 | Per-leg stop loss multiple of credit |
| `EXIT_DTE` | 10 | Smart exit window near expiration |
| `NET_DELTA_WARN` | 10 | Monitor band for absolute net delta |
| `NET_DELTA_ROLL` | 15 | Roll threshold for absolute net delta |
| `MAX_ROLLS_PER_SIDE` | 3 | Safety cap per side |
| `CONCURRENT_TRADES` | 5 | Fixed capital sizing assumption |
| `START_DATE` / `END_DATE` | 2016-05-09 to 2026-05-08 | Backtest window |

## How The SPX Backtest Runs

Entry points:

```powershell
python Options_Using_SPX_10_NetDelta_Fixed4.PY
python Options_Using_SPX_10_NetDelta.PY
```

The primary current variant appears to be `Options_Using_SPX_10_NetDelta_Fixed4.PY`. It uses `Fixed4Strategy`, though the docstring and output now describe a fixed 5-concurrent-trade capital model because `CONCURRENT_TRADES = 5`.

High-level execution flow:

1. `Options_Using_SPX_10_NetDelta_Fixed4.PY` creates `Fixed4Strategy` and calls `backtest_engine.run_main()`.
2. `run_main()` loads VIX data from `VIX_Daily_Data.xlsx`.
3. `data_loader.load_spx_daily_from_minute_files()` reads `spx_2016.xlsx` through `spx_2026.xlsx`, converts intraday rows into daily OHLC bars, and does this with two worker processes.
4. `backtest_engine.run_backtest()` loops through trading dates, manages exits, rolls, re-entries, and new Monday entries.
5. Results are printed by `reporting.print_results()` and exported by `reporting.export_trades_to_csv()`.

Generated output files currently present:

| File | Purpose |
| --- | --- |
| `SPX_IronCondor_10Year_NetDelta_Backtest.csv` | Trade-level results for the net-delta variant |
| `SPX_IronCondor_10Year_NetDelta_Fixed4_Backtest.csv` | Trade-level results for the fixed-capital variant |
| `delta-fixed4.log` | Saved console/log output from a previous run |

## Trade Model

`trade.py` defines the abstract trade interface and the SPX iron condor implementation.

Important classes:

| Class | File | Role |
| --- | --- | --- |
| `Trade` | `trade.py` | Abstract base for all trade types |
| `IronCondorTrade` | `trade.py` | Full iron condor with leg exits, roll accounting, net delta, and PnL |
| `IronCondorTradeOpen` | `trade.py` | Variant with more conservative open-price adjustment behavior |
| `OneSidedSpreadTrade` | `one_sided_spread.py` | Reusable base for single put/call credit spreads |
| `PutSpreadTrade` | `put_spread.py` | Stock put-spread implementation built from scanner output |
| `CallSpreadTrade` | `call_spread.py` | Call spread implementation |

The iron condor tracks both current legs plus roll history. When a side rolls, the closing spread's realized PnL is added to `banked_pnl`, a new spread is opened at the target delta, and `cumulative_credit` increases.

Exit behavior includes:

- 50% profit target on cumulative credit
- per-leg stop loss based on worst intraday movement
- VIX-based put-leg exit
- 10-DTE smart exit that can take profit or cut loss
- expiration settlement
- same-day collision handling where stop loss takes precedence over profit target

## Pricing And Strike Selection

`pricing.py` implements lightweight Black-Scholes helpers:

- `black_scholes_price()`
- `black_scholes_delta()`
- `find_strike_for_delta()`

The strike finder uses binary search and rounds to a 5-point strike increment. The SPX iron condor uses different volatility assumptions by side:

- put vol = historical volatility * 1.10
- call vol = historical volatility * 0.95

Historical volatility is calculated in `volatility.py` from recent SPX closes.

## Data Files

Large local market data files are part of the workflow:

| Pattern / file | Purpose |
| --- | --- |
| `spx_2016.xlsx` ... `spx_2026.xlsx` | SPX intraday data, resampled into daily bars |
| `VIX_Daily_Data.xlsx` | Daily VIX close values |
| `SPY_Daily_Data.xlsx` | SPY daily data, likely earlier/reference workflow |
| `SPY.csv` | Cached/downloaded SPY OHLCV data |
| `yfdatas/*.csv` | Yahoo Finance cache files for stock data and earnings |

Because the SPX files are large and local, this project is data-dependent. A fresh checkout without the spreadsheets will not run the SPX backtest until those files are restored.

## Stock Put-Spread Scanner Workflow

The stock workflow appears newer and still evolving. The main pieces are:

| File | Role |
| --- | --- |
| `scanner.py` | Decides whether to enter a put spread on a ticker/date |
| `CacheDailyOHLCV.py` | Downloads/caches Yahoo Finance daily OHLCV data |
| `CacheEarning.py` | Downloads/caches earnings dates from Yahoo Finance |
| `put_spread.py` | Builds and manages a put credit spread trade |
| `pandas-ta-test.py` | Technical-indicator experiment/test script |
| `CacheDailyOHLCV-test*.py` | Cache test scripts |
| `CacheEarning-test.py` | Earnings-cache test script |

Scanner gates currently include:

1. Entry occurs after an earnings date, controlled by `earnings_lookahead_days`.
2. EMA must be higher than it was `ema_trend_days` ago.
3. RSI slope must exceed `rsi_slope_min`.
4. Current price must be at least 2% above rolling support.
5. Short strike is currently selected as the nearest standard strike below support.

There are useful TODO comments in `scanner.py` noting that the EMA and RSI checks may be too simplistic, and that support-based strike selection should probably move toward delta-based pricing for better backtest realism.

## Dependencies

Declared runtime dependencies in `pyproject.toml` include:

- Python 3.11+
- `numpy`
- `scipy`
- `pandas`
- `openpyxl`
- `yfinance`
- `lxml`
- `pandas-ta-classic`

Development dependencies include:

- `pytest`
- `pytest-cov`
- `ruff`

Install options:

```powershell
pip install -r requirements.txt
pip install -e .[dev]
```

## File Map

| File | Notes |
| --- | --- |
| `config.py` | Central SPX strategy/backtest constants |
| `base_strategy.py` | Date helpers, trade factory, strategy interface |
| `backtest_engine.py` | Shared SPX backtest loop and main runner |
| `Options_Using_SPX_10_NetDelta_Fixed4.PY` | Fixed-capital SPX strategy entry point |
| `Options_Using_SPX_10_NetDelta.PY` | Net-delta entry point subclassing `Fixed4Strategy`; currently mostly a placeholder |
| `trade.py` | Abstract trade plus iron condor implementations |
| `one_sided_spread.py` | Base class for one-sided credit spreads |
| `put_spread.py` | Put spread class and scanner-based constructor |
| `call_spread.py` | Call spread class |
| `pricing.py` | Black-Scholes pricing, delta, and strike search |
| `volatility.py` | Historical volatility helper |
| `data_loader.py` | SPX/VIX data loading |
| `reporting.py` | Console summaries and trade CSV export |
| `scanner.py` | Earnings/technical scanner for stock put spreads |
| `CacheDailyOHLCV.py` | Yahoo Finance OHLCV cache |
| `CacheEarning.py` | Yahoo Finance earnings cache |
| `requirements.txt` / `requirements-dev.txt` | Dependency pins/lists |
| `pyproject.toml` | Package metadata, dependency declaration, ruff config |

## Notable Review Notes

- `README.md` is only a title. This project would benefit from replacing or supplementing it with setup, run commands, and data requirements.
- `Options_Using_SPX_10_NetDelta.PY` subclasses `Fixed4Strategy` but does not currently change behavior. It has a TODO about returning `IronCondorTradeOpen`, but `base_strategy.create_new_trade()` always returns `IronCondorTrade` today.
- Naming is slightly inconsistent: `Fixed4Strategy`, `Fixed4` filenames, and comments mention fixed 4 in places, but the active capital assumption is fixed 5 concurrent trades.
- `pyproject.toml` contains mojibake in comments, likely from an encoding mismatch. It probably still parses, but the comments render poorly.
- `reporting.py` hardcodes fixed concurrent trades as `5` in a few places instead of consistently using `CONCURRENT_TRADES`.
- `backtest_engine.py` uses `sorted_dates.index(date_str)` inside the main date loop, which is simple but O(n^2). It likely does not matter for this dataset, but it is easy to optimize if runs become slow.
- `scanner.py` has several promising TODOs around improving trend detection and replacing support-only strike selection with delta-aware strike selection.
- Some test scripts are standalone exploratory scripts rather than formal pytest tests.

## Suggested Next Steps

1. Add a data manifest explaining where each required `.xlsx` and cache file comes from.
2. Rename or clarify the `Fixed4` variant now that capital sizing is fixed at 5 concurrent trades.
3. Wire `Options_Using_SPX_10_NetDelta.PY` to a genuinely different trade factory if `IronCondorTradeOpen` is intended to be tested.
4. Convert cache/scanner scripts into pytest-style tests around deterministic sample data.
5. Centralize capital sizing so `CONCURRENT_TRADES` is used everywhere instead of hardcoded `5` values.

