import contextlib
import importlib
import importlib.util
import inspect
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "binance_usds_futures_trend.py"
REPO_ROOT = MODULE_PATH.parents[1]
CRON_BRIEF_SCRIPT = REPO_ROOT / "scripts" / "binance_usds_futures_trend_brief.sh"
spec = importlib.util.spec_from_file_location("binance_usds_futures_trend", MODULE_PATH)
assert spec is not None
assert spec.loader is not None
trend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trend)


class BinanceUsdsFuturesTrendTests(unittest.TestCase):
    def test_cli_top_level_error_redacts_signed_query_and_sensitive_fields(self):
        def leaky_fetch_klines(*args, **kwargs):
            raise RuntimeError('boom https://testnet.binancefuture.com/fapi/v2/account?timestamp=1&signature=abc123 X-MBX-APIKEY=my-key secret=my-secret')

        stdout = io.StringIO()
        with mock.patch.object(trend, "fetch_klines", leaky_fetch_klines), contextlib.redirect_stdout(stdout):
            rc = trend.main(["--symbol", "BTCUSDT", "--interval", "1h"])

        self.assertEqual(rc, 1)
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload)
        self.assertNotIn("abc123", encoded)
        self.assertNotIn("my-key", encoded)
        self.assertNotIn("my-secret", encoded)
        self.assertIn("<redacted>", encoded)

    def test_core_realtime_interface_modules_are_importable(self):
        module_names = [
            "scripts.binance_trend_core",
            "scripts.binance_trend_core.types",
            "scripts.binance_trend_core.market_data",
            "scripts.binance_trend_core.signals",
            "scripts.binance_trend_core.strategy",
            "scripts.binance_trend_core.risk",
            "scripts.binance_trend_core.portfolio",
            "scripts.binance_trend_core.execution",
            "scripts.binance_trend_core.brokers",
            "scripts.binance_trend_core.runtime",
            "scripts.binance_trend_core.evolution",
            "scripts.binance_trend_core.loop",
        ]
        for module_name in module_names:
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

    def test_broker_adapter_interface_exposes_required_boundary(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")

        for attr in ["environment", "submit_order", "cancel_order", "get_account_state"]:
            self.assertTrue(hasattr(brokers.BrokerAdapter, attr), attr)
        self.assertIn("instruction", inspect.signature(brokers.BrokerAdapter.submit_order).parameters)
        self.assertIn("order_id", inspect.signature(brokers.BrokerAdapter.cancel_order).parameters)
        self.assertEqual(inspect.signature(brokers.BrokerAdapter.get_account_state).parameters.keys(), {"self"})

        adapter = brokers.RejectingBrokerAdapter(environment="paper")
        self.assertEqual(adapter.environment, "paper")
        self.assertEqual(adapter.get_account_state()["environment"], "paper")
        with self.assertRaises(RuntimeError):
            adapter.submit_order({"symbol": "BTCUSDT", "side": "BUY"})

    def test_signal_engine_wrapper_preserves_short_interval_rejection(self):
        signals = importlib.import_module("scripts.binance_trend_core.signals")
        engine = signals.FunctionSignalEngine(decide_fn=trend.decide)
        candles = [{"open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1} for _ in range(240)]

        with self.assertRaises(ValueError):
            engine.generate_signal(candles, symbol="BTCUSDT", interval="30m")

    def test_cli_scan_still_attaches_portfolio_allocation_and_lifecycle(self):
        scan = self._paper_scan_fixture(
            allocations=[{"symbol": "BTCUSDT", "paper_risk_units": 1.0}],
            results=[
                {
                    "symbol": "BTCUSDT",
                    "action": "hold_long",
                    "position_size": 1.0,
                    "entry_reference": 100.0,
                    "trailing_stop": 94.0,
                    "take_profit_1": 104.0,
                    "take_profit_2": 108.0,
                    "rank_score": 20.0,
                    "ranking_bucket": "strong_confirmed_trend",
                    "reason": "major trend filter passed: participate in trend",
                }
            ],
        )
        original_scan_symbols = getattr(trend, "scan_symbols")
        setattr(trend, "scan_symbols", lambda **kwargs: scan)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                lifecycle_path = pathlib.Path(tmpdir) / "paper-lifecycle.json"
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    rc = trend.main(
                        [
                            "--symbols",
                            "BTCUSDT",
                            "--portfolio-risk-budget",
                            "1",
                            "--max-symbol-risk",
                            "1",
                            "--lifecycle-file",
                            str(lifecycle_path),
                            "--no-save-lifecycle",
                        ]
                    )
        finally:
            setattr(trend, "scan_symbols", original_scan_symbols)

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["scan"]["mode"], "paper")
        self.assertIn("portfolio_allocation", payload["scan"])
        self.assertIn("paper_lifecycle", payload["scan"])
        self.assertEqual(payload["scan"]["paper_lifecycle"]["positions_by_symbol"]["BTCUSDT"]["last_intent"], "entry")

    def test_paper_broker_submit_order_creates_simulated_fill_without_network(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        broker = brokers.PaperBroker(initial_equity=10_000.0, fee_bps=4.0, slippage_bps=2.0)
        fill = broker.submit_order(execution.OrderInstruction(symbol="BTCUSDT", side="BUY", quantity=0.5, metadata={"reference_price": 100.0}))

        self.assertEqual(fill["environment"], "paper")
        self.assertEqual(fill["symbol"], "BTCUSDT")
        self.assertEqual(fill["side"], "BUY")
        self.assertEqual(fill["quantity"], 0.5)
        self.assertTrue(fill["simulated"])
        self.assertFalse(fill["real_order_submitted"])
        self.assertGreater(fill["fill_price"], 100.0)
        state = broker.get_account_state()
        self.assertEqual(state["positions"]["BTCUSDT"]["size"], 0.5)
        self.assertEqual(len(state["fills"]), 1)
        self.assertNotRegex(json.dumps(state).lower(), r"(api_key|secret|signature|signed|live_order)")

        short_fill = broker.submit_order(execution.OrderInstruction(symbol="ETHUSDT", side="SELL", quantity=0.25, metadata={"reference_price": 200.0}))
        self.assertEqual(short_fill["side"], "SELL")
        short_state = broker.get_account_state()
        self.assertEqual(short_state["positions"]["ETHUSDT"]["size"], -0.25)
        self.assertGreater(short_state["positions"]["ETHUSDT"]["entry_price"], 0.0)

    def test_paper_execution_engine_turns_intents_into_broker_instructions(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PaperIntentExecutionEngine()
        intent = types.StrategyIntent(symbol="ETHUSDT", desired_exposure=1.25, action="hold_long", reason="trend")

        plan = engine.plan_orders(intent, {"approved": True}, {"positions_by_symbol": {}})

        self.assertEqual(len(plan.instructions), 1)
        instruction = plan.instructions[0]
        self.assertEqual(instruction.symbol, "ETHUSDT")
        self.assertEqual(instruction.side, "BUY")
        self.assertEqual(instruction.quantity, 1.25)
        self.assertTrue(instruction.metadata["paper_intent"])

        short_intent = types.StrategyIntent(symbol="ETHUSDT", desired_exposure=-0.75, action="hold_short", reason="short trend")
        short_plan = engine.plan_orders(short_intent, {"approved": True}, {"positions_by_symbol": {}})
        self.assertEqual(len(short_plan.instructions), 1)
        self.assertEqual(short_plan.instructions[0].side, "SELL")
        self.assertEqual(short_plan.instructions[0].quantity, 0.75)

    def test_position_reconciliation_execution_engine_plans_only_delta(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="SOLUSDT",
            desired_exposure=1.0,
            action="hold_long",
            reason="trend",
            metadata={"signal": {"entry_reference": 75.0}},
        )

        plan = engine.plan_orders(intent, {"approved": True}, {"positions": {"SOLUSDT": {"size": 0.7}}})

        self.assertEqual(len(plan.instructions), 1)
        instruction = plan.instructions[0]
        self.assertEqual(instruction.side, "BUY")
        self.assertAlmostEqual(instruction.quantity, 0.3)
        self.assertTrue(instruction.metadata["position_reconciliation"])
        self.assertEqual(instruction.metadata["current_exposure"], 0.7)
        self.assertEqual(instruction.metadata["desired_exposure"], 1.0)
        self.assertEqual(instruction.metadata["reference_price"], 75.0)

    def test_position_reconciliation_execution_engine_respects_signal_add_blocker(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="SOLUSDT",
            desired_exposure=1.0,
            action="hold_long",
            reason="major trend still valid but pullback blocks new adds",
            metadata={
                "signal": {
                    "entry_reference": 75.0,
                    "add_allowed": False,
                    "add_blockers": ["below_ema50", "recent_12_candle_downtrend"],
                }
            },
        )

        plan = engine.plan_orders(intent, {"approved": True}, {"positions": {"SOLUSDT": {"size": 0.7}}})

        self.assertEqual(plan.instructions, [])
        self.assertTrue(plan.metadata["skipped"])
        self.assertEqual(plan.metadata["reason"], "add_blocked_by_signal")
        self.assertEqual(plan.metadata["desired_exposure"], 1.0)
        self.assertEqual(plan.metadata["effective_desired_exposure"], 0.7)
        self.assertEqual(plan.metadata["add_blockers"], ["below_ema50", "recent_12_candle_downtrend"])

    def test_position_reconciliation_execution_engine_plans_short_delta_and_buy_protection(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=-0.6,
            action="hold_short",
            reason="major short trend",
            metadata={
                "signal": {
                    "entry_reference": 100.0,
                    "trailing_stop": 110.0,
                    "take_profit_1": 90.0,
                    "take_profit_2": 80.0,
                    "add_allowed": True,
                }
            },
        )

        plan = engine.plan_orders(intent, {"approved": True}, {"positions": {"ETHUSDT": {"size": -0.2}}, "open_algo_orders": []})

        self.assertEqual([item.side for item in plan.instructions], ["SELL", "BUY", "BUY", "BUY"])
        self.assertEqual([item.order_type for item in plan.instructions], ["MARKET", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TAKE_PROFIT_MARKET"])
        self.assertAlmostEqual(plan.instructions[0].quantity, 0.4)
        self.assertEqual(plan.instructions[1].metadata["action"], "protect_short")
        self.assertEqual(plan.instructions[1].metadata["stop_price"], 110.0)
        self.assertTrue(plan.instructions[1].metadata["close_position"])
        self.assertEqual(plan.instructions[2].metadata["stop_price"], 90.0)
        self.assertEqual(plan.instructions[3].metadata["stop_price"], 80.0)
        self.assertTrue(plan.instructions[2].metadata["reduce_only"])
        self.assertTrue(plan.instructions[3].metadata["reduce_only"])

    def test_position_reconciliation_blocks_new_short_adds_when_signal_disallows_add(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=-1.0,
            action="hold_short",
            reason="major short trend but bounce blocks new shorts",
            metadata={"signal": {"entry_reference": 100.0, "add_allowed": False, "add_blockers": ["above_ema50"]}},
        )

        plan = engine.plan_orders(intent, {"approved": True}, {"positions": {"ETHUSDT": {"size": -0.4}}})

        self.assertEqual(plan.instructions, [])
        self.assertTrue(plan.metadata["skipped"])
        self.assertEqual(plan.metadata["reason"], "add_blocked_by_signal")
        self.assertEqual(plan.metadata["effective_desired_exposure"], -0.4)
        self.assertEqual(plan.metadata["add_blockers"], ["above_ema50"])

    def test_position_reconciliation_add_blocker_never_crosses_through_flat(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        long_to_short = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=-1.0,
            action="hold_short",
            reason="major short trend but bounce blocks new shorts",
            metadata={"signal": {"entry_reference": 100.0, "trailing_stop": 110.0, "take_profit_1": 90.0, "take_profit_2": 80.0, "add_allowed": False, "add_blockers": ["above_ema50"]}},
        )
        plan = engine.plan_orders(long_to_short, {"approved": True}, {"positions": {"ETHUSDT": {"size": 0.4}}})
        self.assertEqual(len(plan.instructions), 1)
        self.assertEqual(plan.instructions[0].side, "SELL")
        self.assertAlmostEqual(plan.instructions[0].quantity, 0.4)
        self.assertEqual(plan.metadata["effective_desired_exposure"], 0.0)

        short_to_long = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=1.0,
            action="hold_long",
            reason="major long trend but pullback blocks new longs",
            metadata={"signal": {"entry_reference": 100.0, "trailing_stop": 90.0, "take_profit_1": 110.0, "take_profit_2": 120.0, "add_allowed": False, "add_blockers": ["below_ema50"]}},
        )
        plan = engine.plan_orders(short_to_long, {"approved": True}, {"positions": {"ETHUSDT": {"size": -0.3}}})
        self.assertEqual(len(plan.instructions), 1)
        self.assertEqual(plan.instructions[0].side, "BUY")
        self.assertAlmostEqual(plan.instructions[0].quantity, 0.3)
        self.assertEqual(plan.metadata["effective_desired_exposure"], 0.0)

    def test_position_reconciliation_execution_engine_skips_when_target_reached(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(symbol="SOLUSDT", desired_exposure=1.0, action="hold_long", reason="trend")

        plan = engine.plan_orders(intent, {"approved": True}, {"positions": {"SOLUSDT": {"size": 1.0}}})

        self.assertEqual(plan.instructions, [])
        self.assertTrue(plan.metadata["skipped"])
        self.assertEqual(plan.metadata["reason"], "target_exposure_already_reached")

    def test_position_reconciliation_execution_engine_cancels_stale_take_profit_layers_before_replacing_them(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=0.361,
            action="hold_long",
            reason="trend",
            metadata={
                "signal": {
                    "entry_reference": 1799.44,
                    "trailing_stop": 1757.99,
                    "take_profit_1": 1827.07,
                    "take_profit_2": 1854.70,
                }
            },
        )
        portfolio_state = {
            "positions": {"ETHUSDT": {"size": 0.039}},
            "open_algo_orders": [
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "quantity": "0.019",
                    "reduceOnly": True,
                    "triggerPrice": "1825.20",
                    "clientAlgoId": "old-tp-1",
                    "algoId": 101,
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "quantity": "0.019",
                    "reduceOnly": True,
                    "triggerPrice": "1855.74",
                    "clientAlgoId": "old-tp-2",
                    "algoId": 102,
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "STOP_MARKET",
                    "closePosition": True,
                    "triggerPrice": "1748.85",
                    "clientAlgoId": "existing-stop",
                    "algoId": 103,
                },
            ],
        }

        plan = engine.plan_orders(intent, {"approved": True}, portfolio_state)

        cancel_instructions = [item for item in plan.instructions if item.order_type == "CANCEL_ALGO_ORDER"]
        self.assertEqual([item.metadata["cancel_client_algo_id"] for item in cancel_instructions], ["old-tp-1", "old-tp-2"])
        self.assertEqual([item.metadata["cancel_reason"] for item in cancel_instructions], ["stale_take_profit_replacement", "stale_take_profit_replacement"])
        replacement_tps = [item for item in plan.instructions if item.order_type == "TAKE_PROFIT_MARKET"]
        self.assertEqual(len(replacement_tps), 2)
        self.assertAlmostEqual(sum(item.quantity for item in replacement_tps), 0.361)
        self.assertEqual([item.metadata["protection_role"] for item in replacement_tps], ["take_profit_1", "take_profit_2"])

    def test_reducing_long_replans_take_profit_to_desired_exposure(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=0.3486655,
            action="hold_long",
            reason="trend",
            metadata={
                "signal": {
                    "entry_reference": 1786.31,
                    "trailing_stop": 1757.63,
                    "take_profit_1": 1814.98714286,
                    "take_profit_2": 1843.66428571,
                }
            },
        )
        portfolio_state = {
            "positions": {"ETHUSDT": {"size": 0.497}},
            "open_algo_orders": [
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "quantity": "0.2485",
                    "reduceOnly": True,
                    "triggerPrice": "1814.98714286",
                    "clientAlgoId": "overcovered-tp-1",
                    "algoId": 301,
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "quantity": "0.2485",
                    "reduceOnly": True,
                    "triggerPrice": "1843.66428571",
                    "clientAlgoId": "overcovered-tp-2",
                    "algoId": 302,
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "STOP_MARKET",
                    "closePosition": True,
                    "triggerPrice": "1757.63",
                    "clientAlgoId": "existing-stop",
                    "algoId": 303,
                },
            ],
        }

        plan = engine.plan_orders(intent, {"approved": True}, portfolio_state)

        market_orders = [item for item in plan.instructions if item.order_type == "MARKET"]
        self.assertEqual(len(market_orders), 1)
        self.assertEqual(market_orders[0].side, "SELL")
        self.assertAlmostEqual(market_orders[0].quantity, 0.1483345)
        cancel_instructions = [item for item in plan.instructions if item.order_type == "CANCEL_ALGO_ORDER"]
        self.assertEqual([item.metadata["cancel_client_algo_id"] for item in cancel_instructions], ["overcovered-tp-1", "overcovered-tp-2"])
        replacement_tps = [item for item in plan.instructions if item.order_type == "TAKE_PROFIT_MARKET"]
        self.assertEqual(len(replacement_tps), 2)
        self.assertAlmostEqual(sum(item.quantity for item in replacement_tps), 0.3486655)
        self.assertAlmostEqual(replacement_tps[0].quantity, 0.17433275)
        self.assertAlmostEqual(replacement_tps[1].quantity, 0.17433275)

    def test_reducing_long_keeps_stop_loss_fail_closed_at_current_exposure(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=0.3486655,
            action="hold_long",
            reason="trend",
            metadata={"signal": {"entry_reference": 1786.31, "trailing_stop": 1757.63}},
        )

        plan = engine.plan_orders(intent, {"approved": True}, {"positions": {"ETHUSDT": {"size": 0.497}}})

        stop_orders = [item for item in plan.instructions if item.order_type == "STOP_MARKET"]
        self.assertEqual(len(stop_orders), 1)
        self.assertAlmostEqual(stop_orders[0].quantity, 0.497)
        self.assertTrue(stop_orders[0].metadata["close_position"])

    def test_same_price_overcovered_take_profit_is_replaced(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=0.4,
            action="hold_long",
            reason="trend",
            metadata={"signal": {"entry_reference": 1800.0, "take_profit_1": 1820.0, "take_profit_2": 1840.0}},
        )
        portfolio_state = {
            "positions": {"ETHUSDT": {"size": 0.4}},
            "open_algo_orders": [
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "quantity": "0.3",
                    "reduceOnly": True,
                    "triggerPrice": "1820.0",
                    "clientAlgoId": "too-large-tp-1",
                    "algoId": 401,
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "quantity": "0.3",
                    "reduceOnly": True,
                    "triggerPrice": "1840.0",
                    "clientAlgoId": "too-large-tp-2",
                    "algoId": 402,
                },
            ],
        }

        plan = engine.plan_orders(intent, {"approved": True}, portfolio_state)

        cancel_instructions = [item for item in plan.instructions if item.order_type == "CANCEL_ALGO_ORDER"]
        self.assertEqual([item.metadata["cancel_client_algo_id"] for item in cancel_instructions], ["too-large-tp-1", "too-large-tp-2"])
        replacement_tps = [item for item in plan.instructions if item.order_type == "TAKE_PROFIT_MARKET"]
        self.assertEqual(len(replacement_tps), 2)
        self.assertEqual([item.metadata["protection_role"] for item in replacement_tps], ["take_profit_1", "take_profit_2"])
        self.assertAlmostEqual(sum(item.quantity for item in replacement_tps), 0.4)

    def test_flattening_long_cancels_remaining_take_profit_protection(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=0.0,
            action="flat",
            reason="stop hit",
            metadata={"signal": {"entry_reference": 1767.57, "take_profit_1": 1814.98, "take_profit_2": 1843.66}},
        )
        portfolio_state = {
            "positions": {"ETHUSDT": {"size": 0.349}},
            "open_algo_orders": [
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "quantity": "0.174",
                    "reduceOnly": True,
                    "triggerPrice": "1814.98",
                    "clientAlgoId": "orphan-tp-1",
                    "algoId": 501,
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "orderType": "TAKE_PROFIT_MARKET",
                    "quantity": "0.175",
                    "reduceOnly": True,
                    "triggerPrice": "1843.66",
                    "clientAlgoId": "orphan-tp-2",
                    "algoId": 502,
                },
            ],
        }

        plan = engine.plan_orders(intent, {"approved": True}, portfolio_state)

        market_orders = [item for item in plan.instructions if item.order_type == "MARKET"]
        self.assertEqual(len(market_orders), 1)
        self.assertEqual(market_orders[0].side, "SELL")
        self.assertAlmostEqual(market_orders[0].quantity, 0.349)
        cancel_instructions = [item for item in plan.instructions if item.order_type == "CANCEL_ALGO_ORDER"]
        self.assertEqual([item.metadata["cancel_client_algo_id"] for item in cancel_instructions], ["orphan-tp-1", "orphan-tp-2"])
        self.assertFalse(any(item.order_type == "TAKE_PROFIT_MARKET" for item in plan.instructions))

    def test_position_reconciliation_execution_engine_keeps_only_tightest_stop_loss_when_duplicates_exist(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="ETHUSDT",
            desired_exposure=0.361,
            action="hold_long",
            reason="trend",
            metadata={"signal": {"entry_reference": 1799.44, "trailing_stop": 1757.99}},
        )
        portfolio_state = {
            "positions": {"ETHUSDT": {"size": 0.361}},
            "open_algo_orders": [
                {"symbol": "ETHUSDT", "side": "SELL", "orderType": "STOP_MARKET", "closePosition": True, "triggerPrice": "1748.85", "clientAlgoId": "old-stop", "algoId": 201},
                {"symbol": "ETHUSDT", "side": "SELL", "orderType": "STOP_MARKET", "closePosition": True, "triggerPrice": "1757.99", "clientAlgoId": "tight-stop", "algoId": 202},
            ],
        }

        plan = engine.plan_orders(intent, {"approved": True}, portfolio_state)

        cancel_instructions = [item for item in plan.instructions if item.order_type == "CANCEL_ALGO_ORDER"]
        self.assertEqual([item.metadata["cancel_client_algo_id"] for item in cancel_instructions], ["old-stop"])
        self.assertEqual(cancel_instructions[0].metadata["cancel_reason"], "stale_stop_loss_replacement")
        self.assertFalse(any(item.order_type == "STOP_MARKET" for item in plan.instructions))

    def test_testnet_broker_uses_testnet_base_url_only(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=True,
        )

        self.assertEqual(broker.environment, "testnet")
        self.assertIn("testnet.binancefuture.com", broker.base_url)
        with self.assertRaises(ValueError):
            brokers.BinanceTestnetBroker(
                credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
                base_url="https://fapi.binance.com",
                dry_run=True,
            )
        with self.assertRaises(ValueError):
            brokers.BinanceTestnetBroker(
                credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
                base_url="https://testnet.binancefuture.com.evil.example",
                dry_run=True,
            )

    def test_testnet_broker_fails_closed_when_credentials_missing(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")

        with self.assertRaises(RuntimeError) as ctx:
            brokers.resolve_binance_testnet_credentials(env={})

        message = str(ctx.exception)
        self.assertIn("LALA_KEY", message)
        self.assertIn("LALA_SECRET", message)
        self.assertNotIn("api_key", message.lower())
        self.assertNotIn("secret=", message.lower())

    def test_testnet_broker_dry_run_never_signs_or_submits(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        class ExplodingHttpClient:
            def request(self, *args, **kwargs):
                raise AssertionError("dry-run must not submit HTTP requests")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=True,
            http_client=ExplodingHttpClient(),
        )
        broker._sign_params = lambda params: (_ for _ in ()).throw(AssertionError("dry-run must not sign"))

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.1,
                metadata={"reference_price": 100.0},
            )
        )

        self.assertEqual(event["environment"], "testnet")
        self.assertTrue(event["testnet_dry_run"])
        self.assertFalse(event["real_order_submitted"])
        self.assertFalse(event["signed"])
        self.assertEqual(broker.submitted_order_count, 0)

    def test_testnet_broker_dry_run_tracks_short_entry_price(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=True,
        )
        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="ETHUSDT",
                side="SELL",
                quantity=0.25,
                metadata={"reference_price": 200.0},
            )
        )

        self.assertFalse(event["real_order_submitted"])
        state = broker.get_account_state()
        self.assertEqual(state["positions"]["ETHUSDT"]["size"], -0.25)
        self.assertEqual(state["positions"]["ETHUSDT"]["entry_price"], 200.0)

    def test_testnet_broker_rejects_invalid_algo_cancel_before_signing(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        class ExplodingHttpClient:
            def request(self, *args, **kwargs):
                raise AssertionError("invalid cancel must not submit HTTP requests")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            http_client=ExplodingHttpClient(),
        )
        broker._sign_params = lambda params: (_ for _ in ()).throw(AssertionError("invalid cancel must reject before signing"))

        missing_symbol = broker.cancel_order("123")
        missing_id = broker.submit_order(
            execution.OrderInstruction(symbol="BTCUSDT", side="SELL", quantity=0.0, order_type="CANCEL_ALGO_ORDER", metadata={})
        )

        self.assertEqual(missing_symbol["status"], "rejected")
        self.assertEqual(missing_symbol["reason"], "cancel_symbol_required")
        self.assertFalse(missing_symbol["real_order_submitted"])
        self.assertFalse(missing_symbol["signed"])
        self.assertEqual(missing_id["status"], "rejected")
        self.assertEqual(missing_id["reason"], "cancel_algo_identifier_required")
        self.assertFalse(missing_id["real_order_submitted"])
        self.assertFalse(missing_id["signed"])

    def test_testnet_broker_rejects_algo_cancel_when_global_risk_gate_trips(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        class ExplodingHttpClient:
            def request(self, *args, **kwargs):
                raise AssertionError("risk-rejected cancel must not submit HTTP requests")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            risk_limits=brokers.TestnetRiskLimits(kill_switch=True),
            http_client=ExplodingHttpClient(),
        )
        broker._sign_params = lambda params: (_ for _ in ()).throw(AssertionError("risk-rejected cancel must reject before signing"))

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="SELL",
                quantity=0.0,
                order_type="CANCEL_ALGO_ORDER",
                metadata={"cancel_algo_id": "123"},
            )
        )

        self.assertEqual(event["status"], "rejected")
        self.assertEqual(event["reason"], "kill_switch_enabled")
        self.assertFalse(event["real_order_submitted"])
        self.assertFalse(event["signed"])

    def test_testnet_runtime_record_redacts_sensitive_fields(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")

        payload = {
            "apiKey": "key-value",
            "secret": "secret-value",
            "signature": "abc123",
            "nested": {"X-MBX-APIKEY": "key-value", "orderId": "12345", "clientOrderId": "client-1"},
        }
        redacted = brokers.redact_sensitive_testnet_fields(payload)
        encoded = json.dumps(redacted)

        self.assertNotIn("key-value", encoded)
        self.assertNotIn("secret-value", encoded)
        self.assertNotIn("abc123", encoded)
        self.assertIn("<redacted>", encoded)
        self.assertEqual(redacted["nested"]["orderId"], "12345")

    def test_testnet_broker_blocks_oversized_order_before_signing(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10.0),
        )
        broker._sign_params = lambda params: (_ for _ in ()).throw(AssertionError("risk rejection must happen before signing"))

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="BUY",
                quantity=1.0,
                metadata={"reference_price": 100.0},
            )
        )

        self.assertEqual(event["status"], "rejected")
        self.assertEqual(event["reason"], "max_order_notional_exceeded")
        self.assertFalse(event["real_order_submitted"])

    def test_testnet_broker_rejects_missing_reference_price_before_signing(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10.0),
        )
        broker._sign_params = lambda params: (_ for _ in ()).throw(AssertionError("invalid reference price must reject before signing"))

        event = broker.submit_order(execution.OrderInstruction(symbol="BTCUSDT", side="BUY", quantity=1000.0))

        self.assertEqual(event["status"], "rejected")
        self.assertEqual(event["reason"], "invalid_reference_price")
        self.assertFalse(event["real_order_submitted"])
        self.assertFalse(event["signed"])

    def test_testnet_broker_sanitizes_unknown_signed_submission_failures(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        class LeakyHttpClient:
            def request(self, method, url, headers=None, body=None, timeout=20):
                raise RuntimeError(f"boom url={url} key={(headers or {}).get('X-MBX-APIKEY')}")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10_000.0),
            http_client=LeakyHttpClient(),
        )

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="BUY",
                quantity=1.0,
                metadata={"reference_price": 100.0},
            )
        )
        encoded = json.dumps(event)

        self.assertEqual(event["status"], "submitted_unknown")
        self.assertTrue(event["real_order_submitted"])
        self.assertTrue(event["attempted_real_order_submitted"])
        self.assertTrue(event["signed"])
        self.assertEqual(broker.submitted_order_count, 1)
        self.assertEqual(broker.accepted_order_count, 0)
        self.assertNotIn("signature=", encoded)
        self.assertNotIn("X-MBX-APIKEY", encoded)
        self.assertNotIn("boom url=", encoded)

    def test_testnet_exchange_rules_quantize_order_before_dry_run(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        rules = brokers.SymbolExchangeRules.from_exchange_info(
            "BTCUSDT",
            {
                "filters": [
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ]
            },
        )
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=True,
            exchange_rules_by_symbol={"BTCUSDT": rules},
        )

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.123456,
                metadata={"reference_price": 100.17},
            )
        )

        self.assertEqual(event["status"], "dry_run")
        self.assertEqual(event["quantity"], 0.123)
        self.assertEqual(event["reference_price"], 100.1)
        self.assertEqual(event["request"]["params"]["quantity"], "0.123")
        self.assertEqual(event["exchange_rule_adjustments"]["quantity_before"], 0.123456)
        self.assertEqual(event["exchange_rule_adjustments"]["quantity_after"], 0.123)
        self.assertEqual(event["exchange_rule_adjustments"]["reference_price_after"], 100.1)

    def test_testnet_exchange_rules_reject_order_below_min_qty_before_signing(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        rules = brokers.SymbolExchangeRules.from_exchange_info(
            "BTCUSDT",
            {
                "filters": [
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                    {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ]
            },
        )
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            exchange_rules_by_symbol={"BTCUSDT": rules},
        )

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.0009,
                metadata={"reference_price": 100.0},
            )
        )

        self.assertEqual(event["status"], "rejected")
        self.assertEqual(event["reason"], "exchange_min_qty_not_met")
        self.assertFalse(event["signed"])
        self.assertFalse(event["real_order_submitted"])

    def test_testnet_broker_rejects_zero_quantity_without_raising(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=True,
        )

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="TRXUSDT",
                side="BUY",
                quantity=0.0,
                metadata={"reference_price": 0.01},
            )
        )

        self.assertEqual(event["status"], "rejected")
        self.assertEqual(event["reason"], "non_positive_quantity")
        self.assertFalse(event["signed"])
        self.assertFalse(event["real_order_submitted"])

    def test_testnet_broker_rejects_nan_quantity_before_signing(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        class FailIfCalledHttpClient:
            def request(self, *args, **kwargs):
                raise AssertionError("non-finite quantity must not reach HTTP")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            http_client=FailIfCalledHttpClient(),
        )

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="BUY",
                quantity=float("nan"),
                metadata={"reference_price": 100.0},
            )
        )

        self.assertEqual(event["status"], "rejected")
        self.assertEqual(event["reason"], "non_finite_quantity")
        self.assertFalse(event["signed"])
        self.assertFalse(event["real_order_submitted"])

    def test_testnet_exchange_rules_reject_zero_quantity_after_step_adaptation_before_signing(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        class FailIfCalledHttpClient:
            def request(self, *args, **kwargs):
                raise AssertionError("zero adapted quantity must not reach HTTP")

        rules = brokers.SymbolExchangeRules.from_exchange_info(
            "BTCUSDT",
            {"filters": [{"filterType": "LOT_SIZE", "stepSize": "0.001"}]},
        )
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            http_client=FailIfCalledHttpClient(),
            exchange_rules_by_symbol={"BTCUSDT": rules},
        )

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.0004,
                metadata={"reference_price": 100.0},
            )
        )

        self.assertEqual(event["status"], "rejected")
        self.assertEqual(event["reason"], "exchange_quantity_not_positive_after_adaptation")
        self.assertFalse(event["signed"])
        self.assertFalse(event["real_order_submitted"])

    def test_testnet_snapshot_open_algo_orders_prevent_duplicate_protection(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=True,
        )
        broker.load_positions_from_account_snapshot(
            {
                "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.001", "entryPrice": "66000"}],
                "open_orders": [],
                "open_algo_orders": [
                    {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "side": "SELL", "algoStatus": "NEW", "closePosition": "true", "triggerPrice": "65430"},
                    {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "algoStatus": "NEW", "reduceOnly": "true", "origQty": "0.001", "triggerPrice": "67553"},
                ],
            }
        )
        signal = {
            "symbol": "BTCUSDT",
            "action": "hold_long",
            "position_size": 0.001,
            "entry_reference": 66340.0,
            "trailing_stop": 65430.0,
            "take_profit_2": 67553.0,
        }
        intent = types.StrategyIntent(
            symbol="BTCUSDT",
            action="hold_long",
            desired_exposure=0.001,
            reason="test existing protected position",
            metadata={"signal": signal},
        )
        plan = execution.PositionReconciliationExecutionEngine().plan_orders(
            intent,
            {"approved": True},
            broker.get_account_state(),
        )
        self.assertEqual(plan.instructions, [])
        self.assertEqual(plan.metadata.get("reason"), "target_exposure_already_reached")

    def test_position_reconciliation_adds_stop_and_layered_take_profit_protection_for_existing_long(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="BTCUSDT",
            desired_exposure=0.02,
            action="hold_long",
            reason="trend",
            metadata={
                "signal": {
                    "entry_reference": 100.0,
                    "trailing_stop": 90.0,
                    "take_profit_1": 120.0,
                    "take_profit_2": 140.0,
                }
            },
        )

        plan = engine.plan_orders(
            intent,
            {"approved": True},
            {"positions": {"BTCUSDT": {"size": 0.02}}, "open_orders": [], "open_algo_orders": []},
        )

        self.assertEqual([item.order_type for item in plan.instructions], ["STOP_MARKET", "TAKE_PROFIT_MARKET", "TAKE_PROFIT_MARKET"])
        stop_order, take_profit_1, take_profit_2 = plan.instructions
        self.assertEqual(stop_order.side, "SELL")
        self.assertEqual(take_profit_1.side, "SELL")
        self.assertEqual(take_profit_2.side, "SELL")
        self.assertEqual(stop_order.quantity, 0.02)
        self.assertEqual(take_profit_1.quantity, 0.01)
        self.assertEqual(take_profit_2.quantity, 0.01)
        self.assertTrue(stop_order.metadata["protective_order"])
        self.assertTrue(take_profit_1.metadata["protective_order"])
        self.assertTrue(take_profit_2.metadata["protective_order"])
        self.assertEqual(stop_order.metadata["protection_role"], "stop_loss")
        self.assertEqual(take_profit_1.metadata["protection_role"], "take_profit_1")
        self.assertEqual(take_profit_2.metadata["protection_role"], "take_profit_2")
        self.assertEqual(stop_order.metadata["stop_price"], 90.0)
        self.assertEqual(take_profit_1.metadata["stop_price"], 120.0)
        self.assertEqual(take_profit_2.metadata["stop_price"], 140.0)
        self.assertTrue(stop_order.metadata["close_position"])
        self.assertTrue(take_profit_1.metadata["reduce_only"])
        self.assertTrue(take_profit_2.metadata["reduce_only"])
        self.assertNotIn("close_position", take_profit_1.metadata)
        self.assertNotIn("close_position", take_profit_2.metadata)

    def test_position_reconciliation_adds_only_missing_take_profit_layer(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="BTCUSDT",
            desired_exposure=0.02,
            action="hold_long",
            reason="trend",
            metadata={"signal": {"entry_reference": 100.0, "trailing_stop": 90.0, "take_profit_1": 120.0, "take_profit_2": 140.0}},
        )

        plan = engine.plan_orders(
            intent,
            {"approved": True},
            {
                "positions": {"BTCUSDT": {"size": 0.02}},
                "open_algo_orders": [
                    {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "side": "SELL", "triggerPrice": "90", "closePosition": "true"},
                    {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "triggerPrice": "120", "reduceOnly": "true", "origQty": "0.01"},
                ],
            },
        )

        self.assertEqual([item.order_type for item in plan.instructions], ["TAKE_PROFIT_MARKET"])
        self.assertEqual(plan.instructions[0].metadata["protection_role"], "take_profit_2")
        self.assertEqual(plan.instructions[0].quantity, 0.01)
        self.assertEqual(plan.instructions[0].metadata["stop_price"], 140.0)

    def test_position_reconciliation_tops_up_undercovered_take_profit_layers(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")

        engine = execution.PositionReconciliationExecutionEngine()
        intent = types.StrategyIntent(
            symbol="BTCUSDT",
            desired_exposure=0.02,
            action="hold_long",
            reason="trend",
            metadata={"signal": {"entry_reference": 100.0, "trailing_stop": 90.0, "take_profit_1": 120.0, "take_profit_2": 140.0}},
        )

        plan = engine.plan_orders(
            intent,
            {"approved": True},
            {
                "positions": {"BTCUSDT": {"size": 0.02}},
                "open_algo_orders": [
                    {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "side": "SELL", "triggerPrice": "90", "closePosition": "true"},
                    {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "triggerPrice": "120", "reduceOnly": "true", "origQty": "0.005"},
                    {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "triggerPrice": "140", "reduceOnly": "true", "origQty": "0.005"},
                ],
            },
        )

        self.assertEqual([item.order_type for item in plan.instructions], ["TAKE_PROFIT_MARKET", "TAKE_PROFIT_MARKET"])
        self.assertEqual([item.metadata["protection_role"] for item in plan.instructions], ["take_profit_1", "take_profit_2"])
        self.assertEqual([item.metadata["stop_price"] for item in plan.instructions], [120.0, 140.0])
        self.assertEqual([item.quantity for item in plan.instructions], [0.005, 0.005])

    def test_position_reconciliation_replaces_stop_only_when_trailing_stop_moves_up(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        types = importlib.import_module("scripts.binance_trend_core.types")
        engine = execution.PositionReconciliationExecutionEngine()
        portfolio_state = {
            "positions": {"BTCUSDT": {"size": 0.02}},
            "open_algo_orders": [
                {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "side": "SELL", "triggerPrice": "90", "algoId": 11, "clientAlgoId": "old-stop", "closePosition": "true"},
                {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "triggerPrice": "120", "clientAlgoId": "tp1", "reduceOnly": "true", "origQty": "0.01"},
                {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "triggerPrice": "140", "clientAlgoId": "tp2", "reduceOnly": "true", "origQty": "0.01"},
            ],
        }

        up_intent = types.StrategyIntent(
            symbol="BTCUSDT",
            desired_exposure=0.02,
            action="hold_long",
            reason="trend",
            metadata={"signal": {"entry_reference": 100.0, "trailing_stop": 95.0, "take_profit_1": 120.0, "take_profit_2": 140.0}},
        )
        up_plan = engine.plan_orders(up_intent, {"approved": True}, portfolio_state)

        self.assertEqual([item.order_type for item in up_plan.instructions], ["STOP_MARKET"])
        self.assertEqual(up_plan.instructions[0].metadata["stop_price"], 95.0)
        self.assertEqual(up_plan.instructions[0].metadata["trailing_stop_replacement"], True)

        down_intent = types.StrategyIntent(
            symbol="BTCUSDT",
            desired_exposure=0.02,
            action="hold_long",
            reason="trend",
            metadata={"signal": {"entry_reference": 100.0, "trailing_stop": 88.0, "take_profit_1": 120.0, "take_profit_2": 140.0}},
        )
        down_plan = engine.plan_orders(down_intent, {"approved": True}, portfolio_state)
        self.assertEqual(down_plan.instructions, [])

    def test_testnet_broker_encodes_close_position_conditional_protection_without_quantity(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        rules = brokers.SymbolExchangeRules.from_exchange_info(
            "BTCUSDT",
            {"filters": [{"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"}, {"filterType": "PRICE_FILTER", "tickSize": "0.10"}]},
        )

        class FakeHttpClient:
            def __init__(self):
                self.urls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.urls.append(url)
                return {"orderId": 123, "status": "NEW"}

        client = FakeHttpClient()
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            http_client=client,
            exchange_rules_by_symbol={"BTCUSDT": rules},
        )

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="SELL",
                quantity=0.01,
                order_type="STOP_MARKET",
                metadata={
                    "reference_price": 100.0,
                    "stop_price": 90.09,
                    "protective_order": True,
                    "close_position": True,
                    "working_type": "MARK_PRICE",
                },
            )
        )

        self.assertEqual(event["status"], "submitted")
        params = dict(item.split("=", 1) for item in client.urls[0].split("?", 1)[1].split("&"))
        self.assertIn("/fapi/v1/algoOrder?", client.urls[0])
        self.assertEqual(params["type"], "STOP_MARKET")
        self.assertEqual(params["algoType"], "CONDITIONAL")
        self.assertIn("clientAlgoId", params)
        self.assertEqual(params["triggerPrice"], "90")
        self.assertEqual(event["exchange_rule_adjustments"]["stop_price_before"], 90.09)
        self.assertEqual(event["exchange_rule_adjustments"]["stop_price_after"], 90.0)
        self.assertEqual(params["closePosition"], "true")
        self.assertEqual(params["workingType"], "MARK_PRICE")
        self.assertNotIn("quantity", params)
        self.assertNotIn("reduceOnly", params)

    def test_account_risk_sizing_uses_available_balance_stop_distance_and_equity_fraction_caps(self):
        signal = {
            "symbol": "BTCUSDT",
            "action": "hold_long",
            "entry_reference": 100.0,
            "trailing_stop": 90.0,
            "position_size": 999.0,
        }
        account_snapshot = {"account": {"availableBalance": "5000", "walletBalance": "10000"}}

        sized = trend.apply_account_risk_sizing_to_signal(
            signal,
            account_snapshot,
            account_risk_fraction=0.01,
            target_leverage=2.0,
            max_order_notional=2000.0,
            max_symbol_exposure_fraction=0.10,
        )

        self.assertEqual(sized["position_size"], 10.0)
        sizing = sized["account_risk_sizing"]
        self.assertEqual(sizing["available_balance"], 5000.0)
        self.assertEqual(sizing["account_equity"], 10000.0)
        self.assertEqual(sizing["risk_budget"], 100.0)
        self.assertEqual(sizing["stop_distance"], 10.0)
        self.assertEqual(sizing["max_symbol_exposure_fraction"], 0.1)
        self.assertEqual(sizing["max_symbol_exposure_from_fraction"], 1000.0)
        self.assertIn("max_order_notional_cap", sizing["constraints_applied"])
        self.assertIn("max_symbol_exposure_fraction_cap", sizing["constraints_applied"])

    def test_account_risk_sizing_rejects_non_positive_exposure_fraction(self):
        signal = {"symbol": "BTCUSDT", "action": "hold_long", "entry_reference": 100.0, "trailing_stop": 90.0}
        with self.assertRaises(ValueError):
            trend.apply_account_risk_sizing_to_signal(
                signal,
                {"account": {"availableBalance": "5000"}},
                max_symbol_exposure_fraction=0.0,
            )

    def test_verify_position_protection_requires_safe_long_close_or_reduce_only_orders(self):
        unsafe = trend.verify_position_protection(
            {
                "positions": [
                    {"symbol": "BTCUSDT", "positionAmt": "0.02"},
                ],
                "open_algo_orders": [
                    {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "side": "SELL", "triggerPrice": "90"},
                    {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "BUY", "triggerPrice": "120", "reduceOnly": "true"},
                ],
            }
        )
        self.assertFalse(unsafe["all_positions_protected"])
        self.assertEqual(unsafe["unprotected_symbols"], ["BTCUSDT"])
        self.assertIn("missing_stop_loss", unsafe["symbols"]["BTCUSDT"]["issues"])
        self.assertIn("missing_take_profit", unsafe["symbols"]["BTCUSDT"]["issues"])

        partial = trend.verify_position_protection(
            {
                "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.02"}],
                "open_algo_orders": [
                    {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": "true", "triggerPrice": "90"},
                    {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": "true", "origQty": "0.01", "triggerPrice": "120"},
                ],
            }
        )
        self.assertFalse(partial["all_positions_protected"])
        self.assertEqual(partial["unprotected_symbols"], ["BTCUSDT"])
        self.assertIn("missing_take_profit", partial["symbols"]["BTCUSDT"]["issues"])

        missing_quantity = trend.verify_position_protection(
            {
                "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.02"}],
                "open_algo_orders": [
                    {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": "true", "triggerPrice": "90"},
                    {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": "true", "triggerPrice": "120"},
                ],
            }
        )
        self.assertFalse(missing_quantity["all_positions_protected"])
        self.assertIn("missing_take_profit", missing_quantity["symbols"]["BTCUSDT"]["issues"])

        safe = trend.verify_position_protection(
            {
                "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.02"}],
                "open_algo_orders": [
                    {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": "true", "triggerPrice": "90"},
                    {"symbol": "BTCUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": "true", "origQty": "0.02", "triggerPrice": "120"},
                ],
            }
        )
        self.assertTrue(safe["all_positions_protected"])

    def test_verify_position_protection_supports_safe_short_buy_protection(self):
        safe = trend.verify_position_protection(
            {
                "positions": [{"symbol": "ETHUSDT", "positionAmt": "-0.5"}],
                "open_algo_orders": [
                    {"symbol": "ETHUSDT", "orderType": "STOP_MARKET", "side": "BUY", "closePosition": "true", "triggerPrice": "110"},
                    {"symbol": "ETHUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "BUY", "reduceOnly": "true", "origQty": "0.5", "triggerPrice": "90"},
                ],
            }
        )

        self.assertTrue(safe["all_positions_protected"])
        self.assertEqual(safe["unprotected_symbols"], [])
        self.assertEqual(safe["symbols"]["ETHUSDT"]["position_amt"], -0.5)

        wrong_side = trend.verify_position_protection(
            {
                "positions": [{"symbol": "ETHUSDT", "positionAmt": "-0.5"}],
                "open_algo_orders": [
                    {"symbol": "ETHUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": "true", "triggerPrice": "110"},
                    {"symbol": "ETHUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": "true", "origQty": "0.5", "triggerPrice": "90"},
                ],
            }
        )

        self.assertFalse(wrong_side["all_positions_protected"])
        self.assertEqual(wrong_side["unprotected_symbols"], ["ETHUSDT"])

    def test_verify_position_protection_can_scope_to_cycle_symbols(self):
        scoped = trend.verify_position_protection(
            {
                "positions": [
                    {"symbol": "BTCUSDT", "positionAmt": "0"},
                    {"symbol": "ETHUSDT", "positionAmt": "0.5"},
                ],
                "open_algo_orders": [],
            },
            symbols=["BTCUSDT"],
        )

        self.assertTrue(scoped["all_positions_protected"])
        self.assertEqual(scoped["unprotected_symbols"], [])
        self.assertEqual(scoped["symbols"], {})

    def test_testnet_broker_fetches_exchange_info_rules_from_testnet_endpoint(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")

        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url, headers, body, timeout))
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "filters": [
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                        {"symbol": "ETHUSDT", "filters": []},
                    ]
                }

        client = FakeHttpClient()
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            http_client=client,
        )

        loaded = broker.refresh_exchange_rules(["BTCUSDT"])

        self.assertEqual(client.calls[0][0], "GET")
        self.assertEqual(client.calls[0][1], "https://testnet.binancefuture.com/fapi/v1/exchangeInfo")
        self.assertIn("BTCUSDT", loaded)
        self.assertIn("BTCUSDT", broker.exchange_rules_by_symbol)
        self.assertEqual(str(broker.exchange_rules_by_symbol["BTCUSDT"].step_size), "0.001")
        self.assertNotIn("ETHUSDT", loaded)

    def test_testnet_broker_fetches_signed_account_snapshot(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")

        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url, headers, body, timeout))
                if "/fapi/v2/account" in url:
                    return {"assets": [{"asset": "USDT", "walletBalance": "1000"}]}
                if "/fapi/v2/positionRisk" in url:
                    return [{"symbol": "BTCUSDT", "positionAmt": "0.01"}]
                if "/fapi/v1/openOrders" in url:
                    return [{"symbol": "BTCUSDT", "clientOrderId": "cid-1"}]
                if "/fapi/v1/openAlgoOrders" in url:
                    return [{"symbol": "BTCUSDT", "clientAlgoId": "algo-1", "orderType": "STOP_MARKET"}]
                raise AssertionError(url)

        client = FakeHttpClient()
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            http_client=client,
        )

        snapshot = broker.fetch_signed_account_snapshot(symbol="BTCUSDT")

        self.assertEqual([call[0] for call in client.calls], ["GET", "GET", "GET", "GET"])
        self.assertIn("/fapi/v2/account?", client.calls[0][1])
        self.assertIn("/fapi/v2/positionRisk?", client.calls[1][1])
        self.assertIn("/fapi/v1/openOrders?", client.calls[2][1])
        self.assertIn("/fapi/v1/openAlgoOrders?", client.calls[3][1])
        self.assertEqual(snapshot["environment"], "testnet")
        self.assertEqual(snapshot["account"]["assets"][0]["asset"], "USDT")
        self.assertEqual(snapshot["positions"][0]["symbol"], "BTCUSDT")
        self.assertEqual(snapshot["open_orders"][0]["clientOrderId"], "cid-1")
        self.assertEqual(snapshot["open_algo_orders"][0]["clientAlgoId"], "algo-1")
        encoded = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn("signature=", encoded)
        self.assertNotIn("X-MBX-APIKEY", encoded)

    def test_testnet_broker_reconciles_unknown_local_order_with_open_orders(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
        )
        broker.fills.append(
            {
                "environment": "testnet",
                "symbol": "BTCUSDT",
                "status": "submitted_unknown",
                "client_order_id": "cid-unknown",
            }
        )

        report = broker.reconcile_open_orders(
            open_orders=[{"symbol": "BTCUSDT", "clientOrderId": "cid-unknown", "orderId": 123}]
        )

        self.assertEqual(report["environment"], "testnet")
        self.assertEqual(report["matched_open_order_client_ids"], ["cid-unknown"])
        self.assertEqual(report["missing_unknown_client_ids"], [])
        self.assertEqual(report["unknown_local_count"], 1)

    def test_testnet_broker_reconciles_unknown_local_algo_order_with_open_algo_orders(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
        )
        broker.fills.append(
            {
                "environment": "testnet",
                "symbol": "SOLUSDT",
                "status": "submitted_unknown",
                "client_order_id": "algo-unknown",
                "client_algo_id": "algo-unknown",
            }
        )

        report = broker.reconcile_open_orders(
            {
                "open_orders": [],
                "open_algo_orders": [{"symbol": "SOLUSDT", "clientAlgoId": "algo-unknown", "algoId": 456}],
            }
        )

        self.assertEqual(report["matched_open_order_client_ids"], ["algo-unknown"])
        self.assertEqual(report["missing_unknown_client_ids"], [])
        self.assertEqual(report["unknown_local_count"], 1)

    def test_testnet_client_order_id_is_unique_across_fresh_brokers(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")

        broker_a = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            client_order_id_prefix="testcid",
        )
        broker_b = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            client_order_id_prefix="testcid",
        )

        first = broker_a._build_client_order_id("BTCUSDT")
        second = broker_b._build_client_order_id("BTCUSDT")

        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^testcid-BTCUSDT-[0-9]{13}-[0-9a-f]{6}$")
        self.assertRegex(second, r"^testcid-BTCUSDT-[0-9]{13}-[0-9a-f]{6}$")

    def test_testnet_signed_submission_uses_client_order_id_and_order_journal(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        class FakeHttpClient:
            def request(self, method, url, headers=None, body=None, timeout=20):
                parsed = url.split("?", 1)[1]
                params = dict(item.split("=", 1) for item in parsed.split("&"))
                return {"orderId": 99, "clientOrderId": params["newClientOrderId"], "status": "NEW"}

        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = pathlib.Path(tmpdir) / "orders.jsonl"
            broker = brokers.BinanceTestnetBroker(
                credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
                dry_run=False,
                http_client=FakeHttpClient(),
                order_journal_path=str(journal_path),
                client_order_id_prefix="testcid",
            )

            event = broker.submit_order(
                execution.OrderInstruction(
                    symbol="BTCUSDT",
                    side="BUY",
                    quantity=0.01,
                    metadata={"reference_price": 100.0},
                )
            )

            self.assertEqual(event["status"], "submitted")
            self.assertTrue(event["client_order_id"].startswith("testcid-"))
            self.assertEqual(event["request"]["params"]["newClientOrderId"], event["client_order_id"])
            rows = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["client_order_id"], event["client_order_id"])
            self.assertEqual(rows[0]["status"], "submitted")
            self.assertNotIn("signature", json.dumps(rows[0]))

    def test_testnet_unknown_submission_queries_order_status_by_client_order_id(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if method == "POST":
                    raise TimeoutError("network timeout")
                if "/fapi/v1/order" in url:
                    return {"orderId": 101, "clientOrderId": "testcid-1", "status": "NEW"}
                raise AssertionError(url)

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            http_client=FakeHttpClient(),
            client_order_id_prefix="testcid",
        )

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.01,
                metadata={"reference_price": 100.0},
            )
        )

        self.assertEqual(event["status"], "submitted_confirmed")
        self.assertEqual(event["response"]["orderId"], 101)
        self.assertIn(f"origClientOrderId={event['client_order_id']}", broker.http_client.calls[1][1])
        self.assertTrue(event["client_order_id"].startswith("testcid-BTCUSDT-"))

    def test_testnet_unknown_algo_submission_queries_algo_order_by_client_algo_id(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if method == "POST":
                    raise TimeoutError("network timeout")
                if "/fapi/v1/algoOrder" in url:
                    return {"algoId": 202, "clientAlgoId": "testcid-1", "status": "NEW"}
                raise AssertionError(url)

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            http_client=FakeHttpClient(),
            client_order_id_prefix="testcid",
        )

        event = broker.submit_order(
            execution.OrderInstruction(
                symbol="SOLUSDT",
                side="SELL",
                quantity=1.0,
                order_type="STOP_MARKET",
                metadata={"reference_price": 100.0, "stop_price": 95.0, "close_position": True},
            )
        )

        self.assertEqual(event["status"], "submitted_confirmed")
        self.assertEqual(event["response"]["algoId"], 202)
        self.assertIn("/fapi/v1/algoOrder?", broker.http_client.calls[1][1])
        self.assertIn(f"clientAlgoId={event['client_order_id']}", broker.http_client.calls[1][1])
        self.assertNotIn("origClientOrderId=", broker.http_client.calls[1][1])

    def test_trading_cycle_prioritizes_missing_take_profit_repairs_before_new_addons_when_order_budget_is_tight(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        portfolio = importlib.import_module("scripts.binance_trend_core.portfolio")
        risk = importlib.import_module("scripts.binance_trend_core.risk")
        types = importlib.import_module("scripts.binance_trend_core.types")

        def signal_for(symbol):
            base = {"ETHUSDT": 1800.0, "SOLUSDT": 75.0, "BNBUSDT": 615.0}[symbol]
            return {
                "symbol": symbol,
                "interval": "1h",
                "action": "hold_long",
                "position_size": {"ETHUSDT": 0.2, "SOLUSDT": 2.0, "BNBUSDT": 0.11}[symbol],
                "entry_reference": base,
                "close": base,
                "trailing_stop": base * 0.98,
                "take_profit_1": base * 1.01,
                "take_profit_2": base * 1.02,
                "reason": "trend",
            }

        class StaticSignalEngine:
            def generate_signal(self, candles, *, symbol, interval):
                return signal_for(symbol)

        class SignalStrategy:
            def generate_intent(self, signal):
                return types.StrategyIntent(
                    symbol=signal["symbol"],
                    desired_exposure=float(signal["position_size"]),
                    action="hold_long",
                    reason="trend",
                    metadata={"signal": signal},
                )

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials("key", "secret"),
            dry_run=True,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10_000, max_symbol_exposure=10_000, max_daily_loss=100, max_order_count=2),
        )
        broker.positions["BNBUSDT"] = portfolio.PortfolioPosition(symbol="BNBUSDT", size=0.11, entry_price=615.0)
        broker.open_algo_orders = [
            {"symbol": "BNBUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": True, "triggerPrice": "610", "algoId": "sl-1"}
        ]

        result = loop.run_trading_cycle(
            loop.TradingCycleConfig(
                symbols=["ETHUSDT", "SOLUSDT", "BNBUSDT"],
                interval="1h",
                candles_by_symbol={"ETHUSDT": [{}], "SOLUSDT": [{}], "BNBUSDT": [{}]},
            ),
            broker=broker,
            signal_engine=StaticSignalEngine(),
            strategy=SignalStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PositionReconciliationExecutionEngine(),
        )

        dry_run_bnb_tps = [
            fill for fill in result["fills"]
            if fill.get("symbol") == "BNBUSDT" and fill.get("order_type") == "TAKE_PROFIT_MARKET" and fill.get("status") == "dry_run"
        ]
        rejected_bnb_tps = [
            fill for fill in result["fills"]
            if fill.get("symbol") == "BNBUSDT" and fill.get("order_type") == "TAKE_PROFIT_MARKET" and fill.get("status") == "rejected"
        ]

        self.assertEqual(len(dry_run_bnb_tps), 2)
        self.assertEqual(rejected_bnb_tps, [])

    def test_trading_cycle_preserves_new_entry_protection_sequence_after_existing_repairs(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        risk = importlib.import_module("scripts.binance_trend_core.risk")
        types = importlib.import_module("scripts.binance_trend_core.types")

        def signal_for(symbol):
            base = {"ETHUSDT": 1800.0, "SOLUSDT": 75.0}[symbol]
            return {
                "symbol": symbol,
                "interval": "1h",
                "action": "hold_long",
                "position_size": {"ETHUSDT": 0.2, "SOLUSDT": 2.0}[symbol],
                "entry_reference": base,
                "close": base,
                "trailing_stop": base * 0.98,
                "take_profit_1": base * 1.01,
                "take_profit_2": base * 1.02,
                "reason": "trend",
            }

        class StaticSignalEngine:
            def generate_signal(self, candles, *, symbol, interval):
                return signal_for(symbol)

        class SignalStrategy:
            def generate_intent(self, signal):
                return types.StrategyIntent(
                    symbol=signal["symbol"],
                    desired_exposure=float(signal["position_size"]),
                    action="hold_long",
                    reason="trend",
                    metadata={"signal": signal},
                )

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials("key", "secret"),
            dry_run=True,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10_000, max_symbol_exposure=10_000, max_daily_loss=100, max_order_count=4),
        )

        result = loop.run_trading_cycle(
            loop.TradingCycleConfig(
                symbols=["ETHUSDT", "SOLUSDT"],
                interval="1h",
                candles_by_symbol={"ETHUSDT": [{}], "SOLUSDT": [{}]},
            ),
            broker=broker,
            signal_engine=StaticSignalEngine(),
            strategy=SignalStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PositionReconciliationExecutionEngine(),
        )

        accepted = [(fill.get("symbol"), fill.get("order_type")) for fill in result["fills"] if fill.get("status") == "dry_run"]
        self.assertEqual(
            accepted,
            [
                ("ETHUSDT", "MARKET"),
                ("ETHUSDT", "STOP_MARKET"),
                ("ETHUSDT", "TAKE_PROFIT_MARKET"),
                ("ETHUSDT", "TAKE_PROFIT_MARKET"),
            ],
        )
        self.assertFalse(any(fill.get("symbol") == "SOLUSDT" and fill.get("status") == "dry_run" for fill in result["fills"]))

    def test_trading_cycle_skips_new_entry_when_budget_cannot_cover_its_protection_group_after_repairs(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        portfolio = importlib.import_module("scripts.binance_trend_core.portfolio")
        risk = importlib.import_module("scripts.binance_trend_core.risk")
        types = importlib.import_module("scripts.binance_trend_core.types")

        def signal_for(symbol):
            base = {"BNBUSDT": 615.0, "ETHUSDT": 1800.0}[symbol]
            return {
                "symbol": symbol,
                "interval": "1h",
                "action": "hold_long",
                "position_size": {"BNBUSDT": 0.11, "ETHUSDT": 0.2}[symbol],
                "entry_reference": base,
                "close": base,
                "trailing_stop": base * 0.98,
                "take_profit_1": base * 1.01,
                "take_profit_2": base * 1.02,
                "reason": "trend",
            }

        class StaticSignalEngine:
            def generate_signal(self, candles, *, symbol, interval):
                return signal_for(symbol)

        class SignalStrategy:
            def generate_intent(self, signal):
                return types.StrategyIntent(
                    symbol=signal["symbol"],
                    desired_exposure=float(signal["position_size"]),
                    action="hold_long",
                    reason="trend",
                    metadata={"signal": signal},
                )

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials("key", "secret"),
            dry_run=True,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10_000, max_symbol_exposure=10_000, max_daily_loss=100, max_order_count=2),
        )
        broker.positions["BNBUSDT"] = portfolio.PortfolioPosition(symbol="BNBUSDT", size=0.11, entry_price=615.0)
        broker.open_algo_orders = [
            {"symbol": "BNBUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": True, "triggerPrice": "610", "algoId": "sl-1"},
            {"symbol": "BNBUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True, "origQty": "0.055", "triggerPrice": "621.15", "algoId": "tp-1"},
        ]

        result = loop.run_trading_cycle(
            loop.TradingCycleConfig(
                symbols=["BNBUSDT", "ETHUSDT"],
                interval="1h",
                candles_by_symbol={"BNBUSDT": [{}], "ETHUSDT": [{}]},
            ),
            broker=broker,
            signal_engine=StaticSignalEngine(),
            strategy=SignalStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PositionReconciliationExecutionEngine(),
        )

        accepted = [(fill.get("symbol"), fill.get("order_type"), fill.get("status")) for fill in result["fills"] if fill.get("status") == "dry_run"]
        skipped_eth = [fill for fill in result["fills"] if fill.get("symbol") == "ETHUSDT" and fill.get("status") == "skipped"]
        self.assertEqual(accepted, [("BNBUSDT", "TAKE_PROFIT_MARKET", "dry_run")])
        self.assertEqual(len(skipped_eth), 4)
        self.assertTrue(all(fill.get("reason") == "insufficient_order_budget_for_atomic_entry_protection_group" for fill in skipped_eth))

    def test_trading_cycle_prioritizes_existing_position_repairs_before_same_symbol_addon_when_budget_is_tight(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        portfolio = importlib.import_module("scripts.binance_trend_core.portfolio")
        risk = importlib.import_module("scripts.binance_trend_core.risk")
        types = importlib.import_module("scripts.binance_trend_core.types")

        signal = {
            "symbol": "BNBUSDT",
            "interval": "1h",
            "action": "hold_long",
            "position_size": 0.2,
            "entry_reference": 615.0,
            "close": 615.0,
            "trailing_stop": 602.7,
            "take_profit_1": 621.15,
            "take_profit_2": 627.3,
            "reason": "trend add-on",
        }

        class StaticSignalEngine:
            def generate_signal(self, candles, *, symbol, interval):
                return signal

        class SignalStrategy:
            def generate_intent(self, signal):
                return types.StrategyIntent(
                    symbol=signal["symbol"],
                    desired_exposure=float(signal["position_size"]),
                    action="hold_long",
                    reason="trend add-on",
                    metadata={"signal": signal},
                )

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials("key", "secret"),
            dry_run=True,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10_000, max_symbol_exposure=10_000, max_daily_loss=100, max_order_count=1),
        )
        broker.positions["BNBUSDT"] = portfolio.PortfolioPosition(symbol="BNBUSDT", size=0.1, entry_price=615.0)
        broker.open_algo_orders = [
            {"symbol": "BNBUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": True, "triggerPrice": "610", "algoId": "sl-1"}
        ]

        result = loop.run_trading_cycle(
            loop.TradingCycleConfig(symbols=["BNBUSDT"], interval="1h", candles_by_symbol={"BNBUSDT": [{}]}),
            broker=broker,
            signal_engine=StaticSignalEngine(),
            strategy=SignalStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PositionReconciliationExecutionEngine(),
        )

        accepted = [(fill.get("side"), fill.get("order_type"), fill.get("status")) for fill in result["fills"] if fill.get("status") == "dry_run"]
        self.assertEqual(accepted, [("SELL", "TAKE_PROFIT_MARKET", "dry_run")])
        self.assertFalse(any(fill.get("side") == "BUY" and fill.get("status") == "dry_run" for fill in result["fills"]))

    def test_trading_cycle_skips_stale_atomic_new_entry_when_recheck_state_reaches_target(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        portfolio = importlib.import_module("scripts.binance_trend_core.portfolio")
        risk = importlib.import_module("scripts.binance_trend_core.risk")
        types = importlib.import_module("scripts.binance_trend_core.types")

        signal = {
            "symbol": "ETHUSDT",
            "interval": "1h",
            "action": "hold_long",
            "position_size": 0.2,
            "entry_reference": 1800.0,
            "close": 1800.0,
            "trailing_stop": 1764.0,
            "take_profit_1": 1818.0,
            "take_profit_2": 1836.0,
            "reason": "trend",
        }

        class StaticSignalEngine:
            def generate_signal(self, candles, *, symbol, interval):
                return signal

        class SignalStrategy:
            def generate_intent(self, signal):
                return types.StrategyIntent(
                    symbol=signal["symbol"],
                    desired_exposure=float(signal["position_size"]),
                    action="hold_long",
                    reason="trend",
                    metadata={"signal": signal},
                )

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials("key", "secret"),
            dry_run=True,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10_000, max_symbol_exposure=10_000, max_daily_loss=100, max_order_count=4),
        )
        original_get_account_state = broker.get_account_state
        calls = {"count": 0}

        def get_account_state_with_external_fill():
            calls["count"] += 1
            if calls["count"] >= 2:
                broker.positions["ETHUSDT"] = portfolio.PortfolioPosition(symbol="ETHUSDT", size=0.2, entry_price=1800.0)
                broker.open_algo_orders = [
                    {"symbol": "ETHUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": True, "triggerPrice": "1764", "algoId": "sl-1"},
                    {"symbol": "ETHUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True, "origQty": "0.1", "triggerPrice": "1818", "algoId": "tp-1"},
                    {"symbol": "ETHUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True, "origQty": "0.1", "triggerPrice": "1836", "algoId": "tp-2"},
                ]
            return original_get_account_state()

        broker.get_account_state = get_account_state_with_external_fill

        result = loop.run_trading_cycle(
            loop.TradingCycleConfig(symbols=["ETHUSDT"], interval="1h", candles_by_symbol={"ETHUSDT": [{}]}),
            broker=broker,
            signal_engine=StaticSignalEngine(),
            strategy=SignalStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PositionReconciliationExecutionEngine(),
        )

        self.assertFalse(any(fill.get("status") == "dry_run" for fill in result["fills"]))
        self.assertTrue(all(fill.get("status") == "skipped" and fill.get("reason") == "stale_atomic_entry_group_no_longer_needed" for fill in result["fills"]))

    def test_trading_cycle_filters_duplicate_protections_from_atomic_addon_replan(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        portfolio = importlib.import_module("scripts.binance_trend_core.portfolio")
        risk = importlib.import_module("scripts.binance_trend_core.risk")
        types = importlib.import_module("scripts.binance_trend_core.types")

        signal = {
            "symbol": "BNBUSDT",
            "interval": "1h",
            "action": "hold_long",
            "position_size": 0.2,
            "entry_reference": 615.0,
            "close": 615.0,
            "trailing_stop": 602.7,
            "take_profit_1": 621.15,
            "take_profit_2": 627.3,
            "reason": "trend add-on",
        }

        class StaticSignalEngine:
            def generate_signal(self, candles, *, symbol, interval):
                return signal

        class SignalStrategy:
            def generate_intent(self, signal):
                return types.StrategyIntent(
                    symbol=signal["symbol"],
                    desired_exposure=float(signal["position_size"]),
                    action="hold_long",
                    reason="trend add-on",
                    metadata={"signal": signal},
                )

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials("key", "secret"),
            dry_run=True,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10_000, max_symbol_exposure=10_000, max_daily_loss=100, max_order_count=10),
        )
        broker.positions["BNBUSDT"] = portfolio.PortfolioPosition(symbol="BNBUSDT", size=0.1, entry_price=615.0)

        result = loop.run_trading_cycle(
            loop.TradingCycleConfig(symbols=["BNBUSDT"], interval="1h", candles_by_symbol={"BNBUSDT": [{}]}),
            broker=broker,
            signal_engine=StaticSignalEngine(),
            strategy=SignalStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PositionReconciliationExecutionEngine(),
        )

        dry_run_orders = [
            (fill.get("side"), fill.get("order_type"), fill.get("status"))
            for fill in result["fills"]
            if fill.get("status") == "dry_run"
        ]
        self.assertEqual(
            dry_run_orders,
            [
                ("SELL", "STOP_MARKET", "dry_run"),
                ("SELL", "TAKE_PROFIT_MARKET", "dry_run"),
                ("SELL", "TAKE_PROFIT_MARKET", "dry_run"),
                ("BUY", "MARKET", "dry_run"),
            ],
        )

    def test_trading_cycle_skips_stale_atomic_addon_when_recheck_state_reaches_target(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        portfolio = importlib.import_module("scripts.binance_trend_core.portfolio")
        risk = importlib.import_module("scripts.binance_trend_core.risk")
        types = importlib.import_module("scripts.binance_trend_core.types")

        signal = {
            "symbol": "BNBUSDT",
            "interval": "1h",
            "action": "hold_long",
            "position_size": 0.2,
            "entry_reference": 615.0,
            "close": 615.0,
            "trailing_stop": 602.7,
            "take_profit_1": 621.15,
            "take_profit_2": 627.3,
            "reason": "trend add-on",
        }

        class StaticSignalEngine:
            def generate_signal(self, candles, *, symbol, interval):
                return signal

        class SignalStrategy:
            def generate_intent(self, signal):
                return types.StrategyIntent(
                    symbol=signal["symbol"],
                    desired_exposure=float(signal["position_size"]),
                    action="hold_long",
                    reason="trend add-on",
                    metadata={"signal": signal},
                )

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials("key", "secret"),
            dry_run=True,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10_000, max_symbol_exposure=10_000, max_daily_loss=100, max_order_count=4),
        )
        broker.positions["BNBUSDT"] = portfolio.PortfolioPosition(symbol="BNBUSDT", size=0.1, entry_price=615.0)
        broker.open_algo_orders = [
            {"symbol": "BNBUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": True, "triggerPrice": "602.7", "algoId": "sl-1"},
            {"symbol": "BNBUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True, "origQty": "0.1", "triggerPrice": "621.15", "algoId": "tp-1"},
            {"symbol": "BNBUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True, "origQty": "0.1", "triggerPrice": "627.3", "algoId": "tp-2"},
        ]
        original_get_account_state = broker.get_account_state
        calls = {"count": 0}

        def get_account_state_with_external_addon_fill():
            calls["count"] += 1
            if calls["count"] >= 2:
                broker.positions["BNBUSDT"] = portfolio.PortfolioPosition(symbol="BNBUSDT", size=0.2, entry_price=615.0)
                broker.open_algo_orders = [
                    {"symbol": "BNBUSDT", "orderType": "STOP_MARKET", "side": "SELL", "closePosition": True, "triggerPrice": "602.7", "algoId": "sl-1"},
                    {"symbol": "BNBUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True, "origQty": "0.1", "triggerPrice": "621.15", "algoId": "tp-1"},
                    {"symbol": "BNBUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True, "origQty": "0.1", "triggerPrice": "627.3", "algoId": "tp-2"},
                    {"symbol": "BNBUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True, "origQty": "0.1", "triggerPrice": "621.15", "algoId": "tp-3"},
                    {"symbol": "BNBUSDT", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True, "origQty": "0.1", "triggerPrice": "627.3", "algoId": "tp-4"},
                ]
            return original_get_account_state()

        broker.get_account_state = get_account_state_with_external_addon_fill

        result = loop.run_trading_cycle(
            loop.TradingCycleConfig(symbols=["BNBUSDT"], interval="1h", candles_by_symbol={"BNBUSDT": [{}]}),
            broker=broker,
            signal_engine=StaticSignalEngine(),
            strategy=SignalStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PositionReconciliationExecutionEngine(),
        )

        self.assertFalse(any(fill.get("side") == "BUY" and fill.get("status") == "dry_run" for fill in result["fills"]))
        self.assertTrue(any(fill.get("status") == "skipped" and fill.get("reason") == "stale_atomic_entry_group_no_longer_needed" for fill in result["fills"]))

    def test_trading_cycle_prioritizes_existing_position_reduction_before_protective_repairs(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        portfolio = importlib.import_module("scripts.binance_trend_core.portfolio")
        risk = importlib.import_module("scripts.binance_trend_core.risk")
        types = importlib.import_module("scripts.binance_trend_core.types")

        def signal_for(symbol):
            base = {"BNBUSDT": 615.0, "ETHUSDT": 1800.0}[symbol]
            return {
                "symbol": symbol,
                "interval": "1h",
                "action": "hold_long" if symbol == "BNBUSDT" else "flat",
                "position_size": 0.11 if symbol == "BNBUSDT" else 0.0,
                "entry_reference": base,
                "close": base,
                "trailing_stop": base * 0.98,
                "take_profit_1": base * 1.01,
                "take_profit_2": base * 1.02,
                "reason": "trend" if symbol == "BNBUSDT" else "risk reduction",
            }

        class StaticSignalEngine:
            def generate_signal(self, candles, *, symbol, interval):
                return signal_for(symbol)

        class SignalStrategy:
            def generate_intent(self, signal):
                return types.StrategyIntent(
                    symbol=signal["symbol"],
                    desired_exposure=float(signal["position_size"]),
                    action=str(signal["action"]),
                    reason=str(signal["reason"]),
                    metadata={"signal": signal},
                )

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials("key", "secret"),
            dry_run=True,
            risk_limits=brokers.TestnetRiskLimits(max_order_notional=10_000, max_symbol_exposure=10_000, max_daily_loss=100, max_order_count=1),
        )
        broker.positions["BNBUSDT"] = portfolio.PortfolioPosition(symbol="BNBUSDT", size=0.11, entry_price=615.0)
        broker.positions["ETHUSDT"] = portfolio.PortfolioPosition(symbol="ETHUSDT", size=0.2, entry_price=1800.0)

        result = loop.run_trading_cycle(
            loop.TradingCycleConfig(
                symbols=["BNBUSDT", "ETHUSDT"],
                interval="1h",
                candles_by_symbol={"BNBUSDT": [{}], "ETHUSDT": [{}]},
            ),
            broker=broker,
            signal_engine=StaticSignalEngine(),
            strategy=SignalStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PositionReconciliationExecutionEngine(),
        )

        accepted = [(fill.get("symbol"), fill.get("side"), fill.get("order_type")) for fill in result["fills"] if fill.get("status") == "dry_run"]
        self.assertEqual(accepted, [("ETHUSDT", "SELL", "MARKET")])
        self.assertFalse(any(fill.get("symbol") == "BNBUSDT" and fill.get("status") == "dry_run" for fill in result["fills"]))

    def test_testnet_risk_limits_load_from_config_env_file_and_sanitize_summary(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        with tempfile.TemporaryDirectory() as tmpdir:
            kill_file = pathlib.Path(tmpdir) / "kill-switch"
            kill_file.write_text("enabled\n", encoding="utf-8")
            old_value = os.environ.get("BINANCE_TESTNET_KILL_SWITCH")
            os.environ["BINANCE_TESTNET_KILL_SWITCH"] = "0"
            try:
                limits = brokers.TestnetRiskLimits.from_config(
                    {
                        "max_order_notional": "25.5",
                        "max_symbol_exposure": 100,
                        "max_daily_loss": 10,
                        "max_order_count": 2,
                        "kill_switch": False,
                        "api_secret": "must-not-leak",
                    },
                    kill_switch_env="BINANCE_TESTNET_KILL_SWITCH",
                    kill_switch_file=str(kill_file),
                )
            finally:
                if old_value is None:
                    os.environ.pop("BINANCE_TESTNET_KILL_SWITCH", None)
                else:
                    os.environ["BINANCE_TESTNET_KILL_SWITCH"] = old_value

        self.assertTrue(limits.kill_switch)
        self.assertEqual(limits.max_order_notional, 25.5)
        self.assertEqual(limits.max_order_count, 2)
        summary = limits.sanitized_summary()
        self.assertEqual(summary["kill_switch"], True)
        self.assertNotIn("must-not-leak", json.dumps(summary))
        self.assertEqual(summary["source"], "testnet_risk_limits")

    def test_testnet_risk_limits_reject_invalid_non_finite_config(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        with self.assertRaises(ValueError):
            brokers.TestnetRiskLimits.from_config({"max_order_notional": "nan"})
        with self.assertRaises(ValueError):
            brokers.TestnetRiskLimits.from_config({"max_order_count": 0})

    def test_run_testnet_trading_cycle_refreshes_exchange_rules_and_writes_order_journal(self):
        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if "/fapi/v1/exchangeInfo" in url:
                    return {
                        "symbols": [
                            {
                                "symbol": "BTCUSDT",
                                "filters": [
                                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                                ],
                            }
                        ]
                    }
                if "/fapi/v2/account" in url:
                    return {"assets": [{"asset": "USDT", "walletBalance": "1000"}]}
                if "/fapi/v2/positionRisk" in url:
                    return [{"symbol": "BTCUSDT", "positionAmt": "0.0"}]
                if "/fapi/v1/openOrders" in url:
                    return []
                if "/fapi/v1/openAlgoOrders" in url:
                    return []
                if method == "POST" and ("/fapi/v1/order" in url or "/fapi/v1/algoOrder" in url):
                    params = dict(item.split("=", 1) for item in url.split("?", 1)[1].split("&"))
                    client_id = params.get("newClientOrderId") or params.get("clientAlgoId")
                    return {"orderId": 555, "algoId": 556, "clientOrderId": client_id, "clientAlgoId": client_id, "status": "NEW"}
                raise AssertionError(url)

        def fake_fetch_klines(symbol, interval, limit, base_url):
            return [
                {"open": 100.0 + idx, "high": 101.0 + idx, "low": 99.0 + idx, "close": 100.5 + idx}
                for idx in range(240)
            ]

        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = pathlib.Path(tmpdir) / "orders.jsonl"
            client = FakeHttpClient()
            with mock.patch.dict(os.environ, {"LALA_KEY": "k", "LALA_SECRET": "s"}), mock.patch.object(trend, "fetch_klines", fake_fetch_klines):
                cycle = trend.run_testnet_trading_cycle(
                    ["BTCUSDT"],
                    interval="1h",
                    limit=240,
                    save_runtime_record=False,
                    dry_run=False,
                    testnet_http_client=client,
                    order_journal_path=str(journal_path),
                )

            self.assertEqual(cycle["errors"], [])
            self.assertTrue(any("/fapi/v1/exchangeInfo" in call[1] for call in client.calls))
            self.assertTrue(any(call[0] == "POST" and ("/fapi/v1/order" in call[1] or "/fapi/v1/algoOrder" in call[1]) for call in client.calls))
            rows = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 4)
            self.assertEqual([row["status"] for row in rows], ["submitted", "submitted", "submitted", "submitted"])
            self.assertEqual(rows[0]["order_type"], "MARKET")
            self.assertEqual([row["order_type"] for row in rows[1:]], ["STOP_MARKET", "TAKE_PROFIT_MARKET", "TAKE_PROFIT_MARKET"])
            self.assertEqual(rows[1]["request"]["path"], "/fapi/v1/algoOrder")
            self.assertEqual(rows[2]["request"]["path"], "/fapi/v1/algoOrder")
            self.assertEqual(rows[3]["request"]["path"], "/fapi/v1/algoOrder")
            self.assertEqual(rows[1]["request"]["params"]["closePosition"], "true")
            self.assertEqual(rows[2]["request"]["params"]["reduceOnly"], "true")
            self.assertEqual(rows[3]["request"]["params"]["reduceOnly"], "true")
            self.assertIn("triggerPrice", rows[1]["request"]["params"])
            self.assertIn("triggerPrice", rows[2]["request"]["params"])
            self.assertIn("triggerPrice", rows[3]["request"]["params"])
            self.assertIn("client_order_id", rows[0])
            self.assertIn("exchange_rule_adjustments", rows[0])
            self.assertEqual(rows[1]["request"]["params"]["closePosition"], "true")
            self.assertNotIn("signature", json.dumps(rows))

    def test_run_testnet_trading_cycle_blocks_signed_short_by_default(self):
        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if "/fapi/v1/exchangeInfo" in url:
                    return {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"}, {"filterType": "PRICE_FILTER", "tickSize": "0.10"}, {"filterType": "MIN_NOTIONAL", "notional": "5"}]}]}
                if "/fapi/v2/account" in url:
                    return {"assets": [{"asset": "USDT", "walletBalance": "1000", "availableBalance": "1000"}]}
                if "/fapi/v2/positionRisk" in url:
                    return [{"symbol": "BTCUSDT", "positionAmt": "0.0"}]
                if "/fapi/v1/openOrders" in url or "/fapi/v1/openAlgoOrders" in url:
                    return []
                if method == "POST":
                    raise AssertionError("signed short must be blocked before POST")
                raise AssertionError(url)

        def fake_fetch_klines(symbol, interval, limit, base_url):
            return [
                {"open": 300.0 - idx, "high": 301.0 - idx, "low": 299.0 - idx, "close": 299.5 - idx}
                for idx in range(240)
            ]

        client = FakeHttpClient()
        with mock.patch.dict(os.environ, {"LALA_KEY": "k", "LALA_SECRET": "s"}), mock.patch.object(trend, "fetch_klines", fake_fetch_klines):
            cycle = trend.run_testnet_trading_cycle(
                ["BTCUSDT"],
                interval="1h",
                limit=240,
                save_runtime_record=False,
                dry_run=False,
                testnet_http_client=client,
            )

        self.assertEqual(cycle["errors"], [])
        self.assertFalse(any(call[0] == "POST" for call in client.calls))
        self.assertEqual(cycle["signals"][0]["action"], "flat")
        self.assertTrue(cycle["signals"][0]["short_signal_blocked"])
        self.assertEqual(cycle["desired_orders"], [])

    def test_run_testnet_trading_cycle_uses_remote_position_to_avoid_repeated_full_target_order(self):
        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if "/fapi/v1/exchangeInfo" in url:
                    return {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"}]}]}
                if "/fapi/v2/account" in url:
                    return {"assets": [{"asset": "USDT", "walletBalance": "1000"}]}
                if "/fapi/v2/positionRisk" in url:
                    return [{"symbol": "BTCUSDT", "positionAmt": "0.5", "entryPrice": "100.0"}]
                if "/fapi/v1/openOrders" in url:
                    return []
                if "/fapi/v1/openAlgoOrders" in url:
                    return []
                if method == "POST" and ("/fapi/v1/order" in url or "/fapi/v1/algoOrder" in url):
                    params = dict(item.split("=", 1) for item in url.split("?", 1)[1].split("&"))
                    if params.get("type") == "MARKET":
                        raise AssertionError("should not submit a repeated full target order when remote target is already reached")
                    client_id = params.get("newClientOrderId") or params.get("clientAlgoId")
                    return {"orderId": 123, "algoId": 124, "clientOrderId": client_id, "clientAlgoId": client_id, "status": "NEW"}
                raise AssertionError(url)

        def fake_fetch_klines(symbol, interval, limit, base_url):
            return [
                {"open": 100.0 + idx, "high": 101.0 + idx, "low": 99.0 + idx, "close": 100.5 + idx}
                for idx in range(240)
            ]

        client = FakeHttpClient()
        with mock.patch.dict(os.environ, {"LALA_KEY": "k", "LALA_SECRET": "s"}), mock.patch.object(trend, "fetch_klines", fake_fetch_klines):
            cycle = trend.run_testnet_trading_cycle(
                ["BTCUSDT"],
                interval="1h",
                limit=240,
                save_runtime_record=False,
                dry_run=False,
                testnet_http_client=client,
                sync_account_state=True,
                account_risk_fraction=0.003,
            )

        self.assertEqual(cycle["errors"], [])
        order_posts = [call for call in client.calls if call[0] == "POST" and ("/fapi/v1/order" in call[1] or "/fapi/v1/algoOrder" in call[1])]
        self.assertFalse(any("type=MARKET" in call[1] for call in order_posts))
        self.assertEqual(
            [item["order_type"] for item in cycle["runtime_record"]["execution_events"]["desired_orders"]],
            ["STOP_MARKET", "TAKE_PROFIT_MARKET", "TAKE_PROFIT_MARKET"],
        )
        self.assertEqual(cycle["runtime_record"]["execution_events"]["simulated_fills_count"], 3)

    def test_run_testnet_trading_cycle_reports_unprotected_position_when_post_sync_lacks_tp_sl(self):
        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if "/fapi/v1/exchangeInfo" in url:
                    return {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"}]}]}
                if "/fapi/v2/account" in url:
                    return {"assets": [{"asset": "USDT", "availableBalance": "1000"}]}
                if "/fapi/v2/positionRisk" in url:
                    return [{"symbol": "BTCUSDT", "positionAmt": "0.5", "entryPrice": "100.0"}]
                if "/fapi/v1/openOrders" in url:
                    return []
                if "/fapi/v1/openAlgoOrders" in url:
                    return []
                if method == "POST" and "/fapi/v1/algoOrder" in url:
                    params = dict(item.split("=", 1) for item in url.split("?", 1)[1].split("&"))
                    client_id = params.get("clientAlgoId")
                    return {"algoId": 124, "clientAlgoId": client_id, "status": "NEW"}
                raise AssertionError(url)

        def fake_fetch_klines(symbol, interval, limit, base_url):
            return [
                {"open": 100.0 + idx, "high": 101.0 + idx, "low": 99.0 + idx, "close": 100.5 + idx}
                for idx in range(240)
            ]

        client = FakeHttpClient()
        with mock.patch.dict(os.environ, {"LALA_KEY": "k", "LALA_SECRET": "s"}), mock.patch.object(trend, "fetch_klines", fake_fetch_klines):
            cycle = trend.run_testnet_trading_cycle(
                ["BTCUSDT"],
                interval="1h",
                limit=240,
                save_runtime_record=False,
                dry_run=False,
                testnet_http_client=client,
                sync_account_state=True,
                account_risk_fraction=0.003,
            )

        protection = cycle["testnet_account_sync"]["protection_verification"]
        self.assertFalse(protection["all_positions_protected"])
        self.assertEqual(protection["unprotected_symbols"], ["BTCUSDT"])
        self.assertIn("missing_stop_loss", protection["symbols"]["BTCUSDT"]["issues"])
        self.assertIn("missing_take_profit", protection["symbols"]["BTCUSDT"]["issues"])
        self.assertEqual(cycle["runtime_record"]["execution_events"]["testnet_account_sync"]["unprotected_symbols"], ["BTCUSDT"])

    def test_run_testnet_trading_cycle_can_attach_signed_account_sync_report(self):
        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if "/fapi/v1/exchangeInfo" in url:
                    return {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"}]}]}
                if "/fapi/v2/account" in url:
                    return {"assets": [{"asset": "USDT", "walletBalance": "1000"}]}
                if "/fapi/v2/positionRisk" in url:
                    return [{"symbol": "BTCUSDT", "positionAmt": "0.0"}]
                if "/fapi/v1/openOrders" in url:
                    return [{"symbol": "BTCUSDT", "clientOrderId": "hermes-1"}]
                if "/fapi/v1/openAlgoOrders" in url:
                    return []
                if method == "POST" and ("/fapi/v1/order" in url or "/fapi/v1/algoOrder" in url):
                    params = dict(item.split("=", 1) for item in url.split("?", 1)[1].split("&"))
                    client_id = params.get("newClientOrderId") or params.get("clientAlgoId") or "hermes-1"
                    return {"orderId": 777, "algoId": 778, "clientOrderId": client_id, "clientAlgoId": client_id, "status": "NEW"}
                raise AssertionError(url)

        def fake_fetch_klines(symbol, interval, limit, base_url):
            return [
                {"open": 100.0 + idx, "high": 101.0 + idx, "low": 99.0 + idx, "close": 100.5 + idx}
                for idx in range(240)
            ]

        client = FakeHttpClient()
        with mock.patch.dict(os.environ, {"LALA_KEY": "k", "LALA_SECRET": "s"}), mock.patch.object(trend, "fetch_klines", fake_fetch_klines):
            cycle = trend.run_testnet_trading_cycle(
                ["BTCUSDT"],
                interval="1h",
                limit=240,
                save_runtime_record=False,
                dry_run=False,
                testnet_http_client=client,
                sync_account_state=True,
            )

        self.assertEqual(cycle["errors"], [])
        sync = cycle["testnet_account_sync"]
        self.assertEqual(sync["environment"], "testnet")
        self.assertEqual(sync["before"]["account"]["assets"][0]["asset"], "USDT")
        self.assertEqual(sync["after"]["open_orders"][0]["clientOrderId"], "hermes-1")
        self.assertIn("reconciliation", sync)
        self.assertEqual(cycle["runtime_record"]["execution_events"]["testnet_account_sync"]["after_open_orders_count"], 1)
        self.assertNotIn("signature=", json.dumps(sync))

    def test_testnet_broker_tracks_filled_order_lifecycle_with_trade_pnl_and_slippage(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")

        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if "/fapi/v1/order" in url:
                    self.assert_not_used = None
                    return {
                        "symbol": "BTCUSDT",
                        "orderId": 42,
                        "clientOrderId": "cid-filled",
                        "side": "BUY",
                        "status": "FILLED",
                        "executedQty": "0.020",
                        "avgPrice": "101.00",
                    }
                if "/fapi/v1/userTrades" in url:
                    return [
                        {"symbol": "BTCUSDT", "orderId": 42, "side": "BUY", "price": "101.00", "qty": "0.010", "realizedPnl": "1.50", "commission": "0.0404"},
                        {"symbol": "BTCUSDT", "orderId": 42, "side": "BUY", "price": "101.00", "qty": "0.010", "realizedPnl": "1.50", "commission": "0.0404"},
                    ]
                raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = pathlib.Path(tmpdir) / "orders.jsonl"
            client = FakeHttpClient()
            broker = brokers.BinanceTestnetBroker(
                credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
                dry_run=False,
                http_client=client,
                order_journal_path=str(journal_path),
            )

            lifecycle = broker.track_order_lifecycle("BTCUSDT", "cid-filled", reference_price=100.0)

            self.assertEqual(lifecycle["environment"], "testnet")
            self.assertEqual(lifecycle["client_order_id"], "cid-filled")
            self.assertEqual(lifecycle["order_id"], 42)
            self.assertEqual(lifecycle["current_status"], "FILLED")
            self.assertEqual(lifecycle["lifecycle_state"], "filled")
            self.assertEqual(lifecycle["fills_summary"]["fill_quantity"], 0.02)
            self.assertEqual(lifecycle["fills_summary"]["average_fill_price"], 101.0)
            self.assertEqual(lifecycle["fills_summary"]["realized_pnl"], 3.0)
            self.assertEqual(lifecycle["fills_summary"]["fees"], 0.0808)
            self.assertEqual(lifecycle["fills_summary"]["net_pnl"], 2.9192)
            self.assertEqual(lifecycle["fills_summary"]["slippage_abs"], 1.0)
            self.assertEqual(lifecycle["fills_summary"]["slippage_bps"], 100.0)
            self.assertTrue(any("/fapi/v1/order" in call[1] and "origClientOrderId=cid-filled" in call[1] for call in client.calls))
            self.assertTrue(any("/fapi/v1/userTrades" in call[1] and "orderId=42" in call[1] for call in client.calls))
            rows = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["event_type"], "order_lifecycle")
            self.assertNotIn("signature", json.dumps(rows[0]))

    def test_testnet_order_lifecycle_slippage_is_side_aware_for_sell_orders(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")

        class FakeHttpClient:
            def request(self, method, url, headers=None, body=None, timeout=20):
                if "/fapi/v1/order" in url:
                    return {
                        "symbol": "BTCUSDT",
                        "orderId": 43,
                        "clientOrderId": "cid-sell",
                        "side": "SELL",
                        "status": "FILLED",
                        "avgPrice": "99.00",
                    }
                if "/fapi/v1/userTrades" in url:
                    return [{"symbol": "BTCUSDT", "orderId": 43, "side": "SELL", "price": "99.00", "qty": "0.010", "realizedPnl": "0.50", "commission": "0.01"}]
                raise AssertionError(url)

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=False,
            http_client=FakeHttpClient(),
        )

        lifecycle = broker.track_order_lifecycle("BTCUSDT", "cid-sell", reference_price=100.0)

        self.assertEqual(lifecycle["fills_summary"]["average_fill_price"], 99.0)
        self.assertEqual(lifecycle["fills_summary"]["slippage_abs"], 1.0)
        self.assertEqual(lifecycle["fills_summary"]["slippage_bps"], 100.0)

    def test_run_testnet_trading_cycle_tracks_signed_order_lifecycle_when_enabled(self):
        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if "/fapi/v1/exchangeInfo" in url:
                    return {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"}]}]}
                if "/fapi/v2/account" in url:
                    return {"assets": [{"asset": "USDT", "walletBalance": "1000"}]}
                if "/fapi/v2/positionRisk" in url:
                    return [{"symbol": "BTCUSDT", "positionAmt": "0.0"}]
                if "/fapi/v1/openOrders" in url:
                    return []
                if "/fapi/v1/openAlgoOrders" in url:
                    return []
                if method == "POST" and ("/fapi/v1/order" in url or "/fapi/v1/algoOrder" in url):
                    params = dict(item.split("=", 1) for item in url.split("?", 1)[1].split("&"))
                    client_id = params.get("newClientOrderId") or params.get("clientAlgoId")
                    return {"orderId": 42, "algoId": 43, "clientOrderId": client_id, "clientAlgoId": client_id, "status": "NEW"}
                if method == "GET" and "/fapi/v1/order" in url:
                    return {"symbol": "BTCUSDT", "orderId": 42, "clientOrderId": "hermes-1", "side": "BUY", "status": "FILLED", "avgPrice": "101.00"}
                if "/fapi/v1/userTrades" in url:
                    return [{"symbol": "BTCUSDT", "orderId": 42, "price": "101.00", "qty": "1.0", "realizedPnl": "2.0", "commission": "0.1"}]
                raise AssertionError(url)

        def fake_fetch_klines(symbol, interval, limit, base_url):
            return [
                {"open": 100.0 + idx, "high": 101.0 + idx, "low": 99.0 + idx, "close": 100.5 + idx}
                for idx in range(240)
            ]

        client = FakeHttpClient()
        with mock.patch.dict(os.environ, {"LALA_KEY": "k", "LALA_SECRET": "s"}), mock.patch.object(trend, "fetch_klines", fake_fetch_klines):
            cycle = trend.run_testnet_trading_cycle(
                ["BTCUSDT"],
                interval="1h",
                limit=240,
                save_runtime_record=False,
                dry_run=False,
                testnet_http_client=client,
                track_order_lifecycle=True,
            )

        self.assertEqual(cycle["errors"], [])
        self.assertEqual(len(cycle["testnet_order_lifecycle"]), 1)
        lifecycle = cycle["testnet_order_lifecycle"][0]
        self.assertEqual(lifecycle["current_status"], "FILLED")
        self.assertEqual(lifecycle["fills_summary"]["net_pnl"], 1.9)
        self.assertEqual(cycle["runtime_record"]["execution_events"]["testnet_order_lifecycle"]["tracked_order_count"], 1)
        self.assertTrue(any("/fapi/v1/userTrades" in call[1] for call in client.calls))

    def test_run_testnet_trading_cycle_does_not_promote_submitted_unknown_to_lifecycle(self):
        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def request(self, method, url, headers=None, body=None, timeout=20):
                self.calls.append((method, url))
                if "/fapi/v1/exchangeInfo" in url:
                    return {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"}]}]}
                if "/fapi/v2/account" in url:
                    return {"assets": [{"asset": "USDT", "walletBalance": "1000"}]}
                if "/fapi/v2/positionRisk" in url:
                    return [{"symbol": "BTCUSDT", "positionAmt": "0.0"}]
                if "/fapi/v1/openOrders" in url or "/fapi/v1/openAlgoOrders" in url:
                    return []
                if method == "POST" and "/fapi/v1/order" in url:
                    raise RuntimeError("submission outcome unknown")
                if method == "GET" and "/fapi/v1/order" in url:
                    raise RuntimeError("confirmation failed")
                if "/fapi/v1/userTrades" in url:
                    raise AssertionError("submitted_unknown orders must not fetch fills")
                raise AssertionError(url)

        def fake_fetch_klines(symbol, interval, limit, base_url):
            return [
                {"open": 100.0 + idx, "high": 101.0 + idx, "low": 99.0 + idx, "close": 100.5 + idx}
                for idx in range(240)
            ]

        client = FakeHttpClient()
        with mock.patch.dict(os.environ, {"LALA_KEY": "k", "LALA_SECRET": "s"}), mock.patch.object(trend, "fetch_klines", fake_fetch_klines):
            cycle = trend.run_testnet_trading_cycle(
                ["BTCUSDT"],
                interval="1h",
                limit=240,
                save_runtime_record=False,
                dry_run=False,
                testnet_http_client=client,
                track_order_lifecycle=True,
            )

        self.assertEqual(cycle["errors"], [])
        self.assertGreaterEqual(len(cycle["fills"]), 1)
        self.assertEqual({fill["status"] for fill in cycle["fills"]}, {"submitted_unknown"})
        self.assertEqual(cycle["testnet_order_lifecycle"], [])
        self.assertEqual(cycle["runtime_record"]["execution_events"]["testnet_order_lifecycle"]["tracked_order_count"], 0)
        self.assertEqual(cycle["runtime_record"]["execution_events"]["testnet_order_lifecycle"]["filled_order_count"], 0)
        self.assertFalse(any("/fapi/v1/userTrades" in call[1] for call in client.calls))

    def test_cli_loads_testnet_risk_config_file_and_emits_sanitized_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = pathlib.Path(tmpdir) / "risk.json"
            config_path.write_text(
                json.dumps(
                    {
                        "max_order_notional": 12.5,
                        "max_symbol_exposure": 33,
                        "max_symbol_exposure_fraction": 0.2,
                        "max_daily_loss": 5,
                        "max_order_count": 2,
                        "kill_switch": True,
                        "api_secret": "super-secret",
                    }
                ),
                encoding="utf-8",
            )
            fake_cycle = {
                "errors": [],
                "runtime_record": {"schema_version": "1"},
                "environment": "testnet",
            }
            with mock.patch.object(trend, "run_testnet_trading_cycle", return_value=fake_cycle) as run_cycle:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    exit_code = trend.main([
                        "--run-testnet-cycle",
                        "--symbol",
                        "BTCUSDT",
                        "--interval",
                        "1h",
                        "--limit",
                        "240",
                        "--runtime-record-file",
                        str(pathlib.Path(tmpdir) / "runtime.jsonl"),
                        "--testnet-dry-run",
                        "--testnet-risk-config-file",
                        str(config_path),
                    ])

        self.assertEqual(exit_code, 0)
        called_kwargs = run_cycle.call_args.kwargs
        self.assertEqual(called_kwargs["max_order_notional"], 12.5)
        self.assertEqual(called_kwargs["max_symbol_exposure_fraction"], 0.2)
        self.assertTrue(called_kwargs["kill_switch"])
        rendered = stdout.getvalue()
        self.assertIn('"testnet_risk_limits"', rendered)
        self.assertNotIn("super-secret", rendered)
        self.assertIn('"kill_switch": true', rendered)

    def test_testnet_broker_kill_switch_blocks_all_execution(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        broker = brokers.BinanceTestnetBroker(
            credentials=brokers.BinanceTestnetCredentials(api_key="k", api_secret="s"),
            dry_run=True,
            risk_limits=brokers.TestnetRiskLimits(kill_switch=True),
        )

        event = broker.submit_order(execution.OrderInstruction(symbol="BTCUSDT", side="BUY", quantity=0.1))

        self.assertEqual(event["status"], "rejected")
        self.assertEqual(event["reason"], "kill_switch_enabled")
        self.assertFalse(event["real_order_submitted"])

    def test_shared_trading_cycle_records_portfolio_state_and_runtime_evidence(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        signals = importlib.import_module("scripts.binance_trend_core.signals")
        strategy = importlib.import_module("scripts.binance_trend_core.strategy")
        risk = importlib.import_module("scripts.binance_trend_core.risk")

        candles = [{"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0} for _ in range(240)]
        broker = brokers.PaperBroker(initial_equity=10_000.0)
        cycle = loop.run_trading_cycle(
            loop.TradingCycleConfig(symbols=["BTCUSDT"], interval="1h", candles_by_symbol={"BTCUSDT": candles}),
            broker=broker,
            signal_engine=signals.FunctionSignalEngine(
                decide_fn=lambda candles, symbol, interval, **kwargs: {
                    "symbol": symbol,
                    "interval": interval,
                    "action": "hold_long",
                    "position_size": 0.75,
                    "entry_reference": 101.0,
                    "reason": "unit trend",
                }
            ),
            strategy=strategy.TrendParticipationStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PaperIntentExecutionEngine(),
        )

        self.assertEqual(cycle["environment"], "paper")
        self.assertEqual(cycle["mode"], "paper")
        self.assertFalse(cycle["real_orders_submitted"])
        self.assertEqual(cycle["portfolio_state"]["positions"]["BTCUSDT"]["size"], 0.75)
        self.assertEqual(cycle["runtime_record"]["environment"], "paper")
        self.assertEqual(cycle["runtime_record"]["execution_events"]["simulated_fills_count"], 1)
        self.assertEqual(cycle["runtime_record"]["execution_events"]["real_orders_submitted"], False)

    def test_shared_trading_cycle_can_use_fake_testnet_adapter_without_changing_loop(self):
        execution = importlib.import_module("scripts.binance_trend_core.execution")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        signals = importlib.import_module("scripts.binance_trend_core.signals")
        strategy = importlib.import_module("scripts.binance_trend_core.strategy")
        risk = importlib.import_module("scripts.binance_trend_core.risk")

        class FakeTestnetBroker:
            environment = "testnet"
            def __init__(self):
                self.instructions = []
            def submit_order(self, instruction):
                self.instructions.append(instruction)
                return {"environment": "testnet", "symbol": instruction.symbol, "simulated": True, "real_order_submitted": False}
            def cancel_order(self, order_id):
                return {"environment": "testnet", "order_id": order_id, "cancelled": True}
            def get_account_state(self):
                return {"environment": "testnet", "positions": {}, "fills": []}

        broker = FakeTestnetBroker()
        cycle = loop.run_trading_cycle(
            loop.TradingCycleConfig(symbols=["BTCUSDT"], interval="1h", candles_by_symbol={"BTCUSDT": [{"close": 100.0}] * 240}),
            broker=broker,
            signal_engine=signals.FunctionSignalEngine(decide_fn=lambda candles, symbol, interval, **kwargs: {"symbol": symbol, "interval": interval, "action": "hold_long", "position_size": 0.25, "reason": "shared loop"}),
            strategy=strategy.TrendParticipationStrategy(),
            risk_manager=risk.FunctionRiskManager(),
            execution_engine=execution.PaperIntentExecutionEngine(),
        )

        self.assertEqual(cycle["environment"], "testnet")
        self.assertEqual(len(broker.instructions), 1)
        self.assertFalse(cycle["real_orders_submitted"])

    def test_shared_trading_cycle_rejects_short_intervals_before_broker_execution(self):
        brokers = importlib.import_module("scripts.binance_trend_core.brokers")
        loop = importlib.import_module("scripts.binance_trend_core.loop")
        signals = importlib.import_module("scripts.binance_trend_core.signals")
        strategy = importlib.import_module("scripts.binance_trend_core.strategy")
        risk = importlib.import_module("scripts.binance_trend_core.risk")
        execution = importlib.import_module("scripts.binance_trend_core.execution")

        broker = brokers.PaperBroker()
        with self.assertRaises(ValueError):
            loop.run_trading_cycle(
                loop.TradingCycleConfig(symbols=["BTCUSDT"], interval="30m", candles_by_symbol={"BTCUSDT": [{"close": 100.0}] * 240}),
                broker=broker,
                signal_engine=signals.FunctionSignalEngine(decide_fn=trend.decide),
                strategy=strategy.TrendParticipationStrategy(),
                risk_manager=risk.FunctionRiskManager(),
                execution_engine=execution.PaperIntentExecutionEngine(),
            )
        self.assertEqual(broker.get_account_state()["fills"], [])

    def test_cli_can_run_no_write_paper_cycle_with_runtime_record(self):
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
                runtime_path = pathlib.Path(tmpdir) / "paper-cycle.jsonl"
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    rc = trend.main([
                        "--run-paper-cycle",
                        "--symbols", "BTCUSDT",
                        "--interval", "1h",
                        "--limit", "240",
                        "--runtime-record-file", str(runtime_path),
                        "--no-save-runtime-record",
                    ])
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        cycle = payload["paper_cycle"]
        self.assertEqual(cycle["environment"], "paper")
        self.assertFalse(cycle["real_orders_submitted"])
        self.assertFalse(cycle["runtime_record_saved"])
        self.assertFalse(runtime_path.exists())
        self.assertGreaterEqual(cycle["runtime_record"]["execution_events"]["simulated_fills_count"], 1)

    def test_cli_can_run_testnet_dry_run_cycle_with_shared_loop_and_no_secret_output(self):
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
        original_env = {name: os.environ.get(name) for name in ("LALA_KEY", "LALA_SECRET")}
        setattr(trend, "fetch_klines", lambda symbol, interval, limit, base_url=trend.BINANCE_FAPI_BASE: make_candles(100, 1.0))
        os.environ["LALA_KEY"] = "test-key-value"
        os.environ["LALA_SECRET"] = "test-secret-value"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                runtime_path = pathlib.Path(tmpdir) / "testnet-cycle.jsonl"
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    rc = trend.main([
                        "--run-testnet-cycle",
                        "--symbols", "BTCUSDT",
                        "--interval", "1h",
                        "--limit", "240",
                        "--runtime-record-file", str(runtime_path),
                        "--no-save-runtime-record",
                        "--testnet-dry-run",
                        "--testnet-max-order-notional", "1000000",
                    ])
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)
            for name, value in original_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertNotIn("test-key-value", output)
        self.assertNotIn("test-secret-value", output)
        payload = json.loads(output)
        self.assertTrue(payload["ok"])
        cycle = payload["testnet_cycle"]
        self.assertEqual(cycle["environment"], "testnet")
        self.assertEqual(cycle["runtime_record"]["environment"], "testnet")
        self.assertFalse(cycle["real_orders_submitted"])
        self.assertFalse(cycle["runtime_record_saved"])
        self.assertFalse(runtime_path.exists())
        self.assertTrue(cycle["fills"][0]["testnet_dry_run"])
        self.assertIn("testnet.binancefuture.com", cycle["portfolio_state"]["base_url"])

    def test_cli_testnet_cycle_rejects_short_interval_before_broker_execution(self):
        original_env = {name: os.environ.get(name) for name in ("LALA_KEY", "LALA_SECRET")}
        os.environ["LALA_KEY"] = "test-key-value"
        os.environ["LALA_SECRET"] = "test-secret-value"
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = trend.main([
                    "--run-testnet-cycle",
                    "--symbols", "BTCUSDT",
                    "--interval", "30m",
                    "--testnet-dry-run",
                ])
        finally:
            for name, value in original_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        self.assertEqual(rc, 1)
        payload = json.loads(stdout.getvalue())
        self.assertIn("short interval", payload["error"])
        self.assertNotIn("test-key-value", stdout.getvalue())
        self.assertNotIn("test-secret-value", stdout.getvalue())

    def test_runtime_evidence_loader_rejects_records_without_schema_environment_or_timestamps(self):
        evolution = importlib.import_module("scripts.binance_trend_core.evolution")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-runtime.jsonl"
            path.write_text(json.dumps({"environment": "paper", "generated_at_utc": "u", "generated_at_beijing": "b"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema_version"):
                evolution.load_runtime_records(path)

            path.write_text(json.dumps({"schema_version": "runtime.v1", "environment": "paper", "generated_at_utc": "u"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "generated_at_beijing"):
                evolution.load_runtime_records(path)

    def test_runtime_evidence_loader_rejects_short_intervals(self):
        evolution = importlib.import_module("scripts.binance_trend_core.evolution")
        record = self._runtime_replay_records([0.01])[0]
        record["intervals"] = ["5m"]
        record["market_inputs"] = {"symbols": ["BTCUSDT"], "primary_interval": "5m"}
        with self.assertRaisesRegex(ValueError, "short interval"):
            evolution.build_runtime_replay_dataset([record])

    def test_runtime_evidence_loader_rejects_short_market_input_intervals_even_with_valid_top_level_interval(self):
        evolution = importlib.import_module("scripts.binance_trend_core.evolution")
        record = self._runtime_replay_records([0.01])[0]
        record["intervals"] = ["1h"]
        record["market_inputs"] = {"symbols": ["BTCUSDT"], "primary_interval": "5m", "intervals": ["5m"]}
        with self.assertRaisesRegex(ValueError, "short interval"):
            evolution.build_runtime_replay_dataset([record])

    def test_runtime_evidence_loader_rejects_short_signal_intervals(self):
        evolution = importlib.import_module("scripts.binance_trend_core.evolution")
        record = self._runtime_replay_records([0.01])[0]
        record["signals"][0]["interval"] = "5m"
        with self.assertRaisesRegex(ValueError, "short interval"):
            evolution.build_runtime_replay_dataset([record])

    def test_runtime_replay_uses_identical_captured_inputs_for_all_variants(self):
        evolution = importlib.import_module("scripts.binance_trend_core.evolution")
        records = self._runtime_replay_records([-0.02, 0.03])

        dataset = evolution.build_runtime_replay_dataset(records)
        report = evolution.compare_runtime_strategy_variants(records)

        fingerprints = {item["captured_input_fingerprint"] for item in report["variants"]}
        self.assertEqual(fingerprints, {dataset["captured_input_fingerprint"]})
        self.assertEqual(report["selection_policy"]["auto_promote_defaults"], False)
        self.assertIn("BTCUSDT", dataset["symbols"])

    def test_runtime_evolution_drawdown_guardrail_blocks_higher_return_candidate(self):
        evolution = importlib.import_module("scripts.binance_trend_core.evolution")
        records = self._runtime_replay_records([-0.20, 0.50])

        report = evolution.compare_runtime_strategy_variants(records, max_drawdown_worsening_limit=0.02)
        trend_hold = next(item for item in report["variants"] if item["variant"] == "trend_hold_bias")
        baseline = next(item for item in report["variants"] if item["variant"] == "baseline")

        self.assertGreater(trend_hold["metrics"]["return_proxy"], baseline["metrics"]["return_proxy"])
        self.assertFalse(trend_hold["eligible"])
        self.assertIn("drawdown_guardrail", trend_hold["guardrail_flags"])
        self.assertEqual(report["selected_variant"], "baseline")

    def test_runtime_evolution_report_includes_time_labels_and_no_default_promotion(self):
        evolution = importlib.import_module("scripts.binance_trend_core.evolution")
        report = evolution.compare_runtime_strategy_variants(self._runtime_replay_records([0.01, 0.02]))

        self.assertEqual(report["mode"], "paper")
        self.assertIn("generated_at_utc", report)
        self.assertIn("generated_at_beijing", report)
        self.assertIn("北京时间（UTC+8）", report["summary_zh"])
        self.assertFalse(report["selection_policy"]["auto_promote_defaults"])
        self.assertFalse(report["defaults_changed"])

    def test_cli_can_replay_runtime_evidence_jsonl_without_fetching_new_samples(self):
        records = self._runtime_replay_records([0.01, 0.02])
        original_fetch_klines = getattr(trend, "fetch_klines")
        def fail_fetch(*args, **kwargs):
            raise AssertionError("runtime replay must not fetch live samples")
        setattr(trend, "fetch_klines", fail_fetch)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                path = pathlib.Path(tmpdir) / "runtime.jsonl"
                path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    rc = trend.main(["--replay-runtime-evidence", "--runtime-record-file", str(path)])
        finally:
            setattr(trend, "fetch_klines", original_fetch_klines)

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["runtime_evolution"]["records_loaded"], len(records))
        self.assertFalse(payload["runtime_evolution"]["selection_policy"]["auto_promote_defaults"])

    def _runtime_replay_records(self, return_proxies):
        records = []
        for index, return_proxy in enumerate(return_proxies):
            records.append(
                {
                    "schema_version": "runtime.v1",
                    "environment": "paper",
                    "run_id": f"fixture-{index}",
                    "generated_at_utc": f"2026-06-15T0{index}:00:00+00:00",
                    "generated_at_beijing": f"2026-06-15T0{index + 8}:00:00+08:00",
                    "symbol_universe": ["BTCUSDT"],
                    "intervals": ["1h"],
                    "market_inputs": {"symbols": ["BTCUSDT"], "primary_interval": "1h"},
                    "signals": [
                        {
                            "symbol": "BTCUSDT",
                            "interval": "1h",
                            "action": "hold_long",
                            "position_size": 1.0,
                            "rank_score": 10.0,
                            "trend_strength": 5.0,
                            "return_proxy": return_proxy,
                        }
                    ],
                    "execution_events": {"real_orders_submitted": False},
                    "outcomes": {"errors_count": 0, "return_proxy_by_symbol": {"BTCUSDT": return_proxy}},
                }
            )
        return records

    def test_rejects_short_intervals_below_one_hour(self):
        for interval in ["1m", "5m", "10m", "15m", "30m"]:
            with self.subTest(interval=interval):
                with self.assertRaises(ValueError):
                    trend.validate_interval(interval)

    def test_accepts_one_hour_or_higher_intervals(self):
        for interval in ["1h", "2h", "4h", "1d", "1w"]:
            with self.subTest(interval=interval):
                self.assertEqual(trend.validate_interval(interval), interval)

    def test_fetch_klines_drops_unclosed_latest_candle(self):
        raw_rows = []
        for idx in range(200):
            raw_rows.append([idx, "100", "102", "99", str(100 + idx), "1", idx + 1])
        raw_rows.append([200, "9999", "9999", "9999", "9999", "1", 9999999999999])

        with mock.patch.object(trend, "_get_json", return_value=raw_rows):
            candles = trend.fetch_klines("BTCUSDT", "1h", limit=200)

        self.assertEqual(len(candles), 200)
        self.assertEqual(candles[-1]["close"], 299.0)

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
        self.assertTrue(decision["add_allowed"])
        self.assertGreater(decision["position_size"], 0)
        self.assertGreater(decision["take_profit_1"], decision["entry_reference"])
        self.assertGreater(decision["take_profit_2"], decision["take_profit_1"])
        self.assertLess(decision["trailing_stop"], decision["entry_reference"])

    def test_generates_hold_short_decision_in_strong_downtrend(self):
        candles = []
        price = 300.0
        for _ in range(240):
            open_price = price
            close_price = price - 1.0
            candles.append({"open": open_price, "high": open_price + 0.5, "low": close_price - 0.7, "close": close_price})
            price = close_price

        decision = trend.decide(candles, symbol="ETHUSDT", interval="1h")

        self.assertEqual(decision["action"], "hold_short")
        self.assertEqual(decision["exposure_direction"], "short")
        self.assertGreater(decision["position_size"], 0)
        self.assertTrue(decision["add_allowed"])
        self.assertTrue(decision["hold_existing_allowed"])
        self.assertGreater(decision["trailing_stop"], decision["entry_reference"])
        self.assertLess(decision["take_profit_1"], decision["entry_reference"])
        self.assertLess(decision["take_profit_2"], decision["take_profit_1"])

    def test_trend_participation_strategy_maps_hold_short_to_negative_exposure(self):
        strategy_module = importlib.import_module("scripts.binance_trend_core.strategy")

        intent = strategy_module.TrendParticipationStrategy().generate_intent(
            {"symbol": "ETHUSDT", "action": "hold_short", "position_size": 0.75, "reason": "short trend"}
        )

        self.assertEqual(intent.action, "hold_short")
        self.assertEqual(intent.desired_exposure, -0.75)

    def test_account_risk_sizing_supports_short_stop_above_entry(self):
        signal = {
            "symbol": "ETHUSDT",
            "action": "hold_short",
            "position_size": 1.0,
            "entry_reference": 100.0,
            "trailing_stop": 112.0,
        }
        snapshot = {"account": {"availableBalance": "1000", "totalMarginBalance": "1000"}}

        sized = trend.apply_account_risk_sizing_to_signal(signal, snapshot, account_risk_fraction=0.012, target_leverage=2.0)

        self.assertEqual(sized["action"], "hold_short")
        self.assertGreater(sized["position_size"], 0)
        self.assertEqual(sized["account_risk_sizing"]["direction"], "short")
        self.assertEqual(sized["account_risk_sizing"]["stop_distance"], 12.0)

    def test_hold_long_pullback_blocks_new_adds_but_keeps_existing_trend(self):
        candles = []
        price = 100.0
        for _ in range(200):
            open_price = price
            close_price = price + 1.0
            candles.append({"open": open_price, "high": close_price + 0.7, "low": open_price - 0.5, "close": close_price})
            price = close_price
        for _ in range(40):
            open_price = price
            close_price = price - 1.0
            candles.append({"open": open_price, "high": open_price + 0.5, "low": close_price - 0.7, "close": close_price})
            price = close_price

        decision = trend.decide(candles, symbol="BTCUSDT", interval="1h")

        self.assertEqual(decision["action"], "hold_long")
        self.assertGreater(decision["position_size"], 0)
        self.assertFalse(decision["add_allowed"])
        self.assertTrue(decision["hold_existing_allowed"])
        self.assertIn("below_ema50", decision["add_blockers"])
        self.assertIn("recent_12_candle_downtrend", decision["add_blockers"])

    def test_generates_flat_decision_when_price_below_major_trend(self):
        candles = []
        price = 100.0
        for _ in range(240):
            open_price = price
            close_price = price
            high = close_price + 0.5
            low = close_price - 0.5
            candles.append({"open": open_price, "high": high, "low": low, "close": close_price})

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
            "ETHUSDT": make_candles(100, 0.0),
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
            ("ETHUSDT", "1h"): make_candles(100, 0.0),
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
        self.assertEqual(skip_reasons["ETHUSDT"], "not_trend_hold")
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

    def test_daily_runtime_analysis_links_risk_rebalance_losses_to_hold_long_runtime_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = pathlib.Path(tmpdir) / "runtime.jsonl"
            order_journal_path = pathlib.Path(tmpdir) / "orders.jsonl"
            runtime_record = {
                "schema_version": "runtime.v1",
                "environment": "testnet",
                "generated_at_utc": "2026-06-17T08:00:00+00:00",
                "generated_at_beijing": "2026-06-17T16:00:00+08:00",
                "symbol_universe": ["ETHUSDT"],
                "signals": [{"symbol": "ETHUSDT", "action": "hold_long", "primary_interval": "1h", "major_trend": "long", "close": 1800.0, "ema50": 1750.0, "ema200": 1600.0}],
                "risk": {"account_risk_fraction": 0.01},
                "execution_events": {
                    "desired_orders": [
                        {
                            "symbol": "ETHUSDT",
                            "side": "SELL",
                            "order_type": "MARKET",
                            "quantity": 0.151,
                            "metadata": {"action": "hold_long", "current_exposure": 0.5, "desired_exposure": 0.349, "delta_exposure": -0.151},
                        }
                    ],
                    "submitted_orders": [],
                    "errors": [],
                },
                "outcomes": {"position_protection": {"unprotected_symbols": []}},
            }
            order_lifecycle = {
                "event_type": "order_lifecycle",
                "environment": "testnet",
                "generated_at_utc": "2026-06-17T08:05:00+00:00",
                "generated_at_beijing": "2026-06-17T16:05:00+08:00",
                "symbol": "ETHUSDT",
                "client_order_id": "hermes-ETHUSDT-reduce-1",
                "current_status": "FILLED",
                "fills_summary": {"fill_quantity": 0.151, "average_fill_price": 1767.57, "realized_pnl": -10.0, "fees": 0.2, "net_pnl": -10.2, "slippage_bps": 4.0, "trade_count": 1},
                "order": {"symbol": "ETHUSDT", "side": "SELL", "origType": "MARKET", "status": "FILLED"},
            }
            # Link the lifecycle record back to the desired order metadata so the analyzer can distinguish a hold_long rebalance from a trend exit.
            order_submission = {
                "environment": "testnet",
                "generated_at_utc": "2026-06-17T08:00:30+00:00",
                "generated_at_beijing": "2026-06-17T16:00:30+08:00",
                "symbol": "ETHUSDT",
                "client_order_id": "hermes-ETHUSDT-reduce-1",
                "side": "SELL",
                "order_type": "MARKET",
                "instruction": runtime_record["execution_events"]["desired_orders"][0],
                "status": "submitted",
            }
            runtime_path.write_text(json.dumps(runtime_record) + "\n", encoding="utf-8")
            order_journal_path.write_text(json.dumps(order_submission) + "\n" + json.dumps(order_lifecycle) + "\n", encoding="utf-8")

            report = trend.analyze_daily_runtime(runtime_path, order_journal_path, window_hours=24)

        self.assertEqual(report["schema_version"], "daily_runtime_analysis.v1")
        self.assertEqual(report["runtime_records_loaded"], 1)
        self.assertEqual(report["closed_orders_loaded"], 1)
        self.assertEqual(report["system_health"]["status"], "healthy")
        self.assertEqual(report["order_attribution"]["by_close_reason"], {"risk_rebalance_reduction": 1})
        self.assertIn("risk_rebalance_loss_not_trend_exit", report["strategy_diagnosis"]["findings"])
        self.assertIn("risk_sizing_or_rebalance", report["strategy_evolution_inputs"])
        self.assertIn("continue_observing_before_default_strategy_change", report["recommendations"])

    def test_daily_runtime_analysis_counts_signed_cycle_and_lifecycle_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = pathlib.Path(tmpdir) / "runtime.jsonl"
            order_journal_path = pathlib.Path(tmpdir) / "orders.jsonl"
            runtime_path.write_text(
                json.dumps(
                    {
                        "schema_version": "runtime.v1",
                        "environment": "testnet",
                        "generated_at_utc": "2026-06-17T08:00:00+00:00",
                        "generated_at_beijing": "2026-06-17T16:00:00+08:00",
                        "symbol_universe": ["BTCUSDT"],
                        "signals": [{"symbol": "BTCUSDT", "action": "hold_long", "primary_interval": "1h"}],
                        "execution_events": {
                            "desired_orders": [{"symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "quantity": 0.01}],
                            "real_orders_submitted": True,
                            "simulated_fills": [{"symbol": "BTCUSDT", "status": "submitted"}],
                            "testnet_order_lifecycle": {"tracked_order_count": 2, "filled_order_count": 1, "net_pnl": -1.25},
                            "errors": [],
                        },
                        "outcomes": {"position_protection": {"unprotected_symbols": []}},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            order_journal_path.write_text("", encoding="utf-8")

            report = trend.analyze_daily_runtime(runtime_path, order_journal_path, window_hours=24)

        self.assertEqual(report["system_health"]["real_order_cycles"], 1)
        self.assertEqual(report["system_health"]["broker_event_count"], 1)
        self.assertEqual(report["system_health"]["lifecycle_tracked_order_count"], 2)
        self.assertEqual(report["system_health"]["lifecycle_filled_order_count"], 1)

    def test_daily_runtime_analysis_flags_submitted_unknown_journal_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = pathlib.Path(tmpdir) / "runtime.jsonl"
            order_journal_path = pathlib.Path(tmpdir) / "orders.jsonl"
            runtime_path.write_text(
                json.dumps(
                    {
                        "schema_version": "runtime.v1",
                        "environment": "testnet",
                        "generated_at_utc": "2026-06-17T08:00:00+00:00",
                        "generated_at_beijing": "2026-06-17T16:00:00+08:00",
                        "execution_events": {"desired_orders": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            order_journal_path.write_text(
                json.dumps(
                    {
                        "environment": "testnet",
                        "generated_at_utc": "2026-06-17T08:05:00+00:00",
                        "generated_at_beijing": "2026-06-17T16:05:00+08:00",
                        "event_type": "order_submission",
                        "client_order_id": "cid-unknown",
                        "symbol": "BTCUSDT",
                        "status": "submitted_unknown",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = trend.analyze_daily_runtime(runtime_path, order_journal_path, window_hours=24)

        self.assertEqual(report["system_health"]["status"], "degraded")
        self.assertEqual(report["system_health"]["submitted_unknown_count"], 1)
        self.assertIn("submitted_unknown_orders", report["system_health"]["issues"])

    def test_cli_can_emit_daily_runtime_analysis_without_signed_side_effects(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = pathlib.Path(tmpdir) / "runtime.jsonl"
            order_journal_path = pathlib.Path(tmpdir) / "orders.jsonl"
            runtime_path.write_text(
                json.dumps(
                    {
                        "schema_version": "runtime.v1",
                        "environment": "testnet",
                        "generated_at_utc": "2026-06-17T08:00:00+00:00",
                        "generated_at_beijing": "2026-06-17T16:00:00+08:00",
                        "symbol_universe": ["BTCUSDT"],
                        "signals": [{"symbol": "BTCUSDT", "action": "hold_long", "primary_interval": "1h"}],
                        "execution_events": {"desired_orders": [], "submitted_orders": [], "errors": []},
                        "outcomes": {"position_protection": {"unprotected_symbols": []}},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            order_journal_path.write_text("", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = trend.main(["--daily-analyze-runtime", "--runtime-record-file", str(runtime_path), "--testnet-order-journal-file", str(order_journal_path), "--analysis-window-hours", "24"])

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["daily_runtime_analysis"]["schema_version"], "daily_runtime_analysis.v1")
        self.assertEqual(payload["daily_runtime_analysis"]["system_health"]["status"], "healthy")
        self.assertIn("generated_at_utc", payload["daily_runtime_analysis"])
        self.assertIn("generated_at_beijing", payload["daily_runtime_analysis"])

    def test_closed_order_analysis_classifies_losing_risk_rebalance_from_journal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = pathlib.Path(tmpdir) / "orders.jsonl"
            submission = {
                "environment": "testnet",
                "generated_at_utc": "2026-06-17T07:05:18+00:00",
                "generated_at_beijing": "2026-06-17T15:05:18+08:00",
                "client_order_id": "hermes-ETHUSDT-reduce-1",
                "symbol": "ETHUSDT",
                "side": "SELL",
                "order_type": "MARKET",
                "quantity": 0.151,
                "reference_price": 1778.12,
                "instruction": {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "quantity": 0.151,
                    "order_type": "MARKET",
                    "metadata": {
                        "action": "hold_long",
                        "current_exposure": 0.5,
                        "desired_exposure": 0.349,
                        "delta_exposure": -0.151,
                        "position_reconciliation": True,
                    },
                },
                "status": "submitted",
            }
            lifecycle = {
                "event_type": "order_lifecycle",
                "environment": "testnet",
                "generated_at_utc": "2026-06-17T08:37:09+00:00",
                "generated_at_beijing": "2026-06-17T16:37:09+08:00",
                "symbol": "ETHUSDT",
                "client_order_id": "hermes-ETHUSDT-reduce-1",
                "order_id": 12345,
                "current_status": "FILLED",
                "lifecycle_state": "filled",
                "fills_summary": {
                    "fill_quantity": 0.151,
                    "average_fill_price": 1767.57,
                    "realized_pnl": -10.47659378,
                    "fees": 0.24675277,
                    "net_pnl": -10.72334655,
                    "slippage_bps": 59.332,
                    "trade_count": 1,
                },
                "order": {"symbol": "ETHUSDT", "side": "SELL", "origType": "MARKET", "status": "FILLED", "executedQty": "0.151", "avgPrice": "1767.57"},
                "trades": [{"side": "SELL", "qty": "0.151", "price": "1767.57", "realizedPnl": "-10.47659378", "commission": "0.24675277"}],
            }
            journal_path.write_text(json.dumps(submission) + "\n" + json.dumps(lifecycle) + "\n", encoding="utf-8")

            report = trend.analyze_closed_orders(journal_path)

        self.assertEqual(report["schema_version"], "closed_order_analysis.v1")
        self.assertEqual(report["orders_loaded"], 1)
        self.assertEqual(report["loss_count"], 1)
        self.assertEqual(report["total_realized_pnl"], -10.47659378)
        order = report["closed_orders"][0]
        self.assertEqual(order["schema_version"], "closed_order.v1")
        self.assertEqual(order["symbol"], "ETHUSDT")
        self.assertEqual(order["side"], "SELL")
        self.assertEqual(order["position_effect"], "reduce_or_close_long")
        self.assertEqual(order["close_reason"], "risk_rebalance_reduction")
        self.assertIn("loss_sample", order["analysis_flags"])
        self.assertIn("risk_sizing_or_rebalance", report["strategy_evolution_inputs"])

    def test_cli_can_emit_closed_order_analysis_from_order_journal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = pathlib.Path(tmpdir) / "orders.jsonl"
            journal_path.write_text(
                json.dumps(
                    {
                        "event_type": "order_lifecycle",
                        "environment": "testnet",
                        "generated_at_utc": "2026-06-17T08:37:09+00:00",
                        "generated_at_beijing": "2026-06-17T16:37:09+08:00",
                        "symbol": "ETHUSDT",
                        "client_order_id": "hermes-ETHUSDT-stop-1",
                        "order_id": 12345,
                        "current_status": "FILLED",
                        "fills_summary": {"fill_quantity": 0.349, "average_fill_price": 1767.57, "realized_pnl": -10.47659378, "fees": 0.24675277, "net_pnl": -10.72334655, "slippage_bps": 0.0, "trade_count": 1},
                        "order": {"symbol": "ETHUSDT", "side": "SELL", "origType": "STOP_MARKET", "status": "FILLED"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = trend.main(["--analyze-closed-orders", "--testnet-order-journal-file", str(journal_path)])

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["closed_order_analysis"]["orders_loaded"], 1)
        self.assertEqual(payload["closed_order_analysis"]["closed_orders"][0]["close_reason"], "stop_loss")
        self.assertIn("generated_at_utc", payload["closed_order_analysis"])
        self.assertIn("generated_at_beijing", payload["closed_order_analysis"])

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
