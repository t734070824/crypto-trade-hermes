#!/usr/bin/env python3
"""Minimal Binance USDS futures trend-following paper decision helper.

Uses only free public Binance Futures K-line data. It does not place orders.
All generated timestamps explicitly include UTC and Beijing time (UTC+8).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Iterable

BINANCE_FAPI_BASE = "https://fapi.binance.com"
ALLOWED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
    "LINKUSDT", "AVAXUSDT", "ADAUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT",
    "POLUSDT", "BCHUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
    "INJUSDT", "ATOMUSDT",
}
_SHORT_INTERVALS = {"1m", "3m", "5m", "10m", "15m", "30m"}
_ALLOWED_INTERVALS = {"1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}
BEIJING = timezone(timedelta(hours=8), name="UTC+8")


def validate_interval(interval: str) -> str:
    """Return interval if it respects the >=1h policy, else raise ValueError."""
    if interval in _SHORT_INTERVALS:
        raise ValueError(f"short interval is forbidden by policy: {interval}; use >= 1h")
    if interval not in _ALLOWED_INTERVALS:
        raise ValueError(f"unsupported interval: {interval}; allowed: {sorted(_ALLOWED_INTERVALS)}")
    return interval


def validate_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(f"symbol not in configured trading universe: {symbol}")
    return symbol


def ema(values: Iterable[float], period: int) -> float:
    vals = list(values)
    if len(vals) < period:
        raise ValueError(f"need at least {period} values for EMA")
    alpha = 2.0 / (period + 1.0)
    avg = sum(vals[:period]) / period
    for value in vals[period:]:
        avg = alpha * value + (1.0 - alpha) * avg
    return avg


def atr(candles: list[dict[str, float]], period: int = 14) -> float:
    if len(candles) < period + 1:
        raise ValueError(f"need at least {period + 1} candles for ATR")
    true_ranges: list[float] = []
    for previous, current in zip(candles[:-1], candles[1:]):
        high = float(current["high"])
        low = float(current["low"])
        prev_close = float(previous["close"])
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(true_ranges[-period:]) / period


def parse_klines(raw_klines: list[list[Any]]) -> list[dict[str, float]]:
    candles: list[dict[str, float]] = []
    for row in raw_klines:
        candles.append(
            {
                "open_time": float(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "close_time": float(row[6]),
            }
        )
    return candles


def fetch_klines(symbol: str, interval: str, limit: int = 240, base_url: str = BINANCE_FAPI_BASE) -> list[dict[str, float]]:
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    if not 200 <= limit <= 1500:
        raise ValueError("limit must be between 200 and 1500 to support EMA200")
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    url = f"{base_url.rstrip('/')}/fapi/v1/klines?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "crypto-trade-hermes/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected Binance response: {payload!r}")
    return parse_klines(payload)


def now_stamps() -> dict[str, str]:
    now_utc = datetime.now(UTC)
    return {
        "generated_at_utc": now_utc.isoformat(timespec="seconds"),
        "generated_at_beijing": now_utc.astimezone(BEIJING).isoformat(timespec="seconds"),
    }


def decide(candles: list[dict[str, float]], symbol: str, interval: str, risk_unit: float = 1.0) -> dict[str, Any]:
    """Generate a paper-only trend decision.

    Logic is intentionally simple and testable:
    - only >=1h intervals;
    - major trend filter: close > EMA200 and EMA50 > EMA200;
    - participation: hold/enter long while filter is valid;
    - harvesting: two ATR-based take-profit levels;
    - avoid premature exit: ATR trailing stop below entry reference.
    """
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    if len(candles) < 200:
        raise ValueError("need at least 200 candles for EMA200 trend filter")

    closes = [float(c["close"]) for c in candles]
    last_close = closes[-1]
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    current_atr = atr(candles, 14)
    stamps = now_stamps()

    base: dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "mode": "paper",
        **stamps,
        "entry_reference": round(last_close, 8),
        "ema50": round(ema50, 8),
        "ema200": round(ema200, 8),
        "atr14": round(current_atr, 8),
    }

    if not (last_close > ema200 and ema50 > ema200):
        return {
            **base,
            "action": "flat",
            "position_size": 0,
            "trailing_stop": None,
            "take_profit_1": None,
            "take_profit_2": None,
            "reason": "major trend filter failed: require close > EMA200 and EMA50 > EMA200",
        }

    # Smaller size when price is extended far above the fast trend; this keeps participation
    # but avoids over-adding after vertical moves.
    extension = max(0.0, (last_close - ema50) / max(current_atr, 1e-12))
    size_multiplier = 0.5 if extension > 4.0 else 1.0
    position_size = round(max(0.0, risk_unit * size_multiplier), 4)
    return {
        **base,
        "action": "hold_long",
        "position_size": position_size,
        "trailing_stop": round(last_close - 3.0 * current_atr, 8),
        "take_profit_1": round(last_close + 2.0 * current_atr, 8),
        "take_profit_2": round(last_close + 4.0 * current_atr, 8),
        "reason": "major trend filter passed: participate in trend, harvest by ATR tranches, trail stop by ATR",
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Binance USDS futures paper trend decision")
    parser.add_argument("--symbol", default="BTCUSDT", help="USDS futures symbol in configured universe")
    parser.add_argument("--interval", default="1h", help="K-line interval; must be >= 1h")
    parser.add_argument("--limit", type=int, default=240, help="K-line count, 200-1500")
    parser.add_argument("--risk-unit", type=float, default=1.0, help="Paper position sizing unit")
    parser.add_argument("--base-url", default=BINANCE_FAPI_BASE, help="Override Binance Futures base URL for tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        candles = fetch_klines(args.symbol, args.interval, args.limit, args.base_url)
        decision = decide(candles, args.symbol, args.interval, args.risk_unit)
    except Exception as exc:  # CLI should return structured failure for cron/logging.
        print(json.dumps({"ok": False, "error": str(exc), **now_stamps()}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "decision": decision}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
