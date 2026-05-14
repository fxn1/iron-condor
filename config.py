from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

WING_WIDTH       = 50
NUM_CONTRACTS    = 1
TARGET_DTE       = 30
PUT_DELTA        = 18
CALL_DELTA       = 14
VIX_NO_TRADE     = 25
VIX_EXIT_PUT     = 30
PROFIT_TARGET    = 0.50
STOP_LOSS_MULTIPLIER = 2
EXIT_DTE         = 10
RISK_FREE_RATE   = 0.05

# Net-delta roll thresholds (share-equivalent units, per 1 contract spread)
NET_DELTA_WARN   = 10   # warning band: monitor only
NET_DELTA_ROLL   = 15   # |net delta| > 15 -> roll the threatened side
MAX_ROLLS_PER_SIDE = 3  # safety cap to prevent runaway rolling

# Capital sizing: fixed assumption (NOT data-driven max_concurrent)
CONCURRENT_TRADES = 5   # Observed peak from prior runs (was 4, bumped to match reality)

# Date window (10 years to today's anchor)
START_YEAR = 2016
END_YEAR   = 2026
START_DATE = datetime(2016, 5, 9)
END_DATE   = datetime(2026, 5, 8)
