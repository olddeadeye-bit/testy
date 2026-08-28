"""The UK games, with the column layouts their published archives actually use.

Each :class:`Game` knows its number pool, whether it has a second barrel (the
Thunderball, the Lucky Stars), the true odds of the top prize, and how to read
the CSV that Camelot publishes — whose header names differ per game and include
columns like "Ball Set" that must not be mistaken for a ball.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def _combinations(n: int, k: int) -> int:
    return math.comb(n, k)


@dataclass(frozen=True)
class Game:
    """One lottery game: its shape, its odds, and how to read its archive."""

    key: str
    name: str
    pool: int
    picks: int
    bonus_pool: int = 0
    bonus_picks: int = 0
    bonus_name: str = ""
    draw_days: tuple[str, ...] = ()
    number_columns: tuple[str, ...] = ()
    bonus_columns: tuple[str, ...] = ()
    date_column: str = "DrawDate"
    history_url: str = ""
    top_prize: str = ""
    notes: str = ""
    _odds: int | None = field(default=None, repr=False)

    @property
    def jackpot_odds(self) -> int:
        """One in this many tickets wins the top prize."""
        if self._odds is not None:
            return self._odds
        odds = _combinations(self.pool, self.picks)
        if self.bonus_picks:
            odds *= _combinations(self.bonus_pool, self.bonus_picks)
        return odds

    @property
    def total_combinations(self) -> int:
        return _combinations(self.pool, self.picks)

    def describe(self) -> str:
        line = f"{self.name}: pick {self.picks} from {self.pool}"
        if self.bonus_picks:
            line += (f", plus {self.bonus_picks} {self.bonus_name} "
                     f"from {self.bonus_pool}")
        return f"{line}. Top prize odds 1 in {self.jackpot_odds:,}."


LOTTO = Game(
    key="lotto",
    name="Lotto",
    pool=59, picks=6,
    draw_days=("Wednesday", "Saturday"),
    number_columns=("Ball 1", "Ball 2", "Ball 3", "Ball 4", "Ball 5", "Ball 6"),
    bonus_columns=("Bonus Ball",),
    history_url="https://www.national-lottery.co.uk/results/lotto/draw-history/csv",
    top_prize="Jackpot, shared",
    notes="The bonus ball is drawn from the same barrel and only affects one "
          "prize tier, so it is loaded but not used for picking.",
)

THUNDERBALL = Game(
    key="thunderball",
    name="Thunderball",
    pool=39, picks=5,
    bonus_pool=14, bonus_picks=1, bonus_name="Thunderball",
    draw_days=("Tuesday", "Wednesday", "Friday", "Saturday"),
    number_columns=("Ball 1", "Ball 2", "Ball 3", "Ball 4", "Ball 5"),
    bonus_columns=("Thunderball",),
    history_url="https://www.national-lottery.co.uk/results/thunderball/draw-history/csv",
    top_prize="£500,000, not shared — it is a fixed prize",
    notes="The top prize is fixed rather than a shared jackpot, so avoiding "
          "popular numbers does not raise your payout here. It only matters "
          "for Lotto and EuroMillions.",
)

EUROMILLIONS = Game(
    key="euromillions",
    name="EuroMillions",
    pool=50, picks=5,
    bonus_pool=12, bonus_picks=2, bonus_name="Lucky Stars",
    draw_days=("Tuesday", "Friday"),
    number_columns=("Ball 1", "Ball 2", "Ball 3", "Ball 4", "Ball 5"),
    bonus_columns=("Lucky Star 1", "Lucky Star 2"),
    history_url="https://www.national-lottery.co.uk/results/euromillions/draw-history/csv",
    top_prize="Jackpot, shared across nine countries",
)

SET_FOR_LIFE = Game(
    key="setforlife",
    name="Set For Life",
    pool=47, picks=5,
    bonus_pool=10, bonus_picks=1, bonus_name="Life Ball",
    draw_days=("Monday", "Thursday"),
    number_columns=("Ball 1", "Ball 2", "Ball 3", "Ball 4", "Ball 5"),
    bonus_columns=("Life Ball",),
    history_url="https://www.national-lottery.co.uk/results/set-for-life/draw-history/csv",
    top_prize="£10,000 a month for 30 years, shared",
)

GAMES: dict[str, Game] = {
    g.key: g for g in (LOTTO, THUNDERBALL, EUROMILLIONS, SET_FOR_LIFE)
}


def get_game(key: str) -> Game:
    normalised = key.lower().replace(" ", "").replace("-", "").replace("_", "")
    aliases = {
        "nationallottery": "lotto", "national": "lotto", "uklotto": "lotto",
        "thunder": "thunderball", "euro": "euromillions", "setforlife": "setforlife",
    }
    normalised = aliases.get(normalised, normalised)
    if normalised not in GAMES:
        raise KeyError(f"unknown game {key!r}; try one of: {', '.join(GAMES)}")
    return GAMES[normalised]
