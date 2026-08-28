"""Weather metrics: real observations when you fetch them, honest labels when not.

Atmospheric pressure, temperature, humidity, wind and rainfall cannot be
computed from a date — they have to be measured. :func:`fetch_weather`
downloads daily history from the Open-Meteo archive (free, no key, no account)
and caches it as a CSV you can keep, so a search runs offline afterwards.

Where there is no fetched file, :func:`climatology_metrics` offers smooth
seasonal averages instead. Those are labelled *climatology*, not weather: they
carry the time-of-year signal and nothing else, and they are no substitute for
the real series when you are looking for a real effect.
"""

from __future__ import annotations

import csv
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from .metrics import Metric, metric_from_csv

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Daily variables worth having, mapped to the column names we cache them under.
DAILY_VARIABLES: dict[str, str] = {
    "pressure_msl_mean": "pressure_hpa",
    "temperature_2m_mean": "temperature_c",
    "relative_humidity_2m_mean": "humidity_pct",
    "wind_speed_10m_max": "wind_kmh",
    "precipitation_sum": "rain_mm",
    "cloud_cover_mean": "cloud_pct",
}

LONDON = (51.5072, -0.1276)


class WeatherError(Exception):
    """Something went wrong fetching or reading weather data."""


def fetch_weather(start: date, end: date, *, latitude: float = LONDON[0],
                  longitude: float = LONDON[1], path: str = "data/weather.csv",
                  timeout: int = 60) -> str:
    """Download daily weather history and cache it to ``path``.

    Needs a working internet connection. Open-Meteo's archive covers 1940 to
    a few days ago, worldwide, and asks for no key. The file it writes has a
    ``date`` column plus one column per variable, which is exactly the shape
    :func:`weather_metrics` expects.
    """
    if end < start:
        raise WeatherError("The end date is before the start date.")
    if end > date.today():
        end = date.today() - timedelta(days=5)

    query = urllib.parse.urlencode({
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "UTC",
    })
    try:
        with urllib.request.urlopen(f"{ARCHIVE_URL}?{query}", timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise WeatherError(
            f"The weather archive refused the request ({exc.code}). "
            "Check the dates are in the past and the coordinates are valid."
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise WeatherError(
            f"Could not reach the weather archive: {exc}. Are you online?"
        ) from exc

    daily = payload.get("daily")
    if not daily or not daily.get("time"):
        raise WeatherError("The weather archive returned no data for that request.")

    available = [v for v in DAILY_VARIABLES if v in daily]
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date"] + [DAILY_VARIABLES[v] for v in available])
        for i, day in enumerate(daily["time"]):
            row = [day]
            for variable in available:
                value = daily[variable][i]
                row.append("" if value is None else value)
            writer.writerow(row)
    return path


def weather_metrics(path: str = "data/weather.csv", *,
                    max_staleness_days: int = 3) -> list[Metric]:
    """Build one metric per column of a fetched weather file.

    Pressure is the interesting one to most people who ask about weather and
    lotteries: it swings with every passing front, on a timescale of days, and
    it is genuinely unrelated to anything inside a draw machine — which makes
    it a good honest test of whether the search stays quiet.
    """
    if not os.path.exists(path):
        raise WeatherError(
            f"No weather file at {path}. Fetch one first:\n"
            "    python3 -m lotterypatterns fetch --weather --from 2015-01-01"
        )
    with open(path, newline="", encoding="utf-8-sig") as handle:
        headers = next(csv.reader(handle), [])
    columns = [h for h in headers if h != "date"]
    if not columns:
        raise WeatherError(f"{path} has no data columns beside the date.")

    descriptions = {
        "pressure_hpa": "Mean sea-level air pressure, measured",
        "temperature_c": "Mean daily air temperature, measured",
        "humidity_pct": "Mean relative humidity, measured",
        "wind_kmh": "Peak wind speed, measured",
        "rain_mm": "Total rainfall, measured",
        "cloud_pct": "Mean cloud cover, measured",
    }
    metrics = []
    for column in columns:
        metrics.append(metric_from_csv(
            path, name=column, value_column=column,
            description=descriptions.get(column, f"{column}, measured"),
            units="observed", max_staleness_days=max_staleness_days,
        ))
    return metrics


# --------------------------------------------------------------------------
# Offline fallbacks
# --------------------------------------------------------------------------

def _seasonal(when: date, mean: float, amplitude: float, peak_day: int) -> float:
    day_of_year = when.timetuple().tm_yday
    return mean + amplitude * math.cos(2 * math.pi * (day_of_year - peak_day) / 365.25)


def climatology_metrics() -> list[Metric]:
    """Smooth seasonal averages for when no real weather has been fetched.

    These are the *average* shape of a UK year, not what the weather did on any
    particular day. They are worth including because time of year is itself a
    plausible thing to test against — but a correlation with one of these is a
    correlation with the calendar, and nothing more.
    """
    return [
        Metric("pressure_climatology",
               "Typical UK sea-level pressure for the time of year (average, not weather)",
               lambda d: _seasonal(d, 1013.5, 3.5, 15), "hPa (climatology)"),
        Metric("temperature_climatology",
               "Typical UK temperature for the time of year (average, not weather)",
               lambda d: _seasonal(d, 10.5, 7.0, 200), "degC (climatology)"),
        Metric("daylight_change",
               "How fast day length is changing — fastest at the equinoxes",
               lambda d: math.sin(2 * math.pi * (d.timetuple().tm_yday - 80) / 365.25),
               "rate"),
    ]
