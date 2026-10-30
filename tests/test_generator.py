"""Tests for the generator hunt.

As with every analysis here it must work both ways: stay quiet on a competent
generator, and fire on weak ones whose algorithm is known.
"""

from __future__ import annotations

import cmath
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lotterypatterns import simulate_draws  # noqa: E402
from lotterypatterns.generator import (  # noqa: E402
    GENERATORS, _fft, bit_streams, duplicate_draws, expected_linear_complexity,
    hunt, linear_complexity, linear_complexity_p, plant, spectral_peak, summary,
)


class TestLinearComplexity(unittest.TestCase):
    def test_known_sequences(self):
        self.assertEqual(linear_complexity([1] * 20), 1)
        self.assertEqual(linear_complexity([0, 0, 0, 1]), 4)
        self.assertEqual(linear_complexity([0] * 10), 0)

    def test_a_four_stage_shift_register_has_complexity_four(self):
        s = [1, 0, 0, 1]
        for _ in range(300):
            s.append(s[-1] ^ s[-4])
        self.assertEqual(linear_complexity(s), 4)

    def test_random_bits_need_about_half_their_length(self):
        rng = random.Random(1)
        values = [linear_complexity([rng.getrandbits(1) for _ in range(1000)])
                  for _ in range(20)]
        self.assertAlmostEqual(sum(values) / 20, expected_linear_complexity(1000),
                               delta=1.0)

    def test_exact_lower_tail_matches_simulation(self):
        rng = random.Random(2)
        for n in (200, 201):
            obs = [linear_complexity([rng.getrandbits(1) for _ in range(n)])
                   for _ in range(2500)]
            for m in (1, 2):
                sim = sum(1 for v in obs if v <= n // 2 - m) / len(obs)
                self.assertAlmostEqual(sim, linear_complexity_p(n, n // 2 - m),
                                       delta=0.025)

    def test_p_value_is_a_proper_cumulative_probability(self):
        for n in (100, 101):
            ps = [linear_complexity_p(n, n // 2 + d) for d in range(-6, 8)]
            self.assertTrue(all(a <= b for a, b in zip(ps, ps[1:])))
            self.assertTrue(all(0.0 < p <= 1.0 for p in ps))
            self.assertGreater(ps[-1], 0.99)


class TestSpectrum(unittest.TestCase):
    def test_fft_matches_the_direct_transform(self):
        rng = random.Random(3)
        x = [complex(rng.random()) for _ in range(32)]
        direct = [sum(x[t] * cmath.exp(-2j * cmath.pi * k * t / 32) for t in range(32))
                  for k in range(32)]
        self.assertTrue(all(abs(a - b) < 1e-9 for a, b in zip(direct, _fft(x))))

    def test_a_planted_rhythm_is_found_at_the_right_period(self):
        rng = random.Random(4)
        series = [rng.gauss(0, 1) + 1.5 * math.sin(2 * math.pi * t / 64)
                  for t in range(2048)]
        _g, period, p = spectral_peak(series)
        self.assertEqual(period, 64)
        self.assertLess(p, 1e-6)

    def test_white_noise_has_no_significant_peak(self):
        rng = random.Random(5)
        _g, _period, p = spectral_peak([rng.gauss(0, 1) for _ in range(2048)])
        self.assertGreater(p, 0.01)

    def test_a_constant_series_is_handled(self):
        self.assertEqual(spectral_peak([3.0] * 64)[2], 1.0)


class TestStreams(unittest.TestCase):
    def test_no_two_streams_are_identical(self):
        """Sum parity equals odd-ball-count parity, so offering both double-counts."""
        streams = list(bit_streams(simulate_draws(300, pool=49, picks=6, seed=1)).values())
        for i in range(len(streams)):
            for j in range(i + 1, len(streams)):
                self.assertNotEqual(streams[i], streams[j])


class TestDuplicates(unittest.TestCase):
    def test_expected_count_follows_the_combinatorics(self):
        h = simulate_draws(1000, pool=49, picks=6, seed=2)
        _obs, expected, _p = duplicate_draws(h)
        self.assertAlmostEqual(expected, 1000 * 999 / 2 / math.comb(49, 6), places=9)


class TestHunt(unittest.TestCase):
    def test_a_toy_generator_is_found(self):
        flagged = [c for c in hunt(plant("toy LCG (4,096 states)", 3000)) if c.flagged]
        self.assertTrue(flagged)
        self.assertIn("repeated draws", [c.name for c in flagged])

    def test_a_small_shift_register_is_found(self):
        self.assertTrue(any(c.flagged for c in hunt(plant("16-bit shift register", 4000))))

    def test_a_competent_generator_is_not_flagged(self):
        flagged = sum(1 for s in range(40)
                      if any(c.flagged for c in hunt(plant("Mersenne Twister", 2000,
                                                           seed=900 + s))))
        self.assertLessEqual(flagged, 5)        # well inside the 5% ceiling

    def test_the_summary_is_honest_about_what_a_clean_result_means(self):
        h = plant("Mersenne Twister", 1500, seed=3)
        text = summary(h, hunt(h))
        self.assertIn("does not rule out a competent generator", text)

    def test_every_planted_generator_is_known(self):
        for name in GENERATORS:
            self.assertEqual(len(plant(name, 20)), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
