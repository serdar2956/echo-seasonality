"""Download daily closes for every market in universe.py from Yahoo Finance into PRICE_DIR."""
import sys, time
import pandas as pd
import yfinance as yf
from universe import U


def ticker(stem):
    if stem.startswith("_"):
        return "^" + stem[1:]
    if stem.endswith("_F") or stem.endswith("_X"):
        return stem[:-2] + "=" + stem[-1]
    return stem


def main(out_dir):
    failed = []
    for code, stem, name, *_ in U:
        t = ticker(stem)
        for attempt in range(4):
            try:
                d = yf.download(t, period="max", interval="1d", auto_adjust=False, progress=False, threads=False)
                c = d["Close"]
                c = (c.iloc[:, 0] if hasattr(c, "columns") else c).dropna()
                if len(c) < 300:
                    raise ValueError(f"only {len(c)} rows")
                c.name, c.index.name = "Close", "Date"
                c.to_csv(f"{out_dir}/{stem}.csv")
                print(f"{code:7s} {t:10s} {len(c):6d} rows  {c.index[0].date()} → {c.index[-1].date()}")
                break
            except Exception as e:
                if attempt == 3:
                    failed.append(code); print(f"{code:7s} {t:10s} FAILED: {e}")
                time.sleep(2 * (attempt + 1))
    return failed


if __name__ == "__main__":
    bad = main(sys.argv[1])
    print("failed:", bad or "none")
