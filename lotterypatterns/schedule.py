"""When the next draws are, so a suggestion can be tied to a specific draw.

Draw days are fixed by the operator. Times are UK local, around 20:00-20:30,
which is late enough that a suggestion generated during the day is for that
evening's draw.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .games import Game

_WEEKDAYS = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
             "Friday": 4, "Saturday": 5, "Sunday": 6}

# Ticket sales close shortly before the draw; treat anything after this hour as
# being for the following draw rather than tonight's.
CUTOFF_HOUR = 19


@dataclass(frozen=True)
class UpcomingDraw:
    """One future draw of one game."""

    game_key: str
    game_name: str
    draw_date: date

    @property
    def weekday(self) -> str:
        return self.draw_date.strftime("%A")

    @property
    def label(self) -> str:
        return f"{self.weekday} {self.draw_date.strftime('%d %B %Y').lstrip('0')}"

    def days_away(self, today: date | None = None) -> int:
        return (self.draw_date - (today or date.today())).days


def draw_weekdays(game: Game) -> list[int]:
    return sorted(_WEEKDAYS[day] for day in game.draw_days if day in _WEEKDAYS)


def next_draws(game: Game, count: int = 2, *, today: date | None = None,
               now_hour: int | None = None) -> list[UpcomingDraw]:
    """The next ``count`` draw dates for a game, starting with the soonest.

    A draw happening later today counts as upcoming until the evening cutoff,
    after which the next one is tomorrow's or later.
    """
    today = today or date.today()
    now_hour = datetime.now().hour if now_hour is None else now_hour
    wanted = draw_weekdays(game)
    if not wanted:
        return []

    upcoming: list[UpcomingDraw] = []
    candidate = today
    while len(upcoming) < count:
        if candidate.weekday() in wanted:
            too_late = candidate == today and now_hour >= CUTOFF_HOUR
            if not too_late:
                upcoming.append(UpcomingDraw(game.key, game.name, candidate))
        candidate += timedelta(days=1)
        if (candidate - today).days > 60:      # guard against an empty schedule
            break
    return upcoming


def next_draw(game: Game, *, today: date | None = None,
              now_hour: int | None = None) -> UpcomingDraw | None:
    draws = next_draws(game, 1, today=today, now_hour=now_hour)
    return draws[0] if draws else None
