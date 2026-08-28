"""Command line front end: ``python -m lotterypatterns ...``"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from .bias import analyse_bonus_balls, analyse_main_balls
from .draws import DrawHistory, simulate_biased_draws, simulate_draws
from .games import GAMES, get_game
from .picker import plan_upcoming, suggest
from .features import FEATURES, select_features
from .metrics import BUILTIN_METRICS, METRICS_BY_NAME, default_metrics, metric_from_csv
from .search import METHODS, null_calibration, search


def _parse_lags(raw: str) -> list[int]:
    lags: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            lags.extend(range(int(lo), int(hi) + 1))
        else:
            lags.append(int(chunk))
    return sorted(set(lags))


def _load_history(args: argparse.Namespace) -> DrawHistory:
    if getattr(args, "game", None):
        from .fetch import load_history
        return load_history(get_game(args.game), getattr(args, "draws", None))
    if args.draws:
        return DrawHistory.from_csv(
            args.draws,
            pool=args.pool,
            picks=args.picks,
            date_column=args.date_column,
            number_columns=args.number_columns,
        )
    return simulate_draws(args.simulate, pool=args.pool, picks=args.picks or 6,
                          seed=args.seed, name="simulated (fair)")


def _collect_metrics(args: argparse.Namespace):
    metrics = list(default_metrics(args.metrics))
    for spec in args.metric_csv or []:
        if "=" not in spec:
            raise SystemExit(f"--metric-csv needs NAME=PATH, got {spec!r}")
        name, path = spec.split("=", 1)
        metrics.append(metric_from_csv(path, name=name))
    return metrics


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--draws", help="CSV of draw history (date + one column per ball)")
    parser.add_argument("--game", choices=sorted(GAMES),
                        help="Use a downloaded UK game archive instead of --draws")
    parser.add_argument("--simulate", type=int, default=500,
                        help="Draws to simulate when --draws is omitted (default 500)")
    parser.add_argument("--pool", type=int, default=59, help="Highest ball number")
    parser.add_argument("--picks", type=int, default=None, help="Balls drawn per draw")
    parser.add_argument("--date-column", default="date")
    parser.add_argument("--number-columns", nargs="*", default=None)
    parser.add_argument("--metrics", nargs="*", default=None,
                        help="Restrict to these built-in metrics (default: all)")
    parser.add_argument("--features", nargs="*", default=None,
                        help="Restrict to these draw features (default: all)")
    parser.add_argument("--metric-csv", action="append",
                        help="Add an external metric as NAME=PATH; repeatable")
    parser.add_argument("--lags", default="0-3",
                        help="Lags in draws, e.g. '0,1,5' or '0-3' (default 0-3)")
    parser.add_argument("--methods", nargs="*", default=["pearson", "spearman"],
                        choices=sorted(METHODS), help="Association measures to apply")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=0)


def cmd_search(args: argparse.Namespace) -> int:
    history = _load_history(args)
    report = search(
        history,
        _collect_metrics(args),
        features=select_features(args.features),
        lags=_parse_lags(args.lags),
        methods=args.methods,
        alpha=args.alpha,
    )
    print(report.summary())
    if args.top:
        print(f"\nTop {args.top} by raw p-value:")
        for result in report.ranked(args.top):
            print(f"  {result}")
    if args.out:
        report.to_csv(args.out)
        print(f"\nAll {report.n_tests} results written to {args.out}")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    history = _load_history(args)
    calibration = null_calibration(
        history,
        _collect_metrics(args),
        runs=args.runs,
        seed=args.seed,
        features=select_features(args.features),
        lags=_parse_lags(args.lags),
        methods=args.methods,
        alpha=args.alpha,
    )
    print(calibration.summary())
    print("\nEvery hit above is spurious by construction. Compare your real "
          "search against these numbers before believing anything it found.")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Show the search failing to find a pattern, then finding a planted one."""
    metric = METRICS_BY_NAME[args.planted_metric]
    lags = _parse_lags(args.lags)
    metrics = default_metrics()

    print("=" * 72)
    print("1. A FAIR lottery — there is nothing to find")
    print("=" * 72)
    fair = simulate_draws(args.simulate, pool=args.pool, seed=args.seed,
                          name="simulated (fair)")
    print(search(fair, metrics, lags=lags, alpha=args.alpha).summary())

    print()
    print("=" * 72)
    print(f"2. A RIGGED lottery — balls tilted by {metric.name}, strength {args.strength}")
    print("=" * 72)
    rigged = simulate_biased_draws(args.simulate, metric, strength=args.strength,
                                   pool=args.pool, seed=args.seed, name="simulated (rigged)")
    rigged_report = search(rigged, metrics, lags=lags, alpha=args.alpha)
    print(rigged_report.summary())
    print()
    print("The search says nothing for the fair game and names the right metric "
          "for the rigged one.\nThat is the behaviour you want before pointing it "
          "at real draws.")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """Download real data — draw archives, weather history, or both."""
    from .fetch import FetchError, download_history
    failures = 0

    if args.weather:
        from datetime import date as _date
        from .weather import WeatherError, fetch_weather
        start = _date.fromisoformat(args.start) if args.start else _date(2015, 1, 1)
        try:
            path = fetch_weather(start, _date.today(), latitude=args.latitude,
                                 longitude=args.longitude, path=args.weather_path)
            print(f"Saved weather history to {path}")
        except WeatherError as exc:
            print(f"Weather download failed:\n{exc}")
            failures += 1

    games = [args.game] if args.game else ([] if args.weather else sorted(GAMES))
    for key in games:
        try:
            download_history(key)
        except FetchError as exc:
            print(f"\n{get_game(key).name} download failed:\n{exc}")
            failures += 1
    return 1 if failures else 0


def cmd_bias(args: argparse.Namespace) -> int:
    """Test whether the balls themselves come up evenly."""
    game = get_game(args.game)
    history = _load_history(args)
    main = analyse_main_balls(history, alpha=args.alpha)
    print(main.summary())
    bonus = analyse_bonus_balls(history, game, alpha=args.alpha)
    if bonus is not None:
        print()
        print(bonus.summary())
    if args.show_counts:
        print("\nEvery ball, most drawn first:")
        for ball in main.hottest:
            print(f"  {ball}")
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    """Suggest lines for the next real draws, using everything the tests found."""
    game = get_game(args.game)
    history = _load_history(args)
    plan = plan_upcoming(
        game, history, lines_per_draw=args.lines, draws_ahead=args.draws_ahead,
        alpha=args.alpha, seed=args.seed if args.seed else None,
        run_patterns=not args.quick, run_backtest=args.backtest,
    )
    print(plan.summary())
    if args.why and plan.slips:
        print("\nWhy each line:")
        for i, ticket in enumerate(plan.slips[0].tickets, 1):
            print(f"  {i}. " + "; ".join(ticket.reasons))
    return 0


def cmd_patterns(args: argparse.Namespace) -> int:
    """Run the structural pattern battery."""
    from .patterns import find_patterns
    history = _load_history(args)
    report = find_patterns(history, alpha=args.alpha)
    print(report.summary())
    if args.kind:
        print(f"\nEvery '{args.kind}' result, strongest first:")
        for finding in report.by_kind(args.kind)[:args.top]:
            print(f"  {finding}")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    """Replay history and score each strategy on draws it had not seen."""
    from .backtest import backtest
    history = _load_history(args)
    try:
        report = backtest(history, train=args.train, step=args.step,
                          max_predictions=args.predictions)
    except ValueError as exc:
        print(exc)
        return 1
    print(report.summary())
    return 0


def cmd_games(args: argparse.Namespace) -> int:
    for game in GAMES.values():
        print(game.describe())
        print(f"    Draw days: {', '.join(game.draw_days)}")
        print(f"    Top prize: {game.top_prize}")
        if game.notes:
            print(f"    Note: {game.notes}")
        print()
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from .gui import serve
    serve(port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    print("Draw features (left-hand side of each hypothesis):")
    for feature in FEATURES:
        marker = " *" if feature.needs_previous else "  "
        print(f" {marker} {feature.name:<22} {feature.description}")
    print("\n  * needs the previous draw; undefined for the first draw")
    print("\nBuilt-in metrics (right-hand side):")
    for metric in BUILTIN_METRICS:
        units = f" [{metric.units}]" if metric.units else ""
        print(f"    {metric.name:<22} {metric.description}{units}")
    print("\nAssociation measures:", ", ".join(sorted(METHODS)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lotterypatterns",
        description="Search lottery draws for correlations with strange metrics, "
                    "with the multiple-comparison controls that make the answer mean "
                    "something.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Run the full hypothesis sweep")
    _add_common(search_parser)
    search_parser.add_argument("--top", type=int, default=10,
                               help="Also print this many results by raw p-value")
    search_parser.add_argument("--out", help="Write every result to this CSV")
    search_parser.set_defaults(func=cmd_search)

    cal_parser = subparsers.add_parser(
        "calibrate", help="Run the same search on fair simulated draws")
    _add_common(cal_parser)
    cal_parser.add_argument("--runs", type=int, default=20)
    cal_parser.set_defaults(func=cmd_calibrate)

    demo_parser = subparsers.add_parser(
        "demo", help="Fair game vs rigged game, side by side")
    demo_parser.add_argument("--simulate", type=int, default=500)
    demo_parser.add_argument("--pool", type=int, default=59)
    demo_parser.add_argument("--lags", default="0-1")
    demo_parser.add_argument("--alpha", type=float, default=0.05)
    demo_parser.add_argument("--seed", type=int, default=0)
    demo_parser.add_argument("--planted-metric", default="moon_illumination",
                             choices=sorted(METRICS_BY_NAME))
    demo_parser.add_argument("--strength", type=float, default=1.2)
    demo_parser.set_defaults(func=cmd_demo)

    fetch_parser = subparsers.add_parser(
        "fetch", help="Download real draw archives and weather history")
    fetch_parser.add_argument("--game", choices=sorted(GAMES),
                              help="Just this game (default: all four)")
    fetch_parser.add_argument("--weather", action="store_true",
                              help="Also download daily weather history")
    fetch_parser.add_argument("--from", dest="start", metavar="YYYY-MM-DD",
                              help="Weather start date (default 2015-01-01)")
    fetch_parser.add_argument("--latitude", type=float, default=51.5072)
    fetch_parser.add_argument("--longitude", type=float, default=-0.1276)
    fetch_parser.add_argument("--weather-path", default="data/weather.csv")
    fetch_parser.set_defaults(func=cmd_fetch)

    bias_parser = subparsers.add_parser(
        "bias", help="Test whether the balls are drawn evenly")
    bias_parser.add_argument("--game", default="lotto", choices=sorted(GAMES))
    bias_parser.add_argument("--draws", help="Override the archive path")
    bias_parser.add_argument("--alpha", type=float, default=0.05)
    bias_parser.add_argument("--show-counts", action="store_true")
    bias_parser.set_defaults(func=cmd_bias)

    suggest_parser = subparsers.add_parser(
        "suggest", help="Suggest numbers to play, with an honest account of why")
    suggest_parser.add_argument("--game", default="lotto", choices=sorted(GAMES))
    suggest_parser.add_argument("--lines", type=int, default=5)
    suggest_parser.add_argument("--draws", help="Override the archive path")
    suggest_parser.add_argument("--alpha", type=float, default=0.05)
    suggest_parser.add_argument("--seed", type=int, default=0,
                                help="0 picks fresh lines each run")
    suggest_parser.add_argument("--why", action="store_true",
                                help="Explain each line")
    suggest_parser.add_argument("--draws-ahead", type=int, default=2,
                                help="How many upcoming draws to cover (default 2)")
    suggest_parser.add_argument("--backtest", action="store_true",
                                help="Also walk history forward to test the strategies")
    suggest_parser.add_argument("--quick", action="store_true",
                                help="Skip the structural pattern battery")
    suggest_parser.set_defaults(func=cmd_suggest)

    patterns_parser = subparsers.add_parser(
        "patterns", help="Structural tests: pairs, rhythms, machines, dependence")
    _add_common(patterns_parser)
    patterns_parser.add_argument("--kind", help="Also list one family in full")
    patterns_parser.add_argument("--top", type=int, default=20)
    patterns_parser.set_defaults(func=cmd_patterns)

    backtest_parser = subparsers.add_parser(
        "backtest", help="Score strategies on draws they were not trained on")
    _add_common(backtest_parser)
    backtest_parser.add_argument("--train", type=int, default=None,
                                 help="Draws to learn from before predicting")
    backtest_parser.add_argument("--step", type=int, default=1)
    backtest_parser.add_argument("--predictions", type=int, default=400)
    backtest_parser.set_defaults(func=cmd_backtest)

    games_parser = subparsers.add_parser("games", help="List the UK games and their odds")
    games_parser.set_defaults(func=cmd_games)

    gui_parser = subparsers.add_parser(
        "gui", help="Open the point-and-click version in your browser")
    gui_parser.add_argument("--port", type=int, default=8765)
    gui_parser.add_argument("--no-browser", action="store_true",
                            help="Start the server without opening a browser")
    gui_parser.set_defaults(func=cmd_gui)

    list_parser = subparsers.add_parser("list", help="List features and metrics")
    list_parser.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        # Someone piped us into `head`; that is not an error.
        sys.stdout = None  # type: ignore[assignment]
        return 0


if __name__ == "__main__":
    sys.exit(main())
