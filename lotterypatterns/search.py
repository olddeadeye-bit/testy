"""The search engine: cross every draw feature against every metric, at every lag.

The cross product is the whole point and also the whole danger. Twenty features
times fifteen metrics times four lags times three association measures is 3,600
hypotheses, and at alpha = 0.05 roughly 180 of them will look significant even
if the lottery is perfectly fair. :class:`SearchReport` therefore never reports
a raw p-value on its own: every result carries a false-discovery q-value, the
report knows how many tests were run, and the control metrics show what noise
scored on the very same search.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from .draws import DrawHistory, simulate_draws
from .features import Feature, feature_series, select_features
from .metrics import CONTROL_METRICS, Metric, default_metrics
from .stats import (
    Association,
    benjamini_hochberg,
    bonferroni,
    mutual_information,
    pearson,
    spearman,
)

Method = Callable[[Sequence[float], Sequence[float]], Association]

METHODS: dict[str, Method] = {
    "pearson": pearson,
    "spearman": spearman,
    "mutual_info": mutual_information,
}


@dataclass(frozen=True)
class SearchResult:
    """One tested hypothesis and everything needed to judge it."""

    feature: str
    metric: str
    lag: int
    method: str
    statistic: float
    p_value: float
    n: int
    q_value: float = 1.0
    bonferroni_p: float = 1.0
    is_control: bool = False

    def __str__(self) -> str:
        control = " [CONTROL]" if self.is_control else ""
        return (f"{self.feature} ~ {self.metric} (lag {self.lag}, {self.method}): "
                f"stat={self.statistic:+.4f} p={self.p_value:.4g} "
                f"q={self.q_value:.4g} n={self.n}{control}")

    def as_dict(self) -> dict:
        return {
            "feature": self.feature,
            "metric": self.metric,
            "lag": self.lag,
            "method": self.method,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "q_value": self.q_value,
            "bonferroni_p": self.bonferroni_p,
            "n": self.n,
            "is_control": self.is_control,
        }


@dataclass
class SearchReport:
    """Every hypothesis the search tested, ranked, with the noise floor beside it."""

    results: list[SearchResult]
    draws: int
    alpha: float = 0.05
    game: str = "lottery"
    _by_p: list[SearchResult] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._by_p = sorted(self.results, key=lambda r: r.p_value)

    def __len__(self) -> int:
        return len(self.results)

    @property
    def n_tests(self) -> int:
        return len(self.results)

    def ranked(self, limit: int | None = None) -> list[SearchResult]:
        """Results ordered by raw p-value, strongest first."""
        return self._by_p[:limit] if limit else list(self._by_p)

    def significant(self, *, use_fdr: bool = True) -> list[SearchResult]:
        """Results that survive correction — FDR by default, else Bonferroni."""
        if use_fdr:
            return [r for r in self._by_p if r.q_value <= self.alpha]
        return [r for r in self._by_p if r.bonferroni_p <= self.alpha]

    def naive_hits(self) -> list[SearchResult]:
        """Results that pass an uncorrected threshold — the tempting, wrong list."""
        return [r for r in self._by_p if r.p_value <= self.alpha]

    def controls(self) -> list[SearchResult]:
        return sorted((r for r in self.results if r.is_control),
                      key=lambda r: r.p_value)

    def control_floor(self) -> float | None:
        """The best p-value any control metric achieved: the noise floor.

        A real finding has to beat this. A metric that cannot possibly carry
        information got this far purely by being tested many times, so anything
        that scores no better has no claim to be different.
        """
        controls = self.controls()
        return controls[0].p_value if controls else None

    def expected_naive_hits(self) -> float:
        return self.n_tests * self.alpha

    def summary(self) -> str:
        naive = self.naive_hits()
        survivors = self.significant()
        floor = self.control_floor()
        lines = [
            f"Game:                {self.game}",
            f"Draws analysed:      {self.draws}",
            f"Hypotheses tested:   {self.n_tests}",
            f"alpha:               {self.alpha}",
            "",
            f"Uncorrected p <= {self.alpha}:  {len(naive)} "
            f"(pure noise would give ~{self.expected_naive_hits():.1f})",
            f"Survive FDR control:    {len(survivors)}",
        ]
        if floor is not None:
            lines.append(f"Control-metric floor:   best p = {floor:.4g} "
                         "(what a metric with no information scored)")
        lines.append("")
        if survivors:
            lines.append("Survivors after correction:")
            lines += [f"  {r}" for r in survivors[:20]]
            if floor is not None:
                beat = [r for r in survivors if not r.is_control and r.p_value < floor]
                lines.append("")
                lines.append(
                    f"  {len(beat)} of these also beat the control floor."
                    if beat else
                    "  None of these beat the control floor — treat them as noise."
                )
        else:
            lines.append("Nothing survives multiple-comparison correction.")
            lines.append("That is the expected result for a fair lottery.")
            lines.append("")
            lines.append("Strongest uncorrected results (for reference only):")
            lines += [f"  {r}" for r in self.ranked(5)]
        return "\n".join(lines)

    def to_csv(self, path: str) -> None:
        import csv as _csv
        rows = [r.as_dict() for r in self.ranked()]
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = _csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


def _lagged_pair(feature_values: Sequence[float | None],
                 metric_values: Sequence[float | None],
                 lag: int) -> tuple[list[float], list[float]]:
    """Align a feature against a metric read ``lag`` draws earlier.

    Lag 0 asks whether the metric on the day of the draw tracks the draw. Lag k
    asks whether the metric k draws ago does — the only direction that could
    ever be predictive, since the other direction would need the draw to
    influence its own past.
    """
    if lag < 0:
        raise ValueError("lag must be >= 0; a negative lag tests the future")
    xs, ys = [], []
    for i in range(lag, len(feature_values)):
        f_val = feature_values[i]
        m_val = metric_values[i - lag]
        if f_val is None or m_val is None:
            continue
        xs.append(f_val)
        ys.append(m_val)
    return xs, ys


def search(history: DrawHistory, metrics: Sequence[Metric] | None = None, *,
           features: Sequence[Feature] | None = None,
           lags: Iterable[int] = (0,),
           methods: Sequence[str] = ("pearson", "spearman"),
           alpha: float = 0.05,
           min_samples: int = 30) -> SearchReport:
    """Test every feature against every metric at every lag with every method.

    Returns a :class:`SearchReport` with FDR q-values and Bonferroni-adjusted
    p-values already attached to each result.
    """
    metrics = tuple(metrics) if metrics is not None else default_metrics()
    features = tuple(features) if features is not None else select_features(None)
    lags = tuple(lags)
    unknown = [m for m in methods if m not in METHODS]
    if unknown:
        raise KeyError(f"unknown method(s): {', '.join(unknown)}")

    dates = history.dates
    metric_cache = {m.name: m.series(dates) for m in metrics}
    feature_cache = {f.name: feature_series(history, f) for f in features}

    raw: list[SearchResult] = []
    for feature in features:
        f_values = feature_cache[feature.name]
        for metric in metrics:
            m_values = metric_cache[metric.name]
            for lag in lags:
                xs, ys = _lagged_pair(f_values, m_values, lag)
                if len(xs) < min_samples:
                    continue
                for method_name in methods:
                    assoc = METHODS[method_name](xs, ys)
                    raw.append(SearchResult(
                        feature=feature.name,
                        metric=metric.name,
                        lag=lag,
                        method=method_name,
                        statistic=assoc.statistic,
                        p_value=assoc.p_value,
                        n=assoc.n,
                        is_control=metric.name in CONTROL_METRICS,
                    ))

    if not raw:
        return SearchReport([], draws=len(history), alpha=alpha, game=history.name)

    p_values = [r.p_value for r in raw]
    q_values = benjamini_hochberg(p_values)
    bonf = bonferroni(p_values)
    corrected = [
        SearchResult(**{**r.as_dict(), "q_value": q, "bonferroni_p": b})
        for r, q, b in zip(raw, q_values, bonf)
    ]
    return SearchReport(corrected, draws=len(history), alpha=alpha, game=history.name)


@dataclass
class Calibration:
    """What the same search finds in histories known to contain nothing."""

    runs: int
    n_tests: int
    naive_hits: list[int]
    survivors: list[int]
    best_p: list[float]

    @property
    def mean_naive_hits(self) -> float:
        return statistics.fmean(self.naive_hits)

    @property
    def mean_survivors(self) -> float:
        return statistics.fmean(self.survivors)

    def p_value_for(self, observed_survivors: int) -> float:
        """How often a fair lottery produced at least this many survivors."""
        hits = sum(1 for s in self.survivors if s >= observed_survivors)
        return (hits + 1) / (self.runs + 1)

    def summary(self) -> str:
        return "\n".join([
            f"Null calibration over {self.runs} simulated fair histories",
            f"  Hypotheses per run:        {self.n_tests}",
            f"  Uncorrected hits per run:  mean {self.mean_naive_hits:.1f} "
            f"(range {min(self.naive_hits)}-{max(self.naive_hits)})",
            f"  Survivors per run:         mean {self.mean_survivors:.2f} "
            f"(range {min(self.survivors)}-{max(self.survivors)})",
            f"  Best p-value per run:      median {statistics.median(self.best_p):.4g}",
        ])


def null_calibration(history: DrawHistory, metrics: Sequence[Metric] | None = None, *,
                     runs: int = 20, seed: int = 0, **search_kwargs) -> Calibration:
    """Re-run the identical search against fair, simulated draws.

    This is the control experiment for the whole method. It uses the real
    history's dates and shape but replaces the balls with independent uniform
    draws, so every hit it reports is definitionally spurious. If the real
    search finds no more than this does, the real search found nothing.
    """
    naive_hits, survivors, best_p = [], [], []
    for run in range(runs):
        fake = simulate_draws(
            len(history),
            pool=history.pool,
            picks=history.picks,
            start=history.dates[0],
            seed=seed + run,
            name=f"null-{run}",
        )
        # Reuse the real calendar so date-keyed metrics see identical inputs.
        aligned = DrawHistory(
            [type(d)(real_date, d.numbers, d.bonus)
             for d, real_date in zip(fake, history.dates)],
            pool=history.pool, picks=history.picks, name=f"null-{run}",
        )
        report = search(aligned, metrics, **search_kwargs)
        naive_hits.append(len(report.naive_hits()))
        survivors.append(len(report.significant()))
        ranked = report.ranked(1)
        best_p.append(ranked[0].p_value if ranked else 1.0)

    return Calibration(
        runs=runs,
        n_tests=report.n_tests,
        naive_hits=naive_hits,
        survivors=survivors,
        best_p=best_p,
    )
