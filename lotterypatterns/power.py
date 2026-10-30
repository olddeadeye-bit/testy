"""What could this analysis have found? The question a null result depends on.

"No bias found" is only informative alongside the size of bias that would have
been found. With 520 draws a ball running 30% hot is invisible; with 5,000 it
is not. This module turns a sample size into a minimum detectable effect, so
that a quiet result can be reported as "no ball is more than X% off", which is
a claim, instead of "nothing found", which is not.

Two views are given:

* the per-ball test, analytically (normal approximation to the binomial, at a
  significance level tightened for having tested every ball), and
* the global evenness test, by simulation, because its power depends on how
  the bias is spread and has no tidy closed form once drawing without
  replacement is accounted for.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .stats import chi_square_uniform, normal_sf


def _z_for_two_sided(alpha: float) -> float:
    """The z whose two-sided tail probability is ``alpha``, by bisection."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between 0 and 1")
    lo, hi = 0.0, 40.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if normal_sf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _cdf(z: float) -> float:
    """Standard normal cumulative probability."""
    return 1.0 - normal_sf(abs(z)) / 2.0 if z >= 0 else normal_sf(abs(z)) / 2.0


def ball_power(draws: int, pool: int, picks: int, lift: float, *,
               alpha: float = 0.05) -> float:
    """Chance of flagging a single ball whose rate is ``lift`` times normal.

    The significance level is divided by the number of balls tested, which is
    stricter than Benjamini-Hochberg and so errs towards understating power:
    the true figure is a little higher, never lower.
    """
    p0 = picks / pool
    p1 = min(p0 * lift, 0.999999)
    sd0 = math.sqrt(draws * p0 * (1 - p0))
    sd1 = math.sqrt(draws * p1 * (1 - p1))
    if sd0 == 0 or sd1 == 0:
        return 0.0
    zc = _z_for_two_sided(alpha / pool)
    shift = draws * (p1 - p0)
    upper = 1.0 - _cdf((zc * sd0 - shift) / sd1)
    lower = _cdf((-zc * sd0 - shift) / sd1)
    return min(1.0, upper + lower)


# The normal curve stands in for the binomial, and does so badly when a ball is
# expected to appear only a handful of times. The usual rule of thumb is at
# least ten expected appearances; below that the formula flatters itself (with
# three draws it claimed to catch a ball eight times too common, when the real
# chance was about 61%), so the module declines to answer.
MIN_EXPECTED_APPEARANCES = 10


def reliable(draws: int, pool: int, picks: int) -> bool:
    """Whether the normal approximation can be trusted at this sample size."""
    p0 = picks / pool
    return draws * p0 >= MIN_EXPECTED_APPEARANCES and draws * (1 - p0) >= MIN_EXPECTED_APPEARANCES


def minimum_detectable_lift(draws: int, pool: int, picks: int, *,
                            power: float = 0.8, alpha: float = 0.05) -> float | None:
    """Smallest over-representation of one ball that is flagged ``power`` of the time.

    Returned as a multiple of the normal rate (1.20 means 20% hot), or None if
    even a ball drawn in every single draw would not be reliably caught.
    """
    if not reliable(draws, pool, picks):
        return None
    ceiling = pool / picks                      # a ball in every draw
    if ball_power(draws, pool, picks, ceiling * 0.999, alpha=alpha) < power:
        return None
    lo, hi = 1.0, ceiling * 0.999
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if ball_power(draws, pool, picks, mid, alpha=alpha) >= power:
            hi = mid
        else:
            lo = mid
    return hi


def draws_needed(pool: int, picks: int, lift: float, *, power: float = 0.8,
                 alpha: float = 0.05, limit: int = 2_000_000) -> int | None:
    """How many draws it takes to catch a ball running ``lift`` times normal."""
    if lift <= 1.0:
        raise ValueError("lift must exceed 1.0")
    if not reliable(limit, pool, picks):
        return None
    if ball_power(limit, pool, picks, lift, alpha=alpha) < power:
        return None
    lo, hi = 1, limit
    while lo < hi:
        mid = (lo + hi) // 2
        if reliable(mid, pool, picks) and ball_power(mid, pool, picks, lift, alpha=alpha) >= power:
            hi = mid
        else:
            lo = mid + 1
    return lo


def simulated_detection_rate(draws: int, pool: int, picks: int, lift: float, *,
                             trials: int = 200, alpha: float = 0.05,
                             seed: int = 0) -> float:
    """How often the *global* evenness test fires when one ball is ``lift`` times normal.

    Drawing is simulated for real, without replacement. This is a different
    test from the per-ball one that ``ball_power`` describes, and it is weaker
    at spotting a single hot ball (it spreads its attention across every ball),
    so the two should not be expected to agree.
    """
    rng = random.Random(seed)
    p0 = picks / pool
    extra = max(0.0, p0 * (lift - 1.0))          # chance the ball is forced in
    hits = 0
    for _ in range(trials):
        counts = [0] * pool
        for _ in range(draws):
            chosen = set()
            if extra and rng.random() < extra:
                chosen.add(1)
            while len(chosen) < picks:
                chosen.add(rng.randint(1, pool))
            for ball in chosen:
                counts[ball - 1] += 1
        if chi_square_uniform(counts, picks=picks).p_value <= alpha:
            hits += 1
    return hits / trials


@dataclass(frozen=True)
class PowerReport:
    """What a given archive could and could not have revealed."""

    name: str
    draws: int
    pool: int
    picks: int
    mdl_80: float | None
    mdl_95: float | None
    curve: tuple[tuple[float, float], ...]

    def summary(self) -> str:
        lines = [f"{self.name} - {self.draws:,} draws"]
        if self.mdl_80 is None:
            lines.append("  Too few draws to say how big a bias this could catch.")
            return "\n".join(lines)
        hot = 100 * (self.mdl_80 - 1)
        lines.append(f"  If one number were secretly rigged to come up {hot:.0f}% more "
                     "often than it should,")
        lines.append("  this analysis would catch it 8 times out of 10.")
        lines.append(f"  So \"no bias found\" means: no number is rigged by more than "
                     f"about {hot:.0f}%.")
        lines.append("  A smaller rigging could still be hiding in the data.")
        lines.append("")
        lines.append("  How likely we'd be to catch one rigged number:")
        for lift, p in self.curve:
            lines.append(f"    {100 * (lift - 1):3.0f}% too common   {p:4.0%}   "
                         + "#" * int(round(p * 20)))
        return "\n".join(lines)


def power_report(draws: int, pool: int, picks: int, name: str = "archive", *,
                 alpha: float = 0.05) -> PowerReport:
    curve = tuple((lift, ball_power(draws, pool, picks, lift, alpha=alpha))
                  for lift in (1.05, 1.10, 1.15, 1.20, 1.30, 1.50, 2.00))
    return PowerReport(
        name=name, draws=draws, pool=pool, picks=picks,
        mdl_80=minimum_detectable_lift(draws, pool, picks, power=0.80, alpha=alpha),
        mdl_95=minimum_detectable_lift(draws, pool, picks, power=0.95, alpha=alpha),
        curve=curve,
    )
