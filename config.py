"""Settings for the SGX Triple Screen system. Edit freely."""

# --- Universe -------------------------------------------------------------
# STI constituents (Yahoo Finance symbols). FTSE Russell made no constituent
# changes at the Mar / Jun / Sep 2026 reviews. Lines marked "verify" are ones
# to check against the official list:
# https://www.lseg.com/en/ftse-russell/indices/sgx-st#t-constituents
UNIVERSE = {
    "D05.SI": "DBS Group",
    "O39.SI": "OCBC Bank",
    "U11.SI": "UOB",
    "Z74.SI": "Singtel",
    "S68.SI": "SGX Group",
    "S63.SI": "ST Engineering",
    "BN4.SI": "Keppel",
    "U96.SI": "Sembcorp Industries",
    "5E2.SI": "Seatrium",
    "BS6.SI": "Yangzijiang Shipbuilding",
    "C6L.SI": "Singapore Airlines",
    "S58.SI": "SATS",
    "F34.SI": "Wilmar International",
    "Y92.SI": "Thai Beverage",
    "G13.SI": "Genting Singapore",
    "V03.SI": "Venture Corp",
    "J36.SI": "Jardine Matheson",
    "C07.SI": "Jardine Cycle & Carriage",
    "H78.SI": "Hongkong Land",          # verify
    "9CI.SI": "CapitaLand Investment",
    "C38U.SI": "CapitaLand Integrated Commercial Trust",
    "A17U.SI": "CapitaLand Ascendas REIT",
    "ME8U.SI": "Mapletree Industrial Trust",
    "M44U.SI": "Mapletree Logistics Trust",
    "N2IU.SI": "Mapletree Pan Asia Commercial Trust",
    "AJBU.SI": "Keppel DC REIT",
    "BUOU.SI": "Frasers Logistics & Commercial Trust",  # verify
    "J69U.SI": "Frasers Centrepoint Trust",             # verify
    "U14.SI": "UOL Group",
    "C09.SI": "City Developments",
}
MARKET_INDEX = ("^STI", "Straits Times Index")

# --- Data -----------------------------------------------------------------
HISTORY_PERIOD = "2y"        # daily bars pulled from Yahoo Finance
CHART_DAILY_BARS = 130       # ~6 months on the daily chart
CHART_WEEKLY_BARS = 78       # ~18 months on the weekly chart

# --- Screen 1: weekly tide (Elder: 26-wk EMA + weekly MACD histogram) -----
W_EMA_FAST, W_EMA_SLOW = 13, 26
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9

# --- Screen 2: daily wave -------------------------------------------------
D_EMA_FAST, D_EMA_SLOW = 20, 50
RSI_LEN = 14
RSI_PULLBACK_LONG = 45       # RSI at/below this in an up-tide = pullback
RSI_RALLY_SHORT = 55         # RSI at/above this in a down-tide = rally
FORCE_LEN = 2                # Elder's 2-day EMA of Force Index
ATR_LEN = 14
EXTENDED_ATR = 1.0           # close > EMA20 + 1 ATR = too extended to chase

# --- Screen 3: entry / exit ----------------------------------------------
MIN_STOP_ATR = 0.75          # stop at least this many ATR from entry
ORDER_VALID_SESSIONS = 3     # buy-stop is trailed for up to 3 sessions
ALLOW_SHORTS = True          # shown as "short setup" (CFD / SBL only)
MIN_RR_T1 = 1.0              # below this, a setup is downgraded to watch

# --- Support / resistance -------------------------------------------------
SR_LOOKBACK = 250            # daily bars scanned for swing pivots
SR_PIVOT_WINDOW = 5          # bars each side to qualify as a swing point
SR_CLUSTER_ATR = 0.6         # pivots within 0.6 ATR merge into one level
SR_LEVELS_EACH_SIDE = 3

# --- Risk (Elder's 2% rule; set your own) --------------------------------
ACCOUNT_SIZE_SGD = 100_000
RISK_PER_TRADE_PCT = 1.0
BOARD_LOT = 100

# --- Output ---------------------------------------------------------------
SITE_TITLE = "SGX Triple Screen"
TIMEZONE = "Asia/Singapore"
