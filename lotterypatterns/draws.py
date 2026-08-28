"""Loading and simulating lottery draw history."""

from __future__ import annotations

import csv
import io
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Iterator, Sequence


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date format: {raw!r}")


@dataclass(frozen=True)
class Draw:
    """One drawing: a date, the main balls, and any bonus balls.

    ``machine`` and ``ball_set`` are recorded by the operator and published with
    the results. They matter: a biased ball set or a misbehaving machine would
    show up in one group and not the others, which is a real, testable pattern
    rather than a numerological one.
    """

    drawn_on: date
    numbers: tuple[int, ...]
    bonus: tuple[int, ...] = ()
    machine: str = ""
    ball_set: str = ""

    def __post_init__(self) -> None:
        if not self.numbers:
            raise ValueError(f"draw on {self.drawn_on} has no numbers")
        if len(set(self.numbers)) != len(self.numbers):
            raise ValueError(f"draw on {self.drawn_on} repeats a number: {self.numbers}")

    @property
    def sorted_numbers(self) -> tuple[int, ...]:
        return tuple(sorted(self.numbers))


class DrawHistory(Sequence[Draw]):
    """A chronologically ordered sequence of draws from one lottery game."""

    def __init__(self, draws: Iterable[Draw], *, pool: int, picks: int | None = None,
                 name: str = "lottery") -> None:
        self._draws = tuple(sorted(draws, key=lambda d: d.drawn_on))
        if not self._draws:
            raise ValueError("draw history is empty")
        self.pool = pool
        self.picks = picks if picks is not None else len(self._draws[0].numbers)
        self.name = name
        for draw in self._draws:
            for n in draw.numbers + draw.bonus:
                if not 1 <= n <= pool:
                    raise ValueError(
                        f"draw on {draw.drawn_on} has number {n} outside pool 1..{pool}"
                    )

    def __len__(self) -> int:
        return len(self._draws)

    def __getitem__(self, index):  # type: ignore[override]
        if isinstance(index, slice):
            return DrawHistory(self._draws[index], pool=self.pool, picks=self.picks,
                               name=self.name)
        return self._draws[index]

    def __iter__(self) -> Iterator[Draw]:
        return iter(self._draws)

    def __repr__(self) -> str:
        return (f"DrawHistory({self.name!r}, {len(self)} draws, "
                f"{self._draws[0].drawn_on}..{self._draws[-1].drawn_on}, "
                f"pick {self.picks} of {self.pool})")

    @property
    def dates(self) -> tuple[date, ...]:
        return tuple(d.drawn_on for d in self._draws)

    @classmethod
    def from_csv(cls, path: str, *, pool: int, picks: int | None = None,
                 date_column: str = "date", number_columns: Sequence[str] | None = None,
                 bonus_columns: Sequence[str] = (), name: str | None = None) -> "DrawHistory":
        """Read draws from a CSV with a date column and one column per ball.

        If ``number_columns`` is omitted every column whose name starts with
        ``n`` or ``ball`` is treated as a main ball, which covers the layout of
        most published draw archives.
        """
        with open(path, newline="", encoding="utf-8-sig") as handle:
            text = handle.read()
        return cls.from_csv_text(
            text, pool=pool, picks=picks, date_column=date_column,
            number_columns=number_columns, bonus_columns=bonus_columns,
            name=name or path, source=path,
        )

    @classmethod
    def from_csv_text(cls, text: str, *, pool: int, picks: int | None = None,
                      date_column: str = "date",
                      number_columns: Sequence[str] | None = None,
                      bonus_columns: Sequence[str] = (), name: str | None = None,
                      source: str = "uploaded CSV") -> "DrawHistory":
        """Parse draws from CSV held in memory — the path the GUI upload takes."""
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            raise ValueError(f"{source} contains no rows")
        path = source

        headers = list(rows[0].keys())
        if number_columns is None:
            number_columns = [
                h for h in headers
                if h.lower().startswith(("n", "ball")) and h.lower() != "number_of_draws"
            ]
            if not number_columns:
                raise ValueError(
                    f"could not infer ball columns from headers {headers}; "
                    "pass number_columns explicitly"
                )

        draws = []
        for row in rows:
            numbers = tuple(int(row[c]) for c in number_columns if row[c] not in (None, ""))
            bonus = tuple(int(row[c]) for c in bonus_columns if row.get(c) not in (None, ""))
            draws.append(Draw(
                _parse_date(row[date_column]), numbers, bonus,
                machine=(row.get("Machine") or row.get("machine") or "").strip(),
                ball_set=(row.get("Ball Set") or row.get("ball_set") or "").strip(),
            ))
        return cls(draws, pool=pool, picks=picks, name=name or path)

    def to_csv(self, path: str) -> None:
        width = max(len(d.numbers) for d in self)
        bonus_width = max(len(d.bonus) for d in self)
        headers = ["date"] + [f"n{i + 1}" for i in range(width)]
        headers += [f"bonus{i + 1}" for i in range(bonus_width)]
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for draw in self:
                padded = list(draw.numbers) + [""] * (width - len(draw.numbers))
                padded += list(draw.bonus) + [""] * (bonus_width - len(draw.bonus))
                writer.writerow([draw.drawn_on.isoformat()] + padded)


def simulate_draws(count: int, *, pool: int = 59, picks: int = 6,
                   start: date | None = None, every_days: int = 3,
                   seed: int | None = None, name: str = "simulated") -> DrawHistory:
    """Generate a fair, memoryless draw history — the null model to test against.

    Anything the search finds here is by construction a false positive, which
    makes this the honest yardstick for anything it finds in real data.
    """
    rng = random.Random(seed)
    start = start or date(2000, 1, 1)
    draws = []
    for i in range(count):
        numbers = tuple(rng.sample(range(1, pool + 1), picks))
        draws.append(Draw(start + timedelta(days=i * every_days), numbers))
    return DrawHistory(draws, pool=pool, picks=picks, name=name)


def simulate_biased_draws(count: int, metric, *, strength: float = 0.5,
                          pool: int = 59, picks: int = 6, start: date | None = None,
                          every_days: int = 3, seed: int | None = None,
                          name: str = "biased") -> DrawHistory:
    """Generate a rigged history whose balls really do track ``metric``.

    A search that only ever reports "nothing here" is useless — it would say
    that about a genuinely crooked machine too. This builds a history where the
    metric tilts the draw toward high or low balls, so you can confirm the
    search detects a real effect at a given ``strength`` and sample size before
    trusting it to tell you there is none.
    """
    rng = random.Random(seed)
    start = start or date(2000, 1, 1)
    centre = (pool + 1) / 2.0
    draws = []
    for i in range(count):
        when = start + timedelta(days=i * every_days)
        level = metric(when)
        tilt = 0.0 if level is None else strength * (float(level) - 0.5)
        weights = [math.exp(tilt * (n - centre) / centre) for n in range(1, pool + 1)]
        remaining = list(range(1, pool + 1))
        remaining_weights = list(weights)
        chosen: list[int] = []
        for _ in range(picks):
            pick = rng.choices(range(len(remaining)), weights=remaining_weights)[0]
            chosen.append(remaining.pop(pick))
            remaining_weights.pop(pick)
        draws.append(Draw(when, tuple(chosen)))
    return DrawHistory(draws, pool=pool, picks=picks, name=name)
