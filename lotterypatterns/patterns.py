"""Structural pattern tests: does the draw sequence depart from randomness?

The metric search asks whether draws track something outside them. This asks
whether the draws have structure *inside* them, which is where a real defect
would actually show:

* **Pairs** — do particular numbers come up together more than chance allows?
* **Positions** — is the first ball out of the machine distributed like the last?
* **Recency** — do numbers sleep longer, or return sooner, than they should?
* **Machines and ball sets** — the operator records which physical machine and
  which set of balls was used. If one of them misbehaves, this is where it shows.
* **Serial dependence** — does one draw carry information about the next?
* **Periodicity** — does any number recur on a rhythm?

Every test corrects for how many were run. A finding here would be worth
something precisely because these mechanisms are physical rather than mystical:
balls wear, machines drift, and operators retire equipment over it.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .draws import DrawHistory
from .stats import (
    benjamini_hochberg,
    binomial_z_test,
    chi_square_sf,
    chi_square_uniform,
    normal_sf,
    pearson,
)


@dataclass(frozen=True)
class Finding:
    """One structural test, with its correction already applied."""

    kind: str
    label: str
    statistic: float
    p_value: float
    q_value: float
    detail: str = ""

    @property
    def significant(self) -> bool:
        return self.q_value <= 0.05

    def __str__(self) -> str:
        mark = "*" if self.significant else " "
        return (f"{mark} [{self.kind}] {self.label}: stat={self.statistic:+.3f} "
                f"p={self.p_value:.4g} q={self.q_value:.4g}"
                + (f" — {self.detail}" if self.detail else ""))


@dataclass
class PatternReport:
    """Everything the structural battery tested, with the survivors marked."""

    findings: list[Finding]
    draws: int
    game: str = "lottery"
    alpha: float = 0.05
    notes: list[str] = field(default_factory=list)

    @property
    def survivors(self) -> list[Finding]:
        return sorted((f for f in self.findings if f.q_value <= self.alpha),
                      key=lambda f: f.q_value)

    def by_kind(self, kind: str) -> list[Finding]:
        return sorted((f for f in self.findings if f.kind == kind),
                      key=lambda f: f.p_value)

    def strongest(self, limit: int = 10) -> list[Finding]:
        return sorted(self.findings, key=lambda f: f.p_value)[:limit]

    def summary(self) -> str:
        kinds = sorted({f.kind for f in self.findings})
        lines = [
            f"Structural pattern tests — {self.game}, {self.draws:,} draws",
            "=" * 62,
            f"Tests run: {len(self.findings):,} across {len(kinds)} families "
            f"({', '.join(kinds)})",
            "",
        ]
        for note in self.notes:
            lines.append(f"  note: {note}")
        if self.notes:
            lines.append("")
        if self.survivors:
            lines.append(f"SURVIVED CORRECTION: {len(self.survivors)}")
            for finding in self.survivors[:15]:
                lines.append(f"  {finding}")
            lines.append("")
            lines.append("Check these on draws outside this history before acting "
                         "on them.")
        else:
            lines.append("SURVIVED CORRECTION: none.")
            lines.append("No structural departure from randomness at this sample size.")
            lines.append("")
            lines.append("Strongest results anyway, for reference — these are what "
                         "chance produces:")
            for finding in self.strongest(5):
                lines.append(f"  {finding}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Individual test families
# --------------------------------------------------------------------------

def pair_findings(history: DrawHistory) -> list[tuple[str, str, float, float]]:
    """Do any two numbers come up together more often than chance allows?

    With 59 balls there are 1,711 pairs, so a handful will always look
    remarkable. The correction applied later is what decides.
    """
    pool, picks, n = history.pool, history.picks, len(history)
    counts: Counter[tuple[int, int]] = Counter()
    for draw in history:
        ordered = draw.sorted_numbers
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                counts[(a, b)] += 1
    # P(both in a draw) = C(pool-2, picks-2) / C(pool, picks)
    probability = (math.comb(pool - 2, picks - 2) / math.comb(pool, picks))
    results = []
    for a in range(1, pool + 1):
        for b in range(a + 1, pool + 1):
            observed = counts.get((a, b), 0)
            test = binomial_z_test(observed, n, probability)
            results.append((f"{a} and {b}", f"{observed} together vs "
                            f"{n * probability:.1f} expected",
                            test.statistic, test.p_value))
    return results


def position_findings(history: DrawHistory) -> list[tuple[str, str, float, float]]:
    """Is the ball drawn first distributed like the ball drawn last?

    Only meaningful if the archive records balls in the order they came out.
    A machine that favours certain balls early would show here and nowhere else.
    """
    picks = history.picks
    results = []
    for position in range(picks):
        values = [draw.numbers[position] for draw in history
                  if len(draw.numbers) > position]
        if len(values) < 30:
            continue
        counts = [0] * history.pool
        for value in values:
            counts[value - 1] += 1
        test = chi_square_uniform(counts)
        results.append((f"position {position + 1} evenness",
                        f"mean ball {statistics.fmean(values):.1f}",
                        test.statistic, test.p_value))

    # If the file stores balls already sorted, position 1 is always the lowest
    # and this whole family is meaningless — say so rather than reporting it.
    return results


def recency_findings(history: DrawHistory) -> list[tuple[str, str, float, float]]:
    """Do numbers sleep longer than they should before returning?

    Gaps between appearances of a given ball follow a geometric distribution
    with mean pool/picks. A ball that genuinely runs hot returns sooner; one
    that is sticking returns later.
    """
    pool, picks = history.pool, history.picks
    expected_gap = pool / picks
    last_seen: dict[int, int] = {}
    gaps: dict[int, list[int]] = defaultdict(list)
    for index, draw in enumerate(history):
        for number in draw.numbers:
            if number in last_seen:
                gaps[number].append(index - last_seen[number])
            last_seen[number] = index

    results = []
    for number in range(1, pool + 1):
        observed = gaps.get(number, [])
        if len(observed) < 20:
            continue
        mean_gap = statistics.fmean(observed)
        # Geometric with p = picks/pool: variance is (1-p)/p^2.
        p = picks / pool
        sd_of_mean = math.sqrt((1 - p) / (p * p)) / math.sqrt(len(observed))
        z = (mean_gap - expected_gap) / sd_of_mean if sd_of_mean else 0.0
        results.append((f"ball {number} return time",
                        f"average gap {mean_gap:.1f} draws vs {expected_gap:.1f} expected",
                        z, normal_sf(z)))
    return results


def machine_findings(history: DrawHistory) -> tuple[list, list[str]]:
    """Does one physical machine, or one ball set, draw differently from another?

    This is the most credible pattern in the whole package. Machines and ball
    sets are physical objects that wear, and operators publish which was used.
    """
    results: list[tuple[str, str, float, float]] = []
    notes: list[str] = []

    for attribute, label in (("machine", "machine"), ("ball_set", "ball set")):
        groups: dict[str, list] = defaultdict(list)
        for draw in history:
            key = getattr(draw, attribute)
            if key:
                groups[key].append(draw)
        usable = {k: v for k, v in groups.items() if len(v) >= 50}
        if not usable:
            notes.append(f"no {label} recorded in this archive, so that family "
                         "was skipped")
            continue
        notes.append(f"{len(usable)} {label}s with enough draws to test "
                     f"({', '.join(sorted(usable))})")

        for key, draws in sorted(usable.items()):
            counts = [0] * history.pool
            for draw in draws:
                for number in draw.numbers:
                    counts[number - 1] += 1
            test = chi_square_uniform(counts)
            results.append((f"{label} {key} evenness",
                            f"{len(draws)} draws", test.statistic, test.p_value))

        # And whether the groups differ from *each other*, which is the real
        # question — a shared quirk would cancel out in the per-group tests.
        if len(usable) >= 2:
            keys = sorted(usable)
            table = []
            for key in keys:
                counts = [0] * history.pool
                for draw in usable[key]:
                    for number in draw.numbers:
                        counts[number - 1] += 1
                table.append(counts)
            statistic, df = _contingency_chi_square(table)
            results.append((f"{label}s differ from each other",
                            f"{len(keys)} groups compared",
                            statistic, chi_square_sf(statistic, df)))
    return results, notes


def _contingency_chi_square(table: list[list[int]]) -> tuple[float, int]:
    """Chi-square test of independence on a rows-by-columns count table."""
    rows = len(table)
    columns = len(table[0])
    row_totals = [sum(row) for row in table]
    column_totals = [sum(table[r][c] for r in range(rows)) for c in range(columns)]
    grand = sum(row_totals)
    if grand == 0:
        return 0.0, 1
    statistic = 0.0
    used_columns = 0
    for c in range(columns):
        if column_totals[c] == 0:
            continue
        used_columns += 1
        for r in range(rows):
            expected = row_totals[r] * column_totals[c] / grand
            if expected > 0:
                statistic += (table[r][c] - expected) ** 2 / expected
    return statistic, max(1, (rows - 1) * (used_columns - 1))


def serial_findings(history: DrawHistory) -> list[tuple[str, str, float, float]]:
    """Does one draw tell you anything about the next?

    If draws are independent — and they should be — the sum, the odd count and
    the carry-over from one draw carry no information about the following one.
    """
    sums = [float(sum(d.numbers)) for d in history]
    odds = [float(sum(1 for n in d.numbers if n % 2)) for d in history]
    lows = [float(sum(1 for n in d.numbers if n <= history.pool // 2)) for d in history]

    results = []
    for name, series in (("sum", sums), ("odd count", odds), ("low count", lows)):
        for lag in (1, 2, 3):
            if len(series) <= lag + 10:
                continue
            test = pearson(series[lag:], series[:-lag])
            results.append((f"{name} vs {lag} draw(s) earlier",
                            f"correlation {test.statistic:+.3f}",
                            test.statistic, test.p_value))

    # Carry-over: how many balls repeat from the previous draw, against the
    # hypergeometric expectation.
    repeats = [len(set(a.numbers) & set(b.numbers))
               for a, b in zip(history, list(history)[1:])]
    if repeats:
        expected = history.picks * history.picks / history.pool
        variance = (history.picks * (history.picks / history.pool)
                    * (1 - history.picks / history.pool))
        sd = math.sqrt(variance / len(repeats)) if variance > 0 else 0.0
        z = (statistics.fmean(repeats) - expected) / sd if sd else 0.0
        results.append(("carry-over from previous draw",
                        f"average {statistics.fmean(repeats):.3f} repeats vs "
                        f"{expected:.3f} expected", z, normal_sf(z)))
    return results


def periodicity_findings(history: DrawHistory,
                         periods: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 10, 12, 14)
                         ) -> list[tuple[str, str, float, float]]:
    """Does any ball recur on a rhythm — every seventh draw, say?

    A Rayleigh test on the phase of each appearance. Uniform phases mean no
    rhythm; clustered phases mean the ball favours a position in the cycle.
    """
    results = []
    n = len(history)
    for period in periods:
        if n < period * 12:
            continue
        for number in range(1, history.pool + 1):
            phases = [(index % period) / period * 2 * math.pi
                      for index, draw in enumerate(history)
                      if number in draw.numbers]
            if len(phases) < 25:
                continue
            cos_sum = sum(math.cos(p) for p in phases)
            sin_sum = sum(math.sin(p) for p in phases)
            resultant = math.hypot(cos_sum, sin_sum) / len(phases)
            # Rayleigh: 2n*R^2 is approximately chi-square with 2 df.
            statistic = 2 * len(phases) * resultant * resultant
            results.append((f"ball {number} every {period} draws",
                            f"{len(phases)} appearances, concentration {resultant:.3f}",
                            statistic, math.exp(-statistic / 2)))
    return results


# --------------------------------------------------------------------------
# The battery
# --------------------------------------------------------------------------

FAMILIES = ("pairs", "positions", "recency", "machines", "serial", "periodicity")


def find_patterns(history: DrawHistory, *, families: tuple[str, ...] = FAMILIES,
                  alpha: float = 0.05) -> PatternReport:
    """Run every structural test and correct across the whole battery."""
    raw: list[tuple[str, str, str, float, float]] = []
    notes: list[str] = []

    if "pairs" in families:
        for label, detail, statistic, p in pair_findings(history):
            raw.append(("pairs", label, detail, statistic, p))
    if "positions" in families:
        sorted_already = all(list(d.numbers) == sorted(d.numbers) for d in history)
        if sorted_already:
            notes.append("this archive stores each draw in ascending order, not "
                         "the order the balls came out, so position tests were "
                         "skipped — they would only rediscover the sorting")
        else:
            for label, detail, statistic, p in position_findings(history):
                raw.append(("positions", label, detail, statistic, p))
    if "recency" in families:
        for label, detail, statistic, p in recency_findings(history):
            raw.append(("recency", label, detail, statistic, p))
    if "machines" in families:
        machine_results, machine_notes = machine_findings(history)
        notes.extend(machine_notes)
        for label, detail, statistic, p in machine_results:
            raw.append(("machines", label, detail, statistic, p))
    if "serial" in families:
        for label, detail, statistic, p in serial_findings(history):
            raw.append(("serial", label, detail, statistic, p))
    if "periodicity" in families:
        for label, detail, statistic, p in periodicity_findings(history):
            raw.append(("periodicity", label, detail, statistic, p))

    q_values = benjamini_hochberg([r[4] for r in raw]) if raw else []
    findings = [
        Finding(kind=kind, label=label, detail=detail, statistic=statistic,
                p_value=p, q_value=q)
        for (kind, label, detail, statistic, p), q in zip(raw, q_values)
    ]
    return PatternReport(findings=findings, draws=len(history),
                         game=history.name, alpha=alpha, notes=notes)
