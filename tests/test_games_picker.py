"""Tests for the games, the ball-bias test, the picker and the weather loader."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lotterypatterns import simulate_draws  # noqa: E402
from lotterypatterns.bias import analyse_bonus_balls, analyse_main_balls  # noqa: E402
from lotterypatterns.draws import Draw, DrawHistory  # noqa: E402
from lotterypatterns.fetch import FetchError, load_history  # noqa: E402
from lotterypatterns.games import (  # noqa: E402
    EUROMILLIONS, GAMES, LOTTO, SET_FOR_LIFE, THUNDERBALL, get_game,
)
from lotterypatterns.picker import Ticket, share_index, suggest  # noqa: E402
from lotterypatterns.weather import (  # noqa: E402
    WeatherError, climatology_metrics, weather_metrics,
)

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "data", "sample_draws.csv")


class TestGames(unittest.TestCase):
    def test_odds_match_the_published_figures(self):
        self.assertEqual(LOTTO.jackpot_odds, 45_057_474)
        self.assertEqual(THUNDERBALL.jackpot_odds, 8_060_598)
        self.assertEqual(EUROMILLIONS.jackpot_odds, 139_838_160)
        self.assertEqual(SET_FOR_LIFE.jackpot_odds, 15_339_390)

    def test_lookup_accepts_the_names_people_use(self):
        for alias in ("lotto", "Lotto", "national lottery", "UK-Lotto"):
            self.assertIs(get_game(alias), LOTTO)
        self.assertIs(get_game("thunder"), THUNDERBALL)
        self.assertIs(get_game("euro"), EUROMILLIONS)

    def test_unknown_game_is_refused(self):
        with self.assertRaises(KeyError):
            get_game("scratchcards")

    def test_every_game_declares_its_columns(self):
        for game in GAMES.values():
            self.assertEqual(len(game.number_columns), game.picks)
            self.assertTrue(game.history_url.startswith("https://"))
            if game.bonus_picks:
                self.assertEqual(len(game.bonus_columns), game.bonus_picks)

    def test_ball_set_column_is_never_mistaken_for_a_ball(self):
        for game in GAMES.values():
            self.assertNotIn("Ball Set", game.number_columns)


class TestBallBias(unittest.TestCase):
    def test_fair_draws_show_no_bias(self):
        report = analyse_main_balls(simulate_draws(3000, pool=59, picks=6, seed=21))
        self.assertFalse(report.is_biased)
        self.assertGreater(report.chi_square_p, 0.01)
        self.assertEqual(report.biased_balls, [])
        self.assertIn("no evidence of bias", report.summary())

    def test_a_genuinely_loaded_ball_is_caught(self):
        # Force ball 17 into a fifth of all draws — a machine this broken
        # would have been retired, and the test must see it.
        import random
        rng = random.Random(5)
        draws = []
        for i in range(2000):
            numbers = set()
            if i % 5 == 0:
                numbers.add(17)
            while len(numbers) < 6:
                numbers.add(rng.randint(1, 59))
            draws.append(Draw(date(2010, 1, 1).replace(day=1 + i % 28,
                                                       month=1 + i % 12), tuple(numbers)))
        history = DrawHistory(draws, pool=59, picks=6)
        report = analyse_main_balls(history)
        self.assertTrue(report.is_biased)
        self.assertIn(17, [b.number for b in report.biased_balls])
        self.assertIn("NOT coming up evenly", report.summary())

    def test_excess_is_reported_as_a_percentage(self):
        report = analyse_main_balls(simulate_draws(1500, pool=59, picks=6, seed=8))
        for ball in report.balls:
            self.assertAlmostEqual(
                ball.excess, (ball.observed - ball.expected) / ball.expected * 100.0)

    def test_no_second_barrel_returns_none(self):
        history = simulate_draws(300, pool=59, picks=6, seed=2)
        self.assertIsNone(analyse_bonus_balls(history, LOTTO))

    def test_second_barrel_is_analysed_when_present(self):
        import random
        rng = random.Random(3)
        draws = [
            Draw(date(2020, 1, 1).replace(day=1 + i % 28, month=1 + i % 12),
                 tuple(rng.sample(range(1, 40), 5)),
                 (rng.randint(1, 14),))
            for i in range(800)
        ]
        history = DrawHistory(draws, pool=39, picks=5)
        report = analyse_bonus_balls(history, THUNDERBALL)
        self.assertIsNotNone(report)
        self.assertEqual(report.pool, 14)
        self.assertFalse(report.is_biased)


class TestPopularityModel(unittest.TestCase):
    def test_over_played_shapes_score_above_an_ordinary_line(self):
        consecutive = share_index((1, 2, 3, 4, 5, 6), LOTTO)
        birthdays = share_index((3, 8, 12, 17, 22, 29), LOTTO)
        mixed = share_index((5, 23, 31, 44, 49, 57), LOTTO)
        high = share_index((34, 41, 45, 52, 56, 58), LOTTO)
        self.assertGreater(consecutive, birthdays)
        self.assertGreater(birthdays, mixed)
        self.assertGreater(mixed, high)

    def test_an_even_spacing_pattern_is_penalised(self):
        self.assertGreater(share_index((7, 14, 21, 28, 35, 42), LOTTO),
                           share_index((7, 15, 23, 29, 38, 44), LOTTO))

    def test_numbers_above_thirty_one_are_less_played(self):
        self.assertGreater(share_index((2, 5, 9, 14, 20, 27), LOTTO),
                           share_index((35, 39, 44, 48, 53, 57), LOTTO))

    def test_seven_is_the_most_played_single_number(self):
        from lotterypatterns.picker import _base_popularity
        self.assertEqual(max(range(1, 60), key=_base_popularity), 7)


class TestPicker(unittest.TestCase):
    def test_returns_the_requested_number_of_valid_lines(self):
        result = suggest(LOTTO, count=5, draws_analysed=1000, seed=1)
        self.assertEqual(len(result.tickets), 5)
        for ticket in result.tickets:
            self.assertEqual(len(ticket.numbers), 6)
            self.assertEqual(len(set(ticket.numbers)), 6)
            self.assertTrue(all(1 <= n <= 59 for n in ticket.numbers))
            self.assertEqual(list(ticket.numbers), sorted(ticket.numbers))

    def test_lines_are_distinct(self):
        result = suggest(LOTTO, count=10, draws_analysed=1000, seed=2)
        self.assertEqual(len({t.numbers for t in result.tickets}), 10)

    def test_different_seeds_give_different_lines(self):
        first = suggest(LOTTO, count=3, seed=1).tickets[0].numbers
        second = suggest(LOTTO, count=3, seed=2).tickets[0].numbers
        self.assertNotEqual(first, second)

    def test_suggested_lines_beat_an_average_ticket_on_sharing(self):
        result = suggest(LOTTO, count=5, draws_analysed=1000, seed=4)
        self.assertGreater(result.improvement_pct, 20.0)
        for ticket in result.tickets:
            self.assertLess(ticket.share_index, result.average_share_index)

    def test_thunderball_gets_a_bonus_ball_in_range(self):
        result = suggest(THUNDERBALL, count=4, seed=6)
        for ticket in result.tickets:
            self.assertEqual(len(ticket.numbers), 5)
            self.assertEqual(len(ticket.bonus), 1)
            self.assertTrue(1 <= ticket.bonus[0] <= 14)

    def test_euromillions_gets_two_distinct_lucky_stars(self):
        result = suggest(EUROMILLIONS, count=3, seed=7)
        for ticket in result.tickets:
            self.assertEqual(len(ticket.bonus), 2)
            self.assertEqual(len(set(ticket.bonus)), 2)
            self.assertTrue(all(1 <= b <= 12 for b in ticket.bonus))

    def test_fixed_prize_games_are_told_sharing_does_not_apply(self):
        thunderball = suggest(THUNDERBALL, count=2, seed=8)
        self.assertFalse(thunderball.shared_jackpot)
        self.assertIn("not a factor", thunderball.summary())
        lotto = suggest(LOTTO, count=2, seed=8)
        self.assertTrue(lotto.shared_jackpot)
        self.assertIn("less jackpot-sharing", lotto.summary())

    def test_the_summary_never_overstates_the_odds(self):
        summary = suggest(LOTTO, count=3, draws_analysed=500, seed=9).summary()
        self.assertIn("1 in 45,057,474", summary)
        self.assertIn("do not change that", summary)
        self.assertIn("no number is any likelier", summary)

    def test_a_real_bias_tilts_the_picks_toward_the_biased_balls(self):
        import random
        rng = random.Random(12)
        draws = []
        for i in range(2500):
            numbers = {7, 23} if i % 3 == 0 else set()
            while len(numbers) < 6:
                numbers.add(rng.randint(1, 59))
            draws.append(Draw(date(2010, 1, 1).replace(day=1 + i % 28,
                                                       month=1 + i % 12), tuple(numbers)))
        history = DrawHistory(draws, pool=59, picks=6)
        report = analyse_main_balls(history)
        self.assertTrue(report.is_biased)
        result = suggest(LOTTO, count=8, bias_report=report,
                         draws_analysed=len(history), seed=3)
        self.assertTrue(result.bias_found)
        self.assertIn("NOT", result.summary().upper())
        appearances = sum(1 for t in result.tickets
                          if 7 in t.numbers or 23 in t.numbers)
        self.assertGreater(appearances, 0)

    def test_ticket_formats_with_and_without_a_bonus(self):
        plain = Ticket(numbers=(1, 2, 3, 4, 5, 6))
        self.assertNotIn("+", plain.format(LOTTO))
        with_bonus = Ticket(numbers=(1, 2, 3, 4, 5), bonus=(9,))
        self.assertIn("Thunderball", with_bonus.format(THUNDERBALL))


class TestArchiveLoading(unittest.TestCase):
    def test_missing_archive_explains_how_to_get_one(self):
        with self.assertRaises(FetchError) as ctx:
            load_history(LOTTO, "data/definitely_not_here.csv")
        self.assertIn("fetch --game lotto", str(ctx.exception))

    def test_falls_back_to_inferring_columns_for_other_layouts(self):
        history = load_history(LOTTO, SAMPLE)
        self.assertEqual(len(history), 520)
        self.assertEqual(history.picks, 6)

    def test_official_column_layout_is_used_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lotto.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("DrawDate,Ball 1,Ball 2,Ball 3,Ball 4,Ball 5,Ball 6,"
                             "Bonus Ball,Ball Set,Machine,DrawNumber\n")
                handle.write("05-Aug-2023,7,12,23,34,45,58,3,5,Arthur,2900\n")
                handle.write("02-Aug-2023,1,9,19,28,37,52,44,5,Lancelot,2899\n")
            history = load_history(LOTTO, path)
        self.assertEqual(len(history), 2)
        # "Ball Set" holds 5 — it must not have become a seventh ball.
        self.assertEqual(len(history[0].numbers), 6)
        self.assertEqual(history[1].sorted_numbers, (7, 12, 23, 34, 45, 58))
        self.assertEqual(history[1].bonus, (3,))

    def test_a_file_with_no_date_column_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("when,Ball 1\n2020-01-01,5\n")
            with self.assertRaises(FetchError) as ctx:
                load_history(LOTTO, path)
        self.assertIn("no 'DrawDate' or 'date' column", str(ctx.exception))


class TestWeather(unittest.TestCase):
    def test_climatology_is_seasonal_and_labelled_as_such(self):
        metrics = {m.name: m for m in climatology_metrics()}
        self.assertGreater(metrics["temperature_climatology"](date(2024, 7, 15)),
                           metrics["temperature_climatology"](date(2024, 1, 15)))
        self.assertGreater(metrics["pressure_climatology"](date(2024, 1, 15)),
                           metrics["pressure_climatology"](date(2024, 7, 15)))
        for name in ("pressure_climatology", "temperature_climatology"):
            self.assertIn("climatology", metrics[name].units)
            self.assertIn("average, not weather", metrics[name].description)

    def test_missing_weather_file_says_how_to_fetch_one(self):
        with self.assertRaises(WeatherError) as ctx:
            weather_metrics("data/no_weather_here.csv")
        self.assertIn("fetch --weather", str(ctx.exception))

    def test_metrics_are_built_from_a_fetched_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "weather.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("date,pressure_hpa,temperature_c\n")
                handle.write("2024-01-01,1013.2,4.5\n2024-01-02,1008.7,6.1\n")
            metrics = {m.name: m for m in weather_metrics(path)}
            self.assertEqual(set(metrics), {"pressure_hpa", "temperature_c"})
            self.assertEqual(metrics["pressure_hpa"](date(2024, 1, 1)), 1013.2)
            self.assertEqual(metrics["temperature_c"](date(2024, 1, 2)), 6.1)
            # Beyond the staleness window it declines to guess.
            self.assertIsNone(metrics["pressure_hpa"](date(2024, 2, 1)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
