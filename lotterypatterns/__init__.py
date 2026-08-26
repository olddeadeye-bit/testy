"""Search lottery draw history for correlations against arbitrary strange metrics.

The point of this package is not to find a way to win the lottery. Draws from a
fair machine are independent and uniform, so no metric can predict them. The
point is to run the search *properly*: to generate thousands of candidate
hypotheses, score them, and then apply the multiple-comparison correction and
null calibration that tell you how many "discoveries" a pile of pure noise would
have produced anyway.

Typical use::

    from lotterypatterns import DrawHistory, default_metrics, search

    draws = DrawHistory.from_csv("data/draws.csv", pool=59, picks=6)
    results = search(draws, default_metrics(), lags=range(0, 4))
    for r in results.significant():
        print(r)
"""

from .draws import Draw, DrawHistory, simulate_biased_draws, simulate_draws
from .features import FEATURES, Feature, feature_series
from .metrics import Metric, default_metrics, metric_from_csv
from .search import SearchResult, SearchReport, search, null_calibration
from .stats import (
    benjamini_hochberg,
    bonferroni,
    mutual_information,
    pearson,
    permutation_test,
    spearman,
)

__all__ = [
    "Draw",
    "DrawHistory",
    "simulate_draws",
    "simulate_biased_draws",
    "Feature",
    "FEATURES",
    "feature_series",
    "Metric",
    "default_metrics",
    "metric_from_csv",
    "SearchResult",
    "SearchReport",
    "search",
    "null_calibration",
    "pearson",
    "spearman",
    "mutual_information",
    "permutation_test",
    "benjamini_hochberg",
    "bonferroni",
]

__version__ = "0.1.0"
