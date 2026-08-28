"""Tests for the structural battery, the walk-forward test and the schedule.

Two properties matter for each analysis and both are tested: it must stay quiet
on fair draws, and it must fire on draws with something genuinely planted in
them. An analysis that only ever says "nothing" is worthless, and one that
always finds something is worse.
"""

from __future__ import annotations

import math
import os
import random
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lotterypatterns import simulate_draws  # noqa: E402
from lotterypatterns.backtest import (  # noqa: E402
    backtest, cold_strategy, default_strategies, hot_strategy, overdue_strategy,
    random_strategy,
)
from lotterypatterns.draws import Draw, DrawHistory  # noqa: E402
from lotterypatterns.games import EUROMILLIONS, LOTTO, THUNDERBALL  # noqa: E402
from lotterypatterns.patterns import (  # noqa: E402
    _contingency_chi_square, find_patterns, machine_findings, pair_findings,
    recency_findings, serial_findings,
)
from lotterypatterns.picker import plan_upcoming  # noqa: E402
from lotterypatterns.schedule import next_draw, next_draws  # noqa: E402


def build(n, seed, *, rig=None, machines=False, pool=59, picks=6):
    """A draw history, optionally with something real planted in it."""
    rng = random.Random(seed)
    draws = []
    when = date(2015, 1, 3)
    for i in range(n):
        numbers = set()
        machine = ("Arthur" if i % 2 else "Merlin") if machines else ""
        if rig == "pair" and rng.random() < 0.25:
            numbers |= {12, 44}
        if rig == "machine" and machine == "Merlin" and rng.random() < 0.30:
            numbers.add(38)
        if rig == "ball" and rng.random() < 0.20:
            numbers.add(17)
        while len(numbers) < picks:
            numbers.add(rng.randint(1, pool))
        draws.append(Draw(when, tuple(rng.sample(sorted(numbers), picks)),
                          machine=machine))
        when += timedelta(days=3)
    return DrawHistory(draws, pool=pool, picks=picks, name=rig or "fair")


class TestPatternsOnFairDraws(unittest.TestCase):
    def test_nothing_survives_on_fair_draws(self):
        report = find_patterns(simulate_draws(1200, pool=59, picks=6, seed=41))
        self.assertGreater(len(report.findings), 1000)
        self.assertEqual(report.survivors, [])
        self.assertIn("No structural departure", report.summary())

    def test_q_values_never_below_p_values(self):
        report = find_patterns(simulate_draws(400, pool=59, picks=6, seed=42))
        for finding in report.findings:
            self.assertGreaterEqual(finding.q_value, finding.p_value - 1e-12)

    def test_every_family_is_represented(self):
        report = find_patterns(build(900, 4, machines=True))
        kinds = {f.kind for f in report.findings}
        for expected in ("pairs", "recency", "serial", "periodicity", "machines"):
            self.assertIn(expected, kinds)

    def test_sorted_archives_skip_the_position_family(self):
        draws = [Draw(date(2020, 1, 1) + timedelta(days=3 * i),
                      tuple(sorted(random.Random(i).sample(range(1, 60), 6))))
                 for i in range(300)]
        report = find_patterns(DrawHistory(draws, pool=59, picks=6))
        self.assertNotIn("positions", {f.kind for f in report.findings})
        self.assertTrue(any("ascending order" in n for n in report.notes))


class TestPatternsFindRealStructure(unittest.TestCase):
    def test_a_planted_pair_is_found_and_named(self):
        report = find_patterns(build(1500, 7, rig="pair"))
        pairs = [f for f in report.survivors if f.kind == "pairs"]
        self.assertTrue(pairs)
        self.assertEqual(pairs[0].label, "12 and 44")

    def test_a_planted_pair_also_shows_in_return_times(self):
        report = find_patterns(build(1500, 7, rig="pair"))
        recency = [f.label for f in report.survivors if f.kind == "recency"]
        self.assertTrue(any("ball 12" in label for label in recency))

    def test_a_misbehaving_machine_is_identified_by_name(self):
        report = find_patterns(build(1500, 7, rig="machine", machines=True))
        machines = [f for f in report.survivors if f.kind == "machines"]
        self.assertTrue(machines)
        self.assertTrue(any("Merlin" in f.label for f in machines))

    def test_machines_are_compared_against_each_other(self):
        results, _notes = machine_findings(build(1200, 3, rig="machine", machines=True))
        labels = [r[0] for r in results]
        self.assertIn("machines differ from each other", labels)

    def test_no_machine_column_is_reported_not_silently_skipped(self):
        _results, notes = machine_findings(simulate_draws(300, seed=1))
        self.assertTrue(any("no machine recorded" in n for n in notes))

    def test_serial_dependence_is_flat_on_fair_draws(self):
        results = serial_findings(simulate_draws(1500, pool=59, picks=6, seed=6))
        self.assertTrue(all(p > 0.001 for _l, _d, _s, p in results))

    def test_pair_expectation_matches_the_combinatorics(self):
        history = simulate_draws(1000, pool=59, picks=6, seed=9)
        results = pair_findings(history)
        self.assertEqual(len(results), 59 * 58 // 2)
        # P(both balls in one draw) = C(57,4)/C(59,6) = 0.008767.
        expected = 1000 * math.comb(57, 4) / math.comb(59, 6)
        self.assertAlmostEqual(expected, 8.77, places=2)
        self.assertIn(f"{expected:.1f} expected", results[0][1])

    def test_recency_needs_enough_appearances(self):
        self.assertEqual(recency_findings(simulate_draws(40, seed=2)), [])

    def test_contingency_table(self):
        # Two identical rows cannot differ from each other.
        statistic, df = _contingency_chi_square([[10, 20, 30], [10, 20, 30]])
        self.assertAlmostEqual(statistic, 0.0)
        self.assertEqual(df, 2)
        # Opposite rows must.
        statistic, _df = _contingency_chi_square([[60, 0], [0, 60]])
        self.assertGreater(statistic, 100)


class TestBacktest(unittest.TestCase):
    def test_no_strategy_beats_chance_on_fair_draws(self):
        report = backtest(simulate_draws(1200, pool=59, picks=6, seed=77),
                          train=600, max_predictions=300)
        self.assertFalse(any(r.beat_chance for r in report.results))
        self.assertIn("None of them beat chance", report.summary())

    def test_expected_rate_is_the_same_for_every_strategy(self):
        report = backtest(simulate_draws(800, pool=59, picks=6, seed=5),
                          train=400, max_predictions=150)
        for result in report.results:
            self.assertAlmostEqual(result.expected_per_line, 36 / 59, places=9)

    def test_a_genuine_ball_bias_is_detected_out_of_sample(self):
        report = backtest(build(1400, 9, rig="ball"), train=700, max_predictions=300)
        winners = [r for r in report.results if r.beat_chance]
        self.assertTrue(winners, "a real bias must show up out of sample")
        # Which method spots it can vary; that it is spotted, and by a wide
        # margin, must not.
        self.assertGreater(max(r.edge_pct for r in winners), 20.0)
        baseline = next(r for r in report.results if r.name == "random (baseline)")
        self.assertFalse(baseline.beat_chance)

    def test_correction_is_applied_across_strategies(self):
        report = backtest(simulate_draws(900, pool=59, picks=6, seed=13),
                          train=450, max_predictions=200)
        for result in report.results:
            self.assertGreaterEqual(result.q_value, result.p_value - 1e-12)

    def test_every_prediction_is_a_valid_line(self):
        history = simulate_draws(400, pool=59, picks=6, seed=3)
        for name, strategy in default_strategies(1).items():
            with self.subTest(strategy=name):
                line = list(strategy(history[:200], 6))[:6]
                self.assertEqual(len(line), 6)
                self.assertEqual(len(set(line)), 6, f"{name} returned duplicates")
                self.assertTrue(all(1 <= n <= 59 for n in line))

    def test_hot_and_cold_disagree(self):
        history = simulate_draws(500, pool=59, picks=6, seed=4)
        self.assertNotEqual(set(hot_strategy()(history, 6)),
                            set(cold_strategy()(history, 6)))

    def test_overdue_picks_the_longest_absent_numbers(self):
        history = simulate_draws(300, pool=59, picks=6, seed=8)
        line = overdue_strategy()(history, 6)
        recent = set()
        for draw in list(history)[-5:]:
            recent.update(draw.numbers)
        self.assertFalse(set(line) & recent)

    def test_too_short_a_history_explains_itself(self):
        with self.assertRaises(ValueError) as ctx:
            backtest(simulate_draws(60, seed=1), train=55)
        self.assertIn("Not enough draws", str(ctx.exception))

    def test_random_strategy_is_reproducible(self):
        history = simulate_draws(200, seed=2)
        self.assertEqual(list(random_strategy(7)(history, 6)),
                         list(random_strategy(7)(history, 6)))


class TestSchedule(unittest.TestCase):
    def test_lotto_draws_fall_on_wednesday_and_saturday(self):
        for draw in next_draws(LOTTO, 6, today=date(2026, 8, 28), now_hour=10):
            self.assertIn(draw.weekday, ("Wednesday", "Saturday"))

    def test_thunderball_has_four_draw_days(self):
        days = {d.weekday for d in next_draws(THUNDERBALL, 8,
                                              today=date(2026, 8, 28), now_hour=10)}
        self.assertEqual(days, {"Tuesday", "Wednesday", "Friday", "Saturday"})

    def test_dates_are_in_order_and_in_the_future(self):
        today = date(2026, 8, 28)
        draws = next_draws(EUROMILLIONS, 5, today=today, now_hour=10)
        self.assertEqual([d.draw_date for d in draws],
                         sorted(d.draw_date for d in draws))
        for draw in draws:
            self.assertGreaterEqual(draw.draw_date, today)

    def test_a_draw_today_counts_until_the_evening_cutoff(self):
        friday = date(2026, 8, 28)  # a Thunderball day
        self.assertEqual(next_draw(THUNDERBALL, today=friday, now_hour=10).draw_date,
                         friday)
        self.assertGreater(next_draw(THUNDERBALL, today=friday, now_hour=21).draw_date,
                           friday)

    def test_days_away_counts_from_today(self):
        today = date(2026, 8, 28)
        draw = next_draws(LOTTO, 1, today=today, now_hour=10)[0]
        self.assertEqual(draw.days_away(today), (draw.draw_date - today).days)


class TestPlanUpcoming(unittest.TestCase):
    def test_a_plan_covers_the_next_draws_with_dated_slips(self):
        history = simulate_draws(600, pool=59, picks=6, seed=15)
        plan = plan_upcoming(LOTTO, history, lines_per_draw=2, draws_ahead=3,
                             seed=1, run_patterns=False, today=date(2026, 8, 28))
        self.assertEqual(len(plan.slips), 3)
        for slip in plan.slips:
            self.assertEqual(len(slip.tickets), 2)
            self.assertIn(slip.draw_label.split()[0], ("Wednesday", "Saturday"))
            for ticket in slip.tickets:
                self.assertEqual(len(set(ticket.numbers)), 6)

    def test_thunderball_slips_carry_a_bonus_ball(self):
        history = simulate_draws(500, pool=39, picks=5, seed=16)
        plan = plan_upcoming(THUNDERBALL, history, lines_per_draw=2, draws_ahead=1,
                             seed=2, run_patterns=False, today=date(2026, 8, 28))
        for ticket in plan.slips[0].tickets:
            self.assertEqual(len(ticket.numbers), 5)
            self.assertEqual(len(ticket.bonus), 1)
            self.assertTrue(1 <= ticket.bonus[0] <= 14)

    def test_the_summary_states_the_odds_and_does_not_promise_an_edge(self):
        history = simulate_draws(500, pool=59, picks=6, seed=17)
        summary = plan_upcoming(LOTTO, history, draws_ahead=1, seed=3,
                                run_patterns=False,
                                today=date(2026, 8, 28)).summary()
        self.assertIn("1 in 45,057,474", summary)
        self.assertIn("Unchanged", summary)
        self.assertIn("no number is due, hot or cold", summary)

    def test_a_real_bias_reaches_the_plan(self):
        plan = plan_upcoming(LOTTO, build(2000, 21, rig="ball"), draws_ahead=1,
                             seed=4, run_patterns=False, today=date(2026, 8, 28))
        self.assertTrue(plan.bias_found)
        self.assertIn("BALL BIAS FOUND", plan.summary())

    def test_patterns_and_backtest_can_both_feed_the_plan(self):
        plan = plan_upcoming(LOTTO, build(900, 22, rig="pair"), draws_ahead=1,
                             seed=5, run_patterns=True, run_backtest=True,
                             today=date(2026, 8, 28))
        self.assertTrue(plan.pattern_notes)
        self.assertTrue(plan.backtest_note)
        self.assertIn("STRUCTURAL PATTERNS", plan.summary())


if __name__ == "__main__":
    unittest.main(verbosity=2)
