"""Statistics, implemented on the standard library alone.

Everything here is deliberately conservative. Correlation coefficients get
analytic p-values where the assumptions hold and permutation p-values where
they do not, and the search never reports a raw p-value without a
multiple-comparison correction beside it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Sequence

Number = float
Series = Sequence[float]


# --------------------------------------------------------------------------
# Distribution helpers
# --------------------------------------------------------------------------

def _log_gamma(x: float) -> float:
    return math.lgamma(x)


def _betacf(a: float, b: float, x: float, *, max_iter: int = 300,
            epsilon: float = 3e-16) -> float:
    """Continued-fraction expansion for the incomplete beta function."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < epsilon:
            break
    return h


def incomplete_beta(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        _log_gamma(a + b) - _log_gamma(a) - _log_gamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_sf(t: float, df: float) -> float:
    """Two-sided survival probability for Student's t."""
    if df <= 0:
        return 1.0
    x = df / (df + t * t)
    return incomplete_beta(df / 2.0, 0.5, x)


def normal_sf(z: float) -> float:
    """Two-sided survival probability for the standard normal."""
    return math.erfc(abs(z) / math.sqrt(2.0))


# --------------------------------------------------------------------------
# Association measures
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Association:
    """One measured association: its statistic, its p-value, and its sample size."""

    statistic: float
    p_value: float
    n: int
    method: str

    def __str__(self) -> str:
        return f"{self.method}={self.statistic:+.4f} p={self.p_value:.4g} n={self.n}"


def _clean_pair(xs: Series, ys: Series) -> tuple[list[float], list[float]]:
    if len(xs) != len(ys):
        raise ValueError(f"series lengths differ: {len(xs)} vs {len(ys)}")
    cleaned_x, cleaned_y = [], []
    for x, y in zip(xs, ys):
        if x is None or y is None:
            continue
        if isinstance(x, float) and math.isnan(x):
            continue
        if isinstance(y, float) and math.isnan(y):
            continue
        cleaned_x.append(float(x))
        cleaned_y.append(float(y))
    return cleaned_x, cleaned_y


def pearson(xs: Series, ys: Series) -> Association:
    """Pearson product-moment correlation with a t-based p-value."""
    x, y = _clean_pair(xs, ys)
    n = len(x)
    if n < 3:
        return Association(0.0, 1.0, n, "pearson")
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    dx = [v - mean_x for v in x]
    dy = [v - mean_y for v in y]
    denom = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if denom == 0.0:
        return Association(0.0, 1.0, n, "pearson")
    r = sum(a * b for a, b in zip(dx, dy)) / denom
    r = max(-1.0, min(1.0, r))
    if abs(r) >= 1.0:
        return Association(r, 0.0, n, "pearson")
    t = r * math.sqrt((n - 2) / (1.0 - r * r))
    return Association(r, student_t_sf(t, n - 2), n, "pearson")


def _rank(values: Sequence[float]) -> list[float]:
    """Average ranks, ties shared — the standard correction for Spearman."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(xs: Series, ys: Series) -> Association:
    """Spearman rank correlation — monotone association, outlier resistant."""
    x, y = _clean_pair(xs, ys)
    if len(x) < 3:
        return Association(0.0, 1.0, len(x), "spearman")
    result = pearson(_rank(x), _rank(y))
    return Association(result.statistic, result.p_value, result.n, "spearman")


def _bin_edges(values: Sequence[float], bins: int) -> list[float]:
    lo, hi = min(values), max(values)
    if lo == hi:
        return [lo, hi]
    step = (hi - lo) / bins
    return [lo + i * step for i in range(bins + 1)]


def _bin_index(value: float, edges: Sequence[float]) -> int:
    if len(edges) < 3:
        return 0
    for i in range(1, len(edges) - 1):
        if value < edges[i]:
            return i - 1
    return len(edges) - 2


def mutual_information(xs: Series, ys: Series, bins: int = 6) -> Association:
    """Binned mutual information in bits, with a permutation p-value.

    Mutual information catches non-monotone structure the correlations miss —
    a metric that pushes the ball-sum to the extremes without favouring either
    direction. It is biased upward on small samples, so the p-value here is
    always permutation-based rather than analytic.
    """
    x, y = _clean_pair(xs, ys)
    n = len(x)
    if n < 10:
        return Association(0.0, 1.0, n, "mutual_info")

    def score(a: Sequence[float], b: Sequence[float]) -> float:
        ex, ey = _bin_edges(a, bins), _bin_edges(b, bins)
        joint: dict[tuple[int, int], int] = {}
        px: dict[int, int] = {}
        py: dict[int, int] = {}
        for va, vb in zip(a, b):
            ia, ib = _bin_index(va, ex), _bin_index(vb, ey)
            joint[(ia, ib)] = joint.get((ia, ib), 0) + 1
            px[ia] = px.get(ia, 0) + 1
            py[ib] = py.get(ib, 0) + 1
        total = len(a)
        mi = 0.0
        for (ia, ib), count in joint.items():
            p_joint = count / total
            mi += p_joint * math.log2(p_joint / ((px[ia] / total) * (py[ib] / total)))
        return max(0.0, mi)

    observed = score(x, y)
    p = permutation_test(x, y, lambda a, b: score(a, b), trials=400, seed=0)
    return Association(observed, p, n, "mutual_info")


def permutation_test(xs: Series, ys: Series,
                     statistic: Callable[[Sequence[float], Sequence[float]], float],
                     *, trials: int = 1000, seed: int | None = None,
                     two_sided: bool = False) -> float:
    """Fraction of shuffles whose statistic matches or beats the observed one.

    Uses the (hits + 1) / (trials + 1) estimator, so the p-value is never
    reported as exactly zero — with 1000 trials the strongest claim available
    is p < 0.001, which is the honest resolution of the test.
    """
    x, y = _clean_pair(xs, ys)
    if len(x) < 3:
        return 1.0
    observed = statistic(x, y)
    rng = random.Random(seed)
    shuffled = list(y)
    hits = 0
    for _ in range(trials):
        rng.shuffle(shuffled)
        value = statistic(x, shuffled)
        if (abs(value) >= abs(observed)) if two_sided else (value >= observed):
            hits += 1
    return (hits + 1) / (trials + 1)


# --------------------------------------------------------------------------
# Multiple-comparison control
# --------------------------------------------------------------------------

def bonferroni(p_values: Sequence[float]) -> list[float]:
    """Family-wise error control: multiply by the number of tests, cap at 1."""
    m = len(p_values)
    return [min(1.0, p * m) for p in p_values]


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """False-discovery-rate control, returned as q-values in input order.

    Less brutal than Bonferroni and the right default when the search runs
    thousands of hypotheses and you want to know which are worth a second look
    rather than which survive a family-wise guarantee.
    """
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    q = [0.0] * m
    running_min = 1.0
    for rank in range(m - 1, -1, -1):
        index = order[rank]
        value = p_values[index] * m / (rank + 1)
        running_min = min(running_min, value)
        q[index] = min(1.0, running_min)
    return q


def expected_false_positives(n_tests: int, alpha: float) -> float:
    """How many tests a pile of pure noise would flag at this threshold."""
    return n_tests * alpha
