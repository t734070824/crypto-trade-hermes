import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "binance_usds_futures_trend.py"
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
