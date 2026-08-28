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

## Quick start — the point-and-click version

```bash
python3 -m lotterypatterns gui
```

That is the whole setup. It opens in your browser, and you press **Run the search**.
Nothing to install, nothing sent anywhere — the server binds to localhost only and
your draw data never leaves the machine. Press Control-C in the terminal to stop it.

The GUI covers everything: pick your data (bundled sample, your own CSV, or an
invented fair/rigged game), choose what to test against, drop in your own metric
CSV, and read the result as a plain-English verdict rather than a table of
p-values. Uploading is drag-free — just pick the file; it is read in your browser
and posted to the local server, never to the internet.

Two things in the interface are worth knowing:

- **The verdict banner** says in words whether anything survived, and how many hits
  pure chance would have produced anyway.
- **The p-value histogram** is the honest picture. When there is no pattern, the
  bars sit level with the dashed line. A tall bar on the far left is the only shape
  that suggests something real, and the app only colours it when it genuinely stands
  above chance.

The **Second opinion** button re-runs the whole search on ten lotteries with nothing
in them, so you can see what "finding nothing" normally looks like. It takes about
15 seconds.

## Getting real data

Two commands, both needing an internet connection. Run them once:

```bash
# Every UK game's full published draw history
python3 -m lotterypatterns fetch

# Daily weather back to 2015 — pressure, temperature, humidity, wind, rain
python3 -m lotterypatterns fetch --weather --from 2015-01-01
```

Archives land in `data/` and everything afterwards works offline. If the
National Lottery site blocks the download, the error prints the URL to open in
a browser and where to save the file — the result is identical.

Weather is real measurement, not computation, so it only exists once fetched.
Without it you get `pressure_climatology` and `temperature_climatology`
instead: the *average* shape of a UK year. Those are labelled as climatology
throughout, because a correlation with one of them is a correlation with the
calendar and nothing more.

## Suggesting numbers to play

```bash
python3 -m lotterypatterns suggest --game lotto --lines 5 --why
python3 -m lotterypatterns suggest --game thunderball --lines 5
```

Read what it tells you, because it will not flatter you:

```
  1.  25  38  41  51  54  57
  2.  36  39  41  42  49  55

Based on 2,000 real draws.

BALL BIAS: none. The balls come up evenly, so no number is any likelier
than another.

YOUR ODDS: 1 in 45,057,474. These picks do not change that, and nothing could.

WHAT THESE PICKS ACTUALLY BUY YOU:
  They avoid heavily-played combinations, so they expect about 54% less
  jackpot-sharing than an average ticket.
  Same chance of winning. A bigger cheque if you do.
```

**Why there is no such thing as a "due" number.** Draws are independent. The
machine has no memory of what it did last week, so past draws cannot shift the
next one. Every combination is equally likely, always.

**The one exception, which is tested for.** If a ball set is worn or a machine
is unbalanced, the numbers genuinely stop coming up evenly — real operators
have retired ball sets over exactly this. `python3 -m lotterypatterns bias`
runs a chi-square goodness-of-fit test across every ball, plus a per-ball test
with false-discovery correction. If it finds something, the picker tilts toward
it and says so. It almost always finds nothing, and says that too:

```
Evenness test:  chi-square = 37.5 on 58 df, p = 0.9833
VERDICT: no evidence of bias. The balls are coming up as evenly as chance
predicts. So no number is "due", "hot" or "cold" — those labels describe noise.
For reference, most drawn was ball 41 (69) and least was ball 20 (41); a gap
that size is normal.
```

That last line is the point. A 69-to-41 gap looks enormous and is completely
ordinary — which is why "hot number" lists are worthless.

**What the picker actually optimises.** The one thing about a lottery ticket
that genuinely is under your control: *how many people you split the jackpot
with*. A large minority of players choose birthdays, so 1–31 is heavily
over-played, as are consecutive runs, even spacings like 7-14-21-28, and a few
lucky numbers (7 above all). Jackpots are divided between everyone holding the
winning line, so an unpopular combination wins the same jackpot fewer ways
split. Your odds do not move. Your expected payout does.

The model scores a line's popularity relative to an average ticket:

| Line | Played, vs. average |
| --- | --- |
| 1, 2, 3, 4, 5, 6 | 18.2x |
| 3, 8, 12, 17, 22, 29 (all birthdays) | 3.2x |
| 7, 14, 21, 28, 35, 42 (seven times table) | 3.1x |
| 5, 23, 31, 44, 49, 57 (mixed) | 1.2x |
| 34, 41, 45, 52, 56, 58 (all high) | 0.55x |

Two caveats the tool states itself. **Thunderball's top prize is a fixed
£500,000 paid to every winner**, so there is nothing to optimise — the picker
says so and returns a plain random line. And the suggestions are chosen at
random from among the *many* thousands of similarly unpopular lines rather than
from a single "optimal" ticket: if everyone running this tool played the same
line, they would all share it with each other, which is the very thing being
avoided.

## Quick start — the command line

```bash
# What can be tested against what
python3 -m lotterypatterns list

# The UK games, their shapes and their true odds
python3 -m lotterypatterns games

# Are the balls drawn evenly?
python3 -m lotterypatterns bias --game lotto --show-counts

# Search a downloaded archive rather than a file path
python3 -m lotterypatterns search --game lotto --lags 0-3

# Fair game vs. rigged game, side by side
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

**Metrics** (`lotterypatterns/metrics.py`) turn a date into a number. Forty-one
are built in and every one of them is computed from the date alone, so a search
runs with no network and no data files:

- **The Moon** — illumination, age, ecliptic longitude and latitude,
  declination, true Earth-Moon distance, perigee phase, zodiac sign, and the
  longitude of the ascending node (the eclipse points, on an 18.6-year cycle).
- **The Sun and seasons** — ecliptic longitude, declination, zodiac sign,
  daylight hours at London, the ~11-year sunspot cycle, position in the
  tropical year.
- **The planets** — geocentric ecliptic longitude of Mercury, Venus, Mars,
  Jupiter and Saturn; apparent retrograde motion of Mercury, Venus and Mars,
  determined the way an observer would, by watching which way the planet moved;
  and elongation from the Sun.
- **The stars** — local sidereal time (which constellations are overhead), and
  the altitude above the London horizon of Sirius, Betelgeuse, Vega, Arcturus,
  Antares and Aldebaran.
- **Tides** — a combined solar and lunar tide-raising index built from the true
  positions and the inverse-cube distance law.
- **Calendar** — day of week, day of month, Friday the 13th, date digit sum.
- **Two controls** — `pure_noise` and `coin_flip`.

These are real astronomy, not approximations: the positions come from standard
algorithms (Meeus) in `lotterypatterns/astro.py`, accurate to about an
arcminute for the Sun, a few for the Moon, and a tenth of a degree for the
planets. The test suite checks them against published positions — Jupiter,
Saturn, Mars, Venus and Mercury on a known date, the solstice declinations, and
named new and full moons in two different years.

**Weather** (`lotterypatterns/weather.py`) has to be measured, so it arrives by
download: mean sea-level pressure, temperature, humidity, wind and rainfall,
from the Open-Meteo archive, cached as a CSV. Pressure is the interesting one —
it swings with every passing front, on a timescale of days, and is utterly
unconnected to anything inside a draw machine, which makes it an excellent test
of whether the search stays quiet.

Any other external series joins via `metric_from_csv`, which carries a reading
forward to the draw date for at most `max_staleness_days` and otherwise drops
the draw rather than filling it with a stale number.

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

It will not help you win, and the number picker does not claim to. Draws from a
fair machine are independent and uniform, and no amount of correlation against
sunspots, air pressure or the position of Saturn changes the next draw's
distribution. The picker improves what you would be paid if you won, never the
chance of winning. What a search like this *can* legitimately find is a broken
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
  astro.py      Sun, Moon, planet and star positions (Meeus algorithms)
  weather.py    Open-Meteo downloader, cache, and seasonal fallbacks
  games.py      Lotto, Thunderball, EuroMillions, Set For Life
  fetch.py      Downloads the published draw archives
  bias.py       Chi-square test for whether the balls are drawn evenly
  picker.py     Number suggestions, and an honest account of their worth
  cli.py        gui / search / suggest / bias / fetch / calibrate / demo / list / games
  gui.py        Local web server behind the browser interface
  static/       The single-page GUI
tests/          121 tests, including positions checked against published ephemerides
data/           Sample draw history and a sample external metric
```
