"""Tests for the power analysis: what size of bias a given archive could reveal."""

from __future__ import annotations

import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lotterypatterns.power import (  # noqa: E402
    _cdf, _z_for_two_sided, ball_power, draws_needed, minimum_detectable_lift,
    power_report,
)


class TestPrimitives(unittest.TestCase):
    def test_critical_values_match_the_textbook(self):
        self.assertAlmostEqual(_z_for_two_sided(0.05), 1.9600, places=3)
        self.assertAlmostEqual(_z_for_two_sided(0.01), 2.5758, places=3)

    def test_normal_cdf(self):
        self.assertAlmostEqual(_cdf(0.0), 0.5, places=9)
        self.assertAlmostEqual(_cdf(1.96), 0.975, places=3)
        self.assertAlmostEqual(_cdf(-1.96), 0.025, places=3)

    def test_with_no_effect_power_equals_the_false_alarm_rate(self):
        self.assertAlmostEqual(ball_power(3000, 59, 6, 1.0), 0.05 / 59, places=5)


class TestPowerBehaviour(unittest.TestCase):
    def test_power_rises_with_effect_size_and_with_draws(self):
        weak = ball_power(3000, 49, 6, 1.10)
        strong = ball_power(3000, 49, 6, 1.30)
        self.assertLess(weak, strong)
        self.assertLess(ball_power(1000, 49, 6, 1.2), ball_power(5000, 49, 6, 1.2))

    def test_more_draws_shrink_the_smallest_bias_that_can_be_caught(self):
        small = minimum_detectable_lift(500, 59, 6)
        large = minimum_detectable_lift(5000, 59, 6)
        self.assertGreater(small, large)

    def test_the_minimum_really_gives_the_requested_power(self):
        lift = minimum_detectable_lift(3000, 49, 6, power=0.8)
        self.assertAlmostEqual(ball_power(3000, 49, 6, lift), 0.8, places=3)

    def test_draws_needed_round_trips(self):
        n = draws_needed(49, 6, 1.2, power=0.8)
        self.assertGreaterEqual(ball_power(n, 49, 6, 1.2), 0.8)
        self.assertLess(ball_power(n - 1, 49, 6, 1.2), 0.8)

    def test_too_few_draws_returns_none_not_a_made_up_number(self):
        """With 3 draws the formula once claimed it could catch a ball 8x too
        common; the real chance was about 61%. It must decline instead."""
        self.assertIsNone(minimum_detectable_lift(3, 59, 6))
        self.assertIsNone(minimum_detectable_lift(40, 59, 6))   # 4 expected each
        self.assertIsNotNone(minimum_detectable_lift(200, 59, 6))

    def test_bad_inputs_are_refused(self):
        with self.assertRaises(ValueError):
            draws_needed(49, 6, 0.9)
        with self.assertRaises(ValueError):
            _z_for_two_sided(1.5)


class TestAgainstSimulation(unittest.TestCase):
    def test_the_formula_matches_a_real_simulation(self):
        """Ball 1's count is Binomial(N, p1); simulate it and compare."""
        draws, pool, picks, lift = 3000, 49, 6, 1.20
        rng = random.Random(7)
        p0 = picks / pool
        p1 = p0 * lift
        sd0 = math.sqrt(draws * p0 * (1 - p0))
        zc = _z_for_two_sided(0.05 / pool)
        hits = sum(
            1 for _ in range(1500)
            if abs(sum(1 for _ in range(draws) if rng.random() < p1) - draws * p0)
            / sd0 >= zc)
        self.assertAlmostEqual(hits / 1500, ball_power(draws, pool, picks, lift),
                               delta=0.05)


class TestReport(unittest.TestCase):
    def test_the_summary_is_plain_english(self):
        text = power_report(5055, 49, 6, "German Lotto").summary()
        self.assertIn("rigged", text)
        self.assertIn("8 times out of 10", text)
        self.assertIn("could still be hiding", text)
        self.assertNotIn("chi-square", text)

    def test_real_archive_sizes_give_the_expected_ordering(self):
        german = power_report(5055, 49, 6).mdl_80
        euro = power_report(1983, 50, 5).mdl_80
        self.assertLess(german, euro)


if __name__ == "__main__":
    unittest.main(verbosity=2)
