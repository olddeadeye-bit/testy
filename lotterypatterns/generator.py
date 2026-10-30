"""Is there a recognisable algorithm underneath the draws?

If the draws came from a software generator rather than physical balls, a weak
one leaves fingerprints. This module looks for three:

* **Repeats.** A generator with a small internal state must eventually repeat
  itself, and then identical draws recur far more often than chance allows.
  There are 45 million possible Lotto lines, so among 5,000 draws about 0.28
  identical pairs are expected. Dozens would mean a short cycle.
* **Linear structure.** Shift-register style generators are exactly predictable
  from a short window of output. The Berlekamp-Massey algorithm measures how
  long a linear recurrence is needed to reproduce a bit stream; a random one
  needs about half its length, a linear one needs far less.
* **A hidden rhythm.** A cycle too long to repeat exactly can still show as a
  sharp peak in the frequency spectrum of a draw-level series.

Limits, stated because they decide what a clean result means. Published
archives store each draw's numbers sorted, which destroys the order the
generator produced them in, so only gross weaknesses can show. And a good
generator is built to pass every test like these. A clean result therefore rules
out sloppy generators; it cannot rule out a competent one.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from .draws import DrawHistory
from .stats import benjamini_hochberg


# --------------------------------------------------------------------------
# Linear complexity
# --------------------------------------------------------------------------

def linear_complexity(bits: list[int]) -> int:
    """Length of the shortest linear feedback shift register producing ``bits``.

    Berlekamp-Massey over GF(2), with the polynomials held as Python integers
    so that each step is a handful of word-wide operations.
    """
    c, b = 1, 1
    length, last = 0, -1
    history = 0                     # bit i holds the sample i steps back
    for n, bit in enumerate(bits):
        history = (history << 1) | bit
        discrepancy = (c & history).bit_count() & 1
        if discrepancy:
            t = c
            c ^= b << (n - last)
            if 2 * length <= n:
                length = n + 1 - length
                b = t
                last = n
    return length


def expected_linear_complexity(n: int) -> float:
    """Mean linear complexity of a uniformly random n-bit sequence."""
    return n / 2.0 + (4 + (n % 2)) / 18.0


def linear_complexity_p(n: int, observed: int) -> float:
    """Chance a random n-bit sequence needs a recurrence this short or shorter.

    The complexity of a random sequence sits within a few units of n/2 and its
    deviation d = L - floor(n/2) has an exact geometric law, found by Rueppel:

        even n:  P(d = -j) = 2^-(2j+1),    P(0) = 1/2,   P(d = +j) = 2^-(2j)
        odd  n:  P(d = -j) = 2^-(2j+2),    P(0) = 1/4,   P(d = 1+j) = 2^-(2j+1)

    (and P(d = 1) = 1/2 for odd n). Only the lower tail is used, because a
    short recurrence is the signature of an algorithm. A sequence that is
    unusually complex is not evidence of one.
    """
    d = observed - n // 2
    even = n % 2 == 0
    if d < 0:
        m = -d
        return (2.0 ** (-2 * m + 1) / 3.0) if even else (2.0 ** (-2 * m) / 3.0)
    if d == 0:
        return 2.0 / 3.0 if even else 1.0 / 3.0
    if even:
        return 1.0 - 2.0 ** (-2 * d) / 3.0
    return 1.0 - 2.0 ** (-2 * d + 1) / 3.0


# --------------------------------------------------------------------------
# Frequency spectrum
# --------------------------------------------------------------------------

def _fft(values: list[complex]) -> list[complex]:
    n = len(values)
    if n & (n - 1):
        raise ValueError("length must be a power of two")
    j = 0
    out = list(values)
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            out[i], out[j] = out[j], out[i]
    size = 2
    while size <= n:
        angle = -2.0 * math.pi / size
        w_step = complex(math.cos(angle), math.sin(angle))
        for start in range(0, n, size):
            w = 1 + 0j
            half = size // 2
            for k in range(half):
                u = out[start + k]
                v = out[start + k + half] * w
                out[start + k] = u + v
                out[start + k + half] = u - v
                w *= w_step
        size *= 2
    return out


def spectral_peak(series: list[float]) -> tuple[float, int, float]:
    """Strongest frequency in a series: (normalised power, period, p-value).

    Under white noise each frequency's power, scaled by the series variance, is
    exponentially distributed, so the chance that the strongest of ``m``
    frequencies reaches ``g`` is about ``m * exp(-g)``.
    """
    n = 1 << (len(series).bit_length() - 1)      # largest power of two that fits
    x = series[:n]
    mean = statistics.fmean(x)
    var = statistics.pvariance(x)
    if var == 0:
        return 0.0, 0, 1.0
    spectrum = _fft([complex(v - mean) for v in x])
    half = n // 2
    powers = [abs(spectrum[k]) ** 2 / (n * var) for k in range(1, half)]
    best = max(range(len(powers)), key=powers.__getitem__)
    g = powers[best]
    p = min(1.0, len(powers) * math.exp(-g))
    return g, round(n / (best + 1)), p


# --------------------------------------------------------------------------
# Repeats
# --------------------------------------------------------------------------

def duplicate_draws(history: DrawHistory) -> tuple[int, float, float]:
    """Identical draws found, how many chance predicts, and the p-value."""
    seen: dict[tuple[int, ...], int] = {}
    for draw in history:
        key = draw.sorted_numbers
        seen[key] = seen.get(key, 0) + 1
    observed = sum(c * (c - 1) // 2 for c in seen.values())
    n = len(history)
    space = math.comb(history.pool, history.picks)
    expected = n * (n - 1) / 2 / space
    # Poisson upper tail: P(X >= observed).
    p, term = 0.0, math.exp(-expected)
    cumulative = 0.0
    for k in range(observed):
        cumulative += term
        term *= expected / (k + 1)
    p = max(0.0, 1.0 - cumulative) if observed else 1.0
    return observed, expected, p


# --------------------------------------------------------------------------
# The battery
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Clue:
    name: str
    detail: str
    p_value: float
    q_value: float = 1.0

    @property
    def flagged(self) -> bool:
        return self.q_value <= 0.05


def bit_streams(history: DrawHistory) -> dict[str, list[int]]:
    """Balanced yes/no streams that do not depend on the order balls came out.

    Each must be a genuinely different stream. The parity of a draw's sum is the
    parity of its odd-ball count, so offering both would test one thing twice
    and quietly inflate the correction.
    """
    sums = [sum(d.numbers) for d in history]
    median = statistics.median(sums)
    low = history.pool // 2
    return {
        "sum is odd": [s & 1 for s in sums],
        "sum above median": [1 if s > median else 0 for s in sums],
        "low-ball count is odd":
            [sum(1 for n in d.numbers if n <= low) & 1 for d in history],
    }


def hunt(history: DrawHistory) -> list[Clue]:
    """Run every test and correct across all of them."""
    raw: list[tuple[str, str, float]] = []

    observed, expected, p = duplicate_draws(history)
    raw.append(("repeated draws",
                f"{observed} identical pair(s) found, {expected:.2f} expected", p))

    for name, bits in bit_streams(history).items():
        n, length = len(bits), linear_complexity(bits)
        raw.append((f"linear complexity of '{name}'",
                    f"shortest recurrence has {length} terms; a random stream of "
                    f"{n:,} bits needs about {n // 2:,}",
                    linear_complexity_p(n, length)))

    sums = [float(sum(d.numbers)) for d in history]
    g, period, p = spectral_peak(sums)
    raw.append(("spectral peak in the draw sums",
                f"strongest rhythm repeats every {period} draws, power {g:.1f}", p))

    qs = benjamini_hochberg([r[2] for r in raw])
    return [Clue(n, d, p, q) for (n, d, p), q in zip(raw, qs)]


def summary(history: DrawHistory, clues: list[Clue]) -> str:
    lines = [f"Generator hunt - {history.name}, {len(history):,} draws", "=" * 64]
    for c in clues:
        mark = "FLAGGED" if c.flagged else "clean  "
        lines.append(f"  [{mark}] {c.name}")
        lines.append(f"            {c.detail}   p={c.p_value:.3g} q={c.q_value:.3g}")
    lines.append("")
    if any(c.flagged for c in clues):
        lines.append("Something looks like a recognisable generator. Confirm it on "
                     "draws that were not part of this test before believing it.")
    else:
        lines.append("No fingerprint of a weak generator. That rules out repeating "
                     "cycles, short linear recurrences and obvious rhythms. It does "
                     "not rule out a competent generator, which is built to pass "
                     "exactly these tests.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Planted generators, to check the hunt can find what it claims to
# --------------------------------------------------------------------------

def _lcg(modulus: int, a: int, c: int, seed: int, shift: int = 0, mask: int | None = None):
    state = seed
    while True:
        state = (a * state + c) % modulus
        out = state >> shift
        yield out if mask is None else out & mask


def _lfsr16(seed: int = 0xACE1):
    """A maximal 16-bit shift register (taps 16, 14, 13, 11); outputs its state."""
    state = seed
    while True:
        bit = ((state >> 0) ^ (state >> 2) ^ (state >> 3) ^ (state >> 5)) & 1
        state = (state >> 1) | (bit << 15)
        yield state


def _mersenne(seed: int):
    import random
    rng = random.Random(seed)
    while True:
        yield rng.getrandbits(32)


GENERATORS = {
    "toy LCG (4,096 states)":
        lambda seed: _lcg(4096, 1229, 1, seed % 4096),
    "classic C rand() LCG":
        lambda seed: _lcg(2 ** 31, 1103515245, 12345, seed, shift=16, mask=0x7FFF),
    "16-bit shift register":
        lambda seed: _lfsr16(seed % 65535 + 1),
    "Mersenne Twister":
        _mersenne,
}


def plant(generator: str, count: int, *, pool: int = 49, picks: int = 6,
          seed: int = 1) -> DrawHistory:
    """Draws made the naive way: ball = output mod pool, skipping repeats."""
    from datetime import date, timedelta

    from .draws import Draw

    source = GENERATORS[generator](seed)
    draws, when = [], date(2000, 1, 1)
    for _ in range(count):
        chosen: list[int] = []
        while len(chosen) < picks:
            ball = next(source) % pool + 1
            if ball not in chosen:
                chosen.append(ball)
        draws.append(Draw(when, tuple(sorted(chosen))))      # sorted, like real archives
        when += timedelta(days=3)
    return DrawHistory(draws, pool=pool, picks=picks, name=generator)
