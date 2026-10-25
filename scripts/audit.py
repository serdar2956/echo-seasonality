"""Data audit: coverage, gaps, stale runs, duplicates, outliers for every series used by the site."""
import json, sys, numpy as np, pandas as pd
from universe import U, clean, NO_SPIKE, load, START
DATA = sys.argv[1] if len(sys.argv) > 1 else "data2"
rows = []
latest = None
for code, f, name, group, roll, mx in U:
    raw = pd.read_csv(f"{DATA}/{f}.csv", index_col=0, parse_dates=True)["Close"]
    dup = int(raw.index.duplicated().sum())
    s, nbad = load(code, DATA)
    crypto = group == "Crypto"
    gaps = s.index.to_series().diff().dt.days
    big = gaps[gaps > (3 if crypto else 6)]
    # stale: 5+ identical consecutive closes
    same = (s.diff() == 0).astype(int)
    run = same.groupby((same == 0).cumsum()).cumsum().max()
    r = np.log(s).diff().dropna()
    z = (r - r.mean()) / r.std()
    rows.append(dict(code=code, name=name, group=group, ticker=f, first=str(s.index[0].date()), last=str(s.index[-1].date()),
                     rows=len(s), years=round((s.index[-1] - s.index[0]).days / 365.25, 1), dup=dup, cleaned=nbad,
                     gaps=len(big), max_gap=int(gaps.max()), max_gap_at=str(gaps.idxmax().date()), stale_run=int(run),
                     big_moves=int((z.abs() > 8).sum()), max_move=round(float(np.expm1(r.abs().max()) * 100), 1),
                     max_move_at=str(r.abs().idxmax().date()), roll=roll))
df = pd.DataFrame(rows)
mx = df["last"].max()
df["lag_days"] = (pd.to_datetime(mx) - pd.to_datetime(df["last"])).dt.days
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print(df[["code", "first", "last", "rows", "years", "dup", "cleaned", "gaps", "max_gap", "max_gap_at", "stale_run", "big_moves", "max_move", "max_move_at", "lag_days"]].to_string(index=False))
json.dump(rows, open("audit.json", "w"), indent=0)
