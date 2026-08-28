"""A local web GUI: ``python3 -m lotterypatterns gui`` opens it in your browser.

Everything runs on your own machine. The server binds to localhost only, no
draw data leaves the computer, and there is nothing to install — this is the
standard library's own HTTP server handing a single HTML page to your browser.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .draws import DrawHistory, simulate_biased_draws, simulate_draws
from .features import FEATURES, select_features
from .metrics import BUILTIN_METRICS, METRICS_BY_NAME, default_metrics, metric_from_csv
from .search import METHODS, null_calibration, search

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "static", "app.html")
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class SearchError(Exception):
    """A problem with the request that the user can fix, phrased for a human."""


def _parse_lags(raw: str) -> list[int]:
    lags: list[int] = []
    for chunk in str(raw).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk.lstrip("-"):
            lo, hi = chunk.split("-", 1)
            lags.extend(range(int(lo), int(hi) + 1))
        else:
            lags.append(int(chunk))
    if not lags:
        raise SearchError("Choose at least one lag.")
    if any(lag < 0 for lag in lags):
        raise SearchError("Lags cannot be negative — that would test the future.")
    if max(lags) > 50:
        raise SearchError("Lags above 50 draws are not supported.")
    return sorted(set(lags))


def _history_from_payload(payload: dict[str, Any]) -> DrawHistory:
    source = payload.get("source", "sample")
    pool = int(payload.get("pool", 59))
    picks = int(payload.get("picks", 6))
    count = min(int(payload.get("count", 500)), 20000)
    if not 2 <= pool <= 200:
        raise SearchError("Pool size must be between 2 and 200.")
    if not 1 <= picks < pool:
        raise SearchError("Balls per draw must be at least 1 and fewer than the pool.")

    if source == "sample":
        path = os.path.join(os.path.dirname(HERE), "data", "sample_draws.csv")
        if not os.path.exists(path):
            raise SearchError("The bundled sample data is missing from this copy.")
        return DrawHistory.from_csv(path, pool=59, picks=6, name="sample draws")

    if source == "upload":
        text = payload.get("csv") or ""
        if not text.strip():
            raise SearchError("No CSV was uploaded.")
        if len(text.encode("utf-8")) > MAX_UPLOAD_BYTES:
            raise SearchError("That file is larger than 8 MB.")
        try:
            return DrawHistory.from_csv_text(
                text, pool=pool, picks=picks,
                name=payload.get("filename") or "your draws",
                source=payload.get("filename") or "your CSV",
            )
        except (ValueError, KeyError) as exc:
            raise SearchError(f"Could not read that CSV: {exc}") from exc

    if source == "fair":
        return simulate_draws(count, pool=pool, picks=picks, seed=int(payload.get("seed", 0)),
                              name="simulated fair game")

    if source == "rigged":
        metric_name = payload.get("planted_metric", "moon_illumination")
        if metric_name not in METRICS_BY_NAME:
            raise SearchError(f"Unknown metric to plant: {metric_name}")
        return simulate_biased_draws(
            count, METRICS_BY_NAME[metric_name],
            strength=float(payload.get("strength", 1.2)),
            pool=pool, picks=picks, seed=int(payload.get("seed", 0)),
            name=f"simulated game rigged on {metric_name}",
        )

    raise SearchError(f"Unknown data source: {source}")


def _metrics_from_payload(payload: dict[str, Any]):
    names = payload.get("metrics") or None
    try:
        metrics = list(default_metrics(names))
    except KeyError as exc:
        raise SearchError(str(exc)) from exc

    extra = payload.get("extra_metric")
    if extra and extra.get("csv"):
        import tempfile
        name = extra.get("name") or "your metric"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                         encoding="utf-8") as handle:
            handle.write(extra["csv"])
            temp_path = handle.name
        try:
            metrics.append(metric_from_csv(temp_path, name=name,
                                           description="Your uploaded series"))
        except (ValueError, KeyError) as exc:
            raise SearchError(f"Could not read that metric CSV: {exc}") from exc
        finally:
            os.unlink(temp_path)
    if not metrics:
        raise SearchError("Select at least one metric.")
    return metrics


def _run_search(payload: dict[str, Any]) -> dict[str, Any]:
    history = _history_from_payload(payload)
    metrics = _metrics_from_payload(payload)
    methods = payload.get("methods") or ["pearson", "spearman"]
    unknown = [m for m in methods if m not in METHODS]
    if unknown:
        raise SearchError(f"Unknown measure: {', '.join(unknown)}")
    try:
        features = select_features(payload.get("features") or None)
    except KeyError as exc:
        raise SearchError(str(exc)) from exc

    alpha = float(payload.get("alpha", 0.05))
    if not 0.0 < alpha < 1.0:
        raise SearchError("Alpha must be between 0 and 1.")

    report = search(history, metrics, features=features,
                    lags=_parse_lags(payload.get("lags", "0-3")),
                    methods=methods, alpha=alpha)

    if report.n_tests == 0:
        raise SearchError(
            f"Not enough draws to test anything — {len(history)} loaded, "
            "and each hypothesis needs at least 30 aligned pairs."
        )

    survivors = report.significant()
    floor = report.control_floor()
    return {
        "game": report.game,
        "draws": report.draws,
        "first_date": history.dates[0].isoformat(),
        "last_date": history.dates[-1].isoformat(),
        "n_tests": report.n_tests,
        "alpha": report.alpha,
        "naive_hits": len(report.naive_hits()),
        "expected_naive_hits": report.expected_naive_hits(),
        "survivors": len(survivors),
        "control_floor": floor,
        "beat_floor": sum(1 for r in survivors
                          if not r.is_control and floor is not None and r.p_value < floor),
        "p_values": [r.p_value for r in report.results],
        "results": [r.as_dict() for r in report.ranked(200)],
        "summary": report.summary(),
    }


def _run_calibration(payload: dict[str, Any]) -> dict[str, Any]:
    history = _history_from_payload(payload)
    metrics = _metrics_from_payload(payload)
    runs = max(2, min(int(payload.get("runs", 10)), 50))
    calibration = null_calibration(
        history, metrics, runs=runs, seed=int(payload.get("seed", 0)),
        features=select_features(payload.get("features") or None),
        lags=_parse_lags(payload.get("lags", "0-3")),
        methods=payload.get("methods") or ["pearson", "spearman"],
        alpha=float(payload.get("alpha", 0.05)),
    )
    return {
        "runs": calibration.runs,
        "n_tests": calibration.n_tests,
        "mean_naive_hits": calibration.mean_naive_hits,
        "max_naive_hits": max(calibration.naive_hits),
        "mean_survivors": calibration.mean_survivors,
        "max_survivors": max(calibration.survivors),
        "survivors": calibration.survivors,
        "summary": calibration.summary(),
    }


def _options() -> dict[str, Any]:
    return {
        "features": [{"name": f.name, "description": f.description} for f in FEATURES],
        "metrics": [{"name": m.name, "description": m.description, "units": m.units,
                     "is_control": m.units == "control"} for m in BUILTIN_METRICS],
        "methods": [
            {"name": "pearson", "label": "Pearson",
             "description": "Straight-line relationships. Fast."},
            {"name": "spearman", "label": "Spearman",
             "description": "Any consistently rising or falling relationship."},
            {"name": "mutual_info", "label": "Mutual information",
             "description": "Catches lumpy, non-straight patterns. Much slower."},
        ],
        "today": date.today().isoformat(),
    }


ROUTES = {
    "/api/search": _run_search,
    "/api/calibrate": _run_calibration,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "lotterypatterns"

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _local_only(self) -> bool:
        """Refuse anything not addressed to loopback, blocking DNS rebinding."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("localhost", "127.0.0.1", "::1", "")

    def do_GET(self) -> None:
        if not self._local_only():
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                with open(PAGE, "rb") as handle:
                    self._send(200, handle.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(500, b"app.html is missing from this copy",
                           "text/plain; charset=utf-8")
        elif path == "/api/options":
            self._send_json(200, _options())
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        if not self._local_only():
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        path = self.path.split("?", 1)[0]
        handler = ROUTES.get(path)
        if handler is None:
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD_BYTES * 2:
            self._send_json(413, {"error": "That upload is too large."})
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Malformed request."})
            return

        try:
            self._send_json(200, handler(payload))
        except SearchError as exc:
            self._send_json(400, {"error": str(exc)})
        except (ValueError, KeyError, TypeError) as exc:
            self._send_json(400, {"error": f"Could not run that: {exc}"})
        except Exception as exc:  # pragma: no cover - last resort
            self._send_json(500, {"error": f"Unexpected failure: {exc}"})


def _free_port(preferred: int) -> int:
    for candidate in (preferred, 0):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
                return probe.getsockname()[1]
            except OSError:
                continue
    raise SearchError("No free port available.")


def serve(port: int = 8765, open_browser: bool = True) -> None:
    """Start the GUI and, unless told otherwise, open it in the browser."""
    port = _free_port(port)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Lottery pattern search is running at  {url}")
    print("Everything stays on this machine. Press Control-C to stop.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
