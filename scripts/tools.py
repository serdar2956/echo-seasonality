"""Tool pages data: COT positioning (CFTC), policy rates and CPI (BIS), upcoming events, 30-day seasonal outlook.
Usage: python tools.py DATA_DIR RAW_DIR OUT_JSON
"""
import datetime as dt
import glob
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

DATA, RAW, OUT = sys.argv[1], sys.argv[2], sys.argv[3]


def get(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


# ---------- COT (legacy futures-only report) ----------
COT = [  # (CFTC code, name, group, seasonality asset id)
    ("13874A", "S&P 500 E-mini", "Indices", "SPX"), ("209742", "Nasdaq-100 E-mini", "Indices", "NDX"), ("124603", "Dow Jones E-mini", "Indices", "DJI"),
    ("239742", "Russell 2000 E-mini", "Indices", "RUT"), ("1170E1", "VIX", "Indices", "VIX"),
    ("020601", "30Y T-Bond", "Rates", "ZB"), ("020604", "Ultra T-Bond", "Rates", "UB"), ("043602", "10Y T-Note", "Rates", "ZN"),
    ("043607", "Ultra 10Y T-Note", "Rates", "TN"), ("044601", "5Y T-Note", "Rates", "ZF"), ("042601", "2Y T-Note", "Rates", "ZT"),
    ("045601", "30-Day Fed Funds", "Rates", "ZQ"), ("134741", "SOFR 3M", "Rates", None),
    ("098662", "US Dollar Index", "Currencies", "DXY"), ("099741", "Euro FX", "Currencies", "6E"), ("096742", "British Pound", "Currencies", "6B"),
    ("097741", "Japanese Yen", "Currencies", "6J"), ("092741", "Swiss Franc", "Currencies", "6S"), ("090741", "Canadian Dollar", "Currencies", "6C"),
    ("232741", "Australian Dollar", "Currencies", "6A"), ("112741", "New Zealand Dollar", "Currencies", "6N"), ("095741", "Mexican Peso", "Currencies", "6M"),
    ("102741", "Brazilian Real", "Currencies", "6L"),
    ("088691", "Gold", "Metals", "GOLD"), ("084691", "Silver", "Metals", "SI"), ("085692", "Copper", "Metals", "HG"),
    ("076651", "Platinum", "Metals", "PL"), ("075651", "Palladium", "Metals", "PA"),
    ("067651", "Crude Oil WTI", "Energy", "CL"), ("022651", "Heating Oil (ULSD)", "Energy", "HO"), ("111659", "Gasoline RBOB", "Energy", "RB"),
    ("023651", "Natural Gas", "Energy", "NG"),
    ("001602", "Wheat SRW", "Grains", "ZW"), ("001612", "Wheat HRW", "Grains", "KE"), ("002602", "Corn", "Grains", "ZC"),
    ("005602", "Soybeans", "Grains", "ZS"), ("026603", "Soybean Meal", "Grains", "ZM"), ("007601", "Soybean Oil", "Grains", "ZL"),
    ("004603", "Oats", "Grains", "ZO"), ("039601", "Rough Rice", "Grains", "ZR"),
    ("033661", "Cotton", "Softs", "CT"), ("040701", "Orange Juice", "Softs", "OJ"), ("083731", "Coffee", "Softs", "KC"),
    ("080732", "Sugar", "Softs", "SB"), ("073732", "Cocoa", "Softs", "CC"), ("058644", "Lumber", "Softs", None),
    ("057642", "Live Cattle", "Livestock", "LE"), ("061641", "Feeder Cattle", "Livestock", "GF"), ("054642", "Lean Hogs", "Livestock", "HE"),
    ("052641", "Milk Class III", "Livestock", "DC"), ("052642", "Nonfat Dry Milk", "Livestock", None), ("050642", "Butter", "Livestock", "CB"),
    ("063642", "Cheese", "Livestock", "CSC"),
    ("133741", "Bitcoin", "Crypto", "BTC"), ("146021", "Ether", "Crypto", "ETH"),
]


def cot():
    since = (dt.date.today() - dt.timedelta(days=6 * 365 + 21)).isoformat()
    codes = ",".join(f"'{c}'" for c, _, _, _ in COT)
    q = {"$select": "cftc_contract_market_code,report_date_as_yyyy_mm_dd,open_interest_all,noncomm_positions_long_all,"
                    "noncomm_positions_short_all,comm_positions_long_all,comm_positions_short_all,nonrept_positions_long_all,nonrept_positions_short_all",
         "$where": f"cftc_contract_market_code in ({codes}) AND report_date_as_yyyy_mm_dd >= '{since}T00:00:00.000'",
         "$limit": "50000"}
    rows = json.loads(get("https://publicreporting.cftc.gov/resource/6dca-aqww.json?" + urllib.parse.urlencode(q)))
    df = pd.DataFrame(rows)
    for c in df.columns[2:]:
        df[c] = pd.to_numeric(df[c])
    df["date"] = df.report_date_as_yyyy_mm_dd.str[:10]
    out = []
    for code, name, group, sid in COT:
        g = df[df.cftc_contract_market_code == code].sort_values("date").drop_duplicates("date")
        if len(g) < 20:
            print("COT missing", code, name, len(g))
            continue
        spec = (g.noncomm_positions_long_all - g.noncomm_positions_short_all).values
        comm = (g.comm_positions_long_all - g.comm_positions_short_all).values
        small = (g.nonrept_positions_long_all - g.nonrept_positions_short_all).values
        oi = g.open_interest_all.values
        w = spec[-156:]
        lo, hi = w.min(), w.max()
        idx = (spec[-1] - lo) / (hi - lo) * 100 if hi > lo else 50.0
        out.append(dict(code=code, name=name, group=group, sid=sid, date=g.date.iloc[-1], oi=int(oi[-1]),
                        long=int(g.noncomm_positions_long_all.iloc[-1]), short=int(g.noncomm_positions_short_all.iloc[-1]),
                        spec=int(spec[-1]), chg=int(spec[-1] - spec[-2]), chg4=int(spec[-1] - spec[-5]), comm=int(comm[-1]), comm_chg=int(comm[-1] - comm[-2]), small=int(small[-1]),
                        pct_oi=float(spec[-1] / oi[-1] * 100), index=float(idx),
                        hist=dict(d=g.date.tolist(), spec=spec.astype(int).tolist(), comm=comm.astype(int).tolist(), oi=oi.astype(int).tolist(),
                                  long=g.noncomm_positions_long_all.astype(int).tolist(), short=g.noncomm_positions_short_all.astype(int).tolist())))
    return out


# ---------- policy rates + CPI (BIS) ----------
CB = [("US", "United States", "Fed"), ("XM", "Euro area", "ECB"), ("GB", "United Kingdom", "BoE"), ("JP", "Japan", "BoJ"),
      ("CH", "Switzerland", "SNB"), ("CA", "Canada", "BoC"), ("AU", "Australia", "RBA"), ("NZ", "New Zealand", "RBNZ"),
      ("SE", "Sweden", "Riksbank"), ("NO", "Norway", "Norges Bank"), ("TR", "Türkiye", "CBRT"), ("BR", "Brazil", "BCB"),
      ("MX", "Mexico", "Banxico"), ("ZA", "South Africa", "SARB"), ("IN", "India", "RBI"), ("CN", "China", "PBoC"),
      ("KR", "South Korea", "BoK"), ("PL", "Poland", "NBP"), ("HU", "Hungary", "MNB"), ("CL", "Chile", "BCCh"), ("ID", "Indonesia", "BI")]


def bis(flow, key, start):
    raw = get(f"https://stats.bis.org/api/v2/data/dataflow/BIS/{flow}/1.0/{key}?startPeriod={start}&format=csv")
    return pd.read_csv(io.BytesIO(raw), usecols=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"]).dropna()


def macro():
    areas = "+".join(c for c, _, _ in CB)
    rm = bis("WS_CBPOL", f"M.{areas}", "2005-01")
    rd = bis("WS_CBPOL", f"D.{areas}", (dt.date.today() - dt.timedelta(days=5 * 365)).isoformat())
    cpi = bis("WS_LONG_CPI", f"M.{areas}.771", "2005-01")
    out = []
    for code, country, bank in CB:
        d = rd[rd.REF_AREA == code].sort_values("TIME_PERIOD")
        m = rm[rm.REF_AREA == code].sort_values("TIME_PERIOD")
        c = cpi[cpi.REF_AREA == code].sort_values("TIME_PERIOD")
        if d.empty or c.empty:
            print("macro missing", code, len(d), len(c))
            continue
        v = d.OBS_VALUE.values
        ch = np.nonzero(np.diff(v))[0]
        last_change = dict(date=d.TIME_PERIOD.iloc[ch[-1] + 1], delta=float(v[ch[-1] + 1] - v[ch[-1]])) if len(ch) else None
        # 12 months ago, from the daily series
        yago = (pd.Timestamp(d.TIME_PERIOD.iloc[-1]) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
        prev = d[d.TIME_PERIOD <= yago].OBS_VALUE
        cv = c.OBS_VALUE.values
        out.append(dict(code=code, country=country, bank=bank, rate=float(v[-1]), rate_date=d.TIME_PERIOD.iloc[-1],
                        last_change=last_change, rate_1y=float(prev.iloc[-1]) if len(prev) else None,
                        cpi=float(cv[-1]), cpi_prev=float(cv[-2]), cpi_date=c.TIME_PERIOD.iloc[-1], real=float(v[-1] - cv[-1]),
                        rate_hist=dict(d=m.TIME_PERIOD.tolist(), v=[round(x, 3) for x in m.OBS_VALUE]),
                        cpi_hist=dict(d=c.TIME_PERIOD.tolist(), v=[round(x, 2) for x in c.OBS_VALUE])))
    return out


# ---------- upcoming events ----------
MON = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December"])}


def fomc_upcoming():
    s = open(f"{RAW}/fomc_current.htm", encoding="utf-8", errors="ignore").read()
    out = set()
    for y, block in re.findall(r'(\d{4}) FOMC Meetings</a></h4></div>(.*?)(?=\d{4} FOMC Meetings</a></h4>|$)', s, re.S):
        for mtxt, dtxt in re.findall(r'fomc-meeting__month[^>]*><strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<', block, re.S):
            if "unscheduled" in dtxt.lower() or "notation" in dtxt.lower():
                continue
            nums = re.findall(r"\d+", dtxt)
            month = MON.get(mtxt.split("/")[-1].strip())
            if nums and month:
                out.add(dt.date(int(y), month, int(nums[-1])))
    return sorted(out)


def nfp_rule(y, m):
    ry, rm = (y, m - 1) if m > 1 else (y - 1, 12)
    d12 = dt.date(ry, rm, 12)
    d = d12 + dt.timedelta(days=(5 - d12.weekday()) % 7) + dt.timedelta(days=20)
    if (d.month, d.day) == (1, 1):      # New Year's Day: BLS publishes a week later
        d += dt.timedelta(days=7)
    elif (d.month, d.day) == (7, 4):    # Independence Day: published the Thursday before
        d -= dt.timedelta(days=1)
    return d


def events(today):
    ev = [dict(date=d.isoformat(), kind="FOMC", name="FOMC rate decision") for d in fomc_upcoming() if d >= today]
    for k in range(0, 8):
        y, m = today.year + (today.month - 1 + k) // 12, (today.month - 1 + k) % 12 + 1
        d = nfp_rule(y, m)
        if d >= today:
            ev.append(dict(date=d.isoformat(), kind="NFP", name="US jobs report (NFP)", est=True))
    ev = [e for e in ev if e["date"] <= (today + dt.timedelta(days=200)).isoformat()]
    return sorted(ev, key=lambda e: e["date"])


# ---------- 30-day seasonal outlook from today's date ----------
from universe import U, clean, NO_SPIKE, load
ASSETS = [(i, f, n, g) for i, f, n, g, _, _ in U]


def outlook(horizons=(10, 21, 63)):
    out = []
    for code, fstem, name, group in ASSETS:
        try:
            s = load(code, DATA)[0]
        except FileNotFoundError:
            continue
        last = s.index[-1]
        row = dict(code=code, name=name, group=group, asof=str(last.date()), h={})
        for h in horizons:
            cal = int(round(h * 365 / 252))   # trading-day horizon to calendar days
            rets = {}
            for y in range(s.index[0].year + 1, last.year):
                try:
                    a = s[:pd.Timestamp(y, last.month, min(last.day, 28))].iloc[-1]
                    end = pd.Timestamp(y, last.month, min(last.day, 28)) + pd.Timedelta(days=cal)
                    b = s[:end].iloc[-1]
                except IndexError:
                    continue
                rets[y] = (b / a - 1) * 100
            ys = sorted(rets)
            for k, sel in (("all", ys), ("y15", ys[-15:]), ("y5", ys[-5:])):
                v = np.array([rets[y] for y in sel])
                row["h"].setdefault(str(h), {})[k] = dict(avg=float(v.mean()), med=float(np.median(v)), up=float((v > 0).mean()), n=len(v))
            row["h"][str(h)]["years"] = {str(y): round(rets[y], 2) for y in ys[-15:]}
        out.append(row)
    return out


today = dt.date.today()
res = dict(generated=today.isoformat(), cot=cot(), macro=macro(), events=events(today), outlook=outlook())
json.dump(__import__("universe").rnd(res), open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
print("cot", len(res["cot"]), "macro", len(res["macro"]), "events", len(res["events"]))
for c in res["cot"][:6]:
    print(c["name"], c["date"], c["spec"], c["chg"], round(c["index"]), round(c["pct_oi"], 1))
for m in res["macro"]:
    print(m["country"], m["rate"], m["rate_date"], m["last_change"], m["cpi"], m["cpi_date"], round(m["real"], 2))
print(res["events"][:8])
for o in res["outlook"]:
    print(o["name"], {h: round(v["y15"]["avg"], 2) for h, v in o["h"].items()}, {h: round(v["y15"]["up"], 2) for h, v in o["h"].items()})
