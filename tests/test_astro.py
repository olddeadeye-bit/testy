"""Tests for the astronomy, checked against published positions.

Tolerances are loose enough to allow for the truncated series and for these
being computed at 00:00 UTC, but tight enough that a sign error, a wrong epoch
or a broken Kepler solve would fail.
"""

from __future__ import annotations

import math
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lotterypatterns import astro  # noqa: E402


class TestTimeScales(unittest.TestCase):
    def test_julian_day_reference_values(self):
        self.assertAlmostEqual(astro.julian_day(date(2000, 1, 1)), 2451544.5, places=6)
        self.assertAlmostEqual(astro.julian_day(date(1970, 1, 1)), 2440587.5, places=6)
        self.assertAlmostEqual(astro.julian_day(date(2000, 1, 1), 12.0), 2451545.0,
                               places=6)

    def test_julian_centuries_zero_at_j2000(self):
        self.assertAlmostEqual(astro.julian_centuries(date(2000, 1, 1)),
                               -0.5 / 36525.0, places=9)

    def test_julian_day_advances_by_one_per_day(self):
        a = astro.julian_day(date(2024, 2, 28))
        b = astro.julian_day(date(2024, 2, 29))  # leap day must exist
        self.assertAlmostEqual(b - a, 1.0, places=9)


class TestSun(unittest.TestCase):
    def test_longitude_at_j2000(self):
        # ~280.46 deg at J2000.0 noon, a little less at the preceding midnight.
        self.assertAlmostEqual(astro.sun_longitude(date(2000, 1, 1)), 279.96, delta=0.3)

    def test_obliquity_matches_the_accepted_value(self):
        self.assertAlmostEqual(astro.obliquity(date(2000, 1, 1)), 23.4393, places=3)

    def test_declination_at_the_solstices_and_equinoxes(self):
        self.assertAlmostEqual(astro.sun_declination(date(2024, 6, 20)), 23.44, delta=0.1)
        self.assertAlmostEqual(astro.sun_declination(date(2024, 12, 21)), -23.44,
                               delta=0.1)
        self.assertAlmostEqual(astro.sun_declination(date(2024, 3, 20)), 0.0, delta=0.5)

    def test_longitude_advances_about_a_degree_a_day(self):
        a = astro.sun_longitude(date(2024, 5, 1))
        b = astro.sun_longitude(date(2024, 5, 2))
        self.assertAlmostEqual(b - a, 0.9748, delta=0.02)

    def test_zodiac_signs_line_up_with_the_calendar(self):
        # The Sun enters Aries at the March equinox and Cancer at midsummer.
        self.assertEqual(astro.zodiac_index(astro.sun_longitude(date(2024, 3, 25))), 0)
        self.assertEqual(astro.zodiac_index(astro.sun_longitude(date(2024, 7, 1))), 3)


class TestMoon(unittest.TestCase):
    def test_illumination_at_known_new_and_full_moons(self):
        # New moon 2024-01-11, full moon 2024-01-25 (both UTC).
        self.assertLess(astro.moon_illuminated_fraction(date(2024, 1, 11)), 0.02)
        self.assertGreater(astro.moon_illuminated_fraction(date(2024, 1, 25)), 0.97)
        # And again in a different year, to catch an epoch that only fits once.
        self.assertLess(astro.moon_illuminated_fraction(date(2021, 6, 10)), 0.02)
        self.assertGreater(astro.moon_illuminated_fraction(date(2021, 6, 24)), 0.97)

    def test_phase_angle_tracks_illumination(self):
        for day in range(0, 29, 3):
            when = date(2024, 1, 11) + timedelta(days=day)
            expected = (1 - math.cos(astro.moon_phase_angle(when) * astro.RAD)) / 2
            self.assertAlmostEqual(astro.moon_illuminated_fraction(when), expected,
                                   places=9)

    def test_distance_stays_within_the_real_range(self):
        distances = [astro.moon_distance_km(date(2024, 1, 1) + timedelta(days=d))
                     for d in range(0, 400, 2)]
        self.assertGreater(min(distances), 355000)
        self.assertLess(max(distances), 408000)
        # Over a year it must sweep most of that range, not sit near the mean.
        self.assertGreater(max(distances) - min(distances), 40000)

    def test_declination_stays_inside_the_standstill_limits(self):
        for day in range(0, 366, 5):
            dec = astro.moon_declination(date(2024, 1, 1) + timedelta(days=day))
            self.assertLess(abs(dec), 29.0)

    def test_latitude_stays_within_five_and_a_bit_degrees(self):
        for day in range(0, 200, 3):
            lat = astro.moon_latitude(date(2024, 1, 1) + timedelta(days=day))
            self.assertLess(abs(lat), 5.5)

    def test_node_regresses_over_time(self):
        early = astro.lunar_node_longitude(date(2020, 1, 1))
        later = astro.lunar_node_longitude(date(2020, 7, 1))
        self.assertLess((later - early) % 360.0, 360.0)
        # A full circuit takes 18.6 years, so half a year is roughly 9.7 degrees back.
        self.assertAlmostEqual(((early - later) % 360.0), 9.7, delta=1.0)


class TestPlanets(unittest.TestCase):
    """Geocentric longitudes against published positions for 2024-01-01."""

    KNOWN = {"jupiter": 35.5, "saturn": 333.0, "mars": 267.0, "venus": 242.3,
             "mercury": 262.2}  # stationing direct at 22 deg Sagittarius

    def test_longitudes_match_published_positions(self):
        for planet, expected in self.KNOWN.items():
            with self.subTest(planet=planet):
                actual = astro.planet_longitude(planet, date(2024, 1, 1))
                difference = abs((actual - expected + 180) % 360 - 180)
                self.assertLess(difference, 1.0,
                                f"{planet}: got {actual:.2f}, expected ~{expected}")

    def test_unknown_planet_is_refused(self):
        with self.assertRaises(KeyError):
            astro.planet_longitude("vulcan", date(2024, 1, 1))

    def test_kepler_solver_inverts_the_equation(self):
        for ecc in (0.0, 0.05, 0.2, 0.6):
            for mean_anomaly in (0.0, 45.0, 179.0, 270.0):
                e = astro._solve_kepler(mean_anomaly, ecc)
                recovered = (e - ecc * math.sin(e)) / astro.RAD
                self.assertAlmostEqual(astro._norm(recovered),
                                       astro._norm(mean_anomaly), places=6)

    def test_outer_planets_move_slowly_and_inner_ones_quickly(self):
        def travel(planet):
            a = astro.planet_longitude(planet, date(2024, 1, 1))
            b = astro.planet_longitude(planet, date(2024, 4, 1))
            return abs((b - a + 180) % 360 - 180)
        self.assertGreater(travel("venus"), travel("saturn"))
        self.assertLess(travel("neptune"), 10.0)

    def test_mercury_retrograde_happens_a_few_times_a_year(self):
        days = [date(2024, 1, 1) + timedelta(days=d) for d in range(365)]
        retro = sum(astro.planet_is_retrograde("mercury", d) for d in days)
        # Mercury spends roughly 60 days a year retrograde, in three spells.
        self.assertGreater(retro, 40)
        self.assertLess(retro, 90)

    def test_venus_is_retrograde_far_less_often_than_mercury(self):
        days = [date(2024, 1, 1) + timedelta(days=d) for d in range(365)]
        self.assertLess(sum(astro.planet_is_retrograde("venus", d) for d in days),
                        sum(astro.planet_is_retrograde("mercury", d) for d in days))

    def test_elongation_is_bounded_and_small_for_mercury(self):
        for day in range(0, 365, 7):
            when = date(2024, 1, 1) + timedelta(days=day)
            self.assertLessEqual(astro.planet_elongation("mercury", when), 30.0)
            self.assertLessEqual(astro.planet_elongation("jupiter", when), 180.0)


class TestStars(unittest.TestCase):
    def test_sidereal_time_advances_by_about_a_degree_a_day(self):
        a = astro.greenwich_sidereal_time(date(2024, 1, 1))
        b = astro.greenwich_sidereal_time(date(2024, 1, 2))
        self.assertAlmostEqual((b - a) % 360.0, 0.9856, delta=0.01)

    def test_star_altitudes_stay_physical(self):
        for star in astro.BRIGHT_STARS:
            for day in range(0, 365, 30):
                altitude = astro.star_altitude(star, date(2024, 1, 1) + timedelta(days=day))
                self.assertGreaterEqual(altitude, -90.0)
                self.assertLessEqual(altitude, 90.0)

    def test_polaris_is_always_up_at_london_latitude(self):
        for day in range(0, 365, 15):
            altitude = astro.star_altitude("polaris", date(2024, 1, 1) + timedelta(days=day))
            self.assertAlmostEqual(altitude, astro.LONDON_LAT, delta=1.5)

    def test_a_southern_star_sinks_below_the_horizon(self):
        altitudes = [astro.star_altitude("antares", date(2024, 1, 1) + timedelta(days=d))
                     for d in range(0, 365, 5)]
        self.assertLess(min(altitudes), 0.0)
        self.assertGreater(max(altitudes), 0.0)

    def test_unknown_star_is_refused(self):
        with self.assertRaises(KeyError):
            astro.star_altitude("death star", date(2024, 1, 1))


class TestAngles(unittest.TestCase):
    def test_normalisation(self):
        self.assertAlmostEqual(astro._norm(370.0), 10.0)
        self.assertAlmostEqual(astro._norm(-10.0), 350.0)
        self.assertAlmostEqual(astro._norm180(350.0), -10.0)
        self.assertAlmostEqual(astro._norm180(190.0), -170.0)

    def test_zodiac_covers_twelve_signs(self):
        self.assertEqual(astro.zodiac_index(0.0), 0)
        self.assertEqual(astro.zodiac_index(359.9), 11)
        self.assertEqual(len(astro.ZODIAC), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
