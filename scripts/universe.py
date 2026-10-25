"""Market universe: (id, Yahoo file stem, display name, group, roll_flag, max daily move kept).
roll_flag = continuous front-month futures that Yahoo does not roll-adjust; roll gaps can bias monthly averages."""
U = [
    ("SPX", "_GSPC", "S&P 500", "Indices", False, .5), ("NDX", "_NDX", "Nasdaq 100", "Indices", False, .5),
    ("DJI", "_DJI", "Dow Jones 30", "Indices", False, .5), ("RUT", "_RUT", "Russell 2000", "Indices", False, .5),
    ("VIX", "_VIX", "VIX", "Indices", "index", 1.5),
    ("XU100", "XU100.IS", "BIST 100", "Türkiye", False, .5), ("USDTRY", "TRY_X", "USD/TRY", "Türkiye", False, .5),
    ("DXY", "DX-Y.NYB", "US Dollar Index", "Currencies", False, .5),
    ("6E", "6E_F", "Euro FX", "Currencies", True, .5), ("6B", "6B_F", "British Pound", "Currencies", True, .5),
    ("6C", "6C_F", "Canadian Dollar", "Currencies", True, .5), ("6J", "6J_F", "Japanese Yen", "Currencies", True, .5),
    ("6S", "6S_F", "Swiss Franc", "Currencies", True, .5), ("6A", "6A_F", "Australian Dollar", "Currencies", True, .5),
    ("6N", "6N_F", "New Zealand Dollar", "Currencies", True, .5), ("6M", "6M_F", "Mexican Peso", "Currencies", True, .5),
    ("6L", "6L_F", "Brazilian Real", "Currencies", True, .5),
    ("EURUSD", "EURUSD_X", "EUR/USD", "Forex", False, .5), ("GBPUSD", "GBPUSD_X", "GBP/USD", "Forex", False, .5),
    ("AUDUSD", "AUDUSD_X", "AUD/USD", "Forex", False, .5), ("NZDUSD", "NZDUSD_X", "NZD/USD", "Forex", False, .5),
    ("USDJPY", "JPY_X", "USD/JPY", "Forex", False, .5), ("USDCAD", "CAD_X", "USD/CAD", "Forex", False, .5),
    ("USDCHF", "CHF_X", "USD/CHF", "Forex", False, .5), ("EURGBP", "EURGBP_X", "EUR/GBP", "Forex", False, .5),
    ("EURJPY", "EURJPY_X", "EUR/JPY", "Forex", False, .5), ("GBPJPY", "GBPJPY_X", "GBP/JPY", "Forex", False, .5),
    ("AUDNZD", "AUDNZD_X", "AUD/NZD", "Forex", False, .5),
    ("ZB", "ZB_F", "30Y T-Bond", "Rates", True, .5), ("UB", "UB_F", "Ultra T-Bond", "Rates", True, .5),
    ("ZN", "ZN_F", "10Y T-Note", "Rates", True, .5), ("TN", "TN_F", "Ultra 10Y T-Note", "Rates", True, .5),
    ("ZF", "ZF_F", "5Y T-Note", "Rates", True, .5), ("ZT", "ZT_F", "2Y T-Note", "Rates", True, .5),
    ("ZQ", "ZQ_F", "30-Day Fed Funds", "Rates", True, .5),
    ("CL", "CL_F", "Crude Oil WTI", "Energy", True, .6), ("BZ", "BZ_F", "Brent Crude", "Energy", True, .6),
    ("HO", "HO_F", "Heating Oil", "Energy", True, .6), ("RB", "RB_F", "Gasoline RBOB", "Energy", True, .6),
    ("NG", "NG_F", "Natural Gas", "Energy", True, .6),
    ("GOLD", "GC_F", "Gold", "Metals", False, .5), ("SI", "SI_F", "Silver", "Metals", False, .5),
    ("HG", "HG_F", "Copper", "Metals", False, .5), ("PL", "PL_F", "Platinum", "Metals", True, .5),
    ("PA", "PA_F", "Palladium", "Metals", True, .5),
    ("ZW", "ZW_F", "Wheat SRW", "Grains", True, .5), ("KE", "KE_F", "Wheat HRW", "Grains", True, .5),
    ("ZC", "ZC_F", "Corn", "Grains", True, .5), ("ZS", "ZS_F", "Soybeans", "Grains", True, .5),
    ("ZM", "ZM_F", "Soybean Meal", "Grains", True, .5), ("ZL", "ZL_F", "Soybean Oil", "Grains", True, .5),
    ("ZO", "ZO_F", "Oats", "Grains", True, .5), ("ZR", "ZR_F", "Rough Rice", "Grains", True, .5),
    ("CT", "CT_F", "Cotton", "Softs", True, .5), ("OJ", "OJ_F", "Orange Juice", "Softs", True, .5),
    ("KC", "KC_F", "Coffee", "Softs", True, .5), ("SB", "SB_F", "Sugar", "Softs", True, .5),
    ("CC", "CC_F", "Cocoa", "Softs", True, .5),
    ("LE", "LE_F", "Live Cattle", "Livestock", True, .5), ("GF", "GF_F", "Feeder Cattle", "Livestock", True, .5),
    ("HE", "HE_F", "Lean Hogs", "Livestock", True, .5), ("DC", "DC_F", "Milk Class III", "Livestock", True, .5),
    ("CB", "CB_F", "Butter", "Livestock", True, .5), ("CSC", "CSC_F", "Cheese", "Livestock", True, .5),
    ("BTC", "BTC-USD", "Bitcoin", "Crypto", False, .6), ("ETH", "ETH-USD", "Ether", "Crypto", False, .6),
]
# first clean date per series (audit: sparse or synthetic history before these dates)
START = {"TN": "2016-01-11", "6N": "2001-01-04", "6B": "2001-01-04", "ZO": "2004-01-01", "PL": "2010-03-01", "PA": "2010-03-01",
         "ZM": "2004-01-01", "LE": "2006-02-02", "CB": "2012-01-01", "CSC": "2012-01-01"}
GAP_DAYS = 12   # daily returns spanning a longer data hole are left out of daily statistics


def load(code, data_dir):
    """Read, trim and clean one series. Returns (series, n_bad_ticks, meta)."""
    import pandas as pd
    _, f, name, group, roll, mx = next(u for u in U if u[0] == code)
    s = pd.read_csv(f"{data_dir}/{f}.csv", index_col=0, parse_dates=True)["Close"]
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if code in START:
        s = s[s.index >= START[code]]
    s, n = clean(s, group not in NO_SPIKE)
    return s, n


GROUPS = ["Indices", "Türkiye", "Currencies", "Forex", "Rates", "Energy", "Metals", "Grains", "Softs", "Livestock", "Crypto"]


def clean(s, spikes=True):
    """Drop non-positive prints and one-day spikes that fully reverse (bad ticks). Returns (series, n_dropped)."""
    import numpy as np
    s = s.dropna()
    s = s[s > 0]
    n0 = len(s)
    for _ in range(3 if spikes else 0):
        lr = np.log(s).diff()
        sig = lr.abs().rolling(60, min_periods=20).median().shift(1) * 1.4826
        nxt = lr.shift(-1)
        thr = np.maximum(10 * sig, 0.08)
        spike = (lr.abs() > thr) & (nxt.abs() > 0.7 * lr.abs()) & (np.sign(nxt) == -np.sign(lr)) & ((lr + nxt).abs() < 0.15 * lr.abs())
        if not spike.any():
            break
        s = s[~spike]
    return s, n0 - len(s)


NO_SPIKE = {"Indices", "Türkiye", "Crypto"}   # clean exchange data; large reversals there are real (e.g. March 2020)


def rnd(o, sig=5):
    """Round floats recursively to keep the page payload small."""
    if isinstance(o, float):
        return float(f"{o:.{sig}g}")
    if isinstance(o, dict):
        return {k: rnd(v, sig) for k, v in o.items()}
    if isinstance(o, list):
        return [rnd(v, sig) for v in o]
    return o
