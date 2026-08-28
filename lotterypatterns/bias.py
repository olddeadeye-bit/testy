"""Is the machine actually fair? The one analysis that could make a number 'due'.

Everything else in this package tests draws against outside metrics. This tests
the draws against themselves: if a ball set is worn, a machine is off balance,
or a game's numbers are not being drawn evenly, the balls will come up at
different rates and a goodness-of-fit test will see it.

That is the only mechanism by which some numbers really could be more likely
than others, and it is worth checking properly — real lotteries have retired
ball sets over exactly this. The honest answer is almost always "no evidence",
and this module is built to say that clearly rather than to find something.
"""

from __future__ import annotations

from dataclasses import dataclass

from .draws import DrawHistory
from .games import Game
from .stats import benjamini_hochberg, binomial_z_test, chi_square_uniform


@dataclass(frozen=True)
class BallStat:
    """How often one ball came up, against how often it should have."""

    number: int
    observed: int
    expected: float
    z: float
    p_value: float
    q_value: float

    @property
    def excess(self) -> float:
        """Observed minus expected, as a percentage of expected."""
        return (self.observed - self.expected) / self.expected * 100.0

    def __str__(self) -> str:
        return (f"ball {self.number:2d}: {self.observed} drawn vs "
                f"{self.expected:.1f} expected ({self.excess:+.1f}%), q={self.q_value:.3g}")


@dataclass
class BiasReport:
    """The verdict on whether a barrel draws evenly."""

    barrel: str
    draws: int
    pool: int
    picks: int
    balls: list[BallStat]
    chi_square: float
    chi_square_p: float
    alpha: float = 0.05

    @property
    def biased_balls(self) -> list[BallStat]:
        """Balls whose rate survives correction for having tested every ball."""
        return sorted((b for b in self.balls if b.q_value <= self.alpha),
                      key=lambda b: b.q_value)

    @property
    def is_biased(self) -> bool:
        return self.chi_square_p <= self.alpha or bool(self.biased_balls)

    @property
    def hottest(self) -> list[BallStat]:
        return sorted(self.balls, key=lambda b: -b.observed)

    @property
    def coldest(self) -> list[BallStat]:
        return sorted(self.balls, key=lambda b: b.observed)

    def summary(self) -> str:
        lines = [
            f"{self.barrel}: {self.draws} draws, {self.picks} of {self.pool} per draw",
            f"  Evenness test:  chi-square = {self.chi_square:.1f} "
            f"on {self.pool - 1} df, p = {self.chi_square_p:.4g}",
        ]
        if self.is_biased:
            lines.append("  VERDICT: the balls are NOT coming up evenly.")
            for ball in self.biased_balls[:10]:
                lines.append(f"    {ball}")
            lines.append("  Worth a second look — but confirm it on draws that were "
                         "not part of this test before acting on it.")
        else:
            lines.append("  VERDICT: no evidence of bias. The balls are coming up "
                         "as evenly as chance predicts.")
            lines.append("  So no number is 'due', 'hot' or 'cold' — those labels "
                         "describe noise.")
            spread = self.hottest[0], self.coldest[0]
            lines.append(f"  For reference, most drawn was ball {spread[0].number} "
                         f"({spread[0].observed}) and least was ball "
                         f"{spread[1].number} ({spread[1].observed}); a gap that "
                         "size is normal.")
        return "\n".join(lines)


def _analyse(counts: list[int], pool: int, picks: int, draws: int,
             barrel: str, alpha: float) -> BiasReport:
    probability = picks / pool
    trials = draws
    expected = draws * probability
    tests = [binomial_z_test(counts[n - 1], trials, probability)
             for n in range(1, pool + 1)]
    q_values = benjamini_hochberg([t.p_value for t in tests])
    balls = [
        BallStat(number=n, observed=counts[n - 1], expected=expected,
                 z=tests[n - 1].statistic, p_value=tests[n - 1].p_value,
                 q_value=q_values[n - 1])
        for n in range(1, pool + 1)
    ]
    overall = chi_square_uniform(counts)
    return BiasReport(barrel=barrel, draws=draws, pool=pool, picks=picks,
                      balls=balls, chi_square=overall.statistic,
                      chi_square_p=overall.p_value, alpha=alpha)


def analyse_main_balls(history: DrawHistory, *, alpha: float = 0.05) -> BiasReport:
    """Test the main barrel for uneven draw rates."""
    counts = [0] * history.pool
    for draw in history:
        for number in draw.numbers:
            counts[number - 1] += 1
    return _analyse(counts, history.pool, history.picks, len(history),
                    "Main barrel", alpha)


def analyse_bonus_balls(history: DrawHistory, game: Game, *,
                        alpha: float = 0.05) -> BiasReport | None:
    """Test a second barrel — the Thunderball, the Lucky Stars — if there is one."""
    if game.bonus_pool <= 0:
        return None
    counts = [0] * game.bonus_pool
    used = 0
    for draw in history:
        for number in draw.bonus:
            if 1 <= number <= game.bonus_pool:
                counts[number - 1] += 1
                used += 1
    if used == 0:
        return None
    return _analyse(counts, game.bonus_pool, game.bonus_picks, len(history),
                    f"{game.bonus_name} barrel", alpha)
