import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "binance_usds_futures_trend.py"
REPO_ROOT = MODULE_PATH.parents[1]
CRON_BRIEF_SCRIPT = REPO_ROOT / "scripts" / "binance_usds_futures_trend_brief.sh"
spec = importlib.util.spec_from_file_location("binance_usds_futures_trend", MODULE_PATH)
assert spec is not None
assert spec.loader is not None
trend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trend)


class BinanceUsdsFuturesTrendTests(unittest.TestCase):
    def test_rejects_short_intervals_below_one_hour(self):
        for interval in ["1m", "5m", "10m", "15m", "30m"]:
            with self.subTest(interval=interval):
                with self.assertRaises(ValueError):
                    trend.validate_interval(interval)

    def test_accepts_one_hour_or_higher_intervals(self):
        for interval in ["1h", "2h", "4h", "1d", "1w"]:
            with self.subTest(interval=interval):
                self.assertEqual(trend.validate_interval(interval), interval)

    def test_generates_hold_long_decision_in_strong_uptrend(self):
        candles = []
        price = 100.0
        for i in range(240):
            open_price = price
            close_price = price + 1.0
            high = close_price + 0.7
            low = open_price - 0.5
            candles.append({"open": open_price, "high": high, "low": low, "close": close_price})
            price = close_price

        decision = trend.decide(candles, symbol="BTCUSDT", interval="1h")

        self.assertEqual(decision["symbol"], "BTCUSDT")
        self.assertEqual(decision["interval"], "1h")
        self.assertEqual(decision["action"], "hold_long")
        self.assertGreater(decision["position_size"], 0)
        self.assertGreater(decision["take_profit_1"], decision["entry_reference"])
        self.assertGreater(decision["take_profit_2"], decision["take_profit_1"])
        self.assertLess(decision["trailing_stop"], decision["entry_reference"])

    def test_generates_flat_decision_when_price_below_major_trend(self):
        candles = []
        price = 300.0
        for i in range(240):
            open_price = price
            close_price = price - 1.0
            high = open_price + 0.5
            low = close_price - 0.7
            candles.append({"open": open_price, "high": high, "low": low, "close": close_price})
            price = close_price

        decision = trend.decide(candles, symbol="ETHUSDT", interval="4h")

        self.assertEqual(decision["action"], "flat")
        self.assertEqual(decision["position_size"], 0)
        self.assertIn("major trend filter", decision["reason"])

    def test_rejects_short_public_factor_periods(self):
        for period in ["5m", "15m", "30m"]:
            with self.subTest(period=period):
                with self.assertRaises(ValueError):
                    trend.validate_period(period)

        self.assertEqual(trend.validate_period("1h"), "1h")
        self.assertEqual(trend.validate_period("4h"), "4h")

    def test_rejects_non_positive_risk_unit_and_top(self):
        candles = []
        price = 100.0
        for _ in range(240):
            open_price = price
            close_price = price + 1.0
            candles.append({"open": open_price, "high": close_price + 0.7, "low": open_price - 0.5, "close": close_price})
            price = close_price

        for risk_unit in [0, -1]:
            with self.subTest(risk_unit=risk_unit):
                with self.assertRaises(ValueError):
                    trend.decide(candles, symbol="BTCUSDT", interval="1h", risk_unit=risk_unit)

        for top in [0, -3]:
            with self.subTest(top=top):
                with self.assertRaises(ValueError):
                    trend.scan_symbols(["BTCUSDT"], interval="1h", top=top)

    def test_brief_wrapper_persists_lifecycle_state(self):
        script_text = CRON_BRIEF_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('--state-file state/binance-usds-futures-trend-paper-state.json', script_text)
        self.assertIn('--lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json', script_text)

    def test_market_context_changes_confidence_not_trend_participation(self):
        candles = []
        price = 100.0
        for i in range(240):
            open_price = price
            close_price = price + 1.0
            high = close_price + 0.7
            low = open_price - 0.5
            candles.append({"open": open_price, "high": high, "low": low, "close": close_price})
            price = close_price

        neutral = trend.decide(
            candles,
            symbol="BTCUSDT",
            interval="1h",
            market_context={
                "mark_trend_confirmed": True,
                "latest_funding_rate": 0.0001,
                "open_interest_change_pct": 2.5,
                "global_long_short_ratio": 1.1,
                "taker_buy_sell_ratio": 1.2,
            },
        )
        crowded = trend.decide(
            candles,
            symbol="BTCUSDT",
            interval="1h",
            market_context={
                "mark_trend_confirmed": True,
                "latest_funding_rate": 0.002,
                "open_interest_change_pct": -6.0,
                "global_long_short_ratio": 3.5,
                "taker_buy_sell_ratio": 0.7,
            },
        )

        self.assertEqual(neutral["action"], "hold_long")
        self.assertEqual(crowded["action"], "hold_long")
        self.assertGreater(neutral["confidence_score"], crowded["confidence_score"])
        self.assertGreater(neutral["position_size"], crowded["position_size"])
        self.assertIn("funding_extreme", crowded["factor_flags"])
        self.assertIn("oi_contracting", crowded["factor_flags"])

    def test_scan_symbols_ranks_trends_and_builds_chinese_summary(self):
        def make_candles(start, step):
            candles = []
            price = float(start)
            for _ in range(240):
                open_price = price
                close_price = price + step
                high = max(open_price, close_price) + 0.7
                low = min(open_price, close_price) - 0.5
                candles.append({"open": open_price, "high": high, "low": low, "close": close_price})
                price = close_price
            return candles

        candle_map = {
            "BTCUSDT": make_candles(100, 1.0),
            "SOLUSDT": make_candles(50, 0.6),
            "ETHUSDT": make_candles(300, -1.0),
        }
        context_map = {
            "BTCUSDT": {
                "mark_trend_confirmed": True,
                "latest_funding_rate": 0.0001,
                "open_interest_change_pct": 3.0,
                "global_long_short_ratio": 1.1,
                "taker_buy_sell_ratio": 1.2,
            },
            "SOLUSDT": {
                "mark_trend_confirmed": True,
                "latest_funding_rate": 0.0015,
                "open_interest_change_pct": -6.0,
                "global_long_short_ratio": 3.5,
                "taker_buy_sell_ratio": 0.8,
            },
            "ETHUSDT": {
                "mark_trend_confirmed": False,
                "latest_funding_rate": 0.0002,
                "open_interest_change_pct": 0.0,
                "global_long_short_ratio": 1.0,
                "taker_buy_sell_ratio": 1.0,
            },
        }

        original_fetch_klines = getattr(trend, "fetch_klines")
        original_fetch_market_context = getattr(trend, "fetch_market_context")
        setattr(trend, "fetch_klines", lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: candle_map[symbol])
        setattr(trend, "fetch_market_context", lambda symbol, period, limit=30, base_url=trend.BINANCE_FAPI_BASE: context_map[symbol])
        try:
            scan = trend.scan_symbols(["ETHUSDT", "SOLUSDT", "BTCUSDT"], interval="1h", limit=240, top=2)
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)
            setattr(trend, "fetch_market_context", original_fetch_market_context)

        self.assertEqual(scan["mode"], "paper")
        self.assertEqual(scan["interval"], "1h")
        self.assertIn("generated_at_utc", scan)
        self.assertIn("generated_at_beijing", scan)
        self.assertEqual([item["symbol"] for item in scan["top_trends"]], ["BTCUSDT", "SOLUSDT"])
        self.assertEqual(scan["watchlist"][0]["symbol"], "ETHUSDT")
        self.assertGreater(scan["results"][0]["rank_score"], scan["results"][1]["rank_score"])
        self.assertIn("北京时间（UTC+8）", scan["summary_zh"])
        self.assertIn("最强趋势 Top 2", scan["summary_zh"])

    def test_scan_symbols_multi_timeframe_confirms_and_groups_trends(self):
        def make_candles(start, step):
            candles = []
            price = float(start)
            for _ in range(240):
                open_price = price
                close_price = price + step
                high = max(open_price, close_price) + 0.7
                low = min(open_price, close_price) - 0.5
                candles.append({"open": open_price, "high": high, "low": low, "close": close_price})
                price = close_price
            return candles

        candle_map = {
            ("BTCUSDT", "1h"): make_candles(100, 1.0),
            ("BTCUSDT", "4h"): make_candles(100, 1.1),
            ("BTCUSDT", "1d"): make_candles(100, 1.2),
            ("SOLUSDT", "1h"): make_candles(50, 0.8),
            ("SOLUSDT", "4h"): make_candles(200, -0.4),
            ("SOLUSDT", "1d"): make_candles(200, -0.5),
            ("ETHUSDT", "1h"): make_candles(300, -0.7),
            ("ETHUSDT", "4h"): make_candles(100, 0.7),
            ("ETHUSDT", "1d"): make_candles(100, 0.8),
        }

        original_fetch_klines = getattr(trend, "fetch_klines")
        setattr(trend, "fetch_klines", lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: candle_map[(symbol, interval)])
        try:
            scan = trend.scan_symbols(
                ["SOLUSDT", "ETHUSDT", "BTCUSDT"],
                intervals=["1h", "4h", "1d"],
                limit=240,
                include_context=False,
                top=3,
            )
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)

        self.assertEqual(scan["intervals"], ["1h", "4h", "1d"])
        self.assertEqual(scan["primary_interval"], "1h")
        btc = next(item for item in scan["results"] if item["symbol"] == "BTCUSDT")
        sol = next(item for item in scan["results"] if item["symbol"] == "SOLUSDT")
        eth = next(item for item in scan["results"] if item["symbol"] == "ETHUSDT")

        self.assertEqual(btc["primary_trend"], "hold_long")
        self.assertTrue(btc["higher_timeframe_confirmed"])
        self.assertEqual(btc["timeframe_agreement_score"], 1.0)
        self.assertEqual(set(btc["timeframe_signals"]), {"1h", "4h", "1d"})
        self.assertEqual(btc["ranking_bucket"], "strong_confirmed_trend")
        self.assertGreater(btc["rank_score"], sol["rank_score"])

        self.assertEqual(sol["primary_trend"], "hold_long")
        self.assertFalse(sol["higher_timeframe_confirmed"])
        self.assertEqual(sol["timeframe_agreement_score"], 1 / 3)
        self.assertEqual(sol["ranking_bucket"], "early_trend")

        self.assertEqual(eth["primary_trend"], "flat")
        self.assertEqual(eth["ranking_bucket"], "conflicting_trend")
        self.assertEqual([item["symbol"] for item in scan["strong_confirmed_trends"]], ["BTCUSDT"])
        self.assertEqual([item["symbol"] for item in scan["early_trends"]], ["SOLUSDT"])
        self.assertEqual([item["symbol"] for item in scan["conflicting_trends"]], ["ETHUSDT"])
        self.assertIn("多周期", scan["summary_zh"])
        self.assertIn("1h,4h,1d", scan["summary_zh"])

    def test_rejects_short_intervals_in_multi_timeframe_scan(self):
        with self.assertRaises(ValueError):
            trend.scan_symbols(["BTCUSDT"], intervals=["1h", "30m", "4h"], include_context=False)

        with self.assertRaises(ValueError):
            trend.scan_symbols(["BTCUSDT"], intervals=["1h", "4h", "4h"], include_context=False)

    def test_allocate_portfolio_risk_respects_budget_caps_and_rank_order(self):
        decisions = [
            {"symbol": "ETHUSDT", "action": "flat", "rank_score": 0.0, "position_size": 0.0},
            {"symbol": "DOGEUSDT", "action": "hold_long", "rank_score": 10.0, "position_size": 0.5},
            {"symbol": "SOLUSDT", "action": "hold_long", "rank_score": 50.0, "position_size": 0.8},
            {"symbol": "BTCUSDT", "action": "hold_long", "rank_score": 100.0, "position_size": 1.25},
        ]

        allocation = trend.allocate_portfolio_risk(decisions, total_risk_budget=1.2, max_symbol_risk=1.0)

        self.assertEqual(allocation["mode"], "paper")
        self.assertEqual(allocation["total_risk_budget"], 1.2)
        self.assertEqual(allocation["max_symbol_risk"], 1.0)
        self.assertEqual(allocation["total_allocated_risk"], 1.2)
        self.assertEqual(allocation["unallocated_risk"], 0.0)
        self.assertEqual([item["symbol"] for item in allocation["allocations"]], ["BTCUSDT", "SOLUSDT"])
        self.assertEqual(allocation["allocations"][0]["paper_risk_units"], 1.0)
        self.assertEqual(allocation["allocations"][1]["paper_risk_units"], 0.2)
        self.assertIn("max_symbol_risk_cap", allocation["allocations"][0]["constraints_applied"])
        self.assertIn("remaining_budget_cap", allocation["allocations"][1]["constraints_applied"])
        self.assertIn("rank_score=100.0", allocation["allocations"][0]["allocation_explanation"])
        self.assertEqual(allocation["skipped_symbols"], ["ETHUSDT", "DOGEUSDT"])
        skip_reasons = {item["symbol"]: item["skip_reason"] for item in allocation["skipped_details"]}
        self.assertEqual(skip_reasons["ETHUSDT"], "not_hold_long")
        self.assertEqual(skip_reasons["DOGEUSDT"], "no_remaining_budget")

    def test_scan_symbols_can_include_portfolio_risk_allocation(self):
        def make_candles(start, step):
            candles = []
            price = float(start)
            for _ in range(240):
                open_price = price
                close_price = price + step
                high = max(open_price, close_price) + 2.0
                low = min(open_price, close_price) - 2.0
                candles.append({"open": open_price, "high": high, "low": low, "close": close_price})
                price = close_price
            return candles

        candle_map = {
            "BTCUSDT": make_candles(100, 0.1),
            "SOLUSDT": make_candles(50, 0.08),
            "ETHUSDT": make_candles(300, -0.1),
        }
        original_fetch_klines = getattr(trend, "fetch_klines")
        setattr(trend, "fetch_klines", lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: candle_map[symbol])
        try:
            scan = trend.scan_symbols(
                ["ETHUSDT", "SOLUSDT", "BTCUSDT"],
                interval="1h",
                limit=240,
                include_context=False,
                portfolio_risk_budget=1.5,
                max_symbol_risk=1.0,
            )
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)

        self.assertIn("portfolio_allocation", scan)
        self.assertEqual(scan["portfolio_allocation"]["total_allocated_risk"], 1.5)
        self.assertLessEqual(scan["portfolio_allocation"]["total_allocated_risk"], 1.5)
        self.assertTrue(all(item["paper_risk_units"] <= 1.0 for item in scan["portfolio_allocation"]["allocations"]))
        self.assertIn("组合纸面风险预算", scan["summary_zh"])
        self.assertIn("分配说明", scan["summary_zh"])
        self.assertIn("paper only", scan["summary_zh"])

    def test_rejects_invalid_portfolio_risk_constraints(self):
        with self.assertRaises(ValueError):
            trend.allocate_portfolio_risk([], total_risk_budget=0, max_symbol_risk=1.0)
        with self.assertRaises(ValueError):
            trend.allocate_portfolio_risk([], total_risk_budget=1.0, max_symbol_risk=0)

    def _paper_scan_fixture(self, allocations=None, results=None, errors=None):
        allocations = [] if allocations is None else allocations
        results = [] if results is None else results
        return {
            "mode": "paper",
            "generated_at_utc": "2026-06-15T12:00:00+00:00",
            "generated_at_beijing": "2026-06-15T20:00:00+08:00",
            "interval": "1h",
            "intervals": ["1h", "4h", "1d"],
            "primary_interval": "1h",
            "top_trends": results[:2],
            "portfolio_allocation": {
                "mode": "paper",
                "total_risk_budget": 3.0,
                "max_symbol_risk": 1.0,
                "total_allocated_risk": round(sum(float(item["paper_risk_units"]) for item in allocations), 8),
                "unallocated_risk": 0.0,
                "allocations": allocations,
                "skipped_details": [{"symbol": "XRPUSDT", "skip_reason": "not_hold_long"}],
            },
            "results": results,
            "errors": [] if errors is None else errors,
        }

    def test_apply_paper_state_marks_first_run_and_saves_snapshot(self):
        scan = self._paper_scan_fixture(
            allocations=[{"symbol": "BTCUSDT", "paper_risk_units": 1.0}],
            results=[{"symbol": "BTCUSDT", "action": "hold_long", "ranking_bucket": "strong_confirmed_trend", "rank_score": 10.0}],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "paper-state.json"

            updated = trend.apply_paper_state(scan, state_path)

            self.assertTrue(updated["state_change"]["first_run"])
            self.assertEqual(updated["state_change"]["added_allocations"], [{"symbol": "BTCUSDT", "paper_risk_units": 1.0}])
            self.assertEqual(updated["paper_state"]["mode"], "paper")
            self.assertEqual(updated["paper_state"]["errors_count"], 0)
            self.assertTrue(state_path.exists())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["allocations_by_symbol"]["BTCUSDT"], 1.0)
            self.assertNotIn("secret", json.dumps(saved).lower())

    def test_apply_paper_state_reports_allocation_and_ranking_changes(self):
        previous = self._paper_scan_fixture(
            allocations=[
                {"symbol": "BTCUSDT", "paper_risk_units": 1.0},
                {"symbol": "SOLUSDT", "paper_risk_units": 0.5},
            ],
            results=[
                {"symbol": "BTCUSDT", "action": "hold_long", "ranking_bucket": "strong_confirmed_trend", "rank_score": 20.0},
                {"symbol": "SOLUSDT", "action": "hold_long", "ranking_bucket": "early_trend", "rank_score": 10.0},
                {"symbol": "XRPUSDT", "action": "flat", "ranking_bucket": "watchlist", "rank_score": 0.0},
            ],
        )
        current = self._paper_scan_fixture(
            allocations=[
                {"symbol": "ETHUSDT", "paper_risk_units": 0.8},
                {"symbol": "BTCUSDT", "paper_risk_units": 0.6},
            ],
            results=[
                {"symbol": "ETHUSDT", "action": "hold_long", "ranking_bucket": "strong_confirmed_trend", "rank_score": 30.0},
                {"symbol": "BTCUSDT", "action": "hold_long", "ranking_bucket": "early_trend", "rank_score": 15.0},
                {"symbol": "XRPUSDT", "action": "hold_long", "ranking_bucket": "early_trend", "rank_score": 5.0},
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "paper-state.json"
            trend.apply_paper_state(previous, state_path)

            updated = trend.apply_paper_state(current, state_path)

            change = updated["state_change"]
            self.assertFalse(change["first_run"])
            self.assertEqual(change["added_allocations"], [{"symbol": "ETHUSDT", "paper_risk_units": 0.8}])
            self.assertEqual(change["removed_allocations"], [{"symbol": "SOLUSDT", "previous_paper_risk_units": 0.5}])
            self.assertEqual(
                change["changed_allocations"],
                [{"symbol": "BTCUSDT", "previous_paper_risk_units": 1.0, "current_paper_risk_units": 0.6, "delta": -0.4}],
            )
            self.assertIn({"symbol": "BTCUSDT", "previous_rank": 1, "current_rank": 2}, change["ranking_changes"])
            self.assertIn({"symbol": "XRPUSDT", "previous_action": "flat", "current_action": "hold_long"}, change["action_changes"])
            self.assertIn(
                {"symbol": "BTCUSDT", "previous_bucket": "strong_confirmed_trend", "current_bucket": "early_trend"},
                change["bucket_changes"],
            )

    def test_apply_paper_state_handles_corrupted_state_file(self):
        scan = self._paper_scan_fixture(
            allocations=[{"symbol": "BTCUSDT", "paper_risk_units": 1.0}],
            results=[{"symbol": "BTCUSDT", "action": "hold_long", "ranking_bucket": "strong_confirmed_trend", "rank_score": 10.0}],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "paper-state.json"
            state_path.write_text("{not valid json", encoding="utf-8")

            updated = trend.apply_paper_state(scan, state_path)

            self.assertTrue(updated["state_change"]["first_run"])
            self.assertIn("state_file_error", updated["state_change"])
            self.assertIn("invalid", updated["state_change"]["state_file_error"].lower())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "paper")

    def test_apply_paper_state_can_compute_without_saving(self):
        scan = self._paper_scan_fixture(
            allocations=[{"symbol": "BTCUSDT", "paper_risk_units": 1.0}],
            results=[{"symbol": "BTCUSDT", "action": "hold_long", "ranking_bucket": "strong_confirmed_trend", "rank_score": 10.0}],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "paper-state.json"

            updated = trend.apply_paper_state(scan, state_path, save_state=False)

            self.assertTrue(updated["state_change"]["first_run"])
            self.assertFalse(state_path.exists())

    def test_apply_paper_lifecycle_creates_entry_intent_and_persists_snapshot(self):
        scan = self._paper_scan_fixture(
            results=[
                {
                    "symbol": "BTCUSDT",
                    "action": "hold_long",
                    "position_size": 1.0,
                    "entry_reference": 100.0,
                    "trailing_stop": 94.0,
                    "take_profit_1": 104.0,
                    "take_profit_2": 108.0,
                    "reason": "major trend filter passed: participate in trend",
                    "rank_score": 20.0,
                    "ranking_bucket": "strong_confirmed_trend",
                },
                {
                    "symbol": "ETHUSDT",
                    "action": "flat",
                    "position_size": 0.0,
                    "entry_reference": 50.0,
                    "trailing_stop": None,
                    "take_profit_1": None,
                    "take_profit_2": None,
                    "reason": "major trend filter failed: require close > EMA200 and EMA50 > EMA200",
                    "rank_score": 0.0,
                    "ranking_bucket": "watchlist",
                },
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            lifecycle_path = pathlib.Path(tmpdir) / "paper-lifecycle.json"

            updated = trend.apply_paper_lifecycle(scan, lifecycle_path)

            lifecycle = updated["paper_lifecycle"]
            self.assertTrue(updated["lifecycle_change"]["first_run"])
            btc = lifecycle["positions_by_symbol"]["BTCUSDT"]
            self.assertEqual(btc["status"], "open")
            self.assertEqual(btc["last_intent"], "entry")
            self.assertEqual(btc["current_size"], 1.0)
            self.assertEqual(btc["executed_tranches"], [])
            self.assertEqual(lifecycle["positions_by_symbol"]["ETHUSDT"]["status"], "flat")
            self.assertTrue(lifecycle_path.exists())
            saved = json.loads(lifecycle_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["positions_by_symbol"]["BTCUSDT"]["status"], "open")
            self.assertNotIn("secret", json.dumps(saved).lower())

    def test_apply_paper_lifecycle_updates_trailing_stop_and_records_take_profit_tranche(self):
        previous = self._paper_scan_fixture(
            results=[
                {
                    "symbol": "BTCUSDT",
                    "action": "hold_long",
                    "position_size": 1.0,
                    "entry_reference": 100.0,
                    "trailing_stop": 94.0,
                    "take_profit_1": 104.0,
                    "take_profit_2": 108.0,
                    "reason": "major trend filter passed: participate in trend",
                    "rank_score": 20.0,
                    "ranking_bucket": "strong_confirmed_trend",
                }
            ],
        )
        current = self._paper_scan_fixture(
            results=[
                {
                    "symbol": "BTCUSDT",
                    "action": "hold_long",
                    "position_size": 0.5,
                    "entry_reference": 105.0,
                    "trailing_stop": 100.0,
                    "take_profit_1": 109.0,
                    "take_profit_2": 113.0,
                    "reason": "major trend filter passed: participate in trend",
                    "rank_score": 22.0,
                    "ranking_bucket": "strong_confirmed_trend",
                }
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            lifecycle_path = pathlib.Path(tmpdir) / "paper-lifecycle.json"
            trend.apply_paper_lifecycle(previous, lifecycle_path)

            updated = trend.apply_paper_lifecycle(current, lifecycle_path)

            btc = updated["paper_lifecycle"]["positions_by_symbol"]["BTCUSDT"]
            self.assertEqual(btc["status"], "open")
            self.assertEqual(btc["last_intent"], "reduce")
            self.assertEqual([item["name"] for item in btc["executed_tranches"]], ["take_profit_1"])
            self.assertLess(btc["current_size"], 1.0)
            self.assertGreaterEqual(btc["trailing_stop"], 100.0)
            self.assertFalse(updated["lifecycle_change"]["first_run"])
            self.assertIn({"symbol": "BTCUSDT", "intent": "reduce"}, updated["lifecycle_change"]["intent_changes"])

    def test_apply_paper_lifecycle_exits_open_position_when_signal_flips_flat(self):
        previous = self._paper_scan_fixture(
            results=[
                {
                    "symbol": "BTCUSDT",
                    "action": "hold_long",
                    "position_size": 1.0,
                    "entry_reference": 100.0,
                    "trailing_stop": 94.0,
                    "take_profit_1": 104.0,
                    "take_profit_2": 108.0,
                    "reason": "major trend filter passed: participate in trend",
                    "rank_score": 20.0,
                    "ranking_bucket": "strong_confirmed_trend",
                }
            ],
        )
        current = self._paper_scan_fixture(
            results=[
                {
                    "symbol": "BTCUSDT",
                    "action": "flat",
                    "position_size": 0.0,
                    "entry_reference": 96.0,
                    "trailing_stop": None,
                    "take_profit_1": None,
                    "take_profit_2": None,
                    "reason": "major trend filter failed: require close > EMA200 and EMA50 > EMA200",
                    "rank_score": 0.0,
                    "ranking_bucket": "watchlist",
                }
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            lifecycle_path = pathlib.Path(tmpdir) / "paper-lifecycle.json"
            trend.apply_paper_lifecycle(previous, lifecycle_path)

            updated = trend.apply_paper_lifecycle(current, lifecycle_path)

            btc = updated["paper_lifecycle"]["positions_by_symbol"]["BTCUSDT"]
            self.assertEqual(btc["status"], "closed")
            self.assertEqual(btc["last_intent"], "exit")
            self.assertEqual(btc["current_size"], 0.0)
            self.assertIn("trend filter failed", btc["exit_reason"])
            self.assertTrue(updated["lifecycle_change"]["intent_changes"])

    def test_build_runtime_record_contains_evolution_fields(self):
        scan = self._paper_scan_fixture(
            allocations=[{"symbol": "BTCUSDT", "paper_risk_units": 1.0}],
            results=[
                {
                    "symbol": "BTCUSDT",
                    "interval": "1h",
                    "action": "hold_long",
                    "position_size": 1.0,
                    "confidence_score": 0.9,
                    "rank_score": 20.0,
                    "factor_flags": ["funding_neutral"],
                    "ranking_bucket": "strong_confirmed_trend",
                    "entry_reference": 100.0,
                    "trailing_stop": 94.0,
                    "take_profit_1": 104.0,
                    "take_profit_2": 108.0,
                    "market_context": {"context_period": "1h", "context_limit": 30},
                }
            ],
        )
        scan["paper_lifecycle"] = {
            "positions_by_symbol": {
                "BTCUSDT": {"status": "open", "last_intent": "entry", "current_size": 1.0}
            },
            "open_positions": ["BTCUSDT"],
            "closed_positions": [],
        }

        record = trend.build_runtime_record(
            scan,
            environment="paper",
            strategy_version="v1.3-test",
            config_version="unit-test",
            run_id="test-run-1",
        )

        self.assertEqual(record["schema_version"], "runtime.v1")
        self.assertEqual(record["environment"], "paper")
        self.assertEqual(record["run_id"], "test-run-1")
        self.assertEqual(record["strategy_version"], "v1.3-test")
        self.assertEqual(record["config_version"], "unit-test")
        self.assertIn("generated_at_utc", record)
        self.assertIn("generated_at_beijing", record)
        for key in ["market_inputs", "signals", "risk", "portfolio_state", "execution_events", "outcomes"]:
            self.assertIn(key, record)
        self.assertEqual(record["symbol_universe"], ["BTCUSDT"])
        self.assertEqual(record["intervals"], ["1h", "4h", "1d"])
        self.assertFalse(record["execution_events"]["real_orders_submitted"])
        self.assertEqual(record["execution_events"]["paper_intents"][0]["intent"], "entry")
        self.assertNotRegex(json.dumps(record).lower(), r"(api_key|secret|signed|live_order|order_id)")

    def test_append_runtime_record_writes_jsonl_append_only(self):
        record = {"schema_version": "runtime.v1", "environment": "paper", "run_id": "a"}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "runtime" / "records.jsonl"

            first = trend.append_runtime_record(path, record)
            second = trend.append_runtime_record(path, {**record, "run_id": "b"})

            self.assertEqual(first["records_written"], 1)
            self.assertEqual(second["records_written"], 1)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual([json.loads(line)["run_id"] for line in lines], ["a", "b"])

    def test_cli_scan_can_write_runtime_record_file(self):
        def make_candles(start, step):
            candles = []
            price = float(start)
            for _ in range(240):
                open_price = price
                close_price = price + step
                high = max(open_price, close_price) + 0.7
                low = min(open_price, close_price) - 0.5
                candles.append({"open": open_price, "high": high, "low": low, "close": close_price})
                price = close_price
            return candles

        original_fetch_klines = getattr(trend, "fetch_klines")
        setattr(trend, "fetch_klines", lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: make_candles(100, 1.0))
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                runtime_path = pathlib.Path(tmpdir) / "records.jsonl"
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    rc = trend.main(
                        [
                            "--symbols",
                            "BTCUSDT",
                            "--interval",
                            "1h",
                            "--limit",
                            "240",
                            "--no-context",
                            "--runtime-record-file",
                            str(runtime_path),
                            "--strategy-version",
                            "v1.3-test",
                            "--config-version",
                            "unit-test",
                        ]
                    )

                self.assertEqual(rc, 0)
                payload = json.loads(stdout.getvalue())
                self.assertTrue(payload["ok"])
                self.assertTrue(payload["scan"]["runtime_record_saved"])
                self.assertEqual(payload["scan"]["runtime_record_change"]["records_written"], 1)
                self.assertTrue(payload["scan"]["runtime_record_change"]["append_only"])
                self.assertEqual(payload["scan"]["runtime_record"]["environment"], "paper")
                lines = runtime_path.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(lines), 1)
                record = json.loads(lines[0])
                self.assertEqual(record["environment"], "paper")
                self.assertFalse(record["execution_events"]["real_orders_submitted"])

                bad_stdout = io.StringIO()
                with contextlib.redirect_stdout(bad_stdout):
                    bad_rc = trend.main(
                        [
                            "--symbols",
                            "BTCUSDT",
                            "--interval",
                            "30m",
                            "--limit",
                            "240",
                            "--no-context",
                            "--runtime-record-file",
                            str(runtime_path),
                        ]
                    )
                self.assertEqual(bad_rc, 1)
                self.assertIn("short interval", bad_stdout.getvalue())
                self.assertEqual(len(runtime_path.read_text(encoding="utf-8").splitlines()), 1)
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)

    def test_build_telegram_briefing_zh_is_compact_paper_only_and_includes_state_changes(self):
        scan = self._paper_scan_fixture(
            allocations=[
                {"symbol": "BTCUSDT", "paper_risk_units": 1.0},
                {"symbol": "ETHUSDT", "paper_risk_units": 0.5},
            ],
            results=[
                {"symbol": "BTCUSDT", "action": "hold_long", "ranking_bucket": "strong_confirmed_trend", "rank_score": 20.0},
                {"symbol": "ETHUSDT", "action": "hold_long", "ranking_bucket": "early_trend", "rank_score": 10.0},
                {"symbol": "XRPUSDT", "action": "flat", "ranking_bucket": "watchlist", "rank_score": 0.0},
            ],
            errors=[{"symbol": "DOGEUSDT", "error": "temporary public endpoint error"}],
        )
        scan.update(
            {
                "universe_count": 20,
                "risk_high_trends": [{"symbol": "SOLUSDT"}],
                "conflicting_trends": [{"symbol": "XRPUSDT"}],
                "state_change": {
                    "mode": "paper",
                    "first_run": False,
                    "added_allocations": [{"symbol": "ETHUSDT", "paper_risk_units": 0.5}],
                    "removed_allocations": [{"symbol": "SOLUSDT", "previous_paper_risk_units": 0.3}],
                    "changed_allocations": [
                        {
                            "symbol": "BTCUSDT",
                            "previous_paper_risk_units": 0.8,
                            "current_paper_risk_units": 1.0,
                            "delta": 0.2,
                        }
                    ],
                    "ranking_changes": [{"symbol": "BTCUSDT", "previous_rank": 2, "current_rank": 1}],
                    "action_changes": [{"symbol": "XRPUSDT", "previous_action": "flat", "current_action": "hold_long"}],
                    "bucket_changes": [{"symbol": "BTCUSDT", "previous_bucket": "early_trend", "current_bucket": "strong_confirmed_trend"}],
                },
            }
        )

        brief = trend.build_telegram_briefing_zh(scan)

        self.assertIn("Binance USDS-M Paper Scan", brief)
        self.assertIn("paper only", brief)
        self.assertIn("UTC: 2026-06-15T12:00:00+00:00", brief)
        self.assertIn("北京时间（UTC+8）: 2026-06-15T20:00:00+08:00", brief)
        self.assertIn("Top trends: BTCUSDT, ETHUSDT", brief)
        self.assertIn("Allocation: BTCUSDT=1.0, ETHUSDT=0.5", brief)
        self.assertIn("新增: ETHUSDT=0.5", brief)
        self.assertIn("移除: SOLUSDT(prev=0.3)", brief)
        self.assertIn("变化: BTCUSDT 0.8→1.0 (Δ=0.2)", brief)
        self.assertIn("rank/action/bucket changes: 1/1/1", brief)
        self.assertIn("risk notes: risk_high=SOLUSDT; conflicting=XRPUSDT; errors_count=1", brief)
        self.assertNotIn("temporary public endpoint error", brief)
        self.assertLess(len(brief), 1200)

    def test_main_can_attach_paper_lifecycle_in_scan_mode_without_saving(self):
        scan = self._paper_scan_fixture(
            results=[
                {
                    "symbol": "BTCUSDT",
                    "action": "hold_long",
                    "position_size": 1.0,
                    "entry_reference": 100.0,
                    "trailing_stop": 94.0,
                    "take_profit_1": 104.0,
                    "take_profit_2": 108.0,
                    "reason": "major trend filter passed: participate in trend",
                    "rank_score": 20.0,
                    "ranking_bucket": "strong_confirmed_trend",
                }
            ],
        )
        scan.update({"universe_count": 1, "risk_high_trends": [], "conflicting_trends": []})
        original_scan_symbols = getattr(trend, "scan_symbols")
        setattr(trend, "scan_symbols", lambda **kwargs: scan)
        with tempfile.TemporaryDirectory() as tmpdir:
            lifecycle_path = pathlib.Path(tmpdir) / "paper-lifecycle.json"
            try:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    rc = trend.main([
                        "--symbols",
                        "BTCUSDT",
                        "--lifecycle-file",
                        str(lifecycle_path),
                        "--no-save-lifecycle",
                    ])
            finally:
                setattr(trend, "scan_symbols", original_scan_symbols)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["scan"]["paper_lifecycle"]["positions_by_symbol"]["BTCUSDT"]["last_intent"], "entry")
            self.assertFalse(lifecycle_path.exists())

    def test_main_can_emit_telegram_brief_in_scan_mode(self):
        scan = self._paper_scan_fixture(
            allocations=[{"symbol": "BTCUSDT", "paper_risk_units": 1.0}],
            results=[{"symbol": "BTCUSDT", "action": "hold_long", "ranking_bucket": "strong_confirmed_trend", "rank_score": 10.0}],
        )
        scan.update({"universe_count": 1, "risk_high_trends": [], "conflicting_trends": []})
        original_scan_symbols = getattr(trend, "scan_symbols")
        setattr(trend, "scan_symbols", lambda **kwargs: scan)
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = trend.main(["--symbols", "BTCUSDT", "--state-file", "/tmp/paper-state.json", "--no-save-state", "--telegram-brief"])
        finally:
            setattr(trend, "scan_symbols", original_scan_symbols)

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("Binance USDS-M Paper Scan", output)
        self.assertIn("paper only", output)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(output)

    def test_cron_brief_wrapper_uses_safe_default_multitimeframe_paper_command(self):
        self.assertTrue(CRON_BRIEF_SCRIPT.exists())
        content = CRON_BRIEF_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--all-symbols", content)
        self.assertIn("--intervals 1h,4h,1d", content)
        self.assertIn("--portfolio-risk-budget 3", content)
        self.assertIn("--max-symbol-risk 1", content)
        self.assertIn("--state-file state/binance-usds-futures-trend-paper-state.json", content)
        self.assertIn("--telegram-brief", content)
        self.assertNotRegex(content, r"(1m|5m|10m|15m|30m)")
        self.assertNotRegex(content.lower(), r"(api_key|secret|password|token)=")

    def _backtest_candles(self, start=100.0, steps=None):
        if steps is None:
            steps = [0.4] * 120 + [-0.2] * 60 + [0.5] * 120
        candles = []
        price = float(start)
        for index, step in enumerate(steps):
            open_price = price
            close_price = max(1.0, price + float(step))
            high = max(open_price, close_price) + 0.7
            low = min(open_price, close_price) - 0.5
            candles.append(
                {
                    "open_time": index * 3_600_000,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close_price,
                    "volume": 1000.0,
                    "close_time": (index + 1) * 3_600_000 - 1,
                }
            )
            price = close_price
        return candles

    def test_backtest_symbol_outputs_paper_metrics_with_timezone_labels(self):
        candles = self._backtest_candles()

        result = trend.backtest_symbol(candles, symbol="BTCUSDT", interval="1h", initial_equity=10_000)

        self.assertEqual(result["mode"], "paper")
        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertEqual(result["interval"], "1h")
        self.assertIn("generated_at_utc", result)
        self.assertIn("generated_at_beijing", result)
        self.assertIn("paper only", result["summary_zh"])
        metrics = result["metrics"]
        for key in [
            "cagr",
            "max_drawdown",
            "calmar",
            "sharpe",
            "win_rate",
            "average_holding_candles",
            "turnover",
            "total_return",
        ]:
            self.assertIn(key, metrics)
        self.assertGreater(result["bars_processed"], 0)
        self.assertGreater(len(result["equity_curve"]), 0)
        self.assertEqual(result["errors_count"], 0)
        self.assertEqual(result["per_symbol_contribution"]["BTCUSDT"], metrics["total_return"])
        self.assertNotRegex(json.dumps(result).lower(), r"(api_key|secret|signed|live_order|order_id)")

    def test_backtest_rejects_short_interval_and_insufficient_history(self):
        candles = self._backtest_candles()
        with self.assertRaises(ValueError):
            trend.backtest_symbol(candles, symbol="BTCUSDT", interval="30m")
        with self.assertRaises(ValueError):
            trend.backtest_symbol(candles[:200], symbol="BTCUSDT", interval="1h")

    def test_backtest_symbols_aggregates_per_symbol_contribution_and_errors(self):
        candle_map = {
            "BTCUSDT": self._backtest_candles(100, [0.5] * 260),
            "SOLUSDT": self._backtest_candles(50, [0.25] * 260),
        }
        original_fetch_klines = getattr(trend, "fetch_klines")
        setattr(trend, "fetch_klines", lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: candle_map[symbol])
        try:
            result = trend.backtest_symbols(["BTCUSDT", "SOLUSDT"], interval="4h", limit=260, initial_equity=10_000)
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)

        self.assertEqual(result["mode"], "paper")
        self.assertEqual(result["interval"], "4h")
        self.assertEqual(result["universe_count"], 2)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["errors_count"], 0)
        self.assertEqual(set(result["per_symbol_contribution"]), {"BTCUSDT", "SOLUSDT"})
        self.assertAlmostEqual(
            sum(result["per_symbol_contribution"].values()),
            result["metrics"]["total_return"],
            places=7,
        )
        self.assertEqual([item["symbol"] for item in result["symbol_results"]], ["BTCUSDT", "SOLUSDT"])
        self.assertIn("CAGR", result["summary_zh"])
        self.assertIn("北京时间（UTC+8）", result["summary_zh"])

    def test_backtest_aggregate_metrics_use_combined_portfolio_equity_curve(self):
        symbol_results = [
            {
                "symbol": "BTCUSDT",
                "metrics": {"initial_equity": 100.0, "final_equity": 160.0, "turnover": 1.0},
                "equity_curve": [{"close_time": 1, "equity": 100.0}, {"close_time": 2, "equity": 160.0}],
                "trades": [{"return": 0.6, "holding_candles": 2}],
            },
            {
                "symbol": "ETHUSDT",
                "metrics": {"initial_equity": 300.0, "final_equity": 300.0, "turnover": 0.0},
                "equity_curve": [{"close_time": 1, "equity": 300.0}, {"close_time": 2, "equity": 300.0}],
                "trades": [],
            },
        ]

        metrics = trend._aggregate_backtest_metrics(symbol_results, "1d")
        contribution = trend._per_symbol_contribution(symbol_results)

        self.assertEqual(metrics["initial_equity"], 400.0)
        self.assertEqual(metrics["final_equity"], 460.0)
        self.assertEqual(metrics["total_return"], 0.15)
        self.assertEqual(sum(contribution.values()), metrics["total_return"])
        self.assertNotEqual(metrics["total_return"], 0.3)

    def test_backtest_aggregate_uses_common_timestamps_for_unequal_histories(self):
        symbol_results = [
            {
                "symbol": "BTCUSDT",
                "metrics": {"initial_equity": 100.0, "final_equity": 130.0, "turnover": 0.0},
                "equity_curve": [
                    {"close_time": 1, "equity": 100.0},
                    {"close_time": 2, "equity": 120.0},
                    {"close_time": 3, "equity": 130.0},
                ],
                "trades": [],
            },
            {
                "symbol": "ETHUSDT",
                "metrics": {"initial_equity": 300.0, "final_equity": 330.0, "turnover": 0.0},
                "equity_curve": [
                    {"close_time": 2, "equity": 300.0},
                    {"close_time": 3, "equity": 330.0},
                ],
                "trades": [],
            },
        ]

        metrics = trend._aggregate_backtest_metrics(symbol_results, "1d")
        contribution = trend._per_symbol_contribution(symbol_results)

        self.assertEqual(metrics["final_equity"], 460.0)
        self.assertEqual(metrics["total_return"], 0.15)
        self.assertEqual(round(sum(contribution.values()), 8), metrics["total_return"])

    def test_backtest_fee_impacts_periodic_return_metrics(self):
        candles = self._backtest_candles(100, [0.5] * 260)

        no_fee = trend.backtest_symbol(candles, symbol="BTCUSDT", interval="1h", fee_bps=0)
        high_fee = trend.backtest_symbol(candles, symbol="BTCUSDT", interval="1h", fee_bps=1_000)

        self.assertLess(high_fee["metrics"]["final_equity"], no_fee["metrics"]["final_equity"])
        self.assertLess(high_fee["metrics"]["sharpe"], no_fee["metrics"]["sharpe"])

    def test_backtest_symbol_risk_unit_changes_paper_exposure(self):
        candles = self._backtest_candles(100, [0.5] * 260)

        baseline = trend.backtest_symbol(
            candles,
            symbol="BTCUSDT",
            interval="1h",
            initial_equity=10_000,
            max_position_size=2.0,
            risk_unit=1.0,
        )
        higher_risk_unit = trend.backtest_symbol(
            candles,
            symbol="BTCUSDT",
            interval="1h",
            initial_equity=10_000,
            max_position_size=2.0,
            risk_unit=1.25,
        )

        baseline_max_position = max(point["position_size"] for point in baseline["equity_curve"])
        higher_max_position = max(point["position_size"] for point in higher_risk_unit["equity_curve"])
        self.assertGreater(higher_risk_unit["metrics"]["total_return"], baseline["metrics"]["total_return"])
        self.assertGreater(higher_max_position, baseline_max_position)

    def test_compare_strategy_variants_reports_evidence_and_guardrails(self):
        calls = []
        candle_map = {
            "BTCUSDT": self._backtest_candles(100, [0.5] * 260),
            "ETHUSDT": self._backtest_candles(200, [0.4] * 260),
        }

        original_fetch_klines = getattr(trend, "fetch_klines")
        setattr(
            trend,
            "fetch_klines",
            lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: calls.append(symbol) or candle_map[symbol],
        )
        try:
            result = trend.compare_strategy_variants(["BTCUSDT", "ETHUSDT"], interval="1h", limit=260)
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)

        self.assertEqual(result["mode"], "paper")
        self.assertIn("generated_at_utc", result)
        self.assertIn("generated_at_beijing", result)
        self.assertEqual([item["variant"] for item in result["variants"]], ["baseline", "trend_hold_bias", "risk_capped"])
        self.assertEqual(calls, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(result["selected_variant"], "trend_hold_bias")
        self.assertTrue(result["variants"][1]["selected"])
        self.assertEqual(result["variants"][1]["risk_unit"], 1.15)
        self.assertGreater(result["variants"][1]["evidence_score"], result["variants"][0]["evidence_score"])
        self.assertIn("paper only", result["summary_zh"])

    def test_compare_strategy_variants_rejects_short_interval_and_does_not_select_overfit_drawdown(self):
        with self.assertRaises(ValueError):
            trend.compare_strategy_variants(["BTCUSDT"], interval="30m", limit=500)

        def fake_backtest_symbol(candles, symbol, interval="1h", initial_equity=10_000, fee_bps=4.0, max_position_size=1.0, risk_unit=1.0):
            if round(risk_unit, 2) == 1.15:
                path = [10_000.0, 7_500.0, 12_500.0]
            elif round(risk_unit, 2) == 0.75:
                path = [10_000.0, 9_500.0, 10_600.0]
            else:
                path = [10_000.0, 9_000.0, 11_000.0]
            equity_values = []
            for index in range(260):
                if index < 130:
                    value = path[0] + (path[1] - path[0]) * index / 129
                else:
                    value = path[1] + (path[2] - path[1]) * (index - 130) / 129
                equity_values.append(value)
            return {
                "mode": "paper",
                "symbol": symbol,
                "interval": interval,
                "bars_processed": len(equity_values),
                "metrics": {"initial_equity": 10_000.0, "final_equity": equity_values[-1], "win_rate": 0.5, "average_holding_candles": 10.0, "turnover": 2.0},
                "equity_curve": [{"close_time": index, "equity": value} for index, value in enumerate(equity_values)],
                "trades": [],
                "errors": [],
                "errors_count": 0,
            }

        original_backtest_symbol = getattr(trend, "backtest_symbol")
        original_fetch_klines = getattr(trend, "fetch_klines")
        setattr(trend, "backtest_symbol", fake_backtest_symbol)
        setattr(trend, "fetch_klines", lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: self._backtest_candles())
        try:
            result = trend.compare_strategy_variants(["BTCUSDT"], interval="1h", limit=500, max_drawdown_worsening_limit=0.02)
        finally:
            setattr(trend, "backtest_symbol", original_backtest_symbol)
            setattr(trend, "fetch_klines", original_fetch_klines)

        self.assertEqual(result["selected_variant"], "baseline")
        overfit = next(item for item in result["variants"] if item["variant"] == "trend_hold_bias")
        self.assertFalse(overfit["eligible"])
        self.assertIn("drawdown_guardrail", overfit["guardrail_flags"])

    def test_main_can_emit_strategy_refinement_json_without_orders(self):
        candle_map = {
            "BTCUSDT": self._backtest_candles(100, [0.5] * 260),
            "ETHUSDT": self._backtest_candles(200, [0.4] * 260),
        }

        original_fetch_klines = getattr(trend, "fetch_klines")
        setattr(trend, "fetch_klines", lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: candle_map[symbol])
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = trend.main(["--compare-refinements", "--symbols", "BTCUSDT,ETHUSDT", "--interval", "1h", "--limit", "260"])
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["refinement"]["mode"], "paper")
        self.assertIn("generated_at_utc", payload["refinement"])
        self.assertIn("generated_at_beijing", payload["refinement"])
        self.assertIn("paper only", payload["refinement"]["summary_zh"])
        self.assertNotRegex(stdout.getvalue().lower(), r"(api_key|secret|signed|live_order|order_id)")

    def test_main_can_emit_backtest_json_without_context_or_orders(self):
        original_fetch_klines = getattr(trend, "fetch_klines")
        setattr(trend, "fetch_klines", lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: self._backtest_candles(100, [0.5] * 260))
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = trend.main(["--backtest", "--symbols", "BTCUSDT", "--interval", "1h", "--limit", "260"])
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["backtest"]["mode"], "paper")
        self.assertIn("generated_at_utc", payload["backtest"])
        self.assertIn("generated_at_beijing", payload["backtest"])
        self.assertEqual(payload["backtest"]["errors_count"], 0)
        self.assertIn("paper only", payload["backtest"]["summary_zh"])
        self.assertNotRegex(stdout.getvalue().lower(), r"(api_key|secret|signed|live_order|order_id)")

    def test_fetch_market_context_uses_free_usds_futures_endpoints(self):
        calls = []

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return self.payload.encode("utf-8")

        def fake_urlopen(request, timeout):
            url = request.full_url
            calls.append(url)
            if "/fapi/v1/markPriceKlines" in url:
                return FakeResponse("[[1,\"100\",\"103\",\"99\",\"102\",0,2],[3,\"102\",\"106\",\"101\",\"105\",0,4]]")
            if "/fapi/v1/fundingRate" in url:
                return FakeResponse('[{"fundingRate":"0.0002","fundingTime":1}]')
            if "/futures/data/openInterestHist" in url:
                return FakeResponse('[{"sumOpenInterest":"100"},{"sumOpenInterest":"110"}]')
            if "/futures/data/globalLongShortAccountRatio" in url:
                return FakeResponse('[{"longShortRatio":"1.2"}]')
            if "/futures/data/takerlongshortRatio" in url:
                return FakeResponse('[{"buySellRatio":"1.3"}]')
            raise AssertionError(f"unexpected URL {url}")

        original = trend.urllib.request.urlopen
        trend.urllib.request.urlopen = fake_urlopen
        try:
            context = trend.fetch_market_context("BTCUSDT", "1h", limit=2)
        finally:
            trend.urllib.request.urlopen = original

        self.assertTrue(context["mark_trend_confirmed"])
        self.assertEqual(context["latest_funding_rate"], 0.0002)
        self.assertEqual(context["open_interest_change_pct"], 10.0)
        self.assertEqual(context["global_long_short_ratio"], 1.2)
        self.assertEqual(context["taker_buy_sell_ratio"], 1.3)
        self.assertTrue(any("/fapi/v1/markPriceKlines" in url for url in calls))
        self.assertTrue(any("/futures/data/openInterestHist" in url for url in calls))


if __name__ == "__main__":
    unittest.main()
