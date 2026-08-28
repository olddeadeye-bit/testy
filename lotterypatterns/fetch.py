"""Download real draw history from the National Lottery's published archives.

Camelot publishes every draw of every game as a CSV. This fetches one, checks
it parses, and saves it where the rest of the package expects to find it.

The download needs an internet connection. If it fails — the site blocks the
request, or you are offline — the error tells you the exact URL to open in a
browser instead, which downloads the same file by hand.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

from .draws import DrawHistory
from .games import Game, get_game

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


class FetchError(Exception):
    """The download failed, with a message that says what to do about it."""


def download_history(game: str | Game, *, path: str | None = None,
                     timeout: int = 60) -> str:
    """Fetch one game's full draw history and save it as a CSV.

    Returns the path written. The file is the site's own CSV, unmodified, so
    it stays readable by anything else you point at it.
    """
    game = game if isinstance(game, Game) else get_game(game)
    path = path or os.path.join("data", f"{game.key}_draws.csv")

    request = urllib.request.Request(game.history_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/csv,application/csv,text/plain,*/*",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise FetchError(
            f"The National Lottery site refused the download ({exc.code}).\n"
            f"Open this in your browser to get the same file by hand:\n"
            f"    {game.history_url}\n"
            f"then save it as {path}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FetchError(
            f"Could not reach the National Lottery site: {exc}\n"
            "Check you are online, or download it by hand from:\n"
            f"    {game.history_url}"
        ) from exc

    text = payload.decode("utf-8-sig", errors="replace")
    if "<html" in text[:400].lower():
        raise FetchError(
            "The site returned a web page instead of a CSV — it may be blocking "
            f"automated downloads. Open this in your browser instead:\n"
            f"    {game.history_url}\n"
            f"then save the file as {path}"
        )

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)

    try:
        history = load_history(game, path)
    except Exception as exc:
        os.unlink(path)
        raise FetchError(f"The download did not parse as {game.name} draws: {exc}") from exc

    print(f"Saved {len(history)} {game.name} draws to {path} "
          f"({history.dates[0]} to {history.dates[-1]})")
    return path


def load_history(game: str | Game, path: str | None = None) -> DrawHistory:
    """Read a saved archive using that game's own column layout."""
    game = game if isinstance(game, Game) else get_game(game)
    path = path or os.path.join("data", f"{game.key}_draws.csv")
    if not os.path.exists(path):
        raise FetchError(
            f"No {game.name} history at {path}. Download it first:\n"
            f"    python3 -m lotterypatterns fetch --game {game.key}"
        )
    # The official archives use "Ball 1", "DrawDate" and so on. A file the user
    # points at with --draws may use anything, so fall back to inferring the
    # layout rather than insisting on Camelot's header names.
    import csv as _csv
    with open(path, newline="", encoding="utf-8-sig") as handle:
        headers = next(_csv.reader(handle), [])
    official = all(column in headers for column in game.number_columns)
    date_column = game.date_column if game.date_column in headers else "date"
    if date_column not in headers:
        raise FetchError(
            f"{path} has no '{game.date_column}' or 'date' column. Its columns are: "
            f"{', '.join(headers) or '(none)'}"
        )
    try:
        return DrawHistory.from_csv(
            path, pool=game.pool, picks=game.picks,
            date_column=date_column,
            number_columns=list(game.number_columns) if official else None,
            bonus_columns=[c for c in game.bonus_columns if c in headers],
            name=game.name,
        )
    except ValueError as exc:
        # Much the commonest cause is pointing one game's loader at another
        # game's file, which produces a bare "number out of pool" complaint.
        raise FetchError(
            f"{path} does not look like {game.name} draws ({exc}).\n"
            f"{game.name} draws {game.picks} numbers from 1 to {game.pool}. "
            "Either the file belongs to a different game, or --game names the "
            "wrong one.\n"
            f"To analyse real {game.name} draws, download them with:\n"
            f"    python3 -m lotterypatterns fetch --game {game.key}"
        ) from exc
