"""Tests for the pattern search.

The statistical claims are checked two ways: the measures are verified against
hand-computed values, and the whole search is verified to stay quiet on fair
draws while still detecting a planted effect.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lotterypatterns import (  # noqa: E402
    Draw,
    DrawHistory,
    benjamini_hochberg,
    bonferroni,
    feature_series,
    mutual_information,
    null_calibration,
    pearson,
    permutation_test,
    search,
    simulate_biased_draws,
    simulate_draws,
    spearman,
)
from lotterypatterns.features import FEATURES_BY_NAME  # noqa: E402
from lotterypatterns.metrics import (  # noqa: E402
    METRICS_BY_NAME,
    default_metrics,
    metric_from_csv,
    moon_illumination,
)
from lotterypatterns.search import _lagged_pair  # noqa: E402


class TestDraws(unittest.TestCase):
    def test_history_sorts_by_date(self):
        history = DrawHistory([
            Draw(date(2020, 1, 8), (1, 2, 3)),
            Draw(date(2020, 1, 1), (4, 5, 6)),
        ], pool=59)
        self.assertEqual(history[0].drawn_on, date(2020, 1, 1))

    def test_rejects_duplicate_numbers(self):
        with self.assertRaises(ValueError):
            Draw(date(2020, 1, 1), (7, 7, 9))

    def test_rejects_number_outside_pool(self):
        with self.assertRaises(ValueError):
            DrawHistory([Draw(date(2020, 1, 1), (1, 2, 99))], pool=59)

    def test_csv_round_trip(self):
        original = simulate_draws(25, seed=1)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "draws.csv")
            original.to_csv(path)
            loaded = DrawHistory.from_csv(path, pool=59)
        self.assertEqual(len(loaded), len(original))
        self.assertEqual(loaded[0].sorted_numbers, original[0].sorted_numbers)
        self.assertEqual(loaded.dates, original.dates)

    def test_simulated_draws_are_uniform_enough(self):
        history = simulate_draws(4000, pool=59, picks=6, seed=5)
        counts = [0] * 60
        for draw in history:
            for n in draw.numbers:
                counts[n] += 1
        expected = 4000 * 6 / 59
        self.assertLess(max(abs(c - expected) for c in counts[1:]), expected * 0.25)


class TestFeatures(unittest.TestCase):
    def setUp(self):
        self.draw = Draw(date(2020, 1, 1), (3, 4, 7, 17, 28, 41))
        self.previous = Draw(date(2019, 12, 29), (7, 8, 9, 10, 11, 41))

    def _value(self, name):
        return FEATURES_BY_NAME[name](self.draw, self.previous)

    def test_scalar_features(self):
        self.assertEqual(self._value("sum"), 100.0)
        self.assertEqual(self._value("spread"), 38.0)
        self.assertEqual(self._value("lowest"), 3.0)
        self.assertEqual(self._value("highest"), 41.0)
        self.assertEqual(self._value("odd_count"), 4.0)
        self.assertEqual(self._value("prime_count"), 4.0)  # 3, 7, 17, 41
        self.assertEqual(self._value("consecutive_pairs"), 1.0)  # (3, 4)
        self.assertEqual(self._value("multiple_of_seven"), 2.0)  # 7 and 28
        self.assertEqual(self._value("contains_digit_seven"), 2.0)  # 7 and 17
        self.assertEqual(self._value("digit_sum"), 3 + 4 + 7 + 8 + 10 + 5)
        self.assertEqual(self._value("sum_mod_seven"), 2.0)
        self.assertEqual(self._value("decade_spread"), 4.0)
        self.assertEqual(self._value("max_gap"), 13.0)  # 28 -> 41

    def test_previous_dependent_features(self):
        self.assertEqual(self._value("carry_over"), 2.0)  # 7 and 41
        self.assertEqual(self._value("jump_distance"), abs(100 - 86))

    def test_first_draw_has_no_previous(self):
        history = simulate_draws(5, seed=2)
        values = feature_series(history, FEATURES_BY_NAME["carry_over"])
        self.assertIsNone(values[0])
        self.assertTrue(all(v is not None for v in values[1:]))


class TestMetrics(unittest.TestCase):
    def test_moon_illumination_tracks_known_phases(self):
        # 2000-01-06 was a new moon; a full moon follows about 14.8 days later.
        self.assertLess(moon_illumination(date(2000, 1, 6)), 0.02)
        self.assertGreater(moon_illumination(date(2000, 1, 21)), 0.98)

    def test_metrics_stay_in_their_declared_ranges(self):
        sample = [date(2020, 1, 1).replace(day=1 + i % 28, month=1 + i % 12)
                  for i in range(60)]
        for name in ("moon_illumination", "lunar_distance_phase",
                     "sunspot_cycle_phase", "annual_phase"):
            for when in sample:
                value = METRICS_BY_NAME[name](when)
                self.assertGreaterEqual(value, 0.0, name)
                self.assertLessEqual(value, 1.0, name)

    def test_daylight_is_longer_in_june_than_december(self):
        june = METRICS_BY_NAME["daylight_hours"](date(2020, 6, 21))
        december = METRICS_BY_NAME["daylight_hours"](date(2020, 12, 21))
        self.assertGreater(june, december + 6.0)

    def test_friday_thirteenth(self):
        self.assertEqual(METRICS_BY_NAME["is_friday_thirteenth"](date(2020, 3, 13)), 1.0)
        self.assertEqual(METRICS_BY_NAME["is_friday_thirteenth"](date(2020, 3, 14)), 0.0)

    def test_csv_metric_forward_fills_then_expires(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "metric.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("date,value\n2020-01-01,10\n2020-02-01,20\n")
            metric = metric_from_csv(path, name="thing", max_staleness_days=7)
            self.assertEqual(metric(date(2020, 1, 1)), 10.0)
            self.assertEqual(metric(date(2020, 1, 5)), 10.0)   # carried forward
            self.assertIsNone(metric(date(2020, 1, 20)))       # too stale to use
            self.assertIsNone(metric(date(2019, 12, 1)))       # before the series
            self.assertEqual(metric(date(2020, 2, 2)), 20.0)


class TestStats(unittest.TestCase):
    def test_pearson_on_a_perfect_line(self):
        result = pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        self.assertAlmostEqual(result.statistic, 1.0, places=12)

    def test_pearson_matches_hand_computed_value(self):
        xs = [1, 2, 3, 4, 5]
        ys = [2, 1, 4, 3, 5]
        self.assertAlmostEqual(pearson(xs, ys).statistic, 0.8, places=10)

    def test_pearson_p_value_against_known_case(self):
        # r = 0.8, n = 5 gives t = 2.3094 on 3 df, two-sided p = 0.10409.
        self.assertAlmostEqual(pearson([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]).p_value,
                               0.10409, places=5)

    def test_spearman_is_monotone_invariant(self):
        xs = [1, 2, 3, 4, 5, 6]
        ys = [1, 8, 27, 64, 125, 216]
        self.assertAlmostEqual(spearman(xs, ys).statistic, 1.0, places=12)
        self.assertLess(pearson(xs, ys).statistic, 1.0)

    def test_spearman_handles_ties(self):
        result = spearman([1, 1, 2, 2, 3, 3], [1, 2, 3, 4, 5, 6])
        self.assertGreater(result.statistic, 0.9)

    def test_constant_series_is_not_a_correlation(self):
        result = pearson([1, 2, 3, 4, 5], [7, 7, 7, 7, 7])
        self.assertEqual(result.statistic, 0.0)
        self.assertEqual(result.p_value, 1.0)

    def test_none_values_are_dropped_pairwise(self):
        result = pearson([1, 2, None, 4, 5], [2, 4, 9, 8, 10])
        self.assertAlmostEqual(result.statistic, 1.0, places=12)
        self.assertEqual(result.n, 4)

    def test_mutual_information_sees_a_non_monotone_link(self):
        xs = [i / 50.0 - 1.0 for i in range(100)]
        ys = [x * x for x in xs]  # V shape: zero correlation, real dependence
        self.assertLess(abs(pearson(xs, ys).statistic), 0.2)
        self.assertGreater(mutual_information(xs, ys).statistic, 0.5)

    def test_permutation_p_value_is_never_zero(self):
        xs = list(range(50))
        p = permutation_test(xs, xs, lambda a, b: pearson(a, b).statistic,
                             trials=99, seed=1)
        self.assertGreater(p, 0.0)
        self.assertLessEqual(p, 0.01)

    def test_bonferroni_scales_by_test_count(self):
        self.assertEqual(bonferroni([0.01, 0.02]), [0.02, 0.04])
        self.assertEqual(bonferroni([0.5, 0.6]), [1.0, 1.0])

    def test_benjamini_hochberg_is_monotone_and_bounded(self):
        p_values = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205]
        q_values = benjamini_hochberg(p_values)
        self.assertEqual(len(q_values), len(p_values))
        self.assertTrue(all(0.0 <= q <= 1.0 for q in q_values))
        self.assertTrue(all(a <= b + 1e-12 for a, b in zip(q_values, q_values[1:])))
        self.assertAlmostEqual(q_values[0], 0.008, places=6)  # 0.001 * 8 / 1
        self.assertTrue(all(q >= p for q, p in zip(q_values, p_values)))

    def test_benjamini_hochberg_is_never_stricter_than_bonferroni(self):
        p_values = [0.001, 0.01, 0.02, 0.3, 0.7]
        for q, b in zip(benjamini_hochberg(p_values), bonferroni(p_values)):
            self.assertLessEqual(q, b + 1e-12)

    def test_uniform_p_values_under_the_null(self):
        # Correlating independent noise should give p-values spread over [0, 1].
        import random
        rng = random.Random(11)
        p_values = []
        for _ in range(200):
            xs = [rng.gauss(0, 1) for _ in range(60)]
            ys = [rng.gauss(0, 1) for _ in range(60)]
            p_values.append(pearson(xs, ys).p_value)
        below_five = sum(1 for p in p_values if p <= 0.05)
        self.assertLess(below_five, 25)  # ~10 expected; well clear of chance
        self.assertGreater(sum(p_values) / len(p_values), 0.4)


class TestLagAlignment(unittest.TestCase):
    def test_lag_shifts_the_metric_backwards(self):
        features = [1.0, 2.0, 3.0, 4.0]
        metrics = [10.0, 20.0, 30.0, 40.0]
        xs, ys = _lagged_pair(features, metrics, 1)
        self.assertEqual(xs, [2.0, 3.0, 4.0])
        self.assertEqual(ys, [10.0, 20.0, 30.0])

    def test_negative_lag_is_refused(self):
        with self.assertRaises(ValueError):
            _lagged_pair([1.0], [1.0], -1)

    def test_missing_values_drop_the_pair(self):
        xs, ys = _lagged_pair([1.0, None, 3.0], [4.0, 5.0, None], 0)
        self.assertEqual(xs, [1.0])
        self.assertEqual(ys, [4.0])


class TestSearch(unittest.TestCase):
    def test_fair_draws_yield_no_survivors(self):
        history = simulate_draws(400, seed=17)
        report = search(history, lags=(0, 1))
        self.assertGreater(report.n_tests, 500)
        self.assertEqual(report.significant(), [])

    def test_naive_hit_count_is_near_the_alpha_rate(self):
        history = simulate_draws(400, seed=23)
        report = search(history, lags=(0, 1))
        expected = report.expected_naive_hits()
        self.assertLess(len(report.naive_hits()), expected * 3)

    def test_planted_effect_is_found_and_named(self):
        history = simulate_biased_draws(400, moon_illumination, strength=1.5, seed=3)
        report = search(history, lags=(0,))
        survivors = report.significant()
        self.assertTrue(survivors)
        self.assertEqual(survivors[0].metric, "moon_illumination")
        self.assertEqual(survivors[0].lag, 0)
        self.assertLess(survivors[0].q_value, 0.001)

    def test_controls_are_flagged_and_never_survive(self):
        history = simulate_draws(400, seed=31)
        report = search(history, lags=(0,))
        controls = report.controls()
        self.assertTrue(controls)
        self.assertTrue(all(c.is_control for c in controls))
        self.assertTrue(all(c.q_value > 0.05 for c in controls))

    def test_q_values_never_below_raw_p_values(self):
        report = search(simulate_draws(200, seed=41), lags=(0,))
        for result in report.results:
            self.assertGreaterEqual(result.q_value, result.p_value - 1e-12)
            self.assertGreaterEqual(result.bonferroni_p, result.p_value - 1e-12)

    def test_min_samples_filters_short_histories(self):
        report = search(simulate_draws(20, seed=2), lags=(0,), min_samples=30)
        self.assertEqual(report.n_tests, 0)
        self.assertIn("Nothing survives", report.summary())

    def test_unknown_method_is_rejected(self):
        with self.assertRaises(KeyError):
            search(simulate_draws(50, seed=2), methods=("telepathy",))

    def test_report_csv_export(self):
        report = search(simulate_draws(120, seed=6), lags=(0,))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "results.csv")
            report.to_csv(path)
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        self.assertEqual(len(lines), report.n_tests + 1)
        self.assertIn("q_value", lines[0])

    def test_summary_reports_the_noise_baseline(self):
        report = search(simulate_draws(150, seed=8), lags=(0,))
        summary = report.summary()
        self.assertIn("Hypotheses tested", summary)
        self.assertIn("pure noise would give", summary)
        self.assertIn("Control-metric floor", summary)


class TestCalibration(unittest.TestCase):
    def test_null_runs_produce_few_survivors(self):
        history = simulate_draws(250, seed=13)
        calibration = null_calibration(
            history, default_metrics(("moon_illumination", "daylight_hours",
                                      "pure_noise", "coin_flip")),
            runs=5, lags=(0,), seed=100)
        self.assertEqual(calibration.runs, 5)
        self.assertLess(calibration.mean_survivors, 1.0)
        self.assertLessEqual(calibration.p_value_for(1000), 1.0)
        self.assertIn("Null calibration", calibration.summary())


if __name__ == "__main__":
    unittest.main(verbosity=2)
