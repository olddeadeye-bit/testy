"""Command line front end: ``python -m lotterypatterns ...``"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from .draws import DrawHistory, simulate_biased_draws, simulate_draws
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
