"""Seasonality site data: seasonal paths, calendar effects, event-day effects, US election cycle.
All tests: permutation p-values, Benjamini-Hochberg across every test on the site, stability checks.
"""
import datetime as dt
import glob
import html
import json
import re
import sys

import numpy as np
import pandas as pd
from numba import njit

DATA, RAW, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
from universe import U, GROUPS, clean, NO_SPIKE, load, GAP_DAYS, START
MIN_YEARS = 6
COST_PCT = 0.05
N_PERM, N_PERM_MAX = 10000, 100000   # fixed seed; borderline results get 100k shuffles so verdicts do not flip between runs
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
rng = np.random.default_rng(7)
TESTS = []   # every tested row, for BH


# ------------------------------------------------------------------ event calendars
def fomc_dates():
    mon = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                           "September", "October", "November", "December"])}
    out = set()
    for f in glob.glob(f"{RAW}/fomc_19*.htm") + glob.glob(f"{RAW}/fomc_20[0-2][0-9].htm"):
        s = open(f, encoding="utf-8", errors="ignore").read()
        for h in re.findall(r'<h5[^>]*>([^<]+)</h5>', s):
            h = html.unescape(h).strip()
            if "Meeting" not in h or "unscheduled" in h.lower():
                continue
            m = re.match(r"([A-Za-z]+)\s+(\d+)(?:-(?:([A-Za-z]+)\s+)?(\d+))?\s+Meeting\s+-\s+(\d{4})", h)
            if not m:
                continue
            m1, d1, m2, d2, y = m.groups()
            month = mon[m2] if m2 else mon[m1]
            day = int(d2) if d2 else int(d1)
            out.add(dt.date(int(y), month, day))
    s = open(f"{RAW}/fomc_current.htm", encoding="utf-8", errors="ignore").read()
    for y, block in re.findall(r'(\d{4}) FOMC Meetings</a></h4></div>(.*?)(?=\d{4} FOMC Meetings</a></h4>|$)', s, re.S):
        for mtxt, dtxt in re.findall(r'fomc-meeting__month[^>]*><strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<', block, re.S):
            if "unscheduled" in dtxt.lower() or "notation" in dtxt.lower():
                continue
            months = mtxt.split("/")
            nums = re.findall(r"\d+", dtxt)
            if not nums:
                continue
            month = mon.get(months[-1].strip())
            if month is None:
                continue
            out.add(dt.date(int(y), month, int(nums[-1])))
    return sorted(out)


def nfp_dates(start=1990, end=2026):
    """BLS rule: third Friday after the end of the reference week (week containing the 12th of the prior month)."""
    out = []
    for y in range(start, end + 1):
        for m in range(1, 13):
            ry, rm = (y, m - 1) if m > 1 else (y - 1, 12)
            d12 = dt.date(ry, rm, 12)
            sat = d12 + dt.timedelta(days=(5 - d12.weekday()) % 7)
            out.append(sat + dt.timedelta(days=20))
    return out


def tcmb_changes():
    s = open(f"{RAW}/tcmb_repo.htm", encoding="utf-8", errors="ignore").read()
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S):
        c = [html.unescape(re.sub("<[^>]+>", "", x)).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        if len(c) >= 3 and re.match(r"\d\d\.\d\d\.\d{4}", c[0]):
            try:
                rows.append((dt.datetime.strptime(c[0], "%d.%m.%Y").date(), float(c[2])))
            except ValueError:
                pass
    rows.sort()
    hikes, cuts = [], []
    for (d0, r0), (d1, r1) in zip(rows, rows[1:]):
        (hikes if r1 > r0 else cuts if r1 < r0 else []).append(d1)
    return hikes, cuts


# ------------------------------------------------------------------ statistics
@njit(cache=True)
def _perm_count(x, li, k, obs, nperm, seed):
    """Share of label shuffles whose |group mean − rest mean| reaches the observed gap, per group."""
    np.random.seed(seed)
    n = len(x)
    tot = x.sum()
    cnt = np.zeros(k)
    for g in range(k):
        cnt[g] = (li == g).sum()
    ge = np.zeros(k)
    lab = li.copy()
    s = np.zeros(k)
    for _ in range(nperm):
        np.random.shuffle(lab)
        s[:] = 0.0
        for i in range(n):
            s[lab[i]] += x[i]
        for g in range(k):
            if cnt[g] > 0 and cnt[g] < n:
                d = s[g] / cnt[g] - (tot - s[g]) / (n - cnt[g])
                if abs(d) >= abs(obs[g]) - 1e-12:
                    ge[g] += 1
    return ge


def _obs(x, li, k):
    s = np.bincount(li, weights=x, minlength=k)
    c = np.bincount(li, minlength=k)
    with np.errstate(invalid="ignore", divide="ignore"):
        return s / c - (x.sum() - s) / (len(x) - c)


@njit(cache=True)
def _perm_binary(x, k, obs, nperm, seed):
    """Two-group case: draw k of n without replacement (partial Fisher-Yates), O(k) per shuffle."""
    np.random.seed(seed)
    n = len(x)
    tot = x.sum()
    idx = np.arange(n)
    ge = 0
    for _ in range(nperm):
        s = 0.0
        for j in range(k):
            r = j + np.random.randint(n - j)
            t = idx[j]; idx[j] = idx[r]; idx[r] = t
            s += x[idx[j]]
        if abs(s / k - (tot - s) / (n - k)) >= abs(obs) - 1e-12:
            ge += 1
    return ge


def perm_groups(x, labels, cats):
    """Permutation p-values for each group mean against the rest. 10,000 shuffles, extended to 100,000 when any p < 0.005."""
    x = np.asarray(x, float)
    idx = {c: i for i, c in enumerate(cats)}
    li = np.array([idx[v] for v in labels], dtype=np.int64)
    k = len(cats)
    obs = _obs(x, li, k)
    ge = _perm_count(x, li, k, np.nan_to_num(obs), N_PERM, int(rng.integers(1 << 31)))
    n_done = N_PERM
    if ((ge + 1) / (n_done + 1)).min() < 0.005:
        ge = ge + _perm_count(x, li, k, np.nan_to_num(obs), N_PERM_MAX - N_PERM, int(rng.integers(1 << 31)))
        n_done = N_PERM_MAX
    return obs, (ge + 1) / (n_done + 1)


def perm_diff(x, mask):
    x = np.asarray(x, float)
    mask = np.asarray(mask, bool)
    k, n = int(mask.sum()), len(x)
    obs = x[mask].mean() - x[~mask].mean()
    kk = min(k, n - k)               # sample the smaller side; the statistic is symmetric
    ge = _perm_binary(x, kk, obs, N_PERM, int(rng.integers(1 << 31)))
    n_done = N_PERM
    if (ge + 1) / (n_done + 1) < 0.005:
        ge += _perm_binary(x, kk, obs, N_PERM_MAX - N_PERM, int(rng.integers(1 << 31)))
        n_done = N_PERM_MAX
    return obs, (ge + 1) / (n_done + 1)


def desc(x):
    x = np.asarray(x, float)
    n = len(x)
    m = float(x.mean())
    se = float(x.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    return dict(n=int(n), mean=m, median=float(np.median(x)), pos=float((x > 0).mean() * 100), lo=m - 1.96 * se, hi=m + 1.96 * se)


def stability(x, mask, years, periods):
    """Sign of (group − others) in each period; returns (same, total, table)."""
    df = pd.DataFrame(dict(x=x, g=mask, y=years))
    tab = {}
    for name, (a, b) in periods.items():
        g = df[(df.y >= a) & (df.y <= b)]
        if g.g.sum() >= 3 and (~g.g).sum() >= 3:
            tab[name] = float(g.x[g.g].mean() - g.x[~g.g].mean())
    return tab


def decades_of(years):
    ys = sorted(set(int(y) for y in years))
    out = {}
    for d in range(ys[0] // 10 * 10, ys[-1] + 1, 10):
        out[f"{d}s"] = (d, d + 9)
    return out


def halves_of(years):
    ys = sorted(set(int(y) for y in years))
    mid = ys[len(ys) // 2]
    return {f"{ys[0]}–{mid - 1}": (ys[0], mid - 1), f"{mid}–{ys[-1]}": (mid, ys[-1])}


def row(label, x, mask, years, cost_scale, periods, obs=None, p=None):
    if obs is None:
        obs, p = perm_diff(x, mask)
    d = desc(np.asarray(x)[mask])
    tab = stability(np.asarray(x), np.asarray(mask), np.asarray(years), periods)
    same = sum(1 for v in tab.values() if np.sign(v) == np.sign(obs))
    r = dict(label=label, **d, diff=float(obs), p=float(p), stab=tab, same=same, total=len(tab),
             cost_ok=bool(abs(d["mean"]) > COST_PCT * cost_scale))
    TESTS.append(r)
    return r


def group_effect(x, labels, years, cats, cost_scale):
    x = np.asarray(x, float)
    labels = np.asarray(labels)
    obs, p = perm_groups(x, labels, cats)
    per = decades_of(years)
    return [row(c, x, labels == c, years, cost_scale, per, obs[i], p[i]) for i, c in enumerate(cats) if (labels == c).sum() >= 3]


# ------------------------------------------------------------------ seasonal paths
def seasonal_paths(s):
    """Average path through the calendar year, indexed to 100 at the prior year-end close."""
    s = s[~((s.index.month == 2) & (s.index.day == 29))]
    years = sorted(set(s.index.year))
    paths, pts = {}, {}
    for y in years[1:]:
        prev = s[s.index.year == y - 1]
        cur = s[s.index.year == y]
        if len(prev) == 0 or len(cur) < 20:
            continue
        base = prev.iloc[-1]
        cal = pd.date_range(f"{y}-01-01", f"{y}-12-31")
        cal = cal[~((cal.month == 2) & (cal.day == 29))]
        v = (cur / base * 100).reindex(cal).ffill().fillna(100.0)
        if y == years[-1]:
            v = v[v.index <= cur.index[-1]]
        paths[y] = v.values
        pts[y] = (v.values / 100 - 1) * base   # price change in points since the prior year-end
    cy = years[-1]
    full = [y for y in paths if y != cy and len(paths[y]) == 365]

    def avg(ys):
        # average daily log changes, then rebuild an index so long histories do not drift from compounding outliers
        arr = np.array([paths[y] for y in ys])
        lr = np.diff(np.log(np.hstack([np.full((len(ys), 1), 100.0), arr])), axis=1).mean(axis=0)
        return [round(float(v), 2) for v in 100 * np.exp(np.cumsum(lr))]

    out = dict(all=avg(full), current=[round(float(v), 2) for v in paths[cy]], current_year=int(cy), first_year=int(full[0]),
               n_years=len(full))
    for k in (2, 5, 10, 15, 20):
        if len(full) >= k:
            out[f"y{k}"] = avg(full[-k:])
    out["windows"] = seasonal_windows({y: paths[y] for y in full[-15:]})
    # points view: plain average of each year's price change since the prior year-end (how most seasonality sites draw it)
    sig = lambda v: float(f"{v:.4g}")
    pavg = lambda ys: [sig(v) for v in np.array([pts[y] for y in ys]).mean(axis=0)]
    out["pts"] = dict(all=pavg(full), current=[sig(v) for v in pts[cy]],
                      **{f"y{k}": pavg(full[-k:]) for k in (2, 5, 10, 15, 20) if len(full) >= k})
    return out


def seasonal_windows(paths, lengths=(10, 20, 30, 45, 60)):
    """Exploratory: calendar windows with the most consistent direction over the last 15 full years."""
    ys = sorted(paths)
    arr = np.array([paths[y] for y in ys])
    cand = []
    for L in lengths:
        for st in range(0, 365 - L):
            rr = (arr[:, st + L] / arr[:, st] - 1) * 100
            win = float((rr > 0).mean())
            cand.append(dict(start=st, end=st + L, days=L, avg=float(rr.mean()), med=float(np.median(rr)),
                             up=win, n=len(ys), years=[round(float(v), 2) for v in rr]))
    def pick(side):
        key = (lambda c: (c["up"], c["avg"])) if side == "bull" else (lambda c: (1 - c["up"], -c["avg"]))
        out = []
        for c in sorted(cand, key=key, reverse=True):
            if (side == "bull" and c["avg"] <= 0) or (side == "bear" and c["avg"] >= 0):
                continue
            if all(c["end"] <= o["start"] or c["start"] >= o["end"] for o in out):
                out.append(c)
            if len(out) == 4:
                break
        return out
    return dict(bull=pick("bull"), bear=pick("bear"), first=int(ys[0]), last=int(ys[-1]))


def month_matrix(s):
    m = s.resample("ME").last().pct_change().dropna() * 100
    out = {}
    for d, v in m.items():
        out.setdefault(int(d.year), [None] * 12)[d.month - 1] = round(float(v), 2)
    return [dict(year=y, m=v) for y, v in sorted(out.items())]


def tom_profile(r):
    """Average daily return by trading-day position around the month turn (−5 … +5)."""
    per = r.index.to_period("M")
    pos = pd.Series(1, index=r.index).groupby(per).cumcount().values
    ln = pd.Series(1, index=r.index).groupby(per).transform("size").values
    off = np.where(pos < 6, pos + 1, np.where(ln - pos <= 5, -(ln - pos), 0))
    out = []
    allm = r.mean()
    for k in [-5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6]:
        x = r.values[off == k]
        if len(x) > 10:
            se = x.std(ddof=1) / np.sqrt(len(x))
            out.append(dict(k=k, mean=float(x.mean()), lo=float(x.mean() - 1.96 * se), hi=float(x.mean() + 1.96 * se), n=int(len(x))))
    return dict(rows=out, base=float(allm))


def month_profile(s, windows=(5, 10, 20)):
    """Average cumulative path inside each calendar month, by trading day, from the prior month-end close."""
    me = s.resample("ME").last()
    out = {}
    cy, cm = s.index[-1].year, s.index[-1].month
    for m in range(1, 13):
        paths = {}
        for y in sorted(set(s.index.year)):
            seg_ = s[(s.index.year == y) & (s.index.month == m)]
            prev = me[me.index < pd.Timestamp(y, m, 1)]
            if len(seg_) < 5 or len(prev) == 0 or (prev.index[-1] < pd.Timestamp(y, m, 1) - pd.Timedelta(days=12)):
                continue
            paths[y] = np.log(seg_.values / prev.iloc[-1])
        full = [y for y in paths if not (y == cy and m == cm)]
        if not full:
            continue
        L = max(len(paths[y]) for y in full)
        def avg(ys):
            arr = np.array([np.pad(paths[y], (0, L - len(paths[y])), mode="edge") for y in ys])
            return [round(float(v), 3) for v in np.expm1(arr.mean(axis=0)) * 100]
        row = dict(all=avg(full), n=len(full))
        for k in windows:
            if len(full) > k:
                row[f"y{k}"] = avg(full[-k:])
        if m == cm and cy in paths:
            row["current"] = [round(float(v), 3) for v in np.expm1(paths[cy]) * 100]
        out[str(m)] = row
    return out


def annual_returns(s):
    ye = s.groupby(s.index.year).last()
    r = ye.pct_change().dropna() * 100
    return [dict(year=int(y), ret=round(float(v), 2)) for y, v in r.items()]


# ------------------------------------------------------------------ main
fomc = fomc_dates()
nfp = nfp_dates()
hikes, cuts = tcmb_changes()
print("FOMC", len(fomc), fomc[0], fomc[-1], "| NFP", len(nfp), "| TCMB hikes", len(hikes), "cuts", len(cuts))

res = dict(assets=[], cost_pct=COST_PCT, n_perm=N_PERM, n_perm_max=N_PERM_MAX,
           calendars=dict(fomc=[len(fomc), str(fomc[0]), str([d for d in fomc if d <= dt.date.today()][-1])],
                          tcmb=[len(hikes) + len(cuts), str(min(hikes + cuts)), str(max(hikes + cuts))]))
for code, fstem, name, group, roll, maxret in U:
    try:
        s, nbad = load(code, DATA)
    except FileNotFoundError:
        print(name, "skipped: no price file"); continue
    if s.index[-1].year - s.index[0].year - 1 < MIN_YEARS:
        print(name, "skipped: short history"); continue
    r = s.pct_change().dropna() * 100
    span = s.index.to_series().diff().dt.days.reindex(r.index)
    r = r[(r.abs() <= maxret * 100) & (span <= GAP_DAYS)]
    # every average and test uses completed calendar years only; the running year is shown separately
    year_done = s.index[-1] >= (pd.Timestamp(s.index[-1].year, 12, 31) if group == "Crypto" else pd.offsets.BYearEnd().rollforward(s.index[-1]))
    last_full = s.index[-1].year if year_done else s.index[-1].year - 1
    r = r[r.index.year <= last_full]
    years = r.index.year.values
    a = dict(code=code, name=name, group=group, start=str(s.index[0].date()), end=str(s.index[-1].date()),
             years=round((s.index[-1] - s.index[0]).days / 365.25, 1), last_full=int(last_full), last=float(f"{float(s.iloc[-1]):.6g}"), roll=roll, dropped=nbad,
             ticker=("^" + fstem[1:]) if fstem.startswith("_") else (fstem[:-2] + "=" + fstem[-1]) if fstem[-2:] in ("_F", "_X") else fstem,
             trimmed=START.get(code))
    a["seasonal"] = seasonal_paths(s)
    a["annual"] = annual_returns(s)
    a["matrix"] = month_matrix(s)
    a["mprof"] = month_profile(s)
    # months
    mr = s.resample("ME").last().pct_change().dropna() * 100
    mr = mr[mr.index.year <= last_full]
    mr = mr[mr.abs() < maxret * 200]
    mlab = [MONTHS[d.month - 1] for d in mr.index]
    a["month"] = group_effect(mr.values, mlab, mr.index.year.values, MONTHS, 2)
    # weekdays
    dlab = [DAYS[d.weekday()] for d in r.index]
    a["dow"] = group_effect(r.values, dlab, years, [d for d in DAYS if d in set(dlab)], 1)
    # turn of month
    per = r.index.to_period("M")
    pos = pd.Series(1, index=r.index).groupby(per).cumcount().values
    ln = pd.Series(1, index=r.index).groupby(per).transform("size").values
    tom = (pos < 3) | (pos == ln - 1)
    a["tom"] = [row("Turn of month", r.values, tom, years, 1, decades_of(years))]
    a["tomprof"] = tom_profile(r)
    # events: event day and the day before
    dates = pd.Index(r.index.date)
    events = []
    for eid, label, evd, since in [("fomc", "FOMC decision", fomc, None), ("nfp", "US jobs report (NFP)", nfp, None),
                                   ("tcmb_hike", "CBRT rate hike", hikes, None), ("tcmb_cut", "CBRT rate cut", cuts, None)]:
        if eid.startswith("tcmb") and group != "Türkiye":
            continue
        evs = set(evd)
        on = np.array([d in evs for d in dates])
        if on.sum() < 8:
            continue
        before = np.zeros(len(on), bool)
        before[:-1] = on[1:]
        lo_year = min(d.year for d in evd)
        keep = years >= lo_year
        x, y_ = r.values[keep], years[keep]
        hv = halves_of(y_)
        e_on = row(label, x, on[keep], y_, 1, hv)
        e_on.update(id=eid, window="Event day")
        e_bf = row(label, x, before[keep], y_, 1, hv)
        e_bf.update(id=eid, window="Day before")
        events += [e_on, e_bf]
    a["events"] = events
    # US presidential election cycle on calendar-year returns
    if not year_done and a["annual"] and a["annual"][-1]["year"] == s.index[-1].year:
        a["annual"][-1]["ytd"] = True
    ann = pd.Series({d["year"]: d["ret"] for d in a["annual"] if not d.get("ytd")})
    cyc_names = {1: "Post-election", 2: "Midterm", 3: "Pre-election", 0: "Election year"}
    lab = [cyc_names[y % 4] for y in ann.index]
    if len(ann) >= 16:
        a["cycle"] = group_effect(ann.values, lab, ann.index.values, ["Post-election", "Midterm", "Pre-election", "Election year"], 4)
        for rr in a["cycle"]:
            rr["stab"] = {}
            rr["same"] = rr["total"] = 0
    else:
        a["cycle"] = []
    for sec in ("month", "dow", "tom", "events", "cycle"):
        for t in a[sec]:
            t["roll"] = roll
    res["assets"].append(a)
    print(name, "done")

# Benjamini-Hochberg over every test on the site
ps = np.array([t["p"] for t in TESTS])
m = len(ps)
order = np.argsort(ps)
q = np.empty(m)
prev = 1.0
for rank in range(m - 1, -1, -1):
    i = order[rank]
    prev = min(prev, ps[i] * m / (rank + 1))
    q[i] = prev
for t, qq in zip(TESTS, q):
    t["q"] = float(qq)
    cons = t["same"] / t["total"] if t["total"] else None
    t["consistency"] = cons
    stable = (cons is None) or (t["total"] >= 2 and cons >= 0.7)
    if qq < 0.05 and stable and t["cost_ok"] and not t.get("roll"):
        t["verdict"] = "strong"
    elif t["p"] < 0.10 and (cons is None or cons >= 0.6):
        t["verdict"] = "weak"
    else:
        t["verdict"] = "noise"
res["n_tests"] = m
res["generated_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
res["groups"] = GROUPS
res["updated"] = max(a["end"] for a in res["assets"])
json.dump(__import__("universe").rnd(res), open(OUT, "w"), ensure_ascii=False, default=float, separators=(",", ":"))
print("tests:", m)
for a in res["assets"]:
    for sec in ("month", "dow", "tom", "events", "cycle"):
        for t in a[sec]:
            if t["verdict"] != "noise":
                print(f'{a["name"]:10s} {sec:6s} {t["label"]:22s} {t.get("window",""):10s} mean={t["mean"]:+.3f} p={t["p"]:.4f} q={t["q"]:.3f} {t["same"]}/{t["total"]} {t["verdict"]}')
