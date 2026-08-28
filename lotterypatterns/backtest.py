"""Walk-forward testing: does a strategy actually predict draws it has not seen?

This is the part that decides whether any of the rest is worth anything. A
pattern found in past draws is a hypothesis, not a result. The only honest way
to judge it is to replay history: stand at draw N knowing only draws 1..N-1,
make a pick, then score it against what actually came out — and repeat all the
way to the present.

Under fair draws every strategy scores the same, because every combination is
equally likely. The expected number of matches per line is picks x picks / pool
— 0.61 for Lotto — no matter how the numbers were chosen. If a strategy really
had an edge, this is where it would appear as a mean above that line, and the
z-test here would find it.

Use it on your own ideas as well as the built-in ones. That is what it is for.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .draws import DrawHistory

# A strategy sees only the draws before the one being predicted, and returns a
# line of the same shape.
Strategy = Callable[[DrawHistory, int], Sequence[int]]


@dataclass
class BacktestResult:
    """How a strategy did against draws it had never seen."""

    name: str
    predictions: int
    picks: int
    pool: int
    matches: list[int] = field(default_factory=list)
    tiers: Counter = field(default_factory=Counter)

    @property
    def expected_per_line(self) -> float:
        """Matches per line under chance — the same for every strategy."""
        return self.picks * self.picks / self.pool

    @property
    def observed_per_line(self) -> float:
        return statistics.fmean(self.matches) if self.matches else 0.0

    @property
    def z_score(self) -> float:
        """How far the observed rate sits from chance, in standard errors."""
        if not self.matches:
            return 0.0
        p = self.picks / self.pool
        variance = self.picks * p * (1 - p)
        sd = math.sqrt(variance / len(self.matches))
        return (self.observed_per_line - self.expected_per_line) / sd if sd else 0.0

    @property
    def p_value(self) -> float:
        from .stats import normal_sf
        return normal_sf(self.z_score)

    q_value: float = 1.0

    @property
    def edge_pct(self) -> float:
        if self.expected_per_line == 0:
            return 0.0
        return (self.observed_per_line / self.expected_per_line - 1.0) * 100.0

    def row(self) -> str:
        return (f"{self.name:<24} {self.observed_per_line:6.4f} "
                f"{self.expected_per_line:9.4f} {self.edge_pct:+8.2f}% "
                f"{self.z_score:+7.2f} {self.p_value:9.4g} {self.q_value:9.4g}")

    @property
    def beat_chance(self) -> bool:
        """Corrected across every strategy tried, not just this one."""
        return self.q_value <= 0.05 and self.z_score > 0


@dataclass
class BacktestReport:
    """Every strategy tried, against the same held-out draws."""

    results: list[BacktestResult]
    predictions: int
    trained_on: int
    game: str = "lottery"

    def best(self) -> BacktestResult | None:
        return max(self.results, key=lambda r: r.observed_per_line, default=None)

    def summary(self) -> str:
        lines = [
            f"Walk-forward test — {self.game}",
            "=" * 74,
            f"Each strategy predicted {self.predictions:,} draws it had not seen, "
            f"starting from a history of {self.trained_on:,}.",
            "",
            f"{'strategy':<24} {'actual':>6} {'by chance':>9} {'edge':>9} "
            f"{'z':>7} {'p':>9} {'q':>9}",
            "-" * 84,
        ]
        for result in sorted(self.results, key=lambda r: -r.observed_per_line):
            lines.append(result.row())
        lines.append("")

        winners = [r for r in self.results if r.beat_chance]
        nearly = [r for r in self.results
                  if r.p_value < 0.05 and r.z_score > 0 and not r.beat_chance]
        if winners:
            lines.append("BEAT CHANCE: " + ", ".join(r.name for r in winners))
            lines.append("Survives correction for having tried "
                         f"{len(self.results)} strategies. Confirm it on later "
                         "draws before staking anything on it.")
        else:
            lines.append("None of them beat chance.")
            if nearly:
                lines.append(
                    "Looked like it at first glance: "
                    + ", ".join(f"{r.name} ({r.edge_pct:+.1f}%, p={r.p_value:.3f})"
                                for r in nearly)
                    + f" — but {len(self.results)} strategies were tried, and after "
                    "correcting for that (the q column) it is noise.")
            else:
                lines.append("Every strategy landed on the rate that any random line "
                             "gets, which is what fair draws produce.")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Strategies to test
# --------------------------------------------------------------------------

def random_strategy(seed: int = 0) -> Strategy:
    """The baseline. Everything else has to beat this, and nothing does."""
    rng = random.Random(seed)

    def pick(history: DrawHistory, picks: int) -> Sequence[int]:
        return rng.sample(range(1, history.pool + 1), picks)
    return pick


def hot_strategy(window: int = 100) -> Strategy:
    """The most common folk method: play whatever has come up most lately."""
    def pick(history: DrawHistory, picks: int) -> Sequence[int]:
        counts: Counter[int] = Counter()
        for draw in list(history)[-window:]:
            counts.update(draw.numbers)
        ranked = [n for n, _ in counts.most_common()]
        ranked += [n for n in range(1, history.pool + 1) if n not in counts]
        return ranked[:picks]
    return pick


def cold_strategy(window: int = 100) -> Strategy:
    """The other folk method: play whatever is 'due' because it has not shown."""
    def pick(history: DrawHistory, picks: int) -> Sequence[int]:
        counts: Counter[int] = Counter()
        for draw in list(history)[-window:]:
            counts.update(draw.numbers)
        return sorted(range(1, history.pool + 1),
                      key=lambda n: counts.get(n, 0))[:picks]
    return pick


def overdue_strategy() -> Strategy:
    """Play the numbers that have gone longest without appearing."""
    def pick(history: DrawHistory, picks: int) -> Sequence[int]:
        last: dict[int, int] = {}
        for index, draw in enumerate(history):
            for number in draw.numbers:
                last[number] = index
        return sorted(range(1, history.pool + 1),
                      key=lambda n: last.get(n, -1))[:picks]
    return pick


def bias_weighted_strategy(alpha: float = 0.05) -> Strategy:
    """Play the balls the evenness test says are genuinely over-represented.

    On a fair machine this finds nothing and falls back to the balls that
    happen to lead, which is exactly why it scores like every other strategy.
    """
    from .bias import analyse_main_balls

    def pick(history: DrawHistory, picks: int) -> Sequence[int]:
        report = analyse_main_balls(history, alpha=alpha)
        if report.is_biased:
            chosen = [b.number for b in report.biased_balls if b.excess > 0][:picks]
            if len(chosen) == picks:
                return chosen
        else:
            chosen = []
        for ball in report.hottest:
            if len(chosen) == picks:
                break
            if ball.number not in chosen:
                chosen.append(ball.number)
        return chosen
    return pick


def pair_strategy(window: int = 400) -> Strategy:
    """Build a line out of the pairs that have appeared together most often."""
    def pick(history: DrawHistory, picks: int) -> Sequence[int]:
        counts: Counter[tuple[int, int]] = Counter()
        for draw in list(history)[-window:]:
            ordered = draw.sorted_numbers
            for i, a in enumerate(ordered):
                for b in ordered[i + 1:]:
                    counts[(a, b)] += 1
        chosen: list[int] = []
        for (a, b), _ in counts.most_common():
            for number in (a, b):
                if number not in chosen:
                    chosen.append(number)
                if len(chosen) == picks:
                    return chosen
        while len(chosen) < picks:
            for n in range(1, history.pool + 1):
                if n not in chosen:
                    chosen.append(n)
                    break
        return chosen
    return pick


def unpopular_strategy(seed: int = 0) -> Strategy:
    """The one this package recommends — and it does not beat chance either.

    It is not supposed to. It aims at a bigger share of a jackpot, not a better
    chance of winning one, and this test measures only the latter. Including it
    keeps that distinction honest and visible.
    """
    from .games import LOTTO
    from .picker import share_index
    rng = random.Random(seed)

    def pick(history: DrawHistory, picks: int) -> Sequence[int]:
        best, best_index = None, float("inf")
        for _ in range(300):
            line = tuple(sorted(rng.sample(range(1, history.pool + 1), picks)))
            index = share_index(line, LOTTO)
            if index < best_index:
                best, best_index = line, index
        return list(best or [])
    return pick


DEFAULT_STRATEGIES: dict[str, Strategy] = {}


def default_strategies(seed: int = 0) -> dict[str, Strategy]:
    return {
        "random (baseline)": random_strategy(seed),
        "hot numbers": hot_strategy(),
        "cold numbers": cold_strategy(),
        "overdue numbers": overdue_strategy(),
        "bias-weighted": bias_weighted_strategy(),
        "frequent pairs": pair_strategy(),
        "unpopular (ours)": unpopular_strategy(seed),
    }


# --------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------

def backtest(history: DrawHistory, strategies: dict[str, Strategy] | None = None, *,
             train: int | None = None, step: int = 1,
             max_predictions: int = 400) -> BacktestReport:
    """Replay history, predicting each draw from only what came before it."""
    strategies = strategies or default_strategies()
    total = len(history)
    train = train if train is not None else max(200, total // 2)
    if total - train < 20:
        raise ValueError(
            f"Not enough draws to test: {total} in total, and {train} are needed "
            "to train on. Use a longer history or a smaller --train."
        )

    indexes = list(range(train, total, step))
    if len(indexes) > max_predictions:
        stride = math.ceil(len(indexes) / max_predictions)
        indexes = indexes[::stride]

    results = {name: BacktestResult(name=name, predictions=0, picks=history.picks,
                                    pool=history.pool)
               for name in strategies}

    for index in indexes:
        past = history[:index]
        actual = set(history[index].numbers)
        for name, strategy in strategies.items():
            line = list(strategy(past, history.picks))[:history.picks]
            hits = len(actual & set(line))
            result = results[name]
            result.matches.append(hits)
            result.tiers[hits] += 1
            result.predictions += 1

    # Correct across the strategies tried: with seven of them, one landing at
    # p < 0.05 is the expected outcome of trying seven, not a discovery.
    from .stats import benjamini_hochberg
    ordered = list(results.values())
    for result, q in zip(ordered, benjamini_hochberg([r.p_value for r in ordered])):
        result.q_value = q
    return BacktestReport(results=ordered, predictions=len(indexes),
                          trained_on=train, game=history.name)
