import os

# ============================================================================
# PATH CONFIGURATION
# ============================================================================
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
YF_DATA_PATH  = os.environ.get('YFDATA', os.path.join(SCRIPT_DIR, 'yfdatas'))
DATA_PATH     = os.environ.get('DATA', os.path.join(SCRIPT_DIR, 'datas'))
OUTPUT_PATH     = os.environ.get('OUTPUT', os.path.join(SCRIPT_DIR, 'outputs'))

# ============================================================================
# CONFIGURATION
# ============================================================================

WING_WIDTH          = 50    # Width of each option spread wing
NUM_CONTRACTS       = 1     # Number of contracts per side (1 contract = 100 shares)
TARGET_DTE          = 30    # Target days to expiration at entry
PUT_DELTA           = 18    # Short put target delta (positive number, share-equivalent units)
CALL_DELTA          = 14    # Short call target delta (positive number, share-equivalent units)
VIX_NO_TRADE        = 25    # Skip new entries above this VIX level
VIX_EXIT_PUT        = 30    # Exit put side if VIX exceeds this level (even if profit target not hit)
PROFIT_TARGET       = 0.50  # Target profit as a fraction of max potential credit (e.g. 0.5 = 50% of max credit)
STOP_LOSS_MULTIPLIER = 2    # Per leg Stop loss as a multiple of max potential credit (e.g. 2 = 200% of max credit)
EXIT_DTE            = 10    # Smart exit any remaining positions at EXIT_DTE days to expiration (regardless of profit/loss)
RISK_FREE_RATE      = 0.05  # Assumed risk-free rate for option pricing (5% annualized)

# Net-delta roll thresholds (share-equivalent units, per 1 contract spread)
NET_DELTA_WARN      = 10   # Monitor band for absolute net delta (positive number, share-equivalent units)
NET_DELTA_ROLL      = 15   # Roll threshold for absolute net delta (|net delta| > 15 -> roll the threatened side)
MAX_ROLLS_PER_SIDE  = 3  # safety cap per side to prevent runaway rolling

# Capital sizing: fixed assumption (NOT data-driven max_concurrent)
CONCURRENT_TRADES   = 5   # Fixed capital sizing assumption - Observed peak from prior runs (was 4, bumped to match reality)

