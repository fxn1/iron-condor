# config_stocks.py — constants for the stock put spread strategy.
# All scanner + trade sizing values live here so nothing is hardcoded
# in strategy or scanner code.

# ── scanner thresholds ────────────────────────────────────────────────────
SCAN_EARNINGS_LOOKAHEAD_DAYS     = 1      # entry on day N after earnings
SCAN_EMA_PERIOD                  = 20     # EMA(20)
SCAN_EMA_TREND_DAYS              = 5      # EMA today > EMA 5 days ago
SCAN_RSI_PERIOD                  = 14     # RSI(14)
SCAN_RSI_SLOPE_DAYS              = 3      # slope over last 3 days
SCAN_RSI_SLOPE_MIN               = 0.5    # minimum slope to qualify
SCAN_SUPPORT_LOOKBACK            = 20     # rolling N-day low for support
SCAN_MIN_PRICE_ABOVE_SUPPORT_PCT = 0.02   # price must be >= 2% above support
SCAN_STRIKE_INCREMENT            = 5.0    # nearest $5 strike below support

# ── trade sizing ──────────────────────────────────────────────────────────
STOCK_TARGET_DTE      = 60     # ~2 months to expiration
STOCK_WING_WIDTH      = 10     # $10 wide put spread
STOCK_PROFIT_TARGET   = 0.15   # close at 15% of credit (mid of 10-25% range)
STOCK_NUM_CONTRACTS   = 1      # contracts per trade
STOCK_STOP_LOSS_MULT  = 2.0    # 2x credit stop loss (matches SPX convention)
STOCK_VOL_SCALAR      = 0.80   # scale historical volatility to get more realistic option prices for stocks
