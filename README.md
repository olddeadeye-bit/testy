# lotterypatterns

An algorithm that searches lottery draw history for correlations against
arbitrary strange metrics — lunar phase, the sunspot cycle, Mercury retrograde,
daylight hours, Friday the 13th, or any external time series you supply as a
CSV — and then tells you honestly how much of what it found is noise.

Pure standard library. No numpy, no scipy, no network, no install step.

## The problem this solves

Searching for patterns is the easy half. Twenty draw features against fifteen
metrics at four lags with three association measures is **3,600 hypotheses**,
and at the usual α = 0.05 about **180 of them will look significant even if the
lottery is perfectly fair**. Any tool that runs that sweep and prints the
strongest correlations will hand you a discovery every single time.

So this one never reports a raw p-value on its own. Every result carries:

- a **Benjamini–Hochberg q-value** controlling the false discovery rate across
  the whole sweep, and a Bonferroni-adjusted p-value beside it;
- a **control floor** — two of the built-in metrics (`pure_noise`, `coin_flip`)
  are seeded noise keyed to the date and cannot carry information, so whatever
  score they earn is the score noise earns. A finding that does not beat them is
  not a finding;
- a **null calibration** mode that re-runs the identical search against
  simulated fair draws on the real calendar, so you can compare your hit count
  against the hit count of a game with nothing in it.

And because a search that only ever says "nothing here" would say that about a
crooked machine too, `simulate_biased_draws` builds a history that genuinely
does track a metric, so you can confirm the search has the power to detect a
real effect at your sample size before trusting it to report an absence.

## Quick start

```bash
# What can be tested against what
python3 -m lotterypatterns list

# Fair game vs. rigged game, side by side — start here
python3 -m lotterypatterns demo

# Search real draws, including your own external metric
python3 -m lotterypatterns search \
    --draws data/sample_draws.csv --pool 59 --lags 0-3 \
    --metric-csv rainfall_mm=data/sample_external_metric.csv \
    --out results.csv

# What does the same search find in draws known to contain nothing?
python3 -m lotterypatterns calibrate --draws data/sample_draws.csv --runs 20

python3 -m unittest discover -s tests
```

Typical output on fair draws:

```
Hypotheses tested:   2016
Uncorrected p <= 0.05:  64 (pure noise would give ~100.8)
Survive FDR control:    0
Control-metric floor:   best p = 0.002185

Nothing survives multiple-comparison correction.
That is the expected result for a fair lottery.
```

And on a history rigged to follow the moon:

```
sum ~ moon_illumination (lag 0, pearson): stat=+0.6215 p=4.2e-44 q=1.3e-41 n=400
```

## Library use

```python
from lotterypatterns import DrawHistory, default_metrics, search, null_calibration
from lotterypatterns.metrics import metric_from_csv

draws = DrawHistory.from_csv("data/sample_draws.csv", pool=59, picks=6)
metrics = list(default_metrics()) + [metric_from_csv("rainfall.csv", name="rainfall_mm")]

report = search(draws, metrics, lags=range(0, 4), methods=("pearson", "spearman"))
print(report.summary())

for result in report.significant():        # FDR-controlled, not raw p
    print(result)

print(null_calibration(draws, metrics, runs=20).summary())
```

## How a hypothesis is built

Each test pairs one **feature** of a draw with one **metric** sampled on a date,
at a **lag**, scored by one **association measure**.

**Features** (`lotterypatterns/features.py`) turn a draw into a number: `sum`,
`mean`, `spread`, `stdev`, `lowest`, `highest`, `odd_count`, `prime_count`,
`fibonacci_count`, `multiple_of_seven`, `contains_digit_seven`, `digit_sum`,
`consecutive_pairs`, `max_gap`, `decade_spread`, `sum_mod_seven`, `balance`,
`entropy`, plus three that compare against the previous draw (`carry_over`,
`jump_distance`, `centroid_shift`).

**Metrics** (`lotterypatterns/metrics.py`) turn a date into a number. The
built-ins are all computable offline from the date alone — `moon_illumination`,
`moon_age`, `lunar_distance_phase`, `tidal_force`, `solar_declination`,
`daylight_hours`, `sunspot_cycle_phase`, `mercury_retrograde`, `day_of_week`,
`is_friday_thirteenth`, `date_digit_sum`, `day_of_month`, `annual_phase` — plus
the two controls. External series arrive via `metric_from_csv`, which carries a
reading forward to the draw date for at most `max_staleness_days` and otherwise
drops the draw rather than filling it with a stale number.

**Lags** are counted in draws, and only backwards: lag *k* asks whether the
metric *k* draws ago tracks this draw. A negative lag is refused, since the only
way a draw could correlate with a later metric reading is if the draw caused it.

**Measures** are `pearson` (linear, analytic t-based p-value), `spearman`
(monotone, tie-corrected ranks) and `mutual_info` (binned mutual information
with a permutation p-value, which catches non-monotone structure the
correlations miss — a metric that pushes the ball-sum to both extremes without
favouring either direction). `mutual_info` is off by default because its
permutation test is ~400× slower than the analytic ones.

## Reading a result honestly

In order:

1. **Did anything survive FDR correction?** If not, stop. The strongest
   uncorrected result in a 2,000-hypothesis sweep is not evidence of anything.
2. **Does it beat the control floor?** Compare against the best p-value the
   noise metrics achieved on the same sweep.
3. **Is it more than `calibrate` produced?** If fair simulated draws routinely
   yield as many survivors, yours are the same thing.
4. **Was the hypothesis chosen before you looked?** A survivor found by sweeping
   3,600 combinations is a hypothesis to test on *fresh* draws, not a
   conclusion. Hold out the last 20% of your history, or wait for new draws.
5. **Does the mechanism make sense?** `sum_mod_seven ~ mercury_retrograde` at
   lag 1 has no mechanism. That is what the arithmetic of a large search looks
   like from the inside.

## What this will not do

It will not help you win. Draws from a fair machine are independent and
uniform, and no amount of correlation against sunspots changes the next draw's
distribution. What a search like this *can* legitimately find is a broken
machine or a broken process — a biased ball set, a drifting mechanism, a
data-entry artefact in a published archive — which is exactly why the
multiple-comparison machinery matters: without it you cannot tell a real defect
from the 180 fake ones the sweep manufactures for free.

## Layout

```
lotterypatterns/
  draws.py      Draw, DrawHistory, CSV loading, fair and rigged simulators
  features.py   Per-draw features
  metrics.py    Date-keyed metrics, controls, external CSV loader
  stats.py      Correlations, mutual information, permutation tests, FDR
  search.py     The sweep, the report, null calibration
  cli.py        search / calibrate / demo / list
tests/          39 tests, including hand-computed statistical checks
data/           Sample draw history and a sample external metric
```
