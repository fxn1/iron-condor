# Iron Condor Backtesting Project

## Purpose

This repository is a Python backtesting workspace for options strategies.

| strategy                   | filename                                | description        | 
|----------------------------|-----------------------------------------|--------------------|
| `Fixed4Strategy `          | Options_Using_SPX_10_NetDelta_Fixed4.PY | Iron Condor        |
| `StockPutSpreadStrategy`   | strategy_stock_put_spread.py            | Put Credit Spread  |
| `NetDeltaStrategy`         | Options_Using_SPX_10_NetDelta.PY        | Iron Condor (Open) |

SPX Iron Condor : [Fixed4Strategy](Options_Using_SPX_10_NetDelta_Fixed4.PY) - [config](./config.py)

1. Net-Delta Roll Management, Fixed ×5 capital variant.
2. Capital sized to a fixed assumption of CONCURRENT_TRADES (=5) concurrent trades.
3. 18-delta put side and 14-delta call side iron condor with fixed-width wings.
4. Enteries on Mondays, with a configurable lookahead after earnings.
5. Skips entries when VIX is above the configured threshold 
6. avoids duplicate expirations  
7. optionally re-enters after a profit-target exit.  
8. Exits include 50% profit target on cumulative credit
9. per-leg stop loss based on worst intraday movement
10. VIX-based put-leg exit
11. 10-DTE smart exit that can take profit or cut loss
12. expiration settlement
13. same-day collision handling where stop loss takes precedence over profit target
    
Put credit spread : [StockPutSpreadStrategy](strategy_stock_put_spread.py) - [config_stocks](config_stocks.py)
1. Entry  : day after earnings (`earnings_lookahead_days`)
2. EMA must be higher than it was `ema_trend_days` ago.
3. RSI slope must exceed `rsi_slope_min`.
4. Current price must be at least 2% above rolling support.
5. Short strike is currently selected as the nearest standard strike below support.
6. Exit   : handled by PutSpreadTrade.check_exit (profit target, stop, DTE)
7. Reentry: no — one trade per stock per earnings cycle.

## How The SPX Backtest Runs

Entry points:

```powershell
python Options_Using_SPX_10_NetDelta_Fixed4.PY
python strategy_stock_put_spread.py
```

High-level execution flow:

1. `Options_Using_SPX_10_NetDelta_Fixed4.PY` creates `Fixed4Strategy` and calls `backtest_engine.run_main()`.
2. `Fixed4Strategy.load_data()` is intended to load VIX data from `VIX_Daily_Data.xlsx`.
3. `data_loader.load_spx_daily_from_minute_files()` reads `spx_2016.xlsx` through `spx_2026.xlsx`, converts intraday rows into daily OHLC bars, and does this with two worker processes.
4. `backtest_engine.run_backtest()` loops through trading dates, manages exits, rolls, entries and re-entries.
5. Results are printed by `reporting.print_results()` and exported by `reporting.export_trades_to_csv()`.

Generated output files currently present:

| File                                                 | Purpose                                           |
|------------------------------------------------------|---------------------------------------------------|
| `SPX_IronCondor_10Year_NetDelta_Backtest.csv`        | Trade-level results for the net-delta variant     |
| `SPX_IronCondor_10Year_NetDelta_Fixed4_Backtest.csv` | Trade-level results for the fixed-capital variant |
| `delta-fixed4.log`                                   | Saved console/log output from a previous run      |

## Trade Model
Important classes:

| Class                      | File                  | Role                                                                         |
|----------------------------|-----------------------|------------------------------------------------------------------------------|
| `Trade`                    | `trade.py`            | Abstract base for all trade types                                            |
| `IronCondorTrade`          | `trade.py`            | Full iron condor with leg exits, roll accounting, net delta, and PnL         |
| `IronCondorTradeOpen`      | `trade.py`            | Variant with more conservative open-price adjustment behavior                |
| `OneSidedSpreadTrade`      | `one_sided_spread.py` | Reusable base for single put/call credit spreads                             |
| `PutSpreadTrade`           | `put_spread.py`       | Stock put-spread implementation built from scanner output                    |
| `CallSpreadTrade`          | `call_spread.py`      | Call spread implementation                                                   |
| `PutSpreadTradeScanner`    | `scanner.py`          | Builds put-spread trades based on earnings/technical filters                 |
| `Black-Scholes`            | `pricing.py`          | implements lightweight Black-Scholes helpers (price, delta, strike_for_delta |
| `HistoricalVolatility`     | `volatility.py`       | Calculates historical volatility from SPX close prices                       |

## Backtest engine logic
important classes:

| Class           | File                 | Role                                            |
|-----------------|----------------------|-------------------------------------------------|
| Base Strategy   | `base_strategy.py`   | Date helpers, trade factory, strategy interface |
| Backtest Engine | `backtest_engine.py` | Shared SPX backtest loop and main runner        |
| Data Loader     | `data_loader.py`     | SPX/VIX data loading                            |
| Reporting       | `reporting.py`       | Console summaries and trade CSV export          |

The iron condor tracks both current legs plus roll history. When a side rolls, the closing spread's realized PnL is added to `banked_pnl`, a new spread is opened at the target delta, and `cumulative_credit` increases.

The strike finder uses binary search and rounds to a 5-point strike increment. The SPX iron condor uses different volatility assumptions by side:

- put vol = historical volatility * 1.10
- call vol = historical volatility * 0.95

## Data Files

Large local market data files are part of the workflow:

| Pattern / file                      | Strategy               | Purpose                                               |
|-------------------------------------|------------------------|-------------------------------------------------------|
| `spx_2016.xlsx` ... `spx_2026.xlsx` | Fixed4Strategy         | SPX intraday data, resampled into daily bars          |
| `VIX_Daily_Data.xlsx`               | Fixed4Strategy         | Daily VIX close values                                |
| `SPY_Daily_Data.xlsx`               | Fixed4Strategy         | SPY daily data, likely earlier/reference workflow     |
| `SPY.csv`                           | StockPutSpreadStrategy | Cached/downloaded SPY OHLCV data                      |
| `yfdatas/*.csv`                     | StockPutSpreadStrategy | Yahoo Finance cache files for stock data and earnings |

Because the SPX files are large and local, this project is data-dependent. A fresh checkout without the spreadsheets will not run the SPX backtest until those files are restored.

## Stock Put-Spread Scanner Workflow


| File                 | Role                                                   |
|----------------------|--------------------------------------------------------|
| `scanner.py`         | Decides whether to enter a put spread on a ticker/date |
| `CacheDailyOHLCV.py` | Downloads/caches Yahoo Finance daily OHLCV data        |
| `CacheEarning.py`    | Downloads/caches earnings dates from Yahoo Finance     |
| `put_spread.py`      | Builds and manages a put credit spread trade           |

## Dependencies

Declared runtime dependencies : [pyproject.toml](pyproject.toml)

| File                                        | Notes                                                 |
|---------------------------------------------|-------------------------------------------------------|
| `requirements.txt` / `requirements-dev.txt` | Dependency pins/lists                                 |
| `pyproject.toml`                            | Package metadata, dependency declaration, ruff config |

Install options:

```powershell
pip install -r requirements.txt
pip install -e .[dev]
```

## Suggested Bug Fixes

3. Give stock put-spread trades their own reporting/export path, or adapt the generic exporter to branch by trade type.

## Suggested Next Steps

1. ~~Fix SPX startup data loading and add a clear zero-trade / failed-data-load error. (move input, output, data dir)~~
2. Add a data manifest explaining where each required `.xlsx` and cache file comes from.
3. ~~`strategy_stock_put_spread.py` passes a `datetime` into `scanner.scan()`, while earnings dates are plain `date` objects. That can prevent the earnings gate from matching.~~
4. ~~`reporting.py` and `backtest_engine.py` hardcode fixed concurrent trades as `5` in a few places instead of consistently using `CONCURRENT_TRADES`; the final summary margin also omits `NUM_CONTRACTS`. Centralize capital sizing so `CONCURRENT_TRADES` and `NUM_CONTRACTS` are used consistently. Replace hardcoded `5` capital multipliers with `CONCURRENT_TRADES`, and include `NUM_CONTRACTS` in the final summary margin calculation.~~
5. There are useful TODO comments in `scanner.py` noting that the EMA and RSI checks may be too simplistic, and that support-based strike selection should probably move toward delta-based pricing for better backtest realism. 
6. `scanner.py` has several useful TODOs around improving trend detection and replacing support-only strike selection with delta-aware strike selection.
7. Wire `Options_Using_SPX_10_NetDelta.PY` to a genuinely different trade factory if `IronCondorTradeOpen` is intended to be tested. 
8. Convert cache/scanner scripts into pytest-style tests around deterministic sample data. 
9. Rename `Options_Using_SPX_10_NetDelta_Fixed4.PY` to a lowercase `.py` filename and update imports so the code is portable across case-sensitive systems. 
10. Current implementation caveat: the stock strategy is not yet fully wired to the shared reporting/export path. `reporting.print_results()` and `export_trades_to_csv()` assume iron-condor attributes such as `put_rolls`, `call_rolls`, `put_short`, and `call_short`, which `PutSpreadTrade` does not expose.
11. `backtest_engine.py` uses `sorted_dates.index(date_str)` inside the main date loop, which is simple but O(n^2). It likely does not matter for this dataset, but it is easy to optimize if runs become slow.
12. `put_spread.py` uses `STOP_LOSS_MULTIPLIER` from `config.py`; `STOCK_STOP_LOSS_MULT` in `config_stocks.py` is currently not applied. 
13. `Options_Using_SPX_10_NetDelta.PY` subclasses `Fixed4Strategy` but does not currently change behavior. Its TODO mentions `create_new_trade`, but the current strategy interface method is `create_trade`. 
14. Naming is slightly inconsistent: `Fixed4Strategy`, `Fixed4` filenames, and comments mention fixed 4 in places, but the active capital assumption is fixed 5 concurrent trades.
15. `pyproject.toml` contains mojibake in comments, likely from an encoding mismatch. It probably still parses, but the comments render poorly.
16. `NetDeltaStrategy` - wire  `IronCondorTradeOpen` behavior `create_trade()`.
