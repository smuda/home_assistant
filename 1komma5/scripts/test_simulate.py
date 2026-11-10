"""Tests for simulate.py, on small synthetic bucket lists.

Run from this directory: python3 -m unittest test_simulate
"""
import math
import unittest

import simulate as sim

# 2027-01-15 08:00:00 UTC, a multiple of 900 (Stockholm day "01-15")
T0 = 1800000000


def bucket(i=0, base=0.0, imp=1.0, exp=0.5, spot=0.5, soc=50, evhold=False,
           day="01-15"):
    return dict(t=T0 + 900 * i, grid=base * 1000, batt=0.0, imp=imp,
                exp=exp, spot=spot, soc=soc, soc_end=soc, evhold=evhold,
                day=day, base=base)


def end_soc(s0, powers):
    s = float(s0)
    for p in powers:
        s += p * sim.H / sim.CH if p > 0 else p * sim.H / sim.DIS
    return s


def row(t, grid=0.0, batt=0.0, imp_px=1.0, exp_px=0.5, spot=0.5, soc=50.0,
        ev=None):
    return dict(t=t, grid=grid, batt=batt, imp_px=imp_px, exp_px=exp_px,
                spot=spot, soc=soc, ev=ev)


class CostTest(unittest.TestCase):
    def test_import_uses_import_price(self):
        self.assertAlmostEqual(sim.cost(2.0, 1.5, 0.2), 2.0 * sim.H * 1.5)

    def test_export_uses_export_price_and_is_negative(self):
        c = sim.cost(-2.0, 1.5, 0.2)
        self.assertAlmostEqual(c, -2.0 * sim.H * 0.2)
        self.assertLess(c, 0)

    def test_zero_grid_costs_nothing(self):
        self.assertEqual(sim.cost(0.0, 1.5, 0.2), 0.0)


class PowerTest(unittest.TestCase):
    def test_charge_uses_ch(self):
        self.assertAlmostEqual(sim.power(4), 4 * sim.CH / sim.H)

    def test_discharge_uses_dis(self):
        self.assertAlmostEqual(sim.power(-4), -4 * sim.DIS / sim.H)

    def test_zero(self):
        self.assertEqual(sim.power(0), 0)

    def test_asymmetry_is_round_trip_loss(self):
        self.assertGreater(sim.power(1), -sim.power(-1))


class SelfConsumptionTest(unittest.TestCase):
    def test_positive_base_served_from_battery(self):
        Q = [bucket(0, base=2.0), bucket(1, base=2.0)]
        c, s, per = sim.self_consumption(Q, 50)
        self.assertAlmostEqual(c, 0.0)
        self.assertAlmostEqual(s, end_soc(50, [-2.0, -2.0]))
        self.assertAlmostEqual(per["01-15"], c)

    def test_stops_at_smin(self):
        Q = [bucket(0, base=5.0), bucket(1, base=5.0)]
        c, s, _ = sim.self_consumption(Q, sim.SMIN + 1)
        self.assertAlmostEqual(s, sim.SMIN)
        # 1 SOC point = 0.2 kWh; the rest of both buckets comes from grid
        grid_kwh = 2 * 5.0 * sim.H - sim.DIS
        self.assertAlmostEqual(c, grid_kwh * 1.0)

    def test_discharge_capped_by_pmax(self):
        Q = [bucket(0, base=15.0)]
        c, s, _ = sim.self_consumption(Q, 90)
        self.assertAlmostEqual(c, (15.0 - sim.PMAX) * sim.H * 1.0)

    def test_charges_from_surplus_only(self):
        Q = [bucket(0, base=-3.0)]
        c, s, _ = sim.self_consumption(Q, 50)
        self.assertAlmostEqual(s, end_soc(50, [3.0]))
        self.assertAlmostEqual(c, 0.0)

    def test_does_not_charge_from_grid(self):
        Q = [bucket(0, base=0.0), bucket(1, base=0.5, imp=0.01)]
        _, s, _ = sim.self_consumption(Q, 50)
        self.assertLessEqual(s, 50.0)

    def test_surplus_limited_by_smax(self):
        Q = [bucket(0, base=-8.0)]
        _, s, _ = sim.self_consumption(Q, sim.SMAX - 1)
        self.assertAlmostEqual(s, sim.SMAX)

    def test_idle_in_evhold_bucket(self):
        Q = [bucket(0, base=2.0, evhold=True, imp=1.0)]
        c, s, _ = sim.self_consumption(Q, 50, hold=True)
        self.assertAlmostEqual(s, 50)
        self.assertAlmostEqual(c, 2.0 * sim.H * 1.0)

    def test_evhold_ignored_when_hold_false(self):
        Q = [bucket(0, base=2.0, evhold=True)]
        _, s, _ = sim.self_consumption(Q, 50, hold=False)
        self.assertLess(s, 50)


class OptimiseTest(unittest.TestCase):
    def two(self, imp0, exp0, imp1, exp1, **kw):
        return [bucket(0, imp=imp0, exp=exp0, **kw),
                bucket(1, imp=imp1, exp=exp1, **kw)]

    def test_charges_cheap_discharges_expensive(self):
        Q = self.two(0.5, 0.1, 5.0, 4.0)
        acts, V = sim.optimise(Q, 50, 50)
        self.assertGreater(acts[0], 0)
        self.assertLess(acts[1], 0)
        self.assertGreaterEqual(end_soc(50, acts), 50 - 1e-9)

    def test_optimum_beats_idle(self):
        Q = self.two(0.5, 0.1, 5.0, 4.0)
        acts, _ = sim.optimise(Q, 50, 50)
        opt, _ = sim.run_cost(Q, acts)
        idle, _ = sim.run_cost(Q, [0.0, 0.0])
        self.assertLess(opt, idle)

    def test_idle_when_spread_below_round_trip_loss(self):
        # 1 pt costs 0.225 * 0.5 = 0.1125 to put in, returns 0.2 * 0.4
        # = 0.08 when exported
        Q = self.two(0.5, 0.1, 0.6, 0.4)
        acts, _ = sim.optimise(Q, 50, 50)
        self.assertEqual(list(acts), [0, 0])

    def test_never_acts_in_evhold_bucket_when_hold(self):
        Q = [bucket(0, imp=0.5, exp=0.1, evhold=True),
             bucket(1, imp=5.0, exp=4.0, evhold=True),
             bucket(2, imp=5.0, exp=4.0)]
        acts, _ = sim.optimise(Q, 50, 40, hold=True)
        self.assertEqual(acts[0], 0)
        self.assertEqual(acts[1], 0)

    def test_acts_in_evhold_bucket_when_hold_false(self):
        Q = [bucket(0, imp=0.5, exp=0.1, evhold=True),
             bucket(1, imp=5.0, exp=4.0, evhold=True)]
        acts, _ = sim.optimise(Q, 50, 50, hold=False)
        self.assertGreater(acts[0], 0)
        self.assertLess(acts[1], 0)

    def test_respects_gmax(self):
        Q = [bucket(0, base=15.0, imp=0.5, exp=0.1),
             bucket(1, base=0.0, imp=5.0, exp=4.0)]
        acts, _ = sim.optimise(Q, 50, 50)
        self.assertGreater(acts[0], 0)
        self.assertLessEqual(Q[0]["base"] + acts[0], sim.GMAX + 1e-9)
        # an unconstrained charge would be far above one SOC point
        self.assertLess(acts[0], 1.5)

    def test_respects_pmax(self):
        Q = [bucket(0, imp=0.1, exp=0.0), bucket(1, imp=50.0, exp=40.0)]
        acts, _ = sim.optimise(Q, 50, 20)
        self.assertEqual(acts[1], -12 * sim.DIS / sim.H)
        for p in acts:
            self.assertLessEqual(abs(p), sim.PMAX + 0.3 + 1e-9)

    def test_s_end_terminal_constraint(self):
        Q = self.two(1.0, 0.5, 1.0, 0.5)
        acts, V = sim.optimise(Q, 50, 60)
        self.assertGreaterEqual(end_soc(50, acts), 60 - 1e-9)

    def test_s_end_forces_charge_despite_loss(self):
        Q = self.two(1.0, 0.5, 1.0, 0.5)
        acts, _ = sim.optimise(Q, 50, 55)
        self.assertGreater(sum(acts), 0)

    def test_unreachable_s_end_is_infinite(self):
        Q = [bucket(0)]
        _, V = sim.optimise(Q, 50, sim.SMAX)
        self.assertGreater(V[0][50], 1e9)

    def test_V_length_and_terminal(self):
        Q = self.two(1.0, 0.5, 1.0, 0.5)
        _, V = sim.optimise(Q, 50, 40)
        self.assertEqual(len(V), len(Q) + 1)
        self.assertEqual(V[len(Q)][40], 0)
        self.assertEqual(V[len(Q)][sim.SMAX], 0)
        self.assertGreater(V[len(Q)][39], 1e9)
        self.assertEqual(set(V[0]), set(range(sim.SMIN, sim.SMAX + 1)))

    def test_actions_one_per_bucket(self):
        Q = self.two(1.0, 0.5, 1.0, 0.5)
        acts, _ = sim.optimise(Q, 50, 40)
        self.assertEqual(len(acts), 2)

    def test_deterministic(self):
        Q = self.two(1.0, 0.5, 1.0, 0.5)
        self.assertEqual(sim.optimise(Q, 50, 50)[0], sim.optimise(Q, 50, 50)[0])

    def test_prices_callable_drives_plan_not_cost(self):
        Q = self.two(0.5, 0.1, 5.0, 4.0)
        flat = lambda q: (1.0, 1.0)
        acts, _ = sim.optimise(Q, 50, 50, prices=flat)
        self.assertEqual(list(acts), [0, 0])
        # real prices would have traded
        real, _ = sim.optimise(Q, 50, 50)
        self.assertNotEqual(list(real), [0, 0])

    def test_V_is_cost_to_go(self):
        Q = self.two(0.5, 0.1, 5.0, 4.0)
        acts, V = sim.optimise(Q, 50, 50)
        total, _ = sim.run_cost(Q, acts)
        self.assertAlmostEqual(V[0][50], total, places=6)


class RunCostTest(unittest.TestCase):
    def test_sums_with_real_prices(self):
        Q = [bucket(0, base=1.0, imp=2.0, exp=0.5),
             bucket(1, base=1.0, imp=2.0, exp=0.5, day="01-16")]
        total, per = sim.run_cost(Q, [0.0, -3.0])
        exp_total = 1.0 * sim.H * 2.0 + (-2.0) * sim.H * 0.5
        self.assertAlmostEqual(total, exp_total)
        self.assertAlmostEqual(per["01-15"], 0.5)
        self.assertAlmostEqual(per["01-16"], -0.25)


class ViewPricesTest(unittest.TestCase):
    def test_view_prices(self):
        imp, exp = sim.view_prices(bucket(spot=1.0))
        self.assertAlmostEqual(imp, 1.25 + sim.VIEW_ADDER)
        self.assertAlmostEqual(exp, 1.25 + sim.FEED_IN)


class MarginalValueTest(unittest.TestCase):
    def setUp(self):
        self.V = [{}, {s: 0.01 * s * s for s in range(sim.SMIN, sim.SMAX + 1)}]

    def expect(self, s):
        return (self.V[1][s - 1] - self.V[1][s]) / sim.DIS

    def test_interior(self):
        self.assertAlmostEqual(sim.marginal_value(self.V, 0, 50),
                               self.expect(50))

    def test_clamped_at_smin(self):
        want = self.expect(sim.SMIN + 1)
        self.assertAlmostEqual(sim.marginal_value(self.V, 0, sim.SMIN), want)
        self.assertAlmostEqual(sim.marginal_value(self.V, 0, 0), want)

    def test_clamped_at_smax(self):
        want = self.expect(sim.SMAX)
        self.assertAlmostEqual(sim.marginal_value(self.V, 0, sim.SMAX), want)
        self.assertAlmostEqual(sim.marginal_value(self.V, 0, 120), want)


class BucketsTest(unittest.TestCase):
    def rows3(self, t, **kw):
        return [row(t + 300 * k, **kw) for k in range(3)]

    def test_aggregates_means_and_edges(self):
        rows = [row(T0, grid=1000, batt=100, imp_px=1, exp_px=0.1, spot=0.3,
                    soc=60),
                row(T0 + 300, grid=2000, batt=200, imp_px=2, exp_px=0.2,
                    spot=0.6, soc=59),
                row(T0 + 600, grid=3000, batt=300, imp_px=3, exp_px=0.3,
                    spot=0.9, soc=58)]
        (b,) = sim.buckets(rows)
        self.assertEqual(b["t"], T0)
        self.assertAlmostEqual(b["grid"], 2000)
        self.assertAlmostEqual(b["batt"], 200)
        self.assertAlmostEqual(b["imp"], 2)
        self.assertAlmostEqual(b["exp"], 0.2)
        self.assertAlmostEqual(b["spot"], 0.6)
        self.assertEqual(b["soc"], 60)
        self.assertEqual(b["soc_end"], 58)
        self.assertAlmostEqual(b["base"], (2000 - 200) / 1000)
        self.assertEqual(b["day"], "01-15")

    def test_splits_into_15_min_buckets(self):
        rows = self.rows3(T0) + self.rows3(T0 + 900)
        bs = sim.buckets(rows)
        self.assertEqual([b["t"] for b in bs], [T0, T0 + 900])

    def test_unaligned_t_keyed_by_floor(self):
        rows = [row(T0 + 100 + 300 * k) for k in range(3)]
        (b,) = sim.buckets(rows)
        self.assertEqual(b["t"], T0)

    def test_skips_bucket_with_fewer_than_three_rows(self):
        rows = [row(T0), row(T0 + 300)] + self.rows3(T0 + 900)
        bs = sim.buckets(rows)
        self.assertEqual([b["t"] for b in bs], [T0 + 900])

    def test_exactly_three_rows_kept(self):
        self.assertEqual(len(sim.buckets(self.rows3(T0))), 1)

    def test_evhold_from_ev_mean(self):
        rows = [row(T0 + 300 * k, ev=e) for k, e in enumerate([0, 0, 2000])]
        self.assertTrue(sim.buckets(rows)[0]["evhold"])
        rows = [row(T0 + 300 * k, ev=e) for k, e in enumerate([0, 0, 1000])]
        self.assertFalse(sim.buckets(rows)[0]["evhold"])

    def test_evhold_ignores_none(self):
        rows = [row(T0, ev=None), row(T0 + 300, ev=1000),
                row(T0 + 600, ev=1000)]
        self.assertTrue(sim.buckets(rows)[0]["evhold"])

    def test_evhold_false_when_all_none(self):
        self.assertFalse(sim.buckets(self.rows3(T0, ev=None))[0]["evhold"])

    def test_evhold_threshold_is_strict(self):
        self.assertFalse(sim.buckets(self.rows3(T0, ev=500))[0]["evhold"])

    def test_day_uses_stockholm_time(self):
        # 2027-01-15 23:30 UTC is 00:30 on the 16th in Stockholm
        t = 1800000000 + 15 * 3600 + 30 * 60
        t = t // 900 * 900
        (b,) = sim.buckets(self.rows3(t))
        self.assertEqual(b["day"], "01-16")


class LowSocBurstsTest(unittest.TestCase):
    DAY = 86400

    def test_counts_low_soc_high_discharge_charge(self):
        rows = [row(T0, soc=5, batt=6000),
                row(T0 + 300, soc=3, batt=12000),
                row(T0 + self.DAY, soc=0, batt=9000)]
        kwh, days = sim.low_soc_bursts(rows)
        self.assertAlmostEqual(kwh, (6000 + 12000 + 9000) / 1000 / 12)
        n = days if isinstance(days, int) else len(days)
        self.assertEqual(n, 2)

    def test_thresholds(self):
        rows = [row(T0, soc=5.1, batt=9000),   # soc too high
                row(T0 + 300, soc=4, batt=5000),   # batt not > 5000
                row(T0 + 600, soc=4, batt=-9000)]  # discharging
        kwh, days = sim.low_soc_bursts(rows)
        self.assertEqual(kwh, 0)
        n = days if isinstance(days, int) else len(days)
        self.assertEqual(n, 0)


class HoldValuationTest(unittest.TestCase):
    def test_idle_import_split_by_evhold(self):
        def idle(i, ev):
            q = bucket(i, base=2.0, imp=2.0, soc=50, evhold=ev)
            q["batt"] = 0.0
            return q
        Q = [idle(0, True), idle(1, False)]
        flat = {s: 1.0 for s in range(sim.SMIN, sim.SMAX + 1)}
        V = [flat, flat, flat]      # equal values -> marginal value 0
        out = sim.hold_valuation(Q, V)
        for key in ("EV hold", "no EV"):
            kwh, above, lost = out[key]
            self.assertAlmostEqual(kwh, 2.0 * sim.H)
            self.assertAlmostEqual(above, 2.0 * sim.H)
            self.assertAlmostEqual(lost, 2.0 * 2.0 * sim.H)


class FlowsTest(unittest.TestCase):
    def test_sources_and_sinks(self):
        Q = [bucket(0, base=1.0, imp=2.0, exp=0.5),    # charge from grid
             bucket(1, base=-2.0, imp=2.0, exp=0.5),   # charge from PV
             bucket(2, base=2.0, imp=3.0, exp=0.5)]    # discharge, 2 to load
        f = sim.flows(Q, [3.0, 1.0, -4.0])
        self.assertAlmostEqual(f["grid_charge_kwh"], 3.0 * sim.H)
        self.assertAlmostEqual(f["grid_charge_price"], 2.0)
        self.assertAlmostEqual(f["pv_charge_kwh"], 1.0 * sim.H)
        self.assertAlmostEqual(f["house_kwh"], 2.0 * sim.H)
        self.assertAlmostEqual(f["house_price"], 3.0)
        self.assertAlmostEqual(f["export_kwh"], 2.0 * sim.H)
        self.assertAlmostEqual(f["export_price"], 0.5)


class TariffAgreementTest(unittest.TestCase):
    def test_counts_sides_where_plans_differ(self):
        Q = [bucket(i) for i in range(4)]
        Q[0]["batt"] = 2000.0       # charging
        Q[1]["batt"] = -2000.0      # discharging
        p_real = [2.0, -2.0, 0.0, 2.0]
        p_view = [0.0, -2.0, 2.0, 0.0]
        # bucket 0: actual matches real; 1: plans agree, skipped;
        # 2: actual idle matches real; 3: actual idle matches view
        got = sim.tariff_agreement(Q, p_real, p_view, lambda d: True)
        self.assertEqual(got, (3, 2, 1))

    def test_selector_filters(self):
        Q = [bucket(0)]
        got = sim.tariff_agreement(Q, [2.0], [0.0], lambda d: False)
        self.assertEqual(got, (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
