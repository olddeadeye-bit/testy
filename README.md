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

## Quick start — no Terminal at all

Double-click the launcher for your computer:

| | |
| --- | --- |
| **Windows** | `Start Lottery Tool.bat` |
| **Mac** | `Start Lottery Tool.command` |

Either one finds Python, downloads the draw history on first run, and opens the
app in your browser. A console window appears and reports what it is doing;
leave it open while you use the app, and close it to stop.

**Windows**: if Python is missing, the launcher points you at
python.org/downloads and tells you to tick *"Add python.exe to PATH"* on the
installer's first screen — the step whose omission causes most of the trouble.
SmartScreen may warn about an unrecognised app; choose *More info* then *Run
anyway*.

**Mac**: if macOS says the file is from an unidentified developer (which happens
when the folder arrived as a downloaded ZIP rather than a `git clone`),
right-click it, choose **Open**, then **Open** again. Once only.

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

## Finding patterns in the draws themselves

The metric search asks whether draws follow something outside them. This asks
whether the draw sequence has structure *inside* it — which is where a real
defect would actually show, because the mechanisms are physical rather than
mystical:

```bash
python3 -m lotterypatterns patterns --game lotto
```

Six families, every one corrected across the whole battery:

| Family | What it asks |
| --- | --- |
| **pairs** | Do two numbers come up together more than the combinatorics allow? |
| **positions** | Is the first ball out of the machine distributed like the last? |
| **recency** | Do numbers sleep longer, or return sooner, than a geometric gap predicts? |
| **machines** | Does one physical machine or ball set draw differently from another? |
| **serial** | Does one draw carry information about the next? |
| **periodicity** | Does any ball recur on a rhythm — every seventh draw, say? |

**machines** is the most credible of the six. Operators publish which machine
and which ball set produced each draw, and those are physical objects that
wear. Ball sets have been retired over exactly this. The test checks each group
for evenness *and* whether the groups differ from one another, which is the
sharper question — a quirk shared by every machine would cancel out in the
per-group tests.

The battery has been checked in both directions, which is the only way to trust
it. Planted a pair into 1,500 draws and it came back:

```
* [pairs]   12 and 44: p=0 q=0 — 398 together vs 13.2 expected
* [recency] ball 12 return time: average gap 2.9 draws vs 9.8 expected
```

Planted a bias into one of two machines and it named the machine:

```
* [machines]    machine Merlin evenness: stat=+687.5 p=1.9e-108
* [periodicity] ball 38 every 2 draws: 361 appearances, concentration 0.612
```

## Does any of it actually predict anything?

This is the question that separates a pattern-finding tool from data-dredging,
and it has a definite answer, obtainable by replaying history:

```bash
python3 -m lotterypatterns backtest --game lotto
```

Stand at draw N knowing only draws 1..N-1. Make a pick. Score it against what
actually came out. Repeat to the present. Under fair draws every strategy
scores the same — the expected matches per line is `picks x picks / pool`,
0.6102 for Lotto, no matter how the numbers were chosen.

```
strategy                 actual by chance      edge       z         p         q
------------------------------------------------------------------------------
hot numbers              0.7308    0.6102   +19.76%   +2.63  0.008624   0.06037
overdue numbers          0.6500    0.6102    +6.53%   +0.87    0.3857    0.6749
bias-weighted            0.6231    0.6102    +2.12%   +0.28    0.7786    0.8905
random (baseline)        0.6038    0.6102    -1.04%   -0.14    0.8905    0.8905
frequent pairs           0.5962    0.6102    -2.30%   -0.31    0.7602    0.8905
unpopular (ours)         0.5692    0.6102    -6.71%   -0.89    0.3726    0.6749
cold numbers             0.5615    0.6102    -7.97%   -1.06    0.2895    0.6749

None of them beat chance.
Looked like it at first glance: hot numbers (+19.8%, p=0.009) — but 7
strategies were tried, and after correcting for that (the q column) it is noise.
```

That is the whole discipline in one table. "Hot numbers" beat chance by 19.8%
with p=0.009, and it is still nothing, because seven strategies were tried and
q says so.

**And the test has teeth.** Given a machine with three genuinely over-weighted
balls, it does not shrug:

```
hot numbers              1.1667    0.6102   +91.20%  +11.50  1.345e-30
bias-weighted            1.1325    0.6102   +85.60%  +10.79  3.759e-27
```

So when it reports "nothing beat chance" on your real data, that is a
measurement, not an assumption. `unpopular (ours)` is in the table on purpose:
the strategy this package recommends does not beat chance either, because it
was never meant to — it aims at a bigger share of a jackpot, not a better
chance of one, and this test measures only the latter.

Point it at your own ideas too — a strategy is any function from past draws to
a line.

## Suggesting numbers to play

Suggestions are tied to specific upcoming draws — it knows Lotto runs Wednesday
and Saturday, Thunderball Tuesday, Wednesday, Friday and Saturday, and rolls
past tonight's draw once sales have closed:

```bash
python3 -m lotterypatterns suggest --game lotto --draws-ahead 2 --backtest
python3 -m lotterypatterns suggest --game thunderball --lines 3
```

```
Lotto — Saturday 29 August 2026 (in 1 day)
----------------------------------------------------------
  1.  24  33  35  42  49  59
  2.  27  32  36  41  47  58

Lotto — Wednesday 2 September 2026 (in 5 days)
----------------------------------------------------------
  1.  39  41  42  48  52  57
  2.  35  41  46  47  51  55

==========================================================
Analysed 520 real Lotto draws (2019-01-02 to 2023-04-08).

BALL BIAS: none. Every ball comes up at the rate it should,
  so no number is due, hot or cold.

STRUCTURAL PATTERNS: none survived correction — no pairs,
  rhythms, machine effects or draw-to-draw dependence.

WALK-FORWARD TEST:
  no strategy beat chance on 260 held-out draws; best was hot numbers at
  +19.8% (p=0.009, q=0.06 — noise once corrected for trying several)

ODDS: 1 in 45,057,474 per line. Unchanged by any of the above.
SHARING: these lines expect about 53% less jackpot-splitting than an average
ticket.
```

Every line of that report is the output of a test that could have come back
the other way. If the ball-evenness test finds a bias, the picks tilt toward
it and the report says so. If the pattern battery finds structure, it is
listed. If a strategy beats chance out of sample, it is named.

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

# Structural patterns: pairs, rhythms, machines, dependence
python3 -m lotterypatterns patterns --game lotto --kind machines

# Does any strategy beat chance on draws it has not seen?
python3 -m lotterypatterns backtest --game lotto

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
Start Lottery Tool.bat       Double-click this on Windows
Start Lottery Tool.command   Double-click this on Mac
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
  patterns.py   Pairs, positions, recency, machines, serial dependence, rhythms
  backtest.py   Walk-forward testing — the one that decides if any of it works
  schedule.py   When the next draws are
  picker.py     Number suggestions, and an honest account of their worth
  cli.py        gui / search / suggest / patterns / backtest / bias / fetch /
                calibrate / demo / list / games
  gui.py        Local web server behind the browser interface
  static/       The single-page GUI
tests/          153 tests: positions against published ephemerides, and every
                analysis checked both ways — quiet on fair draws, firing on
                draws with something genuinely planted in them
data/           Sample draw history and a sample external metric
```
