"""Daily update: refresh event calendars, download prices, recompute every statistic, validate, and write the site data.

Usage: python scripts/update.py OUT_DIR
The previous data stays live unless every check passes (the workflow fails instead of publishing bad data).
"""
import json, os, shutil, subprocess, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]).resolve()
PRICES, RAW, TMP = HERE.parent / "prices", HERE / "raw", HERE.parent / ".tmp"
CAL = {"fomc_current.htm": ("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "FOMC Meetings"),
       "tcmb_repo.htm": ("https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Core+Functions/Monetary+Policy/Central+Bank+Interest+Rates/1+Week+Repo", "<tr")}
MIN_ASSETS, MIN_COT, MIN_MACRO = 60, 45, 18


def run(*args):
    print("$", " ".join(map(str, args)), flush=True)
    subprocess.run([sys.executable, *map(str, args)], cwd=HERE, check=True)


def refresh_calendars():
    for f, (url, marker) in CAL.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ECHO data bot)"})
            body = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
            if marker in body:
                (RAW / f).write_text(body, encoding="utf-8"); print("calendar updated:", f)
            else:
                print("calendar kept (unexpected content):", f)
        except Exception as e:
            print("calendar kept (download failed):", f, e)


def main():
    for d in (PRICES, TMP, OUT / "data"):
        d.mkdir(parents=True, exist_ok=True)
    refresh_calendars()
    run("fetch_prices.py", PRICES)
    run("compute.py", PRICES, RAW, TMP / "site.json")
    run("tools.py", PRICES, RAW, TMP / "tools.json")
    run("audit.py", PRICES)
    shutil.move(str(HERE / "audit.json"), TMP / "audit.json")
    site, tools = json.loads((TMP / "site.json").read_text()), json.loads((TMP / "tools.json").read_text())
    problems = []
    if len(site["assets"]) < MIN_ASSETS: problems.append(f"only {len(site['assets'])} markets")
    if len(tools["cot"]) < MIN_COT: problems.append(f"only {len(tools['cot'])} COT markets")
    if len(tools["macro"]) < MIN_MACRO: problems.append(f"only {len(tools['macro'])} countries")
    prev = OUT / "data" / "site.json"
    if prev.exists() and json.loads(prev.read_text())["updated"] > site["updated"]:
        problems.append("new data is older than the published data")
    if problems:
        sys.exit("validation failed: " + "; ".join(problems))
    for f in ("site.json", "tools.json", "audit.json"):
        shutil.move(str(TMP / f), OUT / "data" / f)
    (OUT / "data" / "meta.json").write_text(json.dumps({"generated_at": site["generated_at"], "prices_through": site["updated"],
                                                        "markets": len(site["assets"]), "tests": site["n_tests"]}))
    print("published data:", site["updated"], site["generated_at"])


if __name__ == "__main__":
    main()
