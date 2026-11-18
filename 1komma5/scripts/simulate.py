"""Counterfactual battery simulation on 15-min buckets from sim.csv.

Replays the month's house load (grid - battery) against a battery
model and compares what the battery actually did with a greedy
self-consumption policy and a perfect-foresight optimum (backward DP
over integer SOC points).

Sign conventions:
  grid, batt in W: grid + = import, - = export; batt + = charging
  power / base in kW, same signs; base = house load net of PV, i.e.
  what the grid would carry with the battery idle
Prices are kr/kWh. Cost is positive money out.

Model: 1 SOC point = DIS kWh delivered to the house, but CH kWh of AC
needed to put it in (the difference is round-trip loss).
"""
import collections
import csv
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")

H = 0.25              # bucket length, hours
DIS = 0.200           # kWh delivered per SOC point
CH = 0.225            # kWh in per SOC point
SMIN = 8              # battery min SOC
SMAX = 98
PMAX = 10.0           # kW
GMAX = 16.0           # kW import cap, 25 A fuse
VIEW_ADDER = 1.4375   # what 1KOMMA5 adds to 1.25 * spot (grid fee etc.)
FEED_IN = 0.104
INF = float("inf")


def load(path):
    with open(path) as f:
        return [{k: (float(v) if v not in ("", "None") else None)
                 for k, v in r.items()} for r in csv.DictReader(f)]


def buckets(rows):
    groups = collections.OrderedDict()
    for r in rows:
        groups.setdefault(int(r["t"]) // 900 * 900, []).append(r)
    out = []
    for k, rs in groups.items():
        if len(rs) < 3:
            continue

        def mean(f):
            return sum(x[f] for x in rs) / len(rs)

        ev = [x["ev"] for x in rs if x["ev"] is not None]
        q = dict(
            t=k, grid=mean("grid"), batt=mean("batt"), imp=mean("imp_px"),
            exp=mean("exp_px"), spot=mean("spot"),
            soc=rs[0]["soc"], soc_end=rs[-1]["soc"],
            evhold=(sum(ev) / len(ev) > 500) if ev else False,
            day=datetime.fromtimestamp(k, TZ).strftime("%m-%d"))
        q["base"] = (q["grid"] - q["batt"]) / 1000
        out.append(q)
    return out


def cost(g, imp, exp):
    return g * H * imp if g > 0 else g * H * exp


def power(a):
    return a * CH / H if a > 0 else a * DIS / H


def self_consumption(Q, s0, hold=True):
    s = float(s0)
    c = 0.0
    per = collections.defaultdict(float)
    for q in Q:
        b = q["base"]
        p = 0.0
        if not (hold and q["evhold"]):
            if b > 0:
                p = -min(b, PMAX, (s - SMIN) * DIS / H)
            elif b < 0:
                p = min(-b, PMAX, (SMAX - s) * CH / H)
        s += p * H / CH if p > 0 else p * H / DIS
        x = cost(b + p, q["imp"], q["exp"])
        c += x
        per[q["day"]] += x
    return c, s, per


def _real(q):
    return q["imp"], q["exp"]


def view_prices(q):
    return (q["spot"] * 1.25 + VIEW_ADDER, q["spot"] * 1.25 + FEED_IN)


def _best(q, s, Vn, prices, hold):
    """Cheapest (value, action) from SOC s; first minimum wins, which
    keeps the plan deterministic."""
    imp, exp = prices(q)
    best, ba = INF, 0
    for a in ([0] if (hold and q["evhold"]) else range(-13, 11)):
        s2 = s + a
        if s2 < SMIN or s2 > SMAX:
            continue
        p = power(a)
        if abs(p) > PMAX + 0.3:
            continue
        g = q["base"] + p
        if g > GMAX:
            continue
        v = cost(g, imp, exp) + Vn[s2]
        if v < best:
            best, ba = v, a
    return best, ba


def optimise(Q, s0, s_end, prices=None, hold=True):
    prices = prices or _real
    S = range(SMIN, SMAX + 1)
    V = [None] * (len(Q) + 1)
    V[len(Q)] = {s: (0 if s >= s_end else INF) for s in S}
    for i in range(len(Q) - 1, -1, -1):
        V[i] = {s: _best(Q[i], s, V[i + 1], prices, hold)[0] for s in S}
    s = s0
    actions = []
    for i, q in enumerate(Q):
        a = _best(q, s, V[i + 1], prices, hold)[1]
        actions.append(power(a))
        s += a
    return actions, V


def run_cost(Q, powers):
    total = 0.0
    per = collections.defaultdict(float)
    for q, p in zip(Q, powers):
        x = cost(q["base"] + p, q["imp"], q["exp"])
        total += x
        per[q["day"]] += x
    return total, per


def marginal_value(V, i, s):
    """kr per kWh AC the battery would deliver at bucket i from SOC s."""
    s = max(SMIN + 1, min(SMAX, round(s)))
    lo, hi = V[i + 1][s - 1], V[i + 1][s]
    if lo == hi:      # both unreachable (inf) or equal
        return 0.0
    return (lo - hi) / DIS


def hold_valuation(Q, V):
    """Grid import while the battery sat idle, and what it cost against
    the stored energy's value. Keys: kWh, kWh above stored value, kr."""
    tot = {"EV hold": [0.0, 0.0, 0.0], "no EV": [0.0, 0.0, 0.0]}
    for i, q in enumerate(Q):
        g = q["grid"] / 1000
        b = q["batt"] / 1000
        if g < 0.3 or b < -0.2 or b > 0.2 or q["soc"] < SMIN + 3:
            continue
        kwh = min(g, PMAX) * H
        m = marginal_value(V, i, q["soc"])
        t = tot["EV hold" if q["evhold"] else "no EV"]
        t[0] += kwh
        t[1] += kwh * (q["imp"] > m + 0.05)
        t[2] += max(q["imp"] - m, 0) * kwh
    return {k: tuple(v) for k, v in tot.items()}


def flows(Q, powers):
    gc = [0.0, 0.0]
    pv = 0.0
    dl = [0.0, 0.0]
    ex = [0.0, 0.0]
    for q, p in zip(Q, powers):
        b = q["base"]
        g = b + p
        if p > 0:
            from_grid = min(p, max(g, 0))
            gc[0] += from_grid * H
            gc[1] += from_grid * H * q["imp"]
            pv += (p - from_grid) * H
        if p < 0:
            d = -p
            to_load = min(d, max(b, 0))
            to_exp = d - to_load
            dl[0] += to_load * H
            dl[1] += to_load * H * q["imp"]
            ex[0] += to_exp * H
            ex[1] += to_exp * H * q["exp"]
    return dict(
        grid_charge_kwh=gc[0], grid_charge_price=gc[1] / max(gc[0], 1e-9),
        pv_charge_kwh=pv,
        house_kwh=dl[0], house_price=dl[1] / max(dl[0], 1e-9),
        export_kwh=ex[0], export_price=ex[1] / max(ex[0], 1e-9))


def soc_check(Q):
    """End SOC the model predicts from the battery's actual flows."""
    s = Q[0]["soc"]
    for q in Q:
        b = q["batt"] / 1000
        s += b * H / CH if b > 0 else b * H / DIS
    return s


def tariff_agreement(Q, p_real, p_view, sel):
    """Where the tariff-aware and spot-only plans differ in direction
    (charge / discharge / idle, 0.5 kW threshold), how often the
    actual battery sided with each."""
    def kind(p):
        return (p > 0.5, p < -0.5)

    differ = match_real = match_view = 0
    for i, q in enumerate(Q):
        if not sel(datetime.fromtimestamp(q["t"], TZ)):
            continue
        if kind(p_real[i]) == kind(p_view[i]):
            continue
        differ += 1
        act = kind(q["batt"] / 1000)
        match_real += act == kind(p_real[i])
        match_view += act == kind(p_view[i])
    return differ, match_real, match_view


def low_soc_bursts(rows):
    kwh = 0.0
    days = set()
    for r in rows:
        if r["soc"] is None or r["batt"] is None:
            continue
        if r["soc"] <= 5 and r["batt"] > 5000:
            kwh += r["batt"] / 1000 / 12
            days.add(datetime.fromtimestamp(int(r["t"]), TZ).strftime("%m-%d"))
    return kwh, len(days)


def split(per):
    nov = sum(v for d, v in per.items() if d >= "11-01")
    return sum(per.values()) - nov, nov


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "sim.csv"
    rows = load(path)
    Q = buckets(rows)
    s0 = round(Q[0]["soc"])
    s1 = round(Q[-1]["soc_end"])
    days = len(Q) * H / 24
    print("window %s -> %s, %.1f days, SOC %d -> %d"
          % (Q[0]["day"], Q[-1]["day"], days, s0, s1))

    nobatt, _ = run_cost(Q, [0.0] * len(Q))
    actual, _ = run_cost(Q, [q["batt"] / 1000 for q in Q])
    ga, gs, _ = self_consumption(Q, s0, True)
    gb, gbs, _ = self_consumption(Q, s0, False)
    pa, V = optimise(Q, s0, s1)
    pb, _ = optimise(Q, s0, s1, hold=False)
    da, dper = run_cost(Q, pa)
    db, _ = run_cost(Q, pb)
    pv_, _ = optimise(Q, s0, s1, prices=view_prices)
    va, vper = run_cost(Q, pv_)
    print("no battery            %7.0f kr" % nobatt)
    print("actual (1KOMMA5)      %7.0f kr" % actual)
    print("self-cons + EV hold   %7.0f kr  (end SOC %.0f)" % (ga, gs))
    print("self-cons, no EV hold %7.0f kr  (end SOC %.0f)" % (gb, gbs))
    print("optimum + EV hold     %7.0f kr  (Oct %.0f, Nov %.0f)"
          % ((da,) + split(dper)))
    print("optimum, no EV hold   %7.0f kr" % db)
    print("optimum on 1KOMMA5 view, real prices %.0f kr  (Oct %.0f, Nov %.0f)"
          % ((va,) + split(vper)))
    print("model SOC end from actual flows %.0f vs actual %.0f"
          % (soc_check(Q), Q[-1]["soc_end"]))

    for name, pw in (("actual", [q["batt"] / 1000 for q in Q]),
                     ("optimum", pa)):
        f = flows(Q, pw)
        print("%-8s grid-charge %5.0f kWh @ %.2f | PV-charge %4.0f kWh | "
              "discharge->house %5.0f kWh @ %.2f | ->export %4.0f kWh @ %.2f"
              % (name, f["grid_charge_kwh"], f["grid_charge_price"],
                 f["pv_charge_kwh"], f["house_kwh"], f["house_price"],
                 f["export_kwh"], f["export_price"]))

    for k, (kwh, above, lost) in hold_valuation(Q, V).items():
        print("%s idle-import %.0f kWh, of which %.0f kWh at price above "
              "stored value, lost %.0f kr" % (k, kwh, above, lost))

    for label, sel in (
            ("Nov working days", lambda d: d.month == 11 and d.weekday() < 5),
            ("all other days",
             lambda d: not (d.month == 11 and d.weekday() < 5))):
        n, mr, mv = tariff_agreement(Q, pa, pv_, sel)
        print("%s: plans differ in %d buckets; actual matches "
              "tariff-aware %d, spot-only %d" % (label, n, mr, mv))

    kwh, nd = low_soc_bursts(rows)
    print("low-SOC bursts (SOC <= 5, battery > 5 kW): %.0f kWh on %d days"
          % (kwh, nd))


if __name__ == "__main__":
    main()
