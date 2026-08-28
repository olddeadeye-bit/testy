"""Tests for the GUI's request handling.

These call the request handlers directly rather than through a socket, except
for one end-to-end check that the server really serves the page and the API.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lotterypatterns.gui import (  # noqa: E402
    Handler,
    SearchError,
    _free_port,
    _history_from_payload,
    _metrics_from_payload,
    _options,
    _parse_lags,
    _run_calibration,
    _run_search,
)

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "data", "sample_draws.csv")


class TestLagParsing(unittest.TestCase):
    def test_ranges_and_lists(self):
        self.assertEqual(_parse_lags("0-3"), [0, 1, 2, 3])
        self.assertEqual(_parse_lags("0,2,5"), [0, 2, 5])
        self.assertEqual(_parse_lags("1, 1, 0"), [0, 1])

    def test_bad_lags_are_refused_in_plain_english(self):
        for bad in ("", "-2", "0-99"):
            with self.assertRaises(SearchError):
                _parse_lags(bad)


class TestHistoryPayloads(unittest.TestCase):
    def test_sample_source(self):
        history = _history_from_payload({"source": "sample"})
        self.assertEqual(len(history), 520)

    def test_fair_and_rigged_sources(self):
        fair = _history_from_payload({"source": "fair", "count": 120, "seed": 1})
        self.assertEqual(len(fair), 120)
        rigged = _history_from_payload({
            "source": "rigged", "count": 120, "seed": 1,
            "planted_metric": "moon_illumination", "strength": 1.0})
        self.assertEqual(len(rigged), 120)

    def test_upload_source(self):
        with open(SAMPLE, encoding="utf-8") as handle:
            text = handle.read()
        history = _history_from_payload({
            "source": "upload", "csv": text, "pool": 59, "picks": 6,
            "filename": "mine.csv"})
        self.assertEqual(len(history), 520)
        self.assertEqual(history.name, "mine.csv")

    def test_bad_payloads_raise_search_error(self):
        cases = [
            {"source": "upload", "csv": ""},
            {"source": "upload", "csv": "a,b\n1,2\n", "pool": 59},
            {"source": "fair", "pool": 5, "picks": 9},
            {"source": "fair", "pool": 500},
            {"source": "nonsense"},
            {"source": "rigged", "planted_metric": "astrology"},
        ]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(SearchError):
                _history_from_payload(payload)

    def test_oversized_upload_is_refused(self):
        with self.assertRaises(SearchError):
            _history_from_payload({"source": "upload", "csv": "x" * (9 * 1024 * 1024)})


class TestMetricPayloads(unittest.TestCase):
    def test_named_subset(self):
        metrics = _metrics_from_payload({"metrics": ["moon_illumination", "pure_noise"]})
        self.assertEqual([m.name for m in metrics], ["moon_illumination", "pure_noise"])

    def test_unknown_metric_is_refused(self):
        with self.assertRaises(SearchError):
            _metrics_from_payload({"metrics": ["ley_lines"]})

    def test_uploaded_metric_is_added_and_temp_file_removed(self):
        import glob
        import tempfile
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.csv")))
        metrics = _metrics_from_payload({
            "metrics": ["moon_illumination"],
            "extra_metric": {"csv": "date,value\n2019-01-02,4\n2019-01-05,9\n",
                             "name": "rainfall"}})
        self.assertEqual([m.name for m in metrics], ["moon_illumination", "rainfall"])
        self.assertEqual(set(glob.glob(os.path.join(tempfile.gettempdir(), "*.csv"))), before)

    def test_bad_metric_csv_is_refused(self):
        with self.assertRaises(SearchError):
            _metrics_from_payload({"extra_metric": {"csv": "nothing here", "name": "x"}})


class TestRunning(unittest.TestCase):
    def test_search_on_the_sample_finds_nothing(self):
        result = _run_search({"source": "sample", "lags": "0-1"})
        self.assertEqual(result["survivors"], 0)
        self.assertGreater(result["n_tests"], 500)
        self.assertEqual(len(result["p_values"]), result["n_tests"])
        self.assertLessEqual(len(result["results"]), 200)
        self.assertIsNotNone(result["control_floor"])

    def test_search_on_a_rigged_game_finds_the_planted_metric(self):
        result = _run_search({
            "source": "rigged", "count": 400, "seed": 3, "lags": "0",
            "planted_metric": "moon_illumination", "strength": 1.5})
        self.assertGreater(result["survivors"], 0)
        self.assertEqual(result["results"][0]["metric"], "moon_illumination")
        self.assertGreater(result["beat_floor"], 0)

    def test_too_few_draws_explains_itself(self):
        with self.assertRaises(SearchError) as ctx:
            _run_search({"source": "fair", "count": 25, "lags": "0"})
        self.assertIn("at least 30", str(ctx.exception))

    def test_bad_alpha_and_method_are_refused(self):
        with self.assertRaises(SearchError):
            _run_search({"source": "sample", "alpha": 2.0})
        with self.assertRaises(SearchError):
            _run_search({"source": "sample", "methods": ["astrology"]})

    def test_calibration_reports_near_zero_survivors(self):
        result = _run_calibration({
            "source": "fair", "count": 200, "lags": "0", "runs": 3,
            "metrics": ["moon_illumination", "daylight_hours", "pure_noise"]})
        self.assertEqual(result["runs"], 3)
        self.assertLess(result["mean_survivors"], 1.0)

    def test_options_lists_features_metrics_and_controls(self):
        options = _options()
        self.assertTrue(options["features"])
        self.assertTrue(any(m["is_control"] for m in options["metrics"]))
        self.assertEqual(len(options["methods"]), 3)


class TestServer(unittest.TestCase):
    """One end-to-end pass over a real socket."""

    @classmethod
    def setUpClass(cls):
        cls.port = _free_port(0)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", cls.port), Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _post(self, path, payload, host=None):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        if host:
            request.add_header("Host", host)
        return urllib.request.urlopen(request, timeout=60)

    def test_serves_the_page(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as response:
            body = response.read().decode()
        self.assertEqual(response.status, 200)
        self.assertIn("Lottery Pattern Search", body)

    def test_options_endpoint(self):
        with urllib.request.urlopen(self.base + "/api/options", timeout=10) as response:
            data = json.load(response)
        self.assertIn("metrics", data)

    def test_search_endpoint(self):
        with self._post("/api/search", {"source": "sample", "lags": "0"}) as response:
            data = json.load(response)
        self.assertEqual(data["draws"], 520)

    def test_errors_come_back_as_json_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/api/search", {"source": "upload", "csv": ""})
        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("No CSV", json.load(ctx.exception)["error"])

    def test_unknown_route_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.base + "/secrets", timeout=10)
        self.assertEqual(ctx.exception.code, 404)

    def test_non_loopback_host_header_is_refused(self):
        """Guards against DNS rebinding pointing a hostile page at this server."""
        request = urllib.request.Request(self.base + "/")
        request.add_header("Host", "evil.example.com")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
