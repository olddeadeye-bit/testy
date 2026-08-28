"""Strange metrics: the right-hand side of every hypothesis we test.

A metric maps a calendar date to a number. The built-ins are all computable
offline from the date alone — lunar phase, solar geometry, the sunspot cycle,
calendar numerology — so a search runs with no network and no data files. Real
external series (rainfall, a stock index, earthquake counts, your step count)
plug in through :func:`metric_from_csv`.

Two of the built-ins are deliberate controls: ``pure_noise`` is seeded white
noise and ``coin_flip`` is a fair binary sequence. Neither can carry real
signal, so whatever score they earn is the score noise earns. Any "discovery"
that fails to beat them is not a discovery.
"""

from __future__ import annotations

import bisect
import csv
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Sequence

from . import astro

_EPOCH = date(2000, 1, 1)
_SYNODIC_MONTH = 29.530588853
_TROPICAL_YEAR = 365.242190
# Solar cycle 24 minimum, December 2008, and the mean cycle length.
_SOLAR_MIN_REF = (date(2008, 12, 1) - _EPOCH).days
_SOLAR_CYCLE_DAYS = 11.0 * 365.25


def _days(d: date) -> float:
    return float((d - _EPOCH).days)


def _digit_sum(n: int) -> int:
    return sum(int(c) for c in str(abs(n)))


@dataclass(frozen=True)
class Metric:
    """A named quantity sampled on the date of a draw."""

    name: str
    description: str
    fn: Callable[[date], float | None]
    units: str = ""

    def __call__(self, when: date) -> float | None:
        return self.fn(when)

    def series(self, dates: Sequence[date]) -> list[float | None]:
        return [self.fn(d) for d in dates]


_REGISTRY: list[Metric] = []


def _m(name: str, description: str, units: str = ""):
    def register(fn: Callable[[date], float | None]) -> Metric:
        metric = Metric(name, description, fn, units)
        _REGISTRY.append(metric)
        return metric
    return register


@_m("moon_illumination", "Fraction of the Moon's disc lit, 0 new to 1 full", "fraction")
def moon_illumination(when: date) -> float:
    return astro.moon_illuminated_fraction(when)


@_m("moon_age", "Days since the last new moon", "days")
def moon_age(when: date) -> float:
    return astro.moon_phase_angle(when) / 360.0 * _SYNODIC_MONTH


@_m("moon_ecliptic_longitude",
    "Where the Moon sits along the zodiac, 0 to 360 degrees", "degrees")
def moon_ecliptic_longitude(when: date) -> float:
    return astro.moon_longitude(when)


@_m("moon_ecliptic_latitude",
    "How far the Moon rides above or below the ecliptic", "degrees")
def moon_ecliptic_latitude(when: date) -> float:
    return astro.moon_latitude(when)


@_m("moon_declination",
    "Height of the Moon's path in the sky — swings over 18.6 years", "degrees")
def moon_declination(when: date) -> float:
    return astro.moon_declination(when)


@_m("moon_distance", "Earth-Moon distance, perigee ~356,500 km to apogee ~406,700",
    "km")
def moon_distance(when: date) -> float:
    return astro.moon_distance_km(when)


@_m("lunar_distance_phase",
    "Phase of the anomalistic month, 0 at perigee — the 'supermoon' clock", "fraction")
def lunar_distance_phase(when: date) -> float:
    near, far = 356500.0, 406700.0
    span = (astro.moon_distance_km(when) - near) / (far - near)
    return max(0.0, min(1.0, 1.0 - span))


@_m("moon_zodiac_sign", "Which of the twelve signs the Moon is in, 0 = Aries", "index")
def moon_zodiac_sign(when: date) -> float:
    return float(astro.zodiac_index(astro.moon_longitude(when)))


@_m("lunar_node", "Longitude of the Moon's ascending node — the eclipse points",
    "degrees")
def lunar_node(when: date) -> float:
    return astro.lunar_node_longitude(when)


@_m("tidal_force",
    "Tide-raising force of Sun and Moon combined, from their true positions", "index")
def tidal_force(when: date) -> float:
    # Tidal force falls off as the cube of distance; the Sun contributes about
    # 46% of the Moon's pull at mean distance.
    distance = astro.moon_distance_km(when)
    lunar = (385000.56 / distance) ** 3
    alignment = abs(math.cos(astro.moon_phase_angle(when) * math.pi / 180.0))
    return lunar * (1.0 + 0.46 * alignment)


@_m("sun_ecliptic_longitude",
    "Where the Sun sits along the zodiac — this is the time of year", "degrees")
def sun_ecliptic_longitude(when: date) -> float:
    return astro.sun_longitude(when)


@_m("solar_declination", "Declination of the Sun — the seasons, in degrees", "degrees")
def solar_declination(when: date) -> float:
    return astro.sun_declination(when)


@_m("sun_zodiac_sign", "Which of the twelve signs the Sun is in, 0 = Aries", "index")
def sun_zodiac_sign(when: date) -> float:
    return float(astro.zodiac_index(astro.sun_longitude(when)))


@_m("daylight_hours", "Hours of daylight at 51.5 deg N (London)", "hours")
def daylight_hours(when: date) -> float:
    decl = math.radians(astro.sun_declination(when))
    lat = math.radians(astro.LONDON_LAT)
    cos_h = -math.tan(lat) * math.tan(decl)
    cos_h = max(-1.0, min(1.0, cos_h))
    return 2 * math.degrees(math.acos(cos_h)) / 15.0


@_m("sidereal_time",
    "Sidereal time at London midnight — which constellations are overhead", "degrees")
def sidereal_time(when: date) -> float:
    return astro.local_sidereal_time(when)


@_m("sunspot_cycle_phase",
    "Position in the ~11-year solar cycle, 0 at minimum and 1 at maximum", "fraction")
def sunspot_cycle_phase(when: date) -> float:
    phase = ((_days(when) - _SOLAR_MIN_REF) % _SOLAR_CYCLE_DAYS) / _SOLAR_CYCLE_DAYS
    return (1.0 - math.cos(2 * math.pi * phase)) / 2.0


def _planet_longitude_metric(planet: str) -> None:
    _m(f"{planet}_longitude", f"Geocentric ecliptic longitude of {planet.title()}",
       "degrees")(lambda when, _p=planet: astro.planet_longitude(_p, when))


def _planet_retrograde_metric(planet: str) -> None:
    _m(f"{planet}_retrograde",
       f"1 while {planet.title()} is apparently moving backwards, else 0",
       "boolean")(lambda when, _p=planet: astro.planet_is_retrograde(_p, when))


def _planet_elongation_metric(planet: str) -> None:
    _m(f"{planet}_elongation",
       f"Angle between {planet.title()} and the Sun as seen from Earth", "degrees")(
        lambda when, _p=planet: astro.planet_elongation(_p, when))


for _planet in ("mercury", "venus", "mars", "jupiter", "saturn"):
    _planet_longitude_metric(_planet)
for _planet in ("mercury", "venus", "mars"):
    _planet_retrograde_metric(_planet)
for _planet in ("mercury", "venus", "mars", "jupiter"):
    _planet_elongation_metric(_planet)


def _star_altitude_metric(star: str) -> None:
    _m(f"{star}_altitude",
       f"Height of {star.title()} above the London horizon at midnight; "
       "negative means below it", "degrees")(
        lambda when, _s=star: astro.star_altitude(_s, when))


for _star in ("sirius", "betelgeuse", "vega", "arcturus", "antares", "aldebaran"):
    _star_altitude_metric(_star)


@_m("day_of_week", "Monday 0 through Sunday 6", "index")
def day_of_week(when: date) -> float:
    return float(when.weekday())


@_m("is_friday_thirteenth", "1 on a Friday the 13th, 0 otherwise", "boolean")
def is_friday_thirteenth(when: date) -> float:
    return 1.0 if when.day == 13 and when.weekday() == 4 else 0.0


@_m("date_digit_sum", "Digit sum of the date written as YYYYMMDD", "count")
def date_digit_sum(when: date) -> float:
    return float(_digit_sum(int(when.strftime("%Y%m%d"))))


@_m("day_of_month", "Calendar day of the month", "index")
def day_of_month(when: date) -> float:
    return float(when.day)


@_m("annual_phase", "Position in the tropical year, 0 at the January epoch", "fraction")
def annual_phase(when: date) -> float:
    return (_days(when) % _TROPICAL_YEAR) / _TROPICAL_YEAR


@_m("pure_noise", "CONTROL: seeded white noise, correlated with nothing", "control")
def pure_noise(when: date) -> float:
    return random.Random(f"noise:{when.toordinal()}").gauss(0.0, 1.0)


@_m("coin_flip", "CONTROL: a fair binary sequence keyed to the date", "control")
def coin_flip(when: date) -> float:
    return float(random.Random(f"coin:{when.toordinal()}").getrandbits(1))


BUILTIN_METRICS: tuple[Metric, ...] = tuple(_REGISTRY)
METRICS_BY_NAME: dict[str, Metric] = {m.name: m for m in BUILTIN_METRICS}
CONTROL_METRICS: tuple[str, ...] = ("pure_noise", "coin_flip")


def default_metrics(names: Sequence[str] | None = None) -> tuple[Metric, ...]:
    """Resolve metric names, or return every built-in metric when ``None``."""
    if names is None:
        return BUILTIN_METRICS
    missing = [n for n in names if n not in METRICS_BY_NAME]
    if missing:
        raise KeyError(f"unknown metric(s): {', '.join(missing)}")
    return tuple(METRICS_BY_NAME[n] for n in names)


@dataclass
class _DatedSeries:
    """Date-indexed samples with nearest-earlier lookup within a tolerance."""

    dates: list[int]
    values: list[float]
    max_staleness_days: int = 7
    _sorted: bool = field(default=False, repr=False)

    def lookup(self, when: date) -> float | None:
        if not self._sorted:
            pairs = sorted(zip(self.dates, self.values))
            self.dates = [p[0] for p in pairs]
            self.values = [p[1] for p in pairs]
            self._sorted = True
        target = when.toordinal()
        index = bisect.bisect_right(self.dates, target) - 1
        if index < 0:
            return None
        if target - self.dates[index] > self.max_staleness_days:
            return None
        return self.values[index]


def metric_from_csv(path: str, *, name: str | None = None, description: str = "",
                    date_column: str = "date", value_column: str = "value",
                    date_format: str | None = None, units: str = "",
                    max_staleness_days: int = 7) -> Metric:
    """Build a metric from a two-column CSV of dates and values.

    Values are carried forward to the draw date, but only for
    ``max_staleness_days``; beyond that the metric reports ``None`` for that
    draw and the draw is dropped from the pair rather than being filled with a
    stale reading.
    """
    dates: list[int] = []
    values: list[float] = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            raw_date = row[date_column].strip()
            raw_value = row[value_column].strip()
            if not raw_date or not raw_value:
                continue
            if date_format:
                parsed = datetime.strptime(raw_date, date_format).date()
            else:
                parsed = datetime.fromisoformat(raw_date).date()
            dates.append(parsed.toordinal())
            values.append(float(raw_value))
    if not dates:
        raise ValueError(f"{path} yielded no usable rows")

    series = _DatedSeries(dates, values, max_staleness_days)
    return Metric(
        name=name or path,
        description=description or f"External series loaded from {path}",
        fn=series.lookup,
        units=units,
    )
