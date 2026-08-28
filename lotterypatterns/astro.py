"""Positions of the Sun, Moon, planets and stars, computed from the date alone.

Standard astronomical algorithms (Meeus, *Astronomical Algorithms*, 2nd ed.),
truncated to the terms that matter at this scale. Accuracy is around an
arcminute for the Sun, a few arcminutes for the Moon and roughly a tenth of a
degree for the planets — far finer than any use this package puts them to, and
achieved with no ephemeris file and no network.

Angles are degrees unless a name says otherwise. Times are 00:00 UTC on the
given date, which is the resolution a draw date gives us anyway.
"""

from __future__ import annotations

import math
from datetime import date

RAD = math.pi / 180.0
LONDON_LAT = 51.4779
LONDON_LON = -0.0015


def julian_day(when: date, hour: float = 0.0) -> float:
    """Julian Day number for 00:00 UTC (or a given decimal hour) on ``when``."""
    year, month, day = when.year, when.month, when.day
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    return (math.floor(365.25 * (year + 4716))
            + math.floor(30.6001 * (month + 1))
            + day + b - 1524.5 + hour / 24.0)


def julian_centuries(when: date) -> float:
    """Centuries of 36525 days since J2000.0 — the argument every series uses."""
    return (julian_day(when) - 2451545.0) / 36525.0


def _norm(angle: float) -> float:
    return angle % 360.0


def _norm180(angle: float) -> float:
    """Wrap to (-180, 180] — the right range for a latitude or a declination."""
    return (angle + 180.0) % 360.0 - 180.0


# --------------------------------------------------------------------------
# The Sun
# --------------------------------------------------------------------------

def sun_longitude(when: date) -> float:
    """Apparent ecliptic longitude of the Sun. This *is* the time of year."""
    t = julian_centuries(when)
    mean_lon = _norm(280.46646 + 36000.76983 * t + 0.0003032 * t * t)
    anomaly = _norm(357.52911 + 35999.05029 * t - 0.0001537 * t * t)
    centre = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(anomaly * RAD)
              + (0.019993 - 0.000101 * t) * math.sin(2 * anomaly * RAD)
              + 0.000289 * math.sin(3 * anomaly * RAD))
    true_lon = mean_lon + centre
    omega = 125.04 - 1934.136 * t
    return _norm(true_lon - 0.00569 - 0.00478 * math.sin(omega * RAD))


def sun_mean_anomaly(when: date) -> float:
    t = julian_centuries(when)
    return _norm(357.52911 + 35999.05029 * t - 0.0001537 * t * t)


def obliquity(when: date) -> float:
    """Obliquity of the ecliptic — the tilt that gives us seasons."""
    t = julian_centuries(when)
    return (23.439291 - 0.0130042 * t - 1.64e-7 * t * t + 5.036e-7 * t ** 3)


def _to_equatorial(lon: float, lat: float, eps: float) -> tuple[float, float]:
    """Ecliptic longitude and latitude to right ascension and declination."""
    lon_r, lat_r, eps_r = lon * RAD, lat * RAD, eps * RAD
    ra = math.atan2(
        math.sin(lon_r) * math.cos(eps_r) - math.tan(lat_r) * math.sin(eps_r),
        math.cos(lon_r),
    ) / RAD
    dec = math.asin(
        math.sin(lat_r) * math.cos(eps_r)
        + math.cos(lat_r) * math.sin(eps_r) * math.sin(lon_r)
    ) / RAD
    return _norm(ra), dec


def sun_declination(when: date) -> float:
    return _to_equatorial(sun_longitude(when), 0.0, obliquity(when))[1]


def sun_right_ascension(when: date) -> float:
    return _to_equatorial(sun_longitude(when), 0.0, obliquity(when))[0]


# --------------------------------------------------------------------------
# The Moon
# --------------------------------------------------------------------------

def _moon_elements(when: date) -> tuple[float, ...]:
    t = julian_centuries(when)
    lon = _norm(218.3164477 + 481267.88123421 * t - 0.0015786 * t * t)      # L'
    elong = _norm(297.8501921 + 445267.1114034 * t - 0.0018819 * t * t)     # D
    sun_anom = _norm(357.5291092 + 35999.0502909 * t - 0.0001536 * t * t)   # M
    moon_anom = _norm(134.9633964 + 477198.8675055 * t + 0.0087414 * t * t)  # M'
    arg_lat = _norm(93.2720950 + 483202.0175233 * t - 0.0036539 * t * t)    # F
    return t, lon, elong, sun_anom, moon_anom, arg_lat


def moon_longitude(when: date) -> float:
    """Apparent ecliptic longitude of the Moon — where it sits in the zodiac."""
    _t, lon, d, m, mp, f = _moon_elements(when)
    d_r, m_r, mp_r, f_r = d * RAD, m * RAD, mp * RAD, f * RAD
    correction = (
        6.288774 * math.sin(mp_r)
        + 1.274027 * math.sin(2 * d_r - mp_r)
        + 0.658314 * math.sin(2 * d_r)
        + 0.213618 * math.sin(2 * mp_r)
        - 0.185116 * math.sin(m_r)
        - 0.114332 * math.sin(2 * f_r)
        + 0.058793 * math.sin(2 * d_r - 2 * mp_r)
        + 0.057066 * math.sin(2 * d_r - m_r - mp_r)
        + 0.053322 * math.sin(2 * d_r + mp_r)
        + 0.045758 * math.sin(2 * d_r - m_r)
        - 0.040923 * math.sin(m_r - mp_r)
        - 0.034720 * math.sin(d_r)
        - 0.030383 * math.sin(m_r + mp_r)
        + 0.015327 * math.sin(2 * d_r - 2 * f_r)
        - 0.012528 * math.sin(mp_r + 2 * f_r)
        + 0.010980 * math.sin(mp_r - 2 * f_r)
        + 0.010675 * math.sin(4 * d_r - mp_r)
        + 0.010034 * math.sin(3 * mp_r)
        + 0.008548 * math.sin(4 * d_r - 2 * mp_r)
    )
    return _norm(lon + correction)


def moon_latitude(when: date) -> float:
    """Ecliptic latitude of the Moon — how far it rides above or below the path."""
    _t, _lon, d, m, mp, f = _moon_elements(when)
    d_r, m_r, mp_r, f_r = d * RAD, m * RAD, mp * RAD, f * RAD
    return (
        5.128122 * math.sin(f_r)
        + 0.280602 * math.sin(mp_r + f_r)
        + 0.277693 * math.sin(mp_r - f_r)
        + 0.173237 * math.sin(2 * d_r - f_r)
        + 0.055413 * math.sin(2 * d_r - mp_r + f_r)
        + 0.046271 * math.sin(2 * d_r - mp_r - f_r)
        + 0.032573 * math.sin(2 * d_r + f_r)
        + 0.017198 * math.sin(2 * mp_r + f_r)
        + 0.009266 * math.sin(2 * d_r + mp_r - f_r)
    )


def moon_distance_km(when: date) -> float:
    """Earth-Moon distance. Perigee is near 356,500 km, apogee near 406,700."""
    _t, _lon, d, m, mp, f = _moon_elements(when)
    d_r, m_r, mp_r = d * RAD, m * RAD, mp * RAD
    return (385000.56
            - 20905.355 * math.cos(mp_r)
            - 3699.111 * math.cos(2 * d_r - mp_r)
            - 2955.968 * math.cos(2 * d_r)
            - 569.925 * math.cos(2 * mp_r)
            + 48.888 * math.cos(m_r)
            - 152.138 * math.cos(2 * d_r - 2 * mp_r)
            - 170.733 * math.cos(2 * d_r + mp_r)
            - 204.586 * math.cos(2 * d_r - m_r)
            - 129.620 * math.cos(m_r - mp_r)
            + 108.743 * math.cos(d_r)
            + 104.755 * math.cos(m_r + mp_r))


def moon_declination(when: date) -> float:
    """Declination of the Moon — its height in the sky, the 18.6-year swing."""
    return _to_equatorial(moon_longitude(when), moon_latitude(when), obliquity(when))[1]


def moon_right_ascension(when: date) -> float:
    return _to_equatorial(moon_longitude(when), moon_latitude(when), obliquity(when))[0]


def moon_phase_angle(when: date) -> float:
    """Sun-Moon elongation: 0 at new moon, 180 at full."""
    return _norm(moon_longitude(when) - sun_longitude(when))


def moon_illuminated_fraction(when: date) -> float:
    """Fraction of the Moon's disc lit, from the true positions of both bodies."""
    return (1.0 - math.cos(moon_phase_angle(when) * RAD)) / 2.0


def lunar_node_longitude(when: date) -> float:
    """Mean ascending node — the eclipse points, on an 18.6-year cycle."""
    t = julian_centuries(when)
    return _norm(125.0445479 - 1934.1362891 * t + 0.0020754 * t * t)


# --------------------------------------------------------------------------
# The planets
# --------------------------------------------------------------------------
# Mean Keplerian elements at J2000 with linear rates (JPL, valid 1800-2050):
# semi-major axis (AU), eccentricity, inclination, mean longitude,
# longitude of perihelion, longitude of ascending node — value then per-century rate.
_PLANETS: dict[str, tuple[tuple[float, float], ...]] = {
    "mercury": ((0.38709927, 0.00000037), (0.20563593, 0.00001906),
                (7.00497902, -0.00594749), (252.25032350, 149472.67411175),
                (77.45779628, 0.16047689), (48.33076593, -0.12534081)),
    "venus": ((0.72333566, 0.00000390), (0.00677672, -0.00004107),
              (3.39467605, -0.00078890), (181.97909950, 58517.81538729),
              (131.60246718, 0.00268329), (76.67984255, -0.27769418)),
    "earth": ((1.00000261, 0.00000562), (0.01671123, -0.00004392),
              (-0.00001531, -0.01294668), (100.46457166, 35999.37244981),
              (102.93768193, 0.32327364), (0.0, 0.0)),
    "mars": ((1.52371034, 0.00001847), (0.09339410, 0.00007882),
             (1.84969142, -0.00813131), (-4.55343205, 19140.30268499),
             (-23.94362959, 0.44441088), (49.55953891, -0.29257343)),
    "jupiter": ((5.20288700, -0.00011607), (0.04838624, -0.00013253),
                (1.30439695, -0.00183714), (34.39644051, 3034.74612775),
                (14.72847983, 0.21252668), (100.47390909, 0.20469106)),
    "saturn": ((9.53667594, -0.00125060), (0.05386179, -0.00050991),
               (2.48599187, 0.00193609), (49.95424423, 1222.49362201),
               (92.59887831, -0.41897216), (113.66242448, -0.28867794)),
    "uranus": ((19.18916464, -0.00196176), (0.04725744, -0.00004397),
               (0.77263783, -0.00242939), (313.23810451, 428.48202785),
               (170.95427630, 0.40805281), (74.01692503, 0.04240589)),
    "neptune": ((30.06992276, 0.00026291), (0.00859048, 0.00005105),
                (1.77004347, 0.00035372), (-55.12002969, 218.45945325),
                (44.96476227, -0.32241464), (131.78422574, -0.00508664)),
}

PLANET_NAMES: tuple[str, ...] = ("mercury", "venus", "mars", "jupiter", "saturn",
                                 "uranus", "neptune")


def _solve_kepler(mean_anomaly: float, ecc: float) -> float:
    """Newton iteration on Kepler's equation. Converges in a handful of passes."""
    m = _norm180(mean_anomaly) * RAD
    e = m + ecc * math.sin(m)
    for _ in range(12):
        delta = (e - ecc * math.sin(e) - m) / (1.0 - ecc * math.cos(e))
        e -= delta
        if abs(delta) < 1e-12:
            break
    return e


def _heliocentric(planet: str, t: float) -> tuple[float, float, float]:
    """Ecliptic rectangular coordinates of a planet, in AU."""
    (a0, ad), (e0, ed), (i0, idot), (l0, ld), (p0, pd), (n0, nd) = _PLANETS[planet]
    a = a0 + ad * t
    ecc = e0 + ed * t
    inc = (i0 + idot * t) * RAD
    mean_lon = l0 + ld * t
    peri = p0 + pd * t
    node = (n0 + nd * t) * RAD

    ecc_anom = _solve_kepler(mean_lon - peri, ecc)
    # Position in the orbital plane, then rotated into the ecliptic frame.
    x_orb = a * (math.cos(ecc_anom) - ecc)
    y_orb = a * math.sqrt(1.0 - ecc * ecc) * math.sin(ecc_anom)
    arg_peri = (peri - (n0 + nd * t)) * RAD
    cos_w, sin_w = math.cos(arg_peri), math.sin(arg_peri)
    x_ecl = x_orb * cos_w - y_orb * sin_w
    y_ecl = x_orb * sin_w + y_orb * cos_w
    return (
        x_ecl * math.cos(node) - y_ecl * math.cos(inc) * math.sin(node),
        x_ecl * math.sin(node) + y_ecl * math.cos(inc) * math.cos(node),
        y_ecl * math.sin(inc),
    )


def planet_longitude(planet: str, when: date) -> float:
    """Geocentric ecliptic longitude of a planet — where you would point at it."""
    if planet not in _PLANETS:
        raise KeyError(f"unknown planet: {planet}")
    t = julian_centuries(when)
    px, py, pz = _heliocentric(planet, t)
    ex, ey, ez = _heliocentric("earth", t)
    return _norm(math.atan2(py - ey, px - ex) / RAD)


def planet_elongation(planet: str, when: date) -> float:
    """Angle between a planet and the Sun as seen from Earth, 0 to 180."""
    return abs(_norm180(planet_longitude(planet, when) - sun_longitude(when)))


def planet_is_retrograde(planet: str, when: date, step_days: int = 3) -> float:
    """1.0 while a planet's apparent motion runs backwards, else 0.0.

    Measured the way an observer would: compare geocentric longitude a few days
    apart and see which way it moved.
    """
    from datetime import timedelta
    before = planet_longitude(planet, when - timedelta(days=step_days))
    after = planet_longitude(planet, when + timedelta(days=step_days))
    return 1.0 if _norm180(after - before) < 0 else 0.0


# --------------------------------------------------------------------------
# The stars
# --------------------------------------------------------------------------

def greenwich_sidereal_time(when: date, hour: float = 0.0) -> float:
    """Sidereal time at Greenwich, in degrees — which stars are overhead."""
    jd = julian_day(when, hour)
    t = (jd - 2451545.0) / 36525.0
    return _norm(280.46061837 + 360.98564736629 * (jd - 2451545.0)
                 + 0.000387933 * t * t - t ** 3 / 38710000.0)


def local_sidereal_time(when: date, longitude: float = LONDON_LON,
                        hour: float = 0.0) -> float:
    return _norm(greenwich_sidereal_time(when, hour) + longitude)


# Bright stars: right ascension and declination at J2000, in degrees.
BRIGHT_STARS: dict[str, tuple[float, float]] = {
    "sirius": (101.28715533, -16.71611586),
    "betelgeuse": (88.79293899, 7.40706400),
    "vega": (279.23473479, 38.78368896),
    "polaris": (37.95456067, 89.26410897),
    "aldebaran": (68.98016279, 16.50930235),
    "antares": (247.35191542, -26.43200261),
    "rigel": (78.63446707, -8.20163837),
    "arcturus": (213.91530029, 19.18240916),
}


def star_altitude(star: str, when: date, hour: float = 0.0,
                  latitude: float = LONDON_LAT,
                  longitude: float = LONDON_LON) -> float:
    """Altitude of a bright star above the horizon, in degrees. Negative is below."""
    if star not in BRIGHT_STARS:
        raise KeyError(f"unknown star: {star}")
    ra, dec = BRIGHT_STARS[star]
    hour_angle = (local_sidereal_time(when, longitude, hour) - ra) * RAD
    lat_r, dec_r = latitude * RAD, dec * RAD
    return math.asin(
        math.sin(lat_r) * math.sin(dec_r)
        + math.cos(lat_r) * math.cos(dec_r) * math.cos(hour_angle)
    ) / RAD


ZODIAC = ("Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
          "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces")


def zodiac_index(longitude: float) -> int:
    """Which of the twelve signs an ecliptic longitude falls in, 0 = Aries."""
    return int(_norm(longitude) // 30)
