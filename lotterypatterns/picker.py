"""Suggest numbers to play, using what the analysis actually established.

Read this before trusting the output.

Nothing changes your chance of winning. In a fair draw every combination is
equally likely, so no analysis of past draws — not this one, not anybody's —
makes one ticket more likely to come up than another. This module does not
pretend otherwise.

What it does is use the two things that are genuinely decidable from data:

1. **Is the machine fair?** :mod:`lotterypatterns.bias` tests whether the balls
   really are drawn evenly. If they are not — a worn ball set, an unbalanced
   machine — then some numbers *are* more likely, and the picker tilts toward
   them. This is the only route by which a number can honestly be called
   likelier, and the test almost always comes back clean.

2. **Will you have to share it?** This one is real and it is worth money. A
   large minority of players pick birthdays, so numbers of 31 and under are
   massively over-played; so are consecutive runs, straight lines on the play
   slip, and a handful of "lucky" numbers. Jackpots are split between everyone
   holding the winning line, so an unpopular combination wins the same jackpot
   less often shared. Same odds of winning, more money when you do.

The second effect only applies to games with a *shared* jackpot — Lotto and
EuroMillions. Thunderball's top prize is a fixed £500,000 paid to every winner,
so there is nothing to optimise there and the picker says so.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field

from .bias import BiasReport
from .games import Game

# --------------------------------------------------------------------------
# How players actually choose, which is nothing like uniformly
# --------------------------------------------------------------------------
# Multipliers on how often a number is picked relative to an even spread.
# Drawn from the published pattern of player behaviour: dates dominate, the
# first twelve (months) most of all, 7 is the single most chosen number, and
# anything above 31 is picked far less because it cannot be a day of a month.

def _base_popularity(number: int) -> float:
    if number <= 12:
        weight = 1.80          # a day *and* a month
    elif number <= 31:
        weight = 1.55          # a day of the month
    else:
        weight = 0.55          # cannot be a date; picked mostly by machine
    if number == 7:
        weight *= 1.35         # the classic lucky number
    elif number in (3, 11, 21, 13):
        weight *= 1.10         # other habitual favourites
    if number % 10 == 0:
        weight *= 0.92         # round numbers feel less "random" to players
    return weight


@dataclass(frozen=True)
class Ticket:
    """One suggested line, with the reasoning that produced it."""

    numbers: tuple[int, ...]
    bonus: tuple[int, ...] = ()
    share_index: float = 1.0
    evidence_score: float = 0.0
    reasons: tuple[str, ...] = ()

    def format(self, game: Game) -> str:
        main = "  ".join(f"{n:2d}" for n in self.numbers)
        if self.bonus:
            extra = "  ".join(f"{n:2d}" for n in self.bonus)
            return f"{main}    +  {extra}  ({game.bonus_name})"
        return main


def share_index(numbers: tuple[int, ...], game: Game) -> float:
    """How heavily played this combination is, relative to an average line.

    1.0 is an ordinary ticket. Below 1.0 means fewer people are expected to
    hold the same line, so a jackpot would be split fewer ways. Above 1.0
    means the opposite — a birthday-heavy line, say, is shared far more.
    """
    index = 1.0
    for number in numbers:
        index *= _base_popularity(number)
    index **= 1.0 / len(numbers)     # geometric mean, so lines stay comparable

    ordered = sorted(numbers)

    # Consecutive runs are chosen far more often than chance would give them.
    runs = sum(1 for a, b in zip(ordered, ordered[1:]) if b - a == 1)
    index *= 1.0 + 0.18 * runs

    # Even spacing — 5, 10, 15, 20 — is a favourite pattern.
    gaps = [b - a for a, b in zip(ordered, ordered[1:])]
    if len(set(gaps)) == 1:
        index *= 2.2
    elif len(set(gaps)) <= 2 and len(gaps) >= 4:
        index *= 1.3

    # All dates is the single most over-played shape there is.
    if ordered[-1] <= 31:
        index *= 1.9
    elif ordered[-1] <= 12:
        index *= 3.0

    # Lines that sit in one part of the slip get picked (and drawn) together.
    decades = {(n - 1) // 10 for n in ordered}
    if len(decades) <= 2:
        index *= 1.25

    # A sum near the middle of the range is where most chosen lines land.
    midpoint = len(numbers) * (game.pool + 1) / 2.0
    spread = math.sqrt(len(numbers)) * game.pool / 6.0
    index *= 1.0 + 0.45 * math.exp(-((sum(ordered) - midpoint) ** 2) / (2 * spread ** 2))

    return index


def _evidence_weights(report: BiasReport | None, pool: int,
                      alpha: float) -> tuple[list[float], list[str]]:
    """Turn a bias finding into per-ball weights. Flat when there is no finding."""
    weights = [1.0] * pool
    notes: list[str] = []
    if report is None or not report.is_biased:
        return weights, notes
    for ball in report.biased_balls:
        if ball.number <= pool:
            # Tilt in proportion to the measured excess, capped so a single
            # noisy ball cannot dominate the ticket.
            tilt = 1.0 + max(-0.5, min(1.0, ball.excess / 100.0))
            weights[ball.number - 1] = tilt
            notes.append(f"ball {ball.number} is drawn {ball.excess:+.1f}% "
                         f"against expectation (q={ball.q_value:.3g})")
    return weights, notes


@dataclass
class Suggestion:
    """A set of suggested lines and an honest account of what they are worth."""

    game: Game
    tickets: list[Ticket]
    draws_analysed: int
    bias_found: bool
    evidence_notes: list[str] = field(default_factory=list)
    average_share_index: float = 1.0
    shared_jackpot: bool = True

    @property
    def improvement_pct(self) -> float:
        """How much less sharing these lines expect than an average ticket."""
        if not self.tickets:
            return 0.0
        mine = statistics.fmean(t.share_index for t in self.tickets)
        return (1.0 - mine / self.average_share_index) * 100.0

    def summary(self) -> str:
        lines = [
            f"{self.game.name} — {len(self.tickets)} suggested "
            f"line{'s' if len(self.tickets) != 1 else ''}",
            "=" * 62,
            "",
        ]
        for i, ticket in enumerate(self.tickets, 1):
            lines.append(f"  {i}.  {ticket.format(self.game)}")
        lines.append("")
        lines.append(f"Based on {self.draws_analysed:,} real draws.")
        lines.append("")

        if self.bias_found:
            lines.append("BALL BIAS: the evenness test found something.")
            for note in self.evidence_notes:
                lines.append(f"  - {note}")
            lines.append("  These picks are tilted toward it. Confirm it on draws "
                         "outside this history before believing it.")
        else:
            lines.append("BALL BIAS: none. The balls come up evenly, so no number "
                         "is any likelier than another.")
        lines.append("")
        lines.append(f"YOUR ODDS: 1 in {self.game.jackpot_odds:,}. "
                     "These picks do not change that, and nothing could.")
        lines.append("")
        if self.shared_jackpot:
            lines.append("WHAT THESE PICKS ACTUALLY BUY YOU:")
            lines.append(f"  They avoid heavily-played combinations, so they expect "
                         f"about {self.improvement_pct:.0f}% less jackpot-sharing than "
                         "an average ticket.")
            lines.append("  Same chance of winning. A bigger cheque if you do.")
        else:
            lines.append("SHARING: not a factor here — "
                         f"{self.game.top_prize.lower()}.")
            lines.append("  So these numbers are simply a fair random pick, which is "
                         "exactly as good as any other for this game.")
        return "\n".join(lines)


def suggest(game: Game, *, count: int = 5, bias_report: BiasReport | None = None,
            bonus_bias: BiasReport | None = None, draws_analysed: int = 0,
            candidates: int = 20000, alpha: float = 0.05,
            seed: int | None = None) -> Suggestion:
    """Produce ``count`` lines for ``game``.

    Candidate lines are drawn at random, scored, and the least-played are kept.
    The final choice is random among the good ones rather than the single
    "best" line — if everyone using this tool played one identical optimal
    ticket, they would all share with each other, which is the very thing the
    scoring is trying to avoid.
    """
    rng = random.Random(seed)
    shared = "not shared" not in game.top_prize.lower()

    weights, notes = _evidence_weights(bias_report, game.pool, alpha)
    bias_found = bool(notes)
    population = list(range(1, game.pool + 1))

    def draw_line() -> tuple[int, ...]:
        if bias_found:
            chosen: list[int] = []
            pool_left = list(population)
            weights_left = list(weights)
            for _ in range(game.picks):
                index = rng.choices(range(len(pool_left)), weights=weights_left)[0]
                chosen.append(pool_left.pop(index))
                weights_left.pop(index)
            return tuple(sorted(chosen))
        return tuple(sorted(rng.sample(population, game.picks)))

    scored: list[tuple[float, tuple[int, ...]]] = []
    for _ in range(max(candidates, count * 200)):
        line = draw_line()
        scored.append((share_index(line, game), line))

    average = statistics.fmean(s for s, _ in scored)
    scored.sort(key=lambda pair: pair[0])

    # Keep the least-played 2%, then choose among them at random so two people
    # running this do not walk away with the same ticket.
    keep = max(count * 10, len(scored) // 50)
    shortlist = scored[:keep]
    rng.shuffle(shortlist)

    tickets: list[Ticket] = []
    seen: set[tuple[int, ...]] = set()
    for index, line in shortlist:
        if line in seen:
            continue
        seen.add(line)
        reasons = []
        if shared:
            reasons.append(f"expects {(1 - index / average) * 100:.0f}% less sharing "
                           "than an average line")
        if max(line) > 31:
            reasons.append(f"{sum(1 for n in line if n > 31)} numbers above 31, "
                           "which birthday players cannot pick")
        bonus: tuple[int, ...] = ()
        if game.bonus_picks:
            if bonus_bias is not None and bonus_bias.is_biased:
                pick_from = [b.number for b in bonus_bias.hottest[:max(3, game.bonus_pool // 3)]]
                bonus = tuple(sorted(rng.sample(pick_from,
                                               min(game.bonus_picks, len(pick_from)))))
            else:
                bonus = tuple(sorted(rng.sample(range(1, game.bonus_pool + 1),
                                                game.bonus_picks)))
        tickets.append(Ticket(numbers=line, bonus=bonus, share_index=index,
                              reasons=tuple(reasons)))
        if len(tickets) == count:
            break

    return Suggestion(game=game, tickets=tickets, draws_analysed=draws_analysed,
                      bias_found=bias_found, evidence_notes=notes,
                      average_share_index=average, shared_jackpot=shared)


# --------------------------------------------------------------------------
# Suggestions tied to a specific upcoming draw
# --------------------------------------------------------------------------

@dataclass
class PlaySlip:
    """Lines to play in one identified, dated draw."""

    game: Game
    draw_date: str
    draw_label: str
    tickets: list[Ticket]
    days_away: int = 0

    def format(self) -> str:
        lines = [f"{self.game.name} — {self.draw_label}"
                 + (" (tonight)" if self.days_away == 0 else
                    f" (in {self.days_away} day{'s' if self.days_away != 1 else ''})"),
                 "-" * 58]
        for i, ticket in enumerate(self.tickets, 1):
            lines.append(f"  {i}.  {ticket.format(self.game)}")
        return "\n".join(lines)


@dataclass
class PlayPlan:
    """Dated slips for the next draws, plus what the evidence actually was."""

    slips: list[PlaySlip]
    game: Game
    draws_analysed: int
    date_range: str = ""
    bias_found: bool = False
    evidence_notes: list[str] = field(default_factory=list)
    pattern_notes: list[str] = field(default_factory=list)
    backtest_note: str = ""
    improvement_pct: float = 0.0
    shared_jackpot: bool = True

    def summary(self) -> str:
        lines = []
        for slip in self.slips:
            lines.append(slip.format())
            lines.append("")

        lines.append("=" * 58)
        lines.append(f"Analysed {self.draws_analysed:,} real {self.game.name} draws"
                     + (f" ({self.date_range})" if self.date_range else "") + ".")
        lines.append("")

        if self.bias_found:
            lines.append("BALL BIAS FOUND — these picks are tilted toward it:")
            for note in self.evidence_notes:
                lines.append(f"  - {note}")
        else:
            lines.append("BALL BIAS: none. Every ball comes up at the rate it should,")
            lines.append("  so no number is due, hot or cold.")
        lines.append("")

        if self.pattern_notes:
            lines.append("STRUCTURAL PATTERNS:")
            for note in self.pattern_notes:
                lines.append(f"  - {note}")
        else:
            lines.append("STRUCTURAL PATTERNS: none survived correction — no pairs,")
            lines.append("  rhythms, machine effects or draw-to-draw dependence.")
        lines.append("")

        if self.backtest_note:
            lines.append("WALK-FORWARD TEST:")
            lines.append(f"  {self.backtest_note}")
            lines.append("")

        lines.append(f"ODDS: 1 in {self.game.jackpot_odds:,} per line. Unchanged by "
                     "any of the above.")
        if self.shared_jackpot:
            lines.append(f"SHARING: these lines expect about {self.improvement_pct:.0f}% "
                         "less jackpot-splitting than an average ticket.")
        else:
            lines.append(f"SHARING: not a factor — {self.game.top_prize.lower()}.")
        return "\n".join(lines)


def plan_upcoming(game: Game, history, *, lines_per_draw: int = 2,
                  draws_ahead: int = 2, alpha: float = 0.05,
                  seed: int | None = None, run_patterns: bool = True,
                  run_backtest: bool = False, today=None) -> PlayPlan:
    """Suggest lines for the next real draws, using every check available.

    Runs the ball-evenness test, the structural pattern battery and optionally
    a walk-forward test, then produces a dated slip per upcoming draw. Where
    the evidence found something, the picks follow it; where it found nothing —
    which is the usual outcome — the picks fall back to avoiding heavily-played
    combinations.
    """
    from .bias import analyse_bonus_balls, analyse_main_balls
    from .schedule import next_draws

    main = analyse_main_balls(history, alpha=alpha)
    bonus = analyse_bonus_balls(history, game, alpha=alpha)

    pattern_notes: list[str] = []
    if run_patterns:
        from .patterns import find_patterns
        report = find_patterns(history, alpha=alpha)
        for finding in report.survivors[:6]:
            pattern_notes.append(f"{finding.label} ({finding.detail}), q={finding.q_value:.3g}")

    backtest_note = ""
    if run_backtest:
        from .backtest import backtest as run
        try:
            # Same settings as the standalone command, so the plan and
            # `backtest` never disagree about the same history.
            result = run(history)
            best = result.best()
            winners = [r for r in result.results if r.beat_chance]
            if winners:
                backtest_note = ("beat chance on held-out draws, surviving "
                                 "correction across every strategy tried: "
                                 + ", ".join(f"{r.name} ({r.edge_pct:+.1f}%)"
                                             for r in winners))
            elif best is not None:
                backtest_note = (
                    f"no strategy beat chance on {result.predictions} held-out "
                    f"draws; best was {best.name} at {best.edge_pct:+.1f}% "
                    f"(p={best.p_value:.3f}, q={best.q_value:.2f} — noise once "
                    "corrected for trying several)")
        except ValueError as exc:
            backtest_note = f"not run: {exc}"

    upcoming = next_draws(game, draws_ahead, today=today)
    slips: list[PlaySlip] = []
    improvement = 0.0
    for offset, draw in enumerate(upcoming):
        result = suggest(game, count=lines_per_draw, bias_report=main,
                         bonus_bias=bonus, draws_analysed=len(history), alpha=alpha,
                         seed=None if seed is None else seed + offset)
        improvement = result.improvement_pct
        slips.append(PlaySlip(game=game, draw_date=draw.draw_date.isoformat(),
                              draw_label=draw.label, tickets=result.tickets,
                              days_away=draw.days_away(today)))

    _, evidence_notes = _evidence_weights(main, game.pool, alpha)
    return PlayPlan(
        slips=slips, game=game, draws_analysed=len(history),
        date_range=f"{history.dates[0]} to {history.dates[-1]}" if len(history) else "",
        bias_found=bool(evidence_notes), evidence_notes=evidence_notes,
        pattern_notes=pattern_notes, backtest_note=backtest_note,
        improvement_pct=improvement,
        shared_jackpot="not shared" not in game.top_prize.lower(),
    )
