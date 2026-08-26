"""Per-draw features: the left-hand side of every hypothesis we test.

A feature turns one draw into one number, so that a run of draws becomes a time
series that can be lined up against a metric. Features that need the previous
draw (carry-over, jump distance) return ``None`` for the first draw and are
dropped from the aligned pair.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Callable, Sequence

from .draws import Draw, DrawHistory

_PRIMES = {
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71,
    73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151,
}
_FIBS = {1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144}


def _digit_sum(n: int) -> int:
    return sum(int(c) for c in str(abs(n)))


@dataclass(frozen=True)
class Feature:
    """A named scalar summary of a draw."""

    name: str
    description: str
    fn: Callable[[Draw, Draw | None], float | None]
    needs_previous: bool = False

    def __call__(self, draw: Draw, previous: Draw | None = None) -> float | None:
        if self.needs_previous and previous is None:
            return None
        return self.fn(draw, previous)


def _f(name: str, description: str, *, needs_previous: bool = False):
    def register(fn: Callable[[Draw, Draw | None], float | None]) -> Feature:
        feature = Feature(name, description, fn, needs_previous)
        _REGISTRY.append(feature)
        return feature
    return register


_REGISTRY: list[Feature] = []


@_f("sum", "Sum of the main balls")
def sum_of_balls(draw: Draw, _prev: Draw | None) -> float:
    return float(sum(draw.numbers))


@_f("mean", "Mean of the main balls")
def mean_of_balls(draw: Draw, _prev: Draw | None) -> float:
    return statistics.fmean(draw.numbers)


@_f("spread", "Highest ball minus lowest ball")
def spread(draw: Draw, _prev: Draw | None) -> float:
    return float(max(draw.numbers) - min(draw.numbers))


@_f("stdev", "Standard deviation of the balls within the draw")
def stdev(draw: Draw, _prev: Draw | None) -> float | None:
    if len(draw.numbers) < 2:
        return None
    return statistics.pstdev(draw.numbers)


@_f("lowest", "Value of the lowest ball")
def lowest(draw: Draw, _prev: Draw | None) -> float:
    return float(min(draw.numbers))


@_f("highest", "Value of the highest ball")
def highest(draw: Draw, _prev: Draw | None) -> float:
    return float(max(draw.numbers))


@_f("odd_count", "How many balls are odd")
def odd_count(draw: Draw, _prev: Draw | None) -> float:
    return float(sum(1 for n in draw.numbers if n % 2))


@_f("prime_count", "How many balls are prime")
def prime_count(draw: Draw, _prev: Draw | None) -> float:
    return float(sum(1 for n in draw.numbers if n in _PRIMES))


@_f("fibonacci_count", "How many balls are Fibonacci numbers")
def fibonacci_count(draw: Draw, _prev: Draw | None) -> float:
    return float(sum(1 for n in draw.numbers if n in _FIBS))


@_f("multiple_of_seven", "How many balls divide by seven")
def multiple_of_seven(draw: Draw, _prev: Draw | None) -> float:
    return float(sum(1 for n in draw.numbers if n % 7 == 0))


@_f("contains_digit_seven", "How many balls contain the digit 7")
def contains_digit_seven(draw: Draw, _prev: Draw | None) -> float:
    return float(sum(1 for n in draw.numbers if "7" in str(n)))


@_f("digit_sum", "Sum of the decimal digits of every ball")
def digit_sum(draw: Draw, _prev: Draw | None) -> float:
    return float(sum(_digit_sum(n) for n in draw.numbers))


@_f("consecutive_pairs", "Count of adjacent pairs like (17, 18)")
def consecutive_pairs(draw: Draw, _prev: Draw | None) -> float:
    ordered = draw.sorted_numbers
    return float(sum(1 for a, b in zip(ordered, ordered[1:]) if b - a == 1))


@_f("max_gap", "Largest gap between neighbouring balls")
def max_gap(draw: Draw, _prev: Draw | None) -> float | None:
    ordered = draw.sorted_numbers
    if len(ordered) < 2:
        return None
    return float(max(b - a for a, b in zip(ordered, ordered[1:])))


@_f("decade_spread", "How many distinct decades (1-10, 11-20, ...) are covered")
def decade_spread(draw: Draw, _prev: Draw | None) -> float:
    return float(len({(n - 1) // 10 for n in draw.numbers}))


@_f("sum_mod_seven", "Sum of the balls modulo 7")
def sum_mod_seven(draw: Draw, _prev: Draw | None) -> float:
    return float(sum(draw.numbers) % 7)


@_f("carry_over", "Balls repeated from the previous draw", needs_previous=True)
def carry_over(draw: Draw, prev: Draw | None) -> float:
    assert prev is not None
    return float(len(set(draw.numbers) & set(prev.numbers)))


@_f("jump_distance", "Absolute change in ball-sum since the previous draw",
    needs_previous=True)
def jump_distance(draw: Draw, prev: Draw | None) -> float:
    assert prev is not None
    return float(abs(sum(draw.numbers) - sum(prev.numbers)))


@_f("centroid_shift", "Signed change in mean ball value since the previous draw",
    needs_previous=True)
def centroid_shift(draw: Draw, prev: Draw | None) -> float:
    assert prev is not None
    return statistics.fmean(draw.numbers) - statistics.fmean(prev.numbers)


@_f("balance", "Distance of the ball-mean from the centre of the pool, unsigned")
def balance(draw: Draw, _prev: Draw | None) -> float:
    return abs(statistics.fmean(draw.numbers) - 30.0)


@_f("entropy", "Shannon entropy of the balls' decade distribution, in bits")
def entropy(draw: Draw, _prev: Draw | None) -> float:
    counts: dict[int, int] = {}
    for n in draw.numbers:
        counts[(n - 1) // 10] = counts.get((n - 1) // 10, 0) + 1
    total = len(draw.numbers)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


FEATURES: tuple[Feature, ...] = tuple(_REGISTRY)
FEATURES_BY_NAME: dict[str, Feature] = {f.name: f for f in FEATURES}


def feature_series(history: DrawHistory, feature: Feature) -> list[float | None]:
    """Evaluate ``feature`` across ``history``, aligned one value per draw."""
    values: list[float | None] = []
    previous: Draw | None = None
    for draw in history:
        values.append(feature(draw, previous))
        previous = draw
    return values


def select_features(names: Sequence[str] | None) -> tuple[Feature, ...]:
    """Resolve feature names, or return every registered feature when ``None``."""
    if names is None:
        return FEATURES
    missing = [n for n in names if n not in FEATURES_BY_NAME]
    if missing:
        raise KeyError(f"unknown feature(s): {', '.join(missing)}")
    return tuple(FEATURES_BY_NAME[n] for n in names)
