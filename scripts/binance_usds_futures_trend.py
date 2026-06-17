#!/usr/bin/env python3
"""Binance USDS futures trend-following paper decision helper.

Uses only free public Binance Futures data. It does not place orders.
All generated timestamps explicitly include UTC and Beijing time (UTC+8).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

BINANCE_FAPI_BASE = "https://fapi.binance.com"
DEFAULT_SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
    "LINKUSDT", "AVAXUSDT", "ADAUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT",
    "POLUSDT", "BCHUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
    "INJUSDT", "ATOMUSDT",
)
ALLOWED_SYMBOLS = set(DEFAULT_SYMBOLS)
_SHORT_INTERVALS = {"1m", "3m", "5m", "10m", "15m", "30m"}
_ALLOWED_INTERVALS = {"1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}
_PUBLIC_FACTOR_PERIODS = {"1h", "2h", "4h", "6h", "12h", "1d"}
BEIJING = timezone(timedelta(hours=8), name="UTC+8")


def sanitize_error_message(message: Any) -> str:
    """Redact credentials/signatures from structured CLI error messages."""
    text = str(message)
    text = re.sub(r"(?i)(signature=)[^&\s\"']+", r"\1<redacted>", text)
    text = re.sub(r"(?i)(X-MBX-APIKEY\s*[=:]\s*)[^&\s\"']+", r"\1<redacted>", text)
    text = re.sub(r"(?i)((?:api[_-]?key|secret|signature)\s*[=:]\s*)[^&\s\"']+", r"\1<redacted>", text)
    return text


def validate_interval(interval: str) -> str:
    """Return interval if it respects the >=1h policy, else raise ValueError."""
    if interval in _SHORT_INTERVALS:
        raise ValueError(f"short interval is forbidden by policy: {interval}; use >= 1h")
    if interval not in _ALLOWED_INTERVALS:
        raise ValueError(f"unsupported interval: {interval}; allowed: {sorted(_ALLOWED_INTERVALS)}")
    return interval


def validate_period(period: str) -> str:
    """Validate public futures statistics periods; reject sub-1h periods."""
    if period in _SHORT_INTERVALS:
        raise ValueError(f"short period is forbidden by policy: {period}; use >= 1h")
    if period not in _PUBLIC_FACTOR_PERIODS:
        raise ValueError(f"unsupported public factor period: {period}; allowed: {sorted(_PUBLIC_FACTOR_PERIODS)}")
    return period


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


def _get_json(path: str, params: dict[str, Any], base_url: str = BINANCE_FAPI_BASE) -> Any:
    query = urllib.parse.urlencode(params)
    url = f"{base_url.rstrip('/')}{path}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "crypto-trade-hermes/0.2"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_klines(symbol: str, interval: str, limit: int = 240, base_url: str = BINANCE_FAPI_BASE) -> list[dict[str, float]]:
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    if not 200 <= limit <= 1500:
        raise ValueError("limit must be between 200 and 1500 to support EMA200")
    payload = _get_json("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit}, base_url)
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected Binance response: {payload!r}")
    return parse_klines(payload)


def _last_float(rows: list[dict[str, Any]], key: str) -> float | None:
    if not rows:
        return None
    value = rows[-1].get(key)
    return None if value is None else float(value)


def _pct_change(first: float | None, last: float | None) -> float | None:
    if first is None or last is None or first == 0:
        return None
    return (last - first) / first * 100.0


def fetch_market_context(
    symbol: str,
    period: str,
    limit: int = 30,
    base_url: str = BINANCE_FAPI_BASE,
) -> dict[str, Any]:
    """Fetch free/public USDS-M futures context factors from Binance endpoints."""
    symbol = validate_symbol(symbol)
    period = validate_period(period)
    if not 2 <= limit <= 500:
        raise ValueError("market context limit must be between 2 and 500")

    mark_rows = _get_json("/fapi/v1/markPriceKlines", {"symbol": symbol, "interval": period, "limit": limit}, base_url)
    mark_candles = parse_klines(mark_rows if isinstance(mark_rows, list) else [])
    mark_trend_confirmed = bool(mark_candles and mark_candles[-1]["close"] >= mark_candles[0]["close"])

    funding_rows = _get_json("/fapi/v1/fundingRate", {"symbol": symbol, "limit": min(limit, 100)}, base_url)
    latest_funding_rate = _last_float(funding_rows if isinstance(funding_rows, list) else [], "fundingRate")

    oi_rows = _get_json("/futures/data/openInterestHist", {"symbol": symbol, "period": period, "limit": limit}, base_url)
    oi_list = oi_rows if isinstance(oi_rows, list) else []
    first_oi = float(oi_list[0]["sumOpenInterest"]) if oi_list else None
    last_oi = float(oi_list[-1]["sumOpenInterest"]) if oi_list else None
    open_interest_change_pct = _pct_change(first_oi, last_oi)

    long_short_rows = _get_json(
        "/futures/data/globalLongShortAccountRatio",
        {"symbol": symbol, "period": period, "limit": min(limit, 500)},
        base_url,
    )
    global_long_short_ratio = _last_float(long_short_rows if isinstance(long_short_rows, list) else [], "longShortRatio")

    taker_rows = _get_json(
        "/futures/data/takerlongshortRatio",
        {"symbol": symbol, "period": period, "limit": min(limit, 500)},
        base_url,
    )
    taker_buy_sell_ratio = _last_float(taker_rows if isinstance(taker_rows, list) else [], "buySellRatio")

    return {
        "mark_trend_confirmed": mark_trend_confirmed,
        "latest_funding_rate": latest_funding_rate,
        "open_interest_change_pct": None if open_interest_change_pct is None else round(open_interest_change_pct, 8),
        "global_long_short_ratio": global_long_short_ratio,
        "taker_buy_sell_ratio": taker_buy_sell_ratio,
        "context_period": period,
        "context_limit": limit,
    }


def score_market_context(market_context: dict[str, Any] | None) -> tuple[float, list[str]]:
    """Return confidence multiplier and diagnostic factor flags.

    Secondary factors reduce/add confidence but do not override the main trend by themselves.
    """
    if not market_context:
        return 1.0, []
    score = 1.0
    flags: list[str] = []

    if market_context.get("mark_trend_confirmed") is False:
        score -= 0.20
        flags.append("mark_trend_divergence")

    funding = market_context.get("latest_funding_rate")
    if funding is not None:
        funding = float(funding)
        if abs(funding) >= 0.001:
            score -= 0.20
            flags.append("funding_extreme")
        elif abs(funding) <= 0.0003:
            score += 0.05
            flags.append("funding_neutral")

    oi_change = market_context.get("open_interest_change_pct")
    if oi_change is not None:
        oi_change = float(oi_change)
        if oi_change <= -5.0:
            score -= 0.20
            flags.append("oi_contracting")
        elif oi_change >= 1.0:
            score += 0.10
            flags.append("oi_expanding")

    long_short = market_context.get("global_long_short_ratio")
    if long_short is not None:
        long_short = float(long_short)
        if long_short >= 3.0:
            score -= 0.15
            flags.append("long_side_crowded")
        elif 0.8 <= long_short <= 1.8:
            score += 0.05
            flags.append("long_short_balanced")

    taker_ratio = market_context.get("taker_buy_sell_ratio")
    if taker_ratio is not None:
        taker_ratio = float(taker_ratio)
        if taker_ratio < 1.0:
            score -= 0.10
            flags.append("taker_sell_pressure")
        elif taker_ratio >= 1.1:
            score += 0.05
            flags.append("taker_buy_pressure")

    return round(min(1.25, max(0.25, score)), 4), flags


def now_stamps() -> dict[str, str]:
    now_utc = datetime.now(UTC)
    return {
        "generated_at_utc": now_utc.isoformat(timespec="seconds"),
        "generated_at_beijing": now_utc.astimezone(BEIJING).isoformat(timespec="seconds"),
    }


def decide(
    candles: list[dict[str, float]],
    symbol: str,
    interval: str,
    risk_unit: float = 1.0,
    market_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a paper-only trend decision.

    Logic is intentionally simple and testable:
    - only >=1h intervals;
    - major trend filter: close > EMA200 and EMA50 > EMA200;
    - v0.2 public factors change confidence/size but do not force premature exits;
    - harvesting: two ATR-based take-profit levels;
    - avoid premature exit: ATR trailing stop below entry reference.
    """
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    if len(candles) < 200:
        raise ValueError("at least 200 candles are required for EMA200 trend filter")
    if risk_unit <= 0:
        raise ValueError("risk_unit must be positive")

    closes = [float(candle["close"]) for candle in candles]
    last_close = closes[-1]

    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    current_atr = atr(candles, 14)
    confidence_score, factor_flags = score_market_context(market_context)
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
        "confidence_score": confidence_score,
        "factor_flags": factor_flags,
        "market_context": market_context or {},
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
    # but avoids over-adding after vertical moves. v0.2 public factors further scale size.
    extension = max(0.0, (last_close - ema50) / max(current_atr, 1e-12))
    size_multiplier = 0.5 if extension > 4.0 else 1.0
    position_size = round(max(0.0, risk_unit * size_multiplier * confidence_score), 4)
    return {
        **base,
        "action": "hold_long",
        "position_size": position_size,
        "trailing_stop": round(last_close - 3.0 * current_atr, 8),
        "take_profit_1": round(last_close + 2.0 * current_atr, 8),
        "take_profit_2": round(last_close + 4.0 * current_atr, 8),
        "reason": "major trend filter passed: participate in trend, harvest by ATR tranches, trail stop by ATR; v0.2 factors adjust confidence only",
    }



def apply_account_risk_sizing_to_signal(
    signal: dict[str, Any],
    account_snapshot: dict[str, Any] | None,
    *,
    account_risk_fraction: float = 0.01,
    target_leverage: float = 2.0,
    max_order_notional: float | None = None,
    max_symbol_exposure: float | None = None,
    max_symbol_exposure_fraction: float | None = None,
) -> dict[str, Any]:
    """Size desired exposure from available margin and stop distance.

    The returned ``position_size`` is a desired total contract quantity. The
    position-reconciliation execution engine later submits only the delta versus
    the current broker position.
    """
    sized = dict(signal)
    if sized.get("action") != "hold_long":
        return sized
    if account_risk_fraction <= 0 or target_leverage <= 0:
        raise ValueError("account_risk_fraction and target_leverage must be positive")
    entry_price = _positive_number(sized.get("entry_reference"), "entry_reference")
    stop_price = _positive_number(sized.get("trailing_stop"), "trailing_stop")
    stop_distance = entry_price - stop_price
    if stop_distance <= 0:
        raise ValueError("trailing_stop must be below entry_reference for long risk sizing")
    available_balance, account_equity = _account_balances_from_snapshot(account_snapshot)
    risk_budget = account_equity * account_risk_fraction
    qty_by_stop_risk = risk_budget / stop_distance
    max_notional_by_margin = available_balance * target_leverage
    constraints = ["stop_distance_risk_budget"]
    notional_cap = max_notional_by_margin
    if max_order_notional is not None:
        notional_cap = min(notional_cap, float(max_order_notional))
        constraints.append("max_order_notional_cap")
    if max_symbol_exposure is not None:
        notional_cap = min(notional_cap, float(max_symbol_exposure))
        constraints.append("max_symbol_exposure_cap")
    max_symbol_exposure_from_fraction = None
    if max_symbol_exposure_fraction is not None:
        fraction = float(max_symbol_exposure_fraction)
        if not math.isfinite(fraction) or fraction <= 0:
            raise ValueError("max_symbol_exposure_fraction must be a finite positive number")
        max_symbol_exposure_from_fraction = account_equity * fraction
        notional_cap = min(notional_cap, max_symbol_exposure_from_fraction)
        constraints.append("max_symbol_exposure_fraction_cap")
    qty_by_notional_cap = notional_cap / entry_price
    desired_qty = max(0.0, min(qty_by_stop_risk, qty_by_notional_cap))
    sized["position_size"] = round(desired_qty, 8)
    sized["account_risk_sizing"] = {
        "method": "available_balance_stop_distance_leverage_cap",
        "available_balance": round(available_balance, 8),
        "account_equity": round(account_equity, 8),
        "account_risk_fraction": round(float(account_risk_fraction), 8),
        "risk_budget": round(risk_budget, 8),
        "entry_reference": round(entry_price, 8),
        "trailing_stop": round(stop_price, 8),
        "stop_distance": round(stop_distance, 8),
        "target_leverage": round(float(target_leverage), 8),
        "max_notional_by_margin": round(max_notional_by_margin, 8),
        "effective_notional_cap": round(notional_cap, 8),
        "max_symbol_exposure_fraction": None if max_symbol_exposure_fraction is None else round(float(max_symbol_exposure_fraction), 8),
        "max_symbol_exposure_from_fraction": None if max_symbol_exposure_from_fraction is None else round(max_symbol_exposure_from_fraction, 8),
        "qty_by_stop_risk": round(qty_by_stop_risk, 8),
        "qty_by_notional_cap": round(qty_by_notional_cap, 8),
        "desired_position_size": round(desired_qty, 8),
        "constraints_applied": constraints,
    }
    return sized


def _positive_number(value: Any, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive finite number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field_name} must be a positive finite number")
    return parsed


def _account_balances_from_snapshot(account_snapshot: dict[str, Any] | None) -> tuple[float, float]:
    account = account_snapshot.get("account") if isinstance(account_snapshot, dict) else None
    if not isinstance(account, dict):
        raise ValueError("account snapshot is required for account risk sizing")

    available_value = _first_positive_number(account, ("availableBalance", "available_balance", "maxWithdrawAmount"))
    equity_value = _first_positive_number(account, ("walletBalance", "totalWalletBalance", "totalMarginBalance", "equity"))
    for asset in account.get("assets") or []:
        if isinstance(asset, dict) and str(asset.get("asset", "")).upper() == "USDT":
            if available_value is None:
                available_value = _first_positive_number(asset, ("availableBalance", "maxWithdrawAmount"))
            if equity_value is None:
                equity_value = _first_positive_number(asset, ("walletBalance", "marginBalance", "crossWalletBalance", "equity"))
    if available_value is None:
        available_value = equity_value
    if available_value is None:
        raise ValueError("account snapshot missing availableBalance or wallet/equity balance")
    if equity_value is None:
        equity_value = available_value
    return available_value, equity_value


def _available_balance_from_snapshot(account_snapshot: dict[str, Any] | None) -> float:
    available_balance, _account_equity = _account_balances_from_snapshot(account_snapshot)
    return available_balance


def _first_positive_number(source: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in source:
            return _positive_number(source[key], key)
    return None

def enrich_for_ranking(decision: dict[str, Any], timeframe_agreement_score: float = 1.0) -> dict[str, Any]:
    """Add portfolio-ranking fields to one paper decision."""
    enriched = dict(decision)
    action = enriched.get("action")
    atr14 = float(enriched.get("atr14") or 0.0)
    entry = float(enriched.get("entry_reference") or 0.0)
    ema50_value = float(enriched.get("ema50") or 0.0)
    ema200_value = float(enriched.get("ema200") or 0.0)
    confidence = float(enriched.get("confidence_score") or 0.0)
    position_size = float(enriched.get("position_size") or 0.0)
    agreement = max(0.0, min(1.0, timeframe_agreement_score))
    enriched["timeframe_agreement_score"] = agreement

    if action != "hold_long" or atr14 <= 0:
        enriched.update({"trend_strength": 0.0, "rank_score": 0.0, "ranking_bucket": "watchlist"})
        return enriched

    price_gap_atr = max(0.0, (entry - ema200_value) / atr14)
    ema_gap_atr = max(0.0, (ema50_value - ema200_value) / atr14)
    extension_atr = max(0.0, (entry - ema50_value) / atr14)
    trend_strength = round(price_gap_atr + ema_gap_atr, 4)
    rank_score = round(trend_strength * confidence * max(position_size, 0.01) * agreement, 4)
    flags = set(enriched.get("factor_flags") or [])
    risk_flags = {"funding_extreme", "oi_contracting", "long_side_crowded", "taker_sell_pressure", "mark_trend_divergence"}
    bucket = "risk_high_trend" if extension_atr > 4.0 or confidence < 0.75 or flags.intersection(risk_flags) else "top_trend"
    enriched.update(
        {
            "trend_strength": trend_strength,
            "rank_score": rank_score,
            "extension_atr": round(extension_atr, 4),
            "ranking_bucket": bucket,
        }
    )
    return enriched


def validate_intervals(interval: str | None = "1h", intervals: list[str] | tuple[str, ...] | None = None) -> list[str]:
    """Validate one or more K-line intervals while preserving order."""
    raw_intervals = [interval or "1h"] if intervals is None else list(intervals)
    if not raw_intervals:
        raise ValueError("at least one interval is required")
    validated = [validate_interval(item) for item in raw_intervals]
    if len(set(validated)) != len(validated):
        raise ValueError("duplicate intervals are not allowed")
    return validated


def _timeframe_signal(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": decision.get("action"),
        "entry_reference": decision.get("entry_reference"),
        "ema50": decision.get("ema50"),
        "ema200": decision.get("ema200"),
        "atr14": decision.get("atr14"),
        "reason": decision.get("reason"),
    }


def enrich_with_timeframes(primary: dict[str, Any], timeframe_decisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Add v0.4 multi-timeframe agreement fields to a primary decision."""
    primary_interval = primary["interval"]
    primary_action = primary.get("action")
    total = max(len(timeframe_decisions), 1)
    matching = sum(1 for decision in timeframe_decisions.values() if decision.get("action") == primary_action)
    agreement = matching / total
    higher_intervals = [item for item in timeframe_decisions if item != primary_interval]
    higher_confirmed = bool(
        primary_action == "hold_long"
        and higher_intervals
        and all(timeframe_decisions[item].get("action") == "hold_long" for item in higher_intervals)
    )
    enriched = enrich_for_ranking(primary, agreement)
    enriched.update(
        {
            "timeframe_signals": {interval: _timeframe_signal(decision) for interval, decision in timeframe_decisions.items()},
            "primary_interval": primary_interval,
            "primary_trend": primary_action,
            "higher_timeframe_confirmed": higher_confirmed,
            "timeframe_agreement_score": agreement,
        }
    )
    if primary_action == "hold_long":
        if higher_confirmed:
            enriched["ranking_bucket"] = "strong_confirmed_trend"
        else:
            enriched["ranking_bucket"] = "early_trend"
    elif any(timeframe_decisions[item].get("action") == "hold_long" for item in higher_intervals):
        enriched["ranking_bucket"] = "conflicting_trend"
    return enriched


def allocate_portfolio_risk(
    decisions: list[dict[str, Any]],
    total_risk_budget: float,
    max_symbol_risk: float,
) -> dict[str, Any]:
    """Allocate paper risk units across ranked hold-long decisions with portfolio caps."""
    if total_risk_budget <= 0:
        raise ValueError("total_risk_budget must be positive")
    if max_symbol_risk <= 0:
        raise ValueError("max_symbol_risk must be positive")

    eligible: list[dict[str, Any]] = []
    skipped_symbols: list[str] = []
    skipped_details: list[dict[str, Any]] = []
    for decision in decisions:
        symbol = str(decision.get("symbol", ""))
        rank_score = float(decision.get("rank_score") or 0.0)
        position_size = float(decision.get("position_size") or 0.0)
        action = decision.get("action")
        if action == "hold_long" and rank_score > 0 and position_size > 0:
            eligible.append(decision)
        elif symbol:
            if action != "hold_long":
                skip_reason = "not_hold_long"
            elif rank_score <= 0:
                skip_reason = "non_positive_rank_score"
            else:
                skip_reason = "non_positive_position_size"
            skipped_symbols.append(symbol)
            skipped_details.append(
                {
                    "symbol": symbol,
                    "skip_reason": skip_reason,
                    "action": action,
                    "rank_score": decision.get("rank_score", 0.0),
                    "position_size": decision.get("position_size", 0.0),
                }
            )

    ranked = sorted(eligible, key=lambda item: (float(item.get("rank_score") or 0.0), item.get("symbol", "")), reverse=True)
    remaining = float(total_risk_budget)
    allocations: list[dict[str, Any]] = []
    for decision in ranked:
        symbol = str(decision.get("symbol", ""))
        if remaining <= 1e-12:
            if symbol:
                skipped_symbols.append(symbol)
                skipped_details.append(
                    {
                        "symbol": symbol,
                        "skip_reason": "no_remaining_budget",
                        "action": decision.get("action"),
                        "rank_score": decision.get("rank_score", 0.0),
                        "position_size": decision.get("position_size", 0.0),
                    }
                )
            continue
        position_size = float(decision.get("position_size") or 0.0)
        desired = min(position_size, float(max_symbol_risk), remaining)
        if desired <= 0:
            if symbol:
                skipped_symbols.append(symbol)
                skipped_details.append(
                    {
                        "symbol": symbol,
                        "skip_reason": "non_positive_allocation",
                        "action": decision.get("action"),
                        "rank_score": decision.get("rank_score", 0.0),
                        "position_size": decision.get("position_size", 0.0),
                    }
                )
            continue
        constraints_applied: list[str] = []
        if desired < position_size:
            constraints_applied.append("position_size_reduced")
        if desired <= float(max_symbol_risk) and position_size > float(max_symbol_risk):
            constraints_applied.append("max_symbol_risk_cap")
        if desired <= remaining and min(position_size, float(max_symbol_risk)) > remaining:
            constraints_applied.append("remaining_budget_cap")
        if not constraints_applied:
            constraints_applied.append("full_position_size")
        paper_risk_units = round(desired, 8)
        allocations.append(
            {
                "symbol": symbol,
                "paper_risk_units": paper_risk_units,
                "rank_score": decision.get("rank_score", 0.0),
                "position_size": decision.get("position_size", 0.0),
                "ranking_bucket": decision.get("ranking_bucket"),
                "timeframe_agreement_score": decision.get("timeframe_agreement_score"),
                "constraints_applied": constraints_applied,
                "allocation_explanation": (
                    f"rank_score={decision.get('rank_score', 0.0)}; "
                    f"requested_position_size={decision.get('position_size', 0.0)}; "
                    f"allocated={paper_risk_units}; constraints={','.join(constraints_applied)}; paper only"
                ),
                "reason": "rank-order capped paper allocation; no live order is placed",
            }
        )
        remaining -= paper_risk_units

    total_allocated = round(sum(float(item["paper_risk_units"]) for item in allocations), 8)
    return {
        "mode": "paper",
        **now_stamps(),
        "total_risk_budget": round(float(total_risk_budget), 8),
        "max_symbol_risk": round(float(max_symbol_risk), 8),
        "total_allocated_risk": total_allocated,
        "unallocated_risk": round(max(0.0, float(total_risk_budget) - total_allocated), 8),
        "allocation_method": "rank_order_capped_greedy",
        "allocations": allocations,
        "skipped_symbols": skipped_symbols,
        "skipped_details": skipped_details,
    }


def _round_float(value: Any, digits: int = 8) -> float:
    return round(float(value or 0.0), digits)


def _symbol_allocations(snapshot: dict[str, Any]) -> dict[str, float]:
    return {str(symbol): float(value) for symbol, value in (snapshot.get("allocations_by_symbol") or {}).items()}


def build_paper_state_snapshot(scan: dict[str, Any]) -> dict[str, Any]:
    """Build a compact paper-only state snapshot safe for local persistence."""
    allocation = scan.get("portfolio_allocation") or {}
    allocations = allocation.get("allocations") or []
    allocations_by_symbol = {
        str(item.get("symbol")): _round_float(item.get("paper_risk_units"))
        for item in allocations
        if item.get("symbol")
    }
    results_by_symbol: dict[str, dict[str, Any]] = {}
    for rank, result in enumerate(scan.get("results") or [], start=1):
        symbol = result.get("symbol")
        if not symbol:
            continue
        results_by_symbol[str(symbol)] = {
            "rank": rank,
            "action": result.get("action"),
            "ranking_bucket": result.get("ranking_bucket"),
            "rank_score": result.get("rank_score", 0.0),
            "position_size": result.get("position_size", 0.0),
        }
    return {
        "mode": "paper",
        "generated_at_utc": scan.get("generated_at_utc"),
        "generated_at_beijing": scan.get("generated_at_beijing"),
        "interval": scan.get("interval"),
        "intervals": list(scan.get("intervals") or [scan.get("interval")]),
        "primary_interval": scan.get("primary_interval", scan.get("interval")),
        "top_trends": [item.get("symbol") for item in scan.get("top_trends") or [] if item.get("symbol")],
        "portfolio_allocation": allocation,
        "allocations_by_symbol": allocations_by_symbol,
        "skipped_details": allocation.get("skipped_details", []),
        "errors_count": len(scan.get("errors") or []),
        "results_by_symbol": results_by_symbol,
    }


def compute_paper_state_change(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Compare two paper state snapshots and return allocation/ranking/action changes."""
    previous_allocations = {} if previous is None else _symbol_allocations(previous)
    current_allocations = _symbol_allocations(current)
    previous_results = {} if previous is None else (previous.get("results_by_symbol") or {})
    current_results = current.get("results_by_symbol") or {}

    added = [
        {"symbol": symbol, "paper_risk_units": current_allocations[symbol]}
        for symbol in sorted(current_allocations)
        if symbol not in previous_allocations
    ]
    removed = [
        {"symbol": symbol, "previous_paper_risk_units": previous_allocations[symbol]}
        for symbol in sorted(previous_allocations)
        if symbol not in current_allocations
    ]
    changed = []
    for symbol in sorted(set(previous_allocations).intersection(current_allocations)):
        previous_units = previous_allocations[symbol]
        current_units = current_allocations[symbol]
        delta = round(current_units - previous_units, 8)
        if abs(delta) > 1e-12:
            changed.append(
                {
                    "symbol": symbol,
                    "previous_paper_risk_units": previous_units,
                    "current_paper_risk_units": current_units,
                    "delta": delta,
                }
            )

    ranking_changes = []
    action_changes = []
    bucket_changes = []
    for symbol in sorted(set(previous_results).intersection(current_results)):
        before = previous_results[symbol]
        after = current_results[symbol]
        if before.get("rank") != after.get("rank"):
            ranking_changes.append({"symbol": symbol, "previous_rank": before.get("rank"), "current_rank": after.get("rank")})
        if before.get("action") != after.get("action"):
            action_changes.append({"symbol": symbol, "previous_action": before.get("action"), "current_action": after.get("action")})
        if before.get("ranking_bucket") != after.get("ranking_bucket"):
            bucket_changes.append(
                {"symbol": symbol, "previous_bucket": before.get("ranking_bucket"), "current_bucket": after.get("ranking_bucket")}
            )

    return {
        "mode": "paper",
        **now_stamps(),
        "first_run": previous is None,
        "previous_state_loaded": previous is not None,
        "current_errors_count": current.get("errors_count", 0),
        "added_allocations": added,
        "removed_allocations": removed,
        "changed_allocations": changed,
        "ranking_changes": ranking_changes,
        "action_changes": action_changes,
        "bucket_changes": bucket_changes,
    }


def load_paper_state(path: str | os.PathLike[str]) -> tuple[dict[str, Any] | None, str | None]:
    state_path = Path(path)
    if not state_path.exists():
        return None, None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"invalid state file JSON: {exc}"
    except OSError as exc:
        return None, f"cannot read state file: {exc}"
    if not isinstance(payload, dict):
        return None, "invalid state file JSON: top-level value is not an object"
    return payload, None


def save_paper_state(path: str | os.PathLike[str], snapshot: dict[str, Any]) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{state_path.name}.", suffix=".tmp", dir=str(state_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, state_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def apply_paper_state(
    scan: dict[str, Any],
    state_file: str | os.PathLike[str],
    save_state: bool = True,
) -> dict[str, Any]:
    """Attach v0.7 paper state snapshot/change to a scan and optionally persist it."""
    updated = dict(scan)
    current = build_paper_state_snapshot(updated)
    previous, state_error = load_paper_state(state_file)
    change = compute_paper_state_change(previous, current)
    if state_error:
        change["state_file_error"] = state_error
    updated["paper_state"] = current
    updated["state_change"] = change
    if save_state:
        save_paper_state(state_file, current)
    return updated


def _optional_round(value: Any, digits: int = 8) -> float | None:
    if value is None:
        return None
    return _round_float(value, digits)


def _paper_position_from_decision(decision: dict[str, Any], previous_position: dict[str, Any] | None) -> dict[str, Any]:
    symbol = str(decision.get("symbol"))
    action = decision.get("action")
    target_size = _round_float(decision.get("position_size"))
    reference = _optional_round(decision.get("entry_reference"))
    previous_open = bool(
        previous_position
        and previous_position.get("status") == "open"
        and float(previous_position.get("current_size") or 0.0) > 0
    )
    previous_size = float(previous_position.get("current_size") or 0.0) if previous_position else 0.0
    previous_entry = previous_position.get("entry_reference") if previous_position else None

    if action == "hold_long" and target_size > 0:
        if not previous_open:
            intent = "entry"
        elif target_size > previous_size + 1e-12:
            intent = "add"
        elif target_size < previous_size - 1e-12:
            intent = "reduce"
        else:
            intent = "hold"

        previous_trailing = None if not previous_position else previous_position.get("trailing_stop")
        current_trailing = decision.get("trailing_stop")
        trailing_candidates = [float(item) for item in (previous_trailing, current_trailing) if item is not None]
        trailing_stop = round(max(trailing_candidates), 8) if trailing_candidates else None
        executed_tranches = list((previous_position or {}).get("executed_tranches") or [])
        executed_names = {item.get("name") for item in executed_tranches if isinstance(item, dict)}
        if previous_open and reference is not None:
            for tranche_name in ("take_profit_1", "take_profit_2"):
                threshold = previous_position.get(tranche_name) if previous_position else None
                if threshold is not None and tranche_name not in executed_names and float(reference) >= float(threshold):
                    executed_tranches.append(
                        {
                            "name": tranche_name,
                            "trigger_price": _round_float(threshold),
                            "executed_at_reference": reference,
                            "size_after": target_size,
                        }
                    )

        return {
            "symbol": symbol,
            "status": "open",
            "last_intent": intent,
            "current_size": target_size,
            "entry_reference": _optional_round(previous_entry) if previous_open and previous_entry is not None else reference,
            "last_reference": reference,
            "trailing_stop": trailing_stop,
            "take_profit_1": _optional_round(decision.get("take_profit_1")),
            "take_profit_2": _optional_round(decision.get("take_profit_2")),
            "executed_tranches": executed_tranches,
            "ranking_bucket": decision.get("ranking_bucket"),
            "rank_score": _round_float(decision.get("rank_score")),
            "reason": decision.get("reason"),
        }

    if previous_open:
        assert previous_position is not None
        return {
            "symbol": symbol,
            "status": "closed",
            "last_intent": "exit",
            "current_size": 0.0,
            "entry_reference": _optional_round(previous_entry),
            "last_reference": reference,
            "trailing_stop": _optional_round(previous_position.get("trailing_stop")),
            "take_profit_1": _optional_round(previous_position.get("take_profit_1")),
            "take_profit_2": _optional_round(previous_position.get("take_profit_2")),
            "executed_tranches": list(previous_position.get("executed_tranches") or []),
            "ranking_bucket": decision.get("ranking_bucket"),
            "rank_score": _round_float(decision.get("rank_score")),
            "exit_reason": decision.get("reason", "signal no longer hold_long"),
            "reason": decision.get("reason"),
        }

    return {
        "symbol": symbol,
        "status": "flat",
        "last_intent": "flat",
        "current_size": 0.0,
        "entry_reference": reference,
        "last_reference": reference,
        "trailing_stop": None,
        "take_profit_1": None,
        "take_profit_2": None,
        "executed_tranches": [],
        "ranking_bucket": decision.get("ranking_bucket"),
        "rank_score": _round_float(decision.get("rank_score")),
        "reason": decision.get("reason"),
    }


def build_paper_lifecycle_snapshot(scan: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build paper-only per-symbol lifecycle state from a scan and optional prior lifecycle."""
    previous_positions = {} if previous is None else (previous.get("positions_by_symbol") or {})
    positions_by_symbol: dict[str, dict[str, Any]] = {}
    seen_symbols: set[str] = set()
    for decision in scan.get("results") or []:
        symbol = decision.get("symbol")
        if not symbol:
            continue
        symbol_text = str(symbol)
        seen_symbols.add(symbol_text)
        previous_position = previous_positions.get(symbol_text)
        positions_by_symbol[symbol_text] = _paper_position_from_decision(decision, previous_position)

    for symbol, previous_position in sorted(previous_positions.items()):
        if symbol in seen_symbols:
            continue
        if previous_position.get("status") == "open" and float(previous_position.get("current_size") or 0.0) > 0:
            carried = dict(previous_position)
            carried["last_intent"] = "hold"
            carried["stale"] = True
            carried["stale_reason"] = "symbol missing from current scan; paper position carried without execution"
            positions_by_symbol[symbol] = carried

    open_positions = [symbol for symbol, item in positions_by_symbol.items() if item.get("status") == "open"]
    closed_positions = [symbol for symbol, item in positions_by_symbol.items() if item.get("status") == "closed"]
    return {
        "mode": "paper",
        "generated_at_utc": scan.get("generated_at_utc"),
        "generated_at_beijing": scan.get("generated_at_beijing"),
        "interval": scan.get("interval"),
        "intervals": list(scan.get("intervals") or [scan.get("interval")]),
        "primary_interval": scan.get("primary_interval", scan.get("interval")),
        "open_positions": open_positions,
        "closed_positions": closed_positions,
        "positions_by_symbol": positions_by_symbol,
        "errors_count": len(scan.get("errors") or []),
    }


def compute_paper_lifecycle_change(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    previous_positions = {} if previous is None else (previous.get("positions_by_symbol") or {})
    current_positions = current.get("positions_by_symbol") or {}
    status_changes: list[dict[str, Any]] = []
    intent_changes: list[dict[str, str]] = []
    tranche_events: list[dict[str, Any]] = []
    for symbol in sorted(set(previous_positions).union(current_positions)):
        before = previous_positions.get(symbol) or {}
        after = current_positions.get(symbol) or {}
        if before.get("status") != after.get("status") and after.get("status"):
            status_changes.append({"symbol": symbol, "previous_status": before.get("status"), "current_status": after.get("status")})
        intent = after.get("last_intent")
        if intent and intent != before.get("last_intent") and intent != "flat":
            intent_changes.append({"symbol": symbol, "intent": str(intent)})
        before_tranches = {item.get("name") for item in before.get("executed_tranches") or [] if isinstance(item, dict)}
        for tranche in after.get("executed_tranches") or []:
            if isinstance(tranche, dict) and tranche.get("name") not in before_tranches:
                tranche_events.append({"symbol": symbol, **tranche})
    return {
        "mode": "paper",
        **now_stamps(),
        "first_run": previous is None,
        "previous_lifecycle_loaded": previous is not None,
        "open_positions": list(current.get("open_positions") or []),
        "closed_positions": list(current.get("closed_positions") or []),
        "status_changes": status_changes,
        "intent_changes": intent_changes,
        "tranche_events": tranche_events,
        "current_errors_count": current.get("errors_count", 0),
    }


def apply_paper_lifecycle(
    scan: dict[str, Any],
    lifecycle_file: str | os.PathLike[str],
    save_lifecycle: bool = True,
) -> dict[str, Any]:
    """Attach v1.1 paper lifecycle state/change to a scan and optionally persist it."""
    updated = dict(scan)
    previous, lifecycle_error = load_paper_state(lifecycle_file)
    current = build_paper_lifecycle_snapshot(updated, previous)
    change = compute_paper_lifecycle_change(previous, current)
    if lifecycle_error:
        change["lifecycle_file_error"] = lifecycle_error
    updated["paper_lifecycle"] = current
    updated["lifecycle_change"] = change
    if save_lifecycle:
        save_paper_state(lifecycle_file, current)
    return updated


def _unique_nonempty(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _runtime_signals(scan: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for rank, item in enumerate(scan.get("results") or [], start=1):
        signals.append(
            {
                "rank": rank,
                "symbol": item.get("symbol"),
                "interval": item.get("interval", scan.get("primary_interval", scan.get("interval"))),
                "action": item.get("action"),
                "primary_trend": item.get("primary_trend", item.get("action")),
                "ranking_bucket": item.get("ranking_bucket"),
                "rank_score": item.get("rank_score"),
                "confidence_score": item.get("confidence_score"),
                "trend_strength": item.get("trend_strength"),
                "position_size": item.get("position_size"),
                "factor_flags": list(item.get("factor_flags") or []),
                "entry_reference": item.get("entry_reference"),
                "trailing_stop": item.get("trailing_stop"),
                "take_profit_1": item.get("take_profit_1"),
                "take_profit_2": item.get("take_profit_2"),
                "timeframe_agreement_score": item.get("timeframe_agreement_score"),
                "higher_timeframe_confirmed": item.get("higher_timeframe_confirmed"),
                "timeframe_signals": item.get("timeframe_signals", {}),
                "reason": item.get("reason"),
            }
        )
    return signals


def _runtime_paper_intents(scan: dict[str, Any]) -> list[dict[str, Any]]:
    lifecycle = scan.get("paper_lifecycle") or {}
    positions = lifecycle.get("positions_by_symbol") or {}
    intents: list[dict[str, Any]] = []
    for symbol, position in sorted(positions.items()):
        intent = position.get("last_intent")
        if not intent or intent == "flat":
            continue
        intents.append(
            {
                "symbol": symbol,
                "intent": intent,
                "status": position.get("status"),
                "paper_size": position.get("current_size"),
                "entry_reference": position.get("entry_reference"),
                "last_reference": position.get("last_reference"),
                "trailing_stop": position.get("trailing_stop"),
                "take_profit_1": position.get("take_profit_1"),
                "take_profit_2": position.get("take_profit_2"),
            }
        )
    if intents:
        return intents
    allocation = scan.get("portfolio_allocation") or {}
    for item in allocation.get("allocations") or []:
        intents.append(
            {
                "symbol": item.get("symbol"),
                "intent": "allocate_paper_risk",
                "paper_size": item.get("paper_risk_units"),
                "rank_score": item.get("rank_score"),
                "constraints_applied": list(item.get("constraints_applied") or []),
            }
        )
    return intents


def build_runtime_record(
    scan: dict[str, Any],
    environment: str = "paper",
    strategy_version: str = "ema50_ema200_atr_trend_paper",
    config_version: str = "default",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build append-only runtime evidence for strategy evolution and audit.

    v1.3 is paper-only. The schema is intentionally environment-aware so v1.5+
    can reuse it with broker adapters without changing the evidence contract.
    """
    if environment != "paper":
        raise ValueError("v1.3 runtime recording only supports environment=paper")
    stamps = {
        "generated_at_utc": scan.get("generated_at_utc"),
        "generated_at_beijing": scan.get("generated_at_beijing"),
    }
    if not stamps["generated_at_utc"] or not stamps["generated_at_beijing"]:
        stamps = now_stamps()
    symbols = _unique_nonempty(item.get("symbol") for item in scan.get("results") or [])
    intervals = [str(item) for item in (scan.get("intervals") or [scan.get("interval")]) if item]
    context_periods = _unique_nonempty(
        (item.get("market_context") or {}).get("context_period")
        for item in scan.get("results") or []
    )
    context_limits = _unique_nonempty(
        (item.get("market_context") or {}).get("context_limit")
        for item in scan.get("results") or []
    )
    lifecycle = scan.get("paper_lifecycle") or {}
    record = {
        "schema_version": "runtime.v1",
        "environment": environment,
        "run_id": run_id or f"{environment}-{stamps['generated_at_utc']}",
        "strategy_version": strategy_version,
        "config_version": config_version,
        **stamps,
        "symbol_universe": symbols,
        "intervals": intervals,
        "market_inputs": {
            "source": "binance_free_public_usds_futures",
            "symbols": symbols,
            "primary_interval": scan.get("primary_interval", scan.get("interval")),
            "intervals": intervals,
            "context_periods": context_periods,
            "context_limits": context_limits,
            "data_freshness": {
                "scan_generated_at_utc": scan.get("generated_at_utc"),
                "scan_generated_at_beijing": scan.get("generated_at_beijing"),
            },
            "errors": list(scan.get("errors") or []),
        },
        "signals": _runtime_signals(scan),
        "risk": {
            "portfolio_allocation": scan.get("portfolio_allocation", {}),
            "risk_high_symbols": [item.get("symbol") for item in scan.get("risk_high_trends") or [] if item.get("symbol")],
            "conflicting_symbols": [item.get("symbol") for item in scan.get("conflicting_trends") or [] if item.get("symbol")],
        },
        "portfolio_state": {
            "paper_state": scan.get("paper_state", {}),
            "paper_lifecycle": lifecycle,
            "state_change": scan.get("state_change", {}),
            "lifecycle_change": scan.get("lifecycle_change", {}),
        },
        "execution_events": {
            "environment": environment,
            "real_orders_submitted": False,
            "paper_intents": _runtime_paper_intents(scan),
        },
        "outcomes": {
            "errors_count": len(scan.get("errors") or []),
            "top_trends": [item.get("symbol") for item in scan.get("top_trends") or [] if item.get("symbol")],
            "watchlist_count": len(scan.get("watchlist") or []),
            "open_positions": list(lifecycle.get("open_positions") or []),
            "closed_positions": list(lifecycle.get("closed_positions") or []),
            "runtime_summary": "paper runtime evidence recorded; no real orders submitted",
        },
    }
    return record


def append_runtime_record(path: str | os.PathLike[str], record: dict[str, Any]) -> dict[str, Any]:
    """Append one JSONL runtime record and return a small write receipt."""
    runtime_path = Path(path)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    with runtime_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    return {"path": str(runtime_path), "records_written": 1}


def _load_jsonl_records(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    jsonl_path = Path(path)
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSONL record: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"line {line_number}: JSONL record must be an object")
            records.append(item)
    return records


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _dict_field(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def _final_order_status(record: dict[str, Any]) -> str:
    order = _dict_field(record, "order")
    return str(record.get("current_status") or record.get("status") or order.get("status") or "UNKNOWN").upper()


def _order_side(record: dict[str, Any], submission: dict[str, Any] | None = None) -> str:
    source = submission or record
    order = _dict_field(record, "order")
    instruction = _dict_field(source, "instruction")
    return str(record.get("side") or order.get("side") or instruction.get("side") or "UNKNOWN").upper()


def _order_type(record: dict[str, Any], submission: dict[str, Any] | None = None) -> str:
    source = submission or record
    order = _dict_field(record, "order")
    instruction = _dict_field(source, "instruction")
    return str(record.get("order_type") or order.get("origType") or order.get("type") or instruction.get("order_type") or "UNKNOWN").upper()


def _instruction_metadata(record: dict[str, Any], submission: dict[str, Any] | None = None) -> dict[str, Any]:
    source = submission or record
    instruction = _dict_field(source, "instruction")
    metadata = instruction.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _infer_position_effect(side: str, status: str) -> str:
    if status not in {"FILLED", "PARTIALLY_FILLED"}:
        return "no_position_change"
    if side == "SELL":
        return "reduce_or_close_long"
    if side == "BUY":
        return "increase_or_open_long"
    return "unknown"


def _infer_close_reason(order_type: str, side: str, status: str, metadata: dict[str, Any]) -> str:
    protection_role = str(metadata.get("protection_role") or "").lower()
    action = str(metadata.get("action") or "").lower()
    delta_exposure = _safe_float(metadata.get("delta_exposure"), 0.0)
    if status == "CANCELED":
        return "canceled_or_replanned"
    if status == "REJECTED":
        return "rejected"
    if status == "EXPIRED":
        return "expired"
    if "stop_loss" in protection_role or order_type in {"STOP_MARKET", "STOP"}:
        return "stop_loss"
    if "take_profit" in protection_role or order_type in {"TAKE_PROFIT_MARKET", "TAKE_PROFIT"}:
        return "take_profit"
    if side == "SELL" and action == "hold_long" and delta_exposure < 0:
        return "risk_rebalance_reduction"
    if side == "SELL" and action in {"flat", "exit"}:
        return "strategy_exit"
    if side == "SELL":
        return "manual_or_unclassified_reduction"
    return "non_closing_or_opening_order"


def _closed_order_analysis_flags(realized_pnl: float, net_pnl: float, slippage_bps: float, close_reason: str, status: str) -> list[str]:
    flags: list[str] = []
    is_closing_sample = close_reason != "non_closing_or_opening_order"
    if realized_pnl < 0 or (is_closing_sample and net_pnl < 0):
        flags.append("loss_sample")
    if abs(slippage_bps) >= 10:
        flags.append("slippage_sample")
    if close_reason == "risk_rebalance_reduction":
        flags.append("risk_sizing_sample")
    if close_reason in {"stop_loss", "take_profit"}:
        flags.append("protection_policy_sample")
    if status in {"REJECTED", "EXPIRED"}:
        flags.append("execution_anomaly_sample")
    return flags


def _strategy_evolution_inputs(closed_orders: list[dict[str, Any]]) -> list[str]:
    inputs: set[str] = set()
    for order in closed_orders:
        reason = order.get("close_reason")
        flags = set(order.get("analysis_flags") or [])
        if reason == "risk_rebalance_reduction":
            inputs.add("risk_sizing_or_rebalance")
        if reason == "stop_loss":
            inputs.add("stop_policy")
        if reason == "take_profit":
            inputs.add("take_profit_policy")
        if "slippage_sample" in flags:
            inputs.add("execution_quality")
        if "loss_sample" in flags:
            inputs.add("loss_attribution")
        if reason in {"canceled_or_replanned", "rejected", "expired"}:
            inputs.add("execution_or_protection_reconciliation")
    return sorted(inputs)


def analyze_closed_orders(order_journal_file: str | os.PathLike[str]) -> dict[str, Any]:
    """Normalize ended testnet order lifecycle records into strategy-evolution evidence."""
    records = _load_jsonl_records(order_journal_file)
    submissions_by_client_id: dict[str, dict[str, Any]] = {}
    for record in records:
        client_order_id = record.get("client_order_id")
        if client_order_id and record.get("event_type") != "order_lifecycle":
            submissions_by_client_id[str(client_order_id)] = record

    closed_orders: list[dict[str, Any]] = []
    for record in records:
        status = _final_order_status(record)
        if status not in {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}:
            continue
        order_payload = _dict_field(record, "order")
        client_order_id = str(record.get("client_order_id") or order_payload.get("clientOrderId") or "")
        submission = submissions_by_client_id.get(client_order_id)
        side = _order_side(record, submission)
        order_type = _order_type(record, submission)
        metadata = _instruction_metadata(record, submission)
        fills_summary = _dict_field(record, "fills_summary")
        realized_pnl = round(_safe_float(fills_summary.get("realized_pnl")), 8)
        fees = round(_safe_float(fills_summary.get("fees")), 8)
        net_pnl = round(_safe_float(fills_summary.get("net_pnl"), realized_pnl - fees), 8)
        fill_quantity = round(_safe_float(fills_summary.get("fill_quantity") or order_payload.get("executedQty") or record.get("quantity")), 8)
        average_fill_price = round(_safe_float(fills_summary.get("average_fill_price") or order_payload.get("avgPrice")), 8)
        slippage_bps = round(_safe_float(fills_summary.get("slippage_bps")), 8)
        close_reason = _infer_close_reason(order_type, side, status, metadata)
        closed_order = {
            "schema_version": "closed_order.v1",
            "environment": record.get("environment", (submission or {}).get("environment", "unknown")),
            "symbol": str(record.get("symbol") or order_payload.get("symbol") or (submission or {}).get("symbol") or "UNKNOWN").upper(),
            "client_order_id": client_order_id,
            "order_id": record.get("order_id") or order_payload.get("orderId"),
            "side": side,
            "order_type": order_type,
            "status": status,
            "position_effect": _infer_position_effect(side, status),
            "close_reason": close_reason,
            "quantity": fill_quantity,
            "average_fill_price": average_fill_price,
            "realized_pnl": realized_pnl,
            "fees": fees,
            "net_pnl": net_pnl,
            "slippage_bps": slippage_bps,
            "trade_count": int(_safe_float(fills_summary.get("trade_count"), 0.0)),
            "opened_or_submitted_at_utc": (submission or {}).get("generated_at_utc"),
            "opened_or_submitted_at_beijing": (submission or {}).get("generated_at_beijing"),
            "closed_at_utc": record.get("generated_at_utc"),
            "closed_at_beijing": record.get("generated_at_beijing"),
            "linked_signal_action": metadata.get("action"),
            "current_exposure": metadata.get("current_exposure"),
            "desired_exposure": metadata.get("desired_exposure"),
        }
        closed_order["analysis_flags"] = _closed_order_analysis_flags(realized_pnl, net_pnl, slippage_bps, close_reason, status)
        closed_orders.append(closed_order)

    by_reason: dict[str, int] = {}
    by_symbol: dict[str, dict[str, Any]] = {}
    for order in closed_orders:
        reason = str(order["close_reason"])
        by_reason[reason] = by_reason.get(reason, 0) + 1
        symbol = str(order["symbol"])
        symbol_summary = by_symbol.setdefault(symbol, {"orders": 0, "realized_pnl": 0.0, "net_pnl": 0.0, "loss_count": 0})
        symbol_summary["orders"] += 1
        symbol_summary["realized_pnl"] = round(float(symbol_summary["realized_pnl"]) + float(order["realized_pnl"]), 8)
        symbol_summary["net_pnl"] = round(float(symbol_summary["net_pnl"]) + float(order["net_pnl"]), 8)
        if "loss_sample" in order.get("analysis_flags", []):
            symbol_summary["loss_count"] += 1

    report = {
        "schema_version": "closed_order_analysis.v1",
        "environment": sorted({str(order.get("environment")) for order in closed_orders}) or [],
        **now_stamps(),
        "source_order_journal_file": str(order_journal_file),
        "orders_loaded": len(closed_orders),
        "loss_count": sum(1 for order in closed_orders if "loss_sample" in order.get("analysis_flags", [])),
        "total_realized_pnl": round(sum(float(order["realized_pnl"]) for order in closed_orders), 8),
        "total_net_pnl": round(sum(float(order["net_pnl"]) for order in closed_orders), 8),
        "by_close_reason": by_reason,
        "by_symbol": by_symbol,
        "strategy_evolution_inputs": _strategy_evolution_inputs(closed_orders),
        "closed_orders": closed_orders,
        "summary_zh": "已结束订单分析：将 FILLED/CANCELED/REJECTED/EXPIRED 订单标准化为 closed_order.v1，用于亏损归因、执行质量、风控 sizing 与保护单策略演进；不会自动修改策略默认参数。",
        "errors_count": 0,
    }
    return report


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _filter_records_by_window(records: list[dict[str, Any]], window_hours: int, timestamp_key: str = "generated_at_utc") -> list[dict[str, Any]]:
    if window_hours <= 0:
        raise ValueError("analysis window must be positive hours")
    dated = [(record, _parse_iso_datetime(record.get(timestamp_key))) for record in records]
    latest = max((stamp for _, stamp in dated if stamp is not None), default=None)
    if latest is None:
        return records
    cutoff = latest - timedelta(hours=window_hours)
    return [record for record, stamp in dated if stamp is None or stamp >= cutoff]


def _list_field(record: dict[str, Any], key: str) -> list[Any]:
    value = record.get(key)
    return value if isinstance(value, list) else []


def _runtime_execution_events(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("execution_events")
    return value if isinstance(value, dict) else {}


def _runtime_signal_action_by_symbol(runtime_records: list[dict[str, Any]]) -> dict[str, str]:
    actions: dict[str, str] = {}
    for record in runtime_records:
        for signal in _list_field(record, "signals"):
            if not isinstance(signal, dict):
                continue
            symbol = str(signal.get("symbol") or "").upper()
            action = str(signal.get("action") or "").lower()
            if symbol and action:
                actions[symbol] = action
    return actions


def _runtime_health(runtime_records: list[dict[str, Any]], closed_orders: list[dict[str, Any]], order_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    issues: list[str] = []
    total_desired_orders = 0
    total_submitted_orders = 0
    broker_event_count = 0
    real_order_cycles = 0
    lifecycle_tracked_order_count = 0
    lifecycle_filled_order_count = 0
    unprotected_symbols: set[str] = set()
    submitted_unknown_count = 0
    execution_error_count = 0
    for raw_order in order_records or []:
        if _final_order_status(raw_order) == "SUBMITTED_UNKNOWN":
            submitted_unknown_count += 1
    for record in runtime_records:
        events = _runtime_execution_events(record)
        desired_orders = _list_field(events, "desired_orders")
        submitted_orders = _list_field(events, "submitted_orders")
        errors = _list_field(events, "errors")
        total_desired_orders += len(desired_orders)
        total_submitted_orders += len(submitted_orders)
        broker_events = submitted_orders or _list_field(events, "simulated_fills")
        broker_event_count += len(broker_events)
        if bool(events.get("real_orders_submitted")):
            real_order_cycles += 1
        lifecycle = _dict_field(events, "testnet_order_lifecycle")
        lifecycle_tracked_order_count += int(_safe_float(lifecycle.get("tracked_order_count"), 0.0))
        lifecycle_filled_order_count += int(_safe_float(lifecycle.get("filled_order_count"), 0.0))
        execution_error_count += len(errors)
        outcomes = _dict_field(record, "outcomes")
        protection = _dict_field(outcomes, "position_protection")
        for symbol in _list_field(protection, "unprotected_symbols"):
            unprotected_symbols.add(str(symbol).upper())
    if execution_error_count:
        issues.append("runtime_execution_errors")
    if unprotected_symbols:
        issues.append("unprotected_symbols")
    if submitted_unknown_count:
        issues.append("submitted_unknown_orders")
    status = "healthy" if not issues else "degraded"
    return {
        "status": status,
        "issues": issues,
        "runtime_records": len(runtime_records),
        "desired_orders": total_desired_orders,
        "submitted_orders": total_submitted_orders,
        "broker_event_count": broker_event_count,
        "real_order_cycles": real_order_cycles,
        "lifecycle_tracked_order_count": lifecycle_tracked_order_count,
        "lifecycle_filled_order_count": lifecycle_filled_order_count,
        "execution_error_count": execution_error_count,
        "submitted_unknown_count": submitted_unknown_count,
        "unprotected_symbols": sorted(unprotected_symbols),
    }


def _daily_strategy_diagnosis(runtime_records: list[dict[str, Any]], closed_orders: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[str] = []
    symbol_actions = _runtime_signal_action_by_symbol(runtime_records)
    risk_rebalance_losses = [order for order in closed_orders if order.get("close_reason") == "risk_rebalance_reduction" and "loss_sample" in order.get("analysis_flags", [])]
    stop_losses = [order for order in closed_orders if order.get("close_reason") == "stop_loss" and "loss_sample" in order.get("analysis_flags", [])]
    take_profits = [order for order in closed_orders if order.get("close_reason") == "take_profit"]
    strategy_exits = [order for order in closed_orders if order.get("close_reason") == "strategy_exit"]
    if risk_rebalance_losses:
        if any(symbol_actions.get(str(order.get("symbol") or "").upper()) == "hold_long" for order in risk_rebalance_losses):
            findings.append("risk_rebalance_loss_not_trend_exit")
        else:
            findings.append("risk_rebalance_loss_requires_signal_context")
    if stop_losses:
        findings.append("stop_loss_samples_need_stop_distance_review")
    if take_profits:
        findings.append("take_profit_samples_need_runner_review")
    if strategy_exits:
        findings.append("strategy_exit_samples_need_trend_break_review")
    if not findings:
        findings.append("no_strategy_change_signal_yet")
    return {
        "findings": findings,
        "risk_rebalance_loss_count": len(risk_rebalance_losses),
        "stop_loss_count": len(stop_losses),
        "take_profit_count": len(take_profits),
        "strategy_exit_count": len(strategy_exits),
        "latest_signal_action_by_symbol": symbol_actions,
    }


def _daily_recommendations(system_health: dict[str, Any], strategy_diagnosis: dict[str, Any], closed_orders: list[dict[str, Any]]) -> list[str]:
    recommendations: list[str] = []
    if system_health.get("status") != "healthy":
        recommendations.append("fix_execution_or_evidence_quality_before_strategy_change")
    findings = set(strategy_diagnosis.get("findings") or [])
    if "risk_rebalance_loss_not_trend_exit" in findings:
        recommendations.append("evaluate_rebalance_hysteresis_or_cooldown_candidate")
    if "stop_loss_samples_need_stop_distance_review" in findings:
        recommendations.append("evaluate_stop_distance_candidate")
    if "take_profit_samples_need_runner_review" in findings:
        recommendations.append("evaluate_take_profit_runner_candidate")
    if closed_orders:
        recommendations.append("continue_observing_before_default_strategy_change")
    else:
        recommendations.append("collect_more_closed_order_evidence")
    return recommendations


def analyze_daily_runtime(runtime_record_file: str | os.PathLike[str], order_journal_file: str | os.PathLike[str], window_hours: int = 24) -> dict[str, Any]:
    """Read runtime/order evidence and produce a daily read-only analyzer report."""
    runtime_records = _filter_records_by_window(_load_jsonl_records(runtime_record_file), window_hours)
    order_records = _filter_records_by_window(_load_jsonl_records(order_journal_file), window_hours)
    closed_report = analyze_closed_orders(order_journal_file)
    closed_orders = _filter_records_by_window(list(closed_report.get("closed_orders") or []), window_hours, timestamp_key="closed_at_utc")
    by_reason: dict[str, int] = {}
    by_symbol: dict[str, dict[str, Any]] = {}
    for order in closed_orders:
        reason = str(order.get("close_reason"))
        by_reason[reason] = by_reason.get(reason, 0) + 1
        symbol = str(order.get("symbol") or "UNKNOWN").upper()
        summary = by_symbol.setdefault(symbol, {"orders": 0, "realized_pnl": 0.0, "net_pnl": 0.0, "loss_count": 0})
        summary["orders"] += 1
        summary["realized_pnl"] = round(float(summary["realized_pnl"]) + _safe_float(order.get("realized_pnl")), 8)
        summary["net_pnl"] = round(float(summary["net_pnl"]) + _safe_float(order.get("net_pnl")), 8)
        if "loss_sample" in (order.get("analysis_flags") or []):
            summary["loss_count"] += 1
    system_health = _runtime_health(runtime_records, closed_orders, order_records)
    strategy_diagnosis = _daily_strategy_diagnosis(runtime_records, closed_orders)
    strategy_evolution_inputs = _strategy_evolution_inputs(closed_orders)
    report = {
        "schema_version": "daily_runtime_analysis.v1",
        "environment": sorted({str(record.get("environment")) for record in runtime_records if record.get("environment")} | {str(order.get("environment")) for order in closed_orders if order.get("environment")}),
        **now_stamps(),
        "analysis_window_hours": window_hours,
        "source_runtime_record_file": str(runtime_record_file),
        "source_order_journal_file": str(order_journal_file),
        "runtime_records_loaded": len(runtime_records),
        "order_journal_records_loaded": len(order_records),
        "closed_orders_loaded": len(closed_orders),
        "system_health": system_health,
        "order_attribution": {
            "by_close_reason": by_reason,
            "by_symbol": by_symbol,
            "loss_count": sum(1 for order in closed_orders if "loss_sample" in (order.get("analysis_flags") or [])),
            "total_realized_pnl": round(sum(_safe_float(order.get("realized_pnl")) for order in closed_orders), 8),
            "total_net_pnl": round(sum(_safe_float(order.get("net_pnl")) for order in closed_orders), 8),
        },
        "strategy_diagnosis": strategy_diagnosis,
        "strategy_evolution_inputs": strategy_evolution_inputs,
        "recommendations": _daily_recommendations(system_health, strategy_diagnosis, closed_orders),
        "summary_zh": "每日只读运行分析：先判断系统/证据健康，再归因已结束订单，最后给出候选策略或风控演进建议；不会自动修改默认策略或触发交易。",
        "errors_count": 0,
    }
    return report


def apply_runtime_record(
    scan: dict[str, Any],
    runtime_record_file: str | os.PathLike[str] | None = None,
    environment: str = "paper",
    strategy_version: str = "ema50_ema200_atr_trend_paper",
    config_version: str = "default",
    save_runtime_record: bool = True,
) -> dict[str, Any]:
    """Attach v1.3 runtime evidence and optionally append it to JSONL."""
    updated = dict(scan)
    record = build_runtime_record(updated, environment, strategy_version, config_version)
    updated["runtime_record"] = record
    updated["runtime_record_saved"] = False
    updated["runtime_record_change"] = {
        "mode": "paper",
        **now_stamps(),
        "schema_version": record.get("schema_version"),
        "environment": environment,
        "records_written": 0,
        "append_only": True,
    }
    if runtime_record_file and save_runtime_record:
        receipt = append_runtime_record(runtime_record_file, record)
        updated["runtime_record_saved"] = True
        updated["runtime_record_file"] = receipt["path"]
        updated["runtime_record_change"].update(receipt)
    elif runtime_record_file:
        updated["runtime_record_file"] = str(runtime_record_file)
        updated["runtime_record_change"]["path"] = str(runtime_record_file)
    return updated


def _interval_hours(interval: str) -> float:
    validated = validate_interval(interval)
    unit = validated[-1]
    amount = int(validated[:-1])
    if unit == "h":
        return float(amount)
    if unit == "d":
        return float(amount * 24)
    if unit == "w":
        return float(amount * 24 * 7)
    if unit == "M":
        return float(amount * 24 * 30)
    raise ValueError(f"unsupported interval for backtest annualization: {interval}")


def _annual_periods(interval: str) -> float:
    return 365.0 * 24.0 / _interval_hours(interval)


def _max_drawdown(equity_values: list[float]) -> float:
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    worst = 0.0
    for value in equity_values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return round(worst, 8)


def _sharpe(periodic_returns: list[float], interval: str) -> float:
    if len(periodic_returns) < 2:
        return 0.0
    mean_return = sum(periodic_returns) / len(periodic_returns)
    variance = sum((item - mean_return) ** 2 for item in periodic_returns) / (len(periodic_returns) - 1)
    if variance <= 0:
        return 0.0
    return round((mean_return / math.sqrt(variance)) * math.sqrt(_annual_periods(interval)), 8)


def _performance_metrics(
    equity_values: list[float],
    periodic_returns: list[float],
    interval: str,
    initial_equity: float,
    trades: list[dict[str, Any]],
    total_turnover: float,
) -> dict[str, float]:
    final_equity = equity_values[-1] if equity_values else initial_equity
    total_return = final_equity / initial_equity - 1.0
    periods = max(len(periodic_returns), 1)
    years = max(periods / _annual_periods(interval), 1e-12)
    cagr = (final_equity / initial_equity) ** (1.0 / years) - 1.0 if final_equity > 0 else -1.0
    max_dd = _max_drawdown([initial_equity, *equity_values])
    calmar = 0.0 if max_dd == 0 else cagr / abs(max_dd)
    wins = [trade for trade in trades if float(trade.get("return", 0.0)) > 0]
    win_rate = 0.0 if not trades else len(wins) / len(trades)
    avg_holding = 0.0 if not trades else sum(float(trade.get("holding_candles", 0.0)) for trade in trades) / len(trades)
    return {
        "initial_equity": round(initial_equity, 8),
        "final_equity": round(final_equity, 8),
        "total_return": round(total_return, 8),
        "cagr": round(cagr, 8),
        "max_drawdown": max_dd,
        "calmar": round(calmar, 8),
        "sharpe": _sharpe(periodic_returns, interval),
        "win_rate": round(win_rate, 8),
        "average_holding_candles": round(avg_holding, 8),
        "turnover": round(total_turnover, 8),
    }


def _build_backtest_summary_zh(backtest: dict[str, Any]) -> str:
    metrics = backtest.get("metrics") or {}
    lines = [
        "Binance USDS-M 历史回测（paper only）",
        f"UTC: {backtest.get('generated_at_utc')}",
        f"北京时间（UTC+8）: {backtest.get('generated_at_beijing')}",
        f"周期: {backtest.get('interval')}; universe={backtest.get('universe_count', 1)}; bars={backtest.get('bars_processed', 0)}",
        "指标: "
        f"CAGR={metrics.get('cagr', 0.0)}; "
        f"max_drawdown={metrics.get('max_drawdown', 0.0)}; "
        f"Calmar={metrics.get('calmar', 0.0)}; "
        f"Sharpe={metrics.get('sharpe', 0.0)}; "
        f"win_rate={metrics.get('win_rate', 0.0)}; "
        f"turnover={metrics.get('turnover', 0.0)}",
        "安全: paper only；未下真实订单；未使用收费 API。",
    ]
    return "\n".join(lines)


def backtest_symbol(
    candles: list[dict[str, float]],
    symbol: str,
    interval: str,
    initial_equity: float = 10_000.0,
    fee_bps: float = 4.0,
    max_position_size: float = 1.0,
    risk_unit: float = 1.0,
) -> dict[str, Any]:
    """Run a simple paper-only historical backtest for one symbol.

    The simulation uses existing EMA/ATR paper decisions and applies the target long
    exposure after each candle close, so no future candle is used to form the signal.
    """
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    if len(candles) <= 200:
        raise ValueError("at least 201 candles are required for historical backtest")
    if initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    if fee_bps < 0:
        raise ValueError("fee_bps must be non-negative")
    if max_position_size <= 0:
        raise ValueError("max_position_size must be positive")
    if risk_unit <= 0:
        raise ValueError("risk_unit must be positive")

    equity = float(initial_equity)
    current_position = 0.0
    entry_equity: float | None = None
    holding_candles = 0
    total_turnover = 0.0
    periodic_returns: list[float] = []
    equity_curve: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []

    for index in range(200, len(candles)):
        previous_close = float(candles[index - 1]["close"])
        close = float(candles[index]["close"])
        before_period_equity = equity
        if current_position > 0 and previous_close > 0:
            equity *= 1.0 + current_position * (close / previous_close - 1.0)
            holding_candles += 1

        decision = decide(candles[: index + 1], symbol, interval, risk_unit=risk_unit, market_context=None)
        target_position = 0.0
        if decision.get("action") == "hold_long":
            target_position = min(float(decision.get("position_size") or 0.0), float(max_position_size))
        position_delta = target_position - current_position
        if abs(position_delta) > 1e-12:
            fee = equity * abs(position_delta) * float(fee_bps) / 10_000.0
            equity -= fee
            total_turnover += abs(position_delta)
            if current_position <= 0 < target_position:
                entry_equity = equity
                holding_candles = 0
            elif current_position > 0 and target_position <= 0:
                trade_return = 0.0 if not entry_equity else equity / entry_equity - 1.0
                trades.append(
                    {
                        "symbol": symbol,
                        "return": round(trade_return, 8),
                        "holding_candles": holding_candles,
                        "exit_index": index,
                        "status": "closed",
                    }
                )
                entry_equity = None
                holding_candles = 0
        current_position = target_position
        periodic_returns.append(0.0 if before_period_equity <= 0 else equity / before_period_equity - 1.0)
        equity_curve.append(
            {
                "index": index,
                "open_time": candles[index].get("open_time"),
                "close_time": candles[index].get("close_time"),
                "close": round(close, 8),
                "equity": round(equity, 8),
                "position_size": round(current_position, 8),
                "action": decision.get("action"),
            }
        )

    if current_position > 0 and entry_equity:
        trades.append(
            {
                "symbol": symbol,
                "return": round(equity / entry_equity - 1.0, 8),
                "holding_candles": holding_candles,
                "exit_index": len(candles) - 1,
                "status": "open_at_end",
            }
        )

    metrics = _performance_metrics(
        [item["equity"] for item in equity_curve],
        periodic_returns,
        interval,
        float(initial_equity),
        trades,
        total_turnover,
    )
    result: dict[str, Any] = {
        "mode": "paper",
        **now_stamps(),
        "symbol": symbol,
        "interval": interval,
        "strategy": "ema50_ema200_atr_trend_paper",
        "bars_processed": len(equity_curve),
        "fee_bps": round(float(fee_bps), 8),
        "max_position_size": round(float(max_position_size), 8),
        "risk_unit": round(float(risk_unit), 8),
        "metrics": metrics,
        "trades": trades,
        "equity_curve": equity_curve,
        "per_symbol_contribution": {symbol: metrics["total_return"]},
        "errors": [],
        "errors_count": 0,
    }
    result["summary_zh"] = _build_backtest_summary_zh(result)
    return result


def _build_backtest_symbols_result(
    selected_symbols: list[str],
    interval: str,
    symbol_results: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    metrics = _aggregate_backtest_metrics(symbol_results, interval)
    per_symbol_contribution = _per_symbol_contribution(symbol_results)
    backtest: dict[str, Any] = {
        "mode": "paper",
        **now_stamps(),
        "interval": interval,
        "universe_count": len(selected_symbols),
        "symbols_tested": [item["symbol"] for item in symbol_results],
        "bars_processed": sum(int(item.get("bars_processed", 0)) for item in symbol_results),
        "strategy": "ema50_ema200_atr_trend_paper",
        "metrics": metrics,
        "per_symbol_contribution": per_symbol_contribution,
        "symbol_results": symbol_results,
        "errors": errors,
        "errors_count": len(errors),
    }
    backtest["summary_zh"] = _build_backtest_summary_zh(backtest)
    return backtest


def _aligned_equity_maps(symbol_results: list[dict[str, Any]]) -> tuple[list[Any], list[dict[Any, float]]]:
    """Return common close_time values and per-symbol equity maps for portfolio aggregation."""
    equity_maps: list[dict[Any, float]] = []
    common_times: set[Any] | None = None
    for result in symbol_results:
        mapping: dict[Any, float] = {}
        for point in result.get("equity_curve", []):
            timestamp = point.get("close_time")
            if timestamp is None:
                continue
            mapping[timestamp] = float(point["equity"])
        equity_maps.append(mapping)
        timestamps = set(mapping)
        common_times = timestamps if common_times is None else common_times & timestamps
    return sorted(common_times or []), equity_maps


def _per_symbol_contribution(symbol_results: list[dict[str, Any]]) -> dict[str, float]:
    common_times, equity_maps = _aligned_equity_maps(symbol_results)
    total_initial_equity = sum(float(item["metrics"].get("initial_equity", 0.0)) for item in symbol_results)
    if total_initial_equity <= 0 or not common_times:
        return {item["symbol"]: 0.0 for item in symbol_results}
    final_time = common_times[-1]
    contributions: dict[str, float] = {}
    for result, equity_map in zip(symbol_results, equity_maps):
        initial = float(result["metrics"].get("initial_equity", 0.0))
        aligned_final = float(equity_map[final_time])
        contributions[result["symbol"]] = round((aligned_final - initial) / total_initial_equity, 8)
    return contributions


def _aggregate_backtest_metrics(symbol_results: list[dict[str, Any]], interval: str) -> dict[str, float]:
    if not symbol_results:
        return {
            "initial_equity": 0.0,
            "final_equity": 0.0,
            "total_return": 0.0,
            "cagr": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "sharpe": 0.0,
            "win_rate": 0.0,
            "average_holding_candles": 0.0,
            "turnover": 0.0,
        }
    initial_equity = sum(float(item["metrics"].get("initial_equity", 0.0)) for item in symbol_results)
    common_times, equity_maps = _aligned_equity_maps(symbol_results)
    if initial_equity <= 0 or not common_times:
        return {
            "initial_equity": round(initial_equity, 8),
            "final_equity": round(initial_equity, 8),
            "total_return": 0.0,
            "cagr": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "sharpe": 0.0,
            "win_rate": 0.0,
            "average_holding_candles": 0.0,
            "turnover": 0.0,
        }

    combined_equity_values = [
        sum(float(equity_map[timestamp]) for equity_map in equity_maps)
        for timestamp in common_times
    ]
    periodic_returns: list[float] = []
    previous_equity = initial_equity
    for equity in combined_equity_values:
        periodic_returns.append(0.0 if previous_equity <= 0 else equity / previous_equity - 1.0)
        previous_equity = equity

    trades = [trade for item in symbol_results for trade in item.get("trades", [])]
    total_turnover = sum(float(item["metrics"].get("turnover", 0.0)) for item in symbol_results)
    return _performance_metrics(
        combined_equity_values,
        periodic_returns,
        interval,
        initial_equity,
        trades,
        total_turnover,
    )


def backtest_symbols(
    symbols: list[str] | tuple[str, ...] | None = None,
    interval: str = "1h",
    limit: int = 500,
    initial_equity: float = 10_000.0,
    fee_bps: float = 4.0,
    max_position_size: float = 1.0,
    risk_unit: float = 1.0,
    base_url: str = BINANCE_FAPI_BASE,
) -> dict[str, Any]:
    """Fetch free K-lines and run paper-only historical backtests for symbols."""
    interval = validate_interval(interval)
    selected_symbols = list(DEFAULT_SYMBOLS if symbols is None else symbols)
    selected_symbols = [validate_symbol(symbol) for symbol in selected_symbols]
    if limit <= 200:
        raise ValueError("backtest limit must be greater than 200")

    symbol_results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for symbol in selected_symbols:
        try:
            candles = fetch_klines(symbol, interval, limit, base_url)
            symbol_results.append(
                backtest_symbol(
                    candles,
                    symbol=symbol,
                    interval=interval,
                    initial_equity=initial_equity,
                    fee_bps=fee_bps,
                    max_position_size=max_position_size,
                    risk_unit=risk_unit,
                )
            )
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    return _build_backtest_symbols_result(selected_symbols, interval, symbol_results, errors)


DEFAULT_REFINEMENT_VARIANTS = (
    {
        "name": "baseline",
        "description": "v0.9 baseline EMA50/EMA200 + ATR trend paper backtest behavior",
        "max_position_size": 1.0,
        "risk_unit": 1.0,
    },
    {
        "name": "trend_hold_bias",
        "description": "slightly higher paper risk unit for confirmed trend participation diagnostics",
        "max_position_size": 1.15,
        "risk_unit": 1.15,
    },
    {
        "name": "risk_capped",
        "description": "lower paper exposure cap for defensive drawdown comparison",
        "max_position_size": 0.75,
        "risk_unit": 0.75,
    },
)


def _abs_drawdown(metrics: dict[str, Any]) -> float:
    return abs(float(metrics.get("max_drawdown", 0.0) or 0.0))


def _evidence_score(metrics: dict[str, Any]) -> float:
    """Rank evidence without ignoring risk-adjusted metrics."""
    cagr = float(metrics.get("cagr", 0.0) or 0.0)
    calmar = float(metrics.get("calmar", 0.0) or 0.0)
    sharpe = float(metrics.get("sharpe", 0.0) or 0.0)
    return round(cagr + 0.03 * calmar + 0.02 * sharpe, 8)


def _build_refinement_summary_zh(refinement: dict[str, Any]) -> str:
    selected = refinement.get("selected_variant") or "none"
    lines = [
        "Binance USDS-M 策略证据化对比（paper only）",
        f"UTC: {refinement.get('generated_at_utc')}",
        f"北京时间（UTC+8）: {refinement.get('generated_at_beijing')}",
        f"周期: {refinement.get('interval')}; universe={refinement.get('universe_count', 0)}; selected={selected}",
    ]
    for item in refinement.get("variants", []):
        metrics = item.get("metrics") or {}
        eligibility = "eligible" if item.get("eligible") else "blocked"
        lines.append(
            f"{item.get('variant')}: {eligibility}; score={item.get('evidence_score')}; "
            f"CAGR={metrics.get('cagr', 0.0)}; max_drawdown={metrics.get('max_drawdown', 0.0)}; "
            f"Calmar={metrics.get('calmar', 0.0)}; Sharpe={metrics.get('sharpe', 0.0)}"
        )
    lines.append("安全: paper only；候选策略仅作历史证据诊断；未下真实订单；未使用收费 API。")
    return "\n".join(lines)


def compare_strategy_variants(
    symbols: list[str] | tuple[str, ...] | None = None,
    interval: str = "1h",
    limit: int = 500,
    initial_equity: float = 10_000.0,
    fee_bps: float = 4.0,
    base_url: str = BINANCE_FAPI_BASE,
    max_drawdown_worsening_limit: float = 0.03,
) -> dict[str, Any]:
    """Compare paper-only strategy variants before changing defaults.

    v1.0 deliberately reports diagnostics only. It does not promote a candidate into
    scan defaults, and it blocks candidates whose drawdown worsens beyond guardrails.
    """
    interval = validate_interval(interval)
    selected_symbols = list(DEFAULT_SYMBOLS if symbols is None else symbols)
    selected_symbols = [validate_symbol(symbol) for symbol in selected_symbols]
    if max_drawdown_worsening_limit < 0:
        raise ValueError("max_drawdown_worsening_limit must be non-negative")

    candles_by_symbol: dict[str, list[dict[str, float]]] = {}
    fetch_errors: list[dict[str, str]] = []
    for symbol in selected_symbols:
        try:
            candles_by_symbol[symbol] = fetch_klines(symbol, interval, limit, base_url)
        except Exception as exc:
            fetch_errors.append({"symbol": symbol, "error": str(exc)})

    variants: list[dict[str, Any]] = []
    baseline_metrics: dict[str, Any] | None = None
    baseline_score = 0.0
    baseline_drawdown = 0.0
    for config in DEFAULT_REFINEMENT_VARIANTS:
        symbol_results: list[dict[str, Any]] = []
        errors = list(fetch_errors)
        for symbol, candles in candles_by_symbol.items():
            try:
                symbol_results.append(
                    backtest_symbol(
                        candles,
                        symbol=symbol,
                        interval=interval,
                        initial_equity=initial_equity,
                        fee_bps=fee_bps,
                        max_position_size=float(config["max_position_size"]),
                        risk_unit=float(config["risk_unit"]),
                    )
                )
            except Exception as exc:
                errors.append({"symbol": symbol, "error": str(exc)})
        backtest = _build_backtest_symbols_result(selected_symbols, interval, symbol_results, errors)
        metrics = dict(backtest.get("metrics") or {})
        score = _evidence_score(metrics)
        guardrail_flags: list[str] = []
        eligible = not bool(backtest.get("errors"))
        if config["name"] == "baseline":
            baseline_metrics = metrics
            baseline_score = score
            baseline_drawdown = _abs_drawdown(metrics)
        else:
            candidate_drawdown = _abs_drawdown(metrics)
            if candidate_drawdown > baseline_drawdown + max_drawdown_worsening_limit:
                eligible = False
                guardrail_flags.append("drawdown_guardrail")
        if backtest.get("errors"):
            guardrail_flags.append("backtest_errors")
        variants.append(
            {
                "variant": config["name"],
                "description": config["description"],
                "mode": "paper",
                "max_position_size": round(float(config["max_position_size"]), 8),
                "risk_unit": round(float(config["risk_unit"]), 8),
                "metrics": metrics,
                "evidence_score": score,
                "eligible": eligible,
                "guardrail_flags": guardrail_flags,
                "errors_count": int(backtest.get("errors_count", len(backtest.get("errors") or [])) or 0),
                "selected": False,
            }
        )

    selected_index = 0
    for index, item in enumerate(variants[1:], start=1):
        if item["eligible"] and float(item["evidence_score"]) > baseline_score:
            if float(item["evidence_score"]) > float(variants[selected_index]["evidence_score"]):
                selected_index = index
    variants[selected_index]["selected"] = True
    refinement: dict[str, Any] = {
        "mode": "paper",
        **now_stamps(),
        "interval": interval,
        "universe_count": len(selected_symbols),
        "symbols_tested": selected_symbols,
        "strategy": "ema50_ema200_atr_trend_paper_refinement_diagnostic",
        "baseline_variant": "baseline",
        "selected_variant": variants[selected_index]["variant"],
        "selection_policy": {
            "score": "cagr + 0.03*calmar + 0.02*sharpe",
            "candidate_must_beat_baseline_score": True,
            "max_drawdown_worsening_limit": round(float(max_drawdown_worsening_limit), 8),
            "auto_promote_defaults": False,
        },
        "baseline_metrics": baseline_metrics or {},
        "variants": variants,
        "errors_count": sum(int(item.get("errors_count", 0)) for item in variants),
    }
    refinement["summary_zh"] = _build_refinement_summary_zh(refinement)
    return refinement


def build_scan_summary_zh(scan: dict[str, Any]) -> str:
    """Build a compact Chinese report with explicit UTC and Beijing time labels."""
    top_n = scan.get("top_n", 0)
    intervals_text = ",".join(scan.get("intervals", [scan.get("interval", "")]))
    mode_label = "多周期" if len(scan.get("intervals", [])) > 1 else "单周期"
    lines = [
        f"Binance USDS-M {mode_label}趋势扫描（paper only）",
        f"UTC: {scan['generated_at_utc']}",
        f"北京时间（UTC+8）: {scan['generated_at_beijing']}",
        f"周期: {intervals_text}；扫描数量: {scan['universe_count']}",
        f"最强趋势 Top {top_n}: " + (", ".join(item["symbol"] for item in scan.get("top_trends", [])) or "无"),
    ]
    if len(scan.get("intervals", [])) > 1:
        strong_symbols = ", ".join(item["symbol"] for item in scan.get("strong_confirmed_trends", [])) or "无"
        early_symbols = ", ".join(item["symbol"] for item in scan.get("early_trends", [])) or "无"
        conflicting_symbols = ", ".join(item["symbol"] for item in scan.get("conflicting_trends", [])) or "无"
        lines.append(f"强确认趋势: {strong_symbols}")
        lines.append(f"早期趋势: {early_symbols}")
        lines.append(f"周期冲突: {conflicting_symbols}")
    risk_symbols = ", ".join(item["symbol"] for item in scan.get("risk_high_trends", [])) or "无"
    watch_symbols = ", ".join(item["symbol"] for item in scan.get("watchlist", [])[:10]) or "无"
    lines.append(f"趋势内但风险偏高: {risk_symbols}")
    lines.append(f"观望/空仓: {watch_symbols}")
    allocation = scan.get("portfolio_allocation")
    if allocation:
        allocated_symbols = ", ".join(
            f"{item['symbol']}={item['paper_risk_units']}" for item in allocation.get("allocations", [])
        ) or "无"
        lines.append(
            "组合纸面风险预算: "
            f"已分配 {allocation['total_allocated_risk']}/{allocation['total_risk_budget']} risk units；"
            f"单标的上限 {allocation['max_symbol_risk']}；分配: {allocated_symbols}"
        )
        allocation_notes = "; ".join(
            f"{item['symbol']}: {item.get('allocation_explanation', item.get('reason', 'paper only'))}"
            for item in allocation.get("allocations", [])[:3]
        ) or "无"
        lines.append(f"分配说明: {allocation_notes}")
    return "\n".join(lines)


def _format_symbol_list(items: list[dict[str, Any]], key: str = "symbol", limit: int = 8) -> str:
    symbols = [str(item.get(key)) for item in items[:limit] if item.get(key)]
    return ", ".join(symbols) if symbols else "无"


def build_telegram_briefing_zh(scan: dict[str, Any]) -> str:
    """Build a compact Telegram-friendly Chinese paper scan briefing.

    The briefing intentionally avoids dumping raw JSON or endpoint error bodies.
    """
    allocation = scan.get("portfolio_allocation") or {}
    allocations = allocation.get("allocations") or []
    allocation_text = ", ".join(
        f"{item.get('symbol')}={item.get('paper_risk_units')}" for item in allocations[:8] if item.get("symbol")
    ) or "无"

    change = scan.get("state_change") or {}
    added_text = ", ".join(
        f"{item.get('symbol')}={item.get('paper_risk_units')}" for item in (change.get("added_allocations") or [])[:8]
    ) or "无"
    removed_text = ", ".join(
        f"{item.get('symbol')}(prev={item.get('previous_paper_risk_units')})"
        for item in (change.get("removed_allocations") or [])[:8]
    ) or "无"
    changed_text = ", ".join(
        f"{item.get('symbol')} {item.get('previous_paper_risk_units')}→{item.get('current_paper_risk_units')} (Δ={item.get('delta')})"
        for item in (change.get("changed_allocations") or [])[:8]
    ) or "无"

    errors_count = len(scan.get("errors") or [])
    if "current_errors_count" in change:
        errors_count = int(change.get("current_errors_count") or 0)
    intervals_text = ",".join(scan.get("intervals") or [scan.get("interval", "")])
    risk_high = _format_symbol_list(scan.get("risk_high_trends") or [])
    conflicting = _format_symbol_list(scan.get("conflicting_trends") or [])
    top_trends = _format_symbol_list(scan.get("top_trends") or [])
    first_run_label = "yes" if change.get("first_run") else "no"

    lines = [
        "Binance USDS-M Paper Scan（paper only）",
        f"UTC: {scan.get('generated_at_utc')}",
        f"北京时间（UTC+8）: {scan.get('generated_at_beijing')}",
        f"周期: {intervals_text}; universe={scan.get('universe_count', 'unknown')}",
        f"Top trends: {top_trends}",
        f"Allocation: {allocation_text}",
        f"State change: first_run={first_run_label}; 新增: {added_text}; 移除: {removed_text}; 变化: {changed_text}",
        "rank/action/bucket changes: "
        f"{len(change.get('ranking_changes') or [])}/{len(change.get('action_changes') or [])}/{len(change.get('bucket_changes') or [])}",
        f"risk notes: risk_high={risk_high}; conflicting={conflicting}; errors_count={errors_count}",
        "安全: paper only；未下真实订单；未使用收费 API。",
    ]
    return "\n".join(lines)


def scan_symbols(
    symbols: list[str] | tuple[str, ...] | None = None,
    interval: str = "1h",
    intervals: list[str] | tuple[str, ...] | None = None,
    limit: int = 240,
    context_limit: int = 30,
    risk_unit: float = 1.0,
    base_url: str = BINANCE_FAPI_BASE,
    include_context: bool = True,
    top: int = 5,
    portfolio_risk_budget: float | None = None,
    max_symbol_risk: float | None = None,
) -> dict[str, Any]:
    """Scan multiple configured symbols and rank paper trend opportunities."""
    scan_intervals = validate_intervals(interval, intervals)
    primary_interval = scan_intervals[0]
    if top < 1:
        raise ValueError("top must be >= 1")
    selected_symbols = list(DEFAULT_SYMBOLS if symbols is None else symbols)
    selected_symbols = [validate_symbol(symbol) for symbol in selected_symbols]
    stamps = now_stamps()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for symbol in selected_symbols:
        try:
            timeframe_decisions: dict[str, dict[str, Any]] = {}
            for current_interval in scan_intervals:
                candles = fetch_klines(symbol, current_interval, limit, base_url)
                market_context = None
                if include_context and current_interval == primary_interval:
                    market_context = fetch_market_context(symbol, current_interval, context_limit, base_url)
                timeframe_decisions[current_interval] = decide(candles, symbol, current_interval, risk_unit, market_context)
            primary_decision = timeframe_decisions[primary_interval]
            if len(scan_intervals) == 1:
                results.append(enrich_for_ranking(primary_decision))
            else:
                results.append(enrich_with_timeframes(primary_decision, timeframe_decisions))
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
            results.append(
                {
                    "symbol": symbol,
                    "interval": primary_interval,
                    "intervals": scan_intervals,
                    "mode": "paper",
                    "action": "error",
                    "primary_trend": "error",
                    "position_size": 0,
                    "confidence_score": 0,
                    "trend_strength": 0.0,
                    "timeframe_agreement_score": 0.0,
                    "rank_score": -1.0,
                    "ranking_bucket": "error",
                    "reason": str(exc),
                }
            )

    ranked = sorted(results, key=lambda item: (float(item.get("rank_score", -1.0)), item.get("symbol", "")), reverse=True)
    top_trends = [item for item in ranked if item.get("action") == "hold_long"][:top]
    risk_high = [item for item in ranked if item.get("ranking_bucket") == "risk_high_trend"]
    strong_confirmed = [item for item in ranked if item.get("ranking_bucket") == "strong_confirmed_trend"]
    early_trends = [item for item in ranked if item.get("ranking_bucket") == "early_trend"]
    conflicting_trends = [item for item in ranked if item.get("ranking_bucket") == "conflicting_trend"]
    watchlist = [item for item in ranked if item.get("action") in {"flat", "error"}]
    scan: dict[str, Any] = {
        "mode": "paper",
        "interval": primary_interval,
        "intervals": scan_intervals,
        "primary_interval": primary_interval,
        **stamps,
        "universe_count": len(selected_symbols),
        "top_n": top,
        "results": ranked,
        "top_trends": top_trends,
        "strong_confirmed_trends": strong_confirmed,
        "early_trends": early_trends,
        "conflicting_trends": conflicting_trends,
        "risk_high_trends": risk_high,
        "watchlist": watchlist,
        "errors": errors,
    }
    if portfolio_risk_budget is not None or max_symbol_risk is not None:
        scan["portfolio_allocation"] = allocate_portfolio_risk(
            ranked,
            total_risk_budget=3.0 if portfolio_risk_budget is None else portfolio_risk_budget,
            max_symbol_risk=1.0 if max_symbol_risk is None else max_symbol_risk,
        )
    scan["summary_zh"] = build_scan_summary_zh(scan)
    return scan


def run_paper_trading_cycle(
    symbols: Iterable[str],
    interval: str = "1h",
    limit: int = 240,
    runtime_record_file: str | os.PathLike[str] | None = None,
    save_runtime_record: bool = True,
    strategy_version: str = "ema50_ema200_atr_trend_paper",
    config_version: str = "default",
    base_url: str = BINANCE_FAPI_BASE,
    risk_unit: float = 1.0,
    initial_equity: float = 10_000.0,
    fee_bps: float = 4.0,
) -> dict[str, Any]:
    """Run one v1.5 shared paper trading cycle with simulated broker fills."""
    try:
        from scripts.binance_trend_core.brokers import PaperBroker
        from scripts.binance_trend_core.execution import PaperIntentExecutionEngine
        from scripts.binance_trend_core.loop import TradingCycleConfig, run_trading_cycle
        from scripts.binance_trend_core.risk import FunctionRiskManager
        from scripts.binance_trend_core.signals import FunctionSignalEngine
        from scripts.binance_trend_core.strategy import TrendParticipationStrategy
    except ModuleNotFoundError:
        from binance_trend_core.brokers import PaperBroker
        from binance_trend_core.execution import PaperIntentExecutionEngine
        from binance_trend_core.loop import TradingCycleConfig, run_trading_cycle
        from binance_trend_core.risk import FunctionRiskManager
        from binance_trend_core.signals import FunctionSignalEngine
        from binance_trend_core.strategy import TrendParticipationStrategy

    selected_symbols = [validate_symbol(symbol) for symbol in symbols]
    interval = validate_interval(interval)
    candles_by_symbol = {
        symbol: fetch_klines(symbol, interval, limit, base_url)
        for symbol in selected_symbols
    }
    broker = PaperBroker(initial_equity=initial_equity, fee_bps=fee_bps)
    cycle = run_trading_cycle(
        TradingCycleConfig(
            symbols=selected_symbols,
            interval=interval,
            limit=limit,
            candles_by_symbol=candles_by_symbol,
            strategy_version=strategy_version,
            config_version=config_version,
        ),
        broker=broker,
        signal_engine=FunctionSignalEngine(
            decide_fn=lambda candles, symbol, interval, **kwargs: decide(
                candles,
                symbol=symbol,
                interval=interval,
                risk_unit=risk_unit,
                market_context=None,
            )
        ),
        strategy=TrendParticipationStrategy(),
        risk_manager=FunctionRiskManager(),
        execution_engine=PaperIntentExecutionEngine(),
    )
    return _attach_cycle_runtime_record_receipt(
        cycle,
        runtime_record_file=runtime_record_file,
        save_runtime_record=save_runtime_record,
        change_mode="paper",
    )


def verify_position_protection(account_snapshot: dict[str, Any], symbols: Iterable[str] | None = None) -> dict[str, Any]:
    """Verify non-zero long testnet positions have safe SL and TP protection.

    When symbols is provided, scope the result to that cycle's symbol group so a
    BTC-only cycle does not report unrelated ETH/SOL protection gaps from the
    account-wide signed snapshot.
    """
    positions = account_snapshot.get("positions", []) if isinstance(account_snapshot, dict) else []
    open_orders = account_snapshot.get("open_orders", []) if isinstance(account_snapshot, dict) else []
    open_algo_orders = account_snapshot.get("open_algo_orders", []) if isinstance(account_snapshot, dict) else []
    wanted_symbols = {validate_symbol(symbol) for symbol in symbols} if symbols is not None else None
    order_rows = []
    if isinstance(open_orders, list):
        order_rows.extend(open_orders)
    if isinstance(open_algo_orders, list):
        order_rows.extend(open_algo_orders)
    by_symbol: dict[str, dict[str, Any]] = {}
    ignored_short_symbols: list[str] = []
    for item in positions if isinstance(positions, list) else []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        try:
            amount = float(item.get("positionAmt") or item.get("position_amt") or item.get("size") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        if wanted_symbols is not None and symbol not in wanted_symbols:
            continue
        if abs(amount) <= 1e-12:
            continue
        if amount < 0:
            ignored_short_symbols.append(symbol)
            continue
        has_stop = False
        take_profit_coverage = 0.0
        target_exposure = abs(amount)
        for order in order_rows:
            if not isinstance(order, dict) or str(order.get("symbol") or "").upper() != symbol:
                continue
            order_type = str(order.get("type") or order.get("origType") or order.get("orderType") or "").upper()
            if order_type in {"STOP", "STOP_MARKET"} and _is_safe_long_snapshot_protection(order, "stop_loss", target_exposure):
                has_stop = True
            if order_type in {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"} and _is_safe_long_snapshot_take_profit(order):
                quantity = _optional_positive_number(order.get("origQty") or order.get("quantity") or order.get("executedQty"))
                if quantity is not None:
                    take_profit_coverage += min(quantity, target_exposure)
        has_take_profit = take_profit_coverage >= target_exposure * 0.999
        issues = []
        if not has_stop:
            issues.append("missing_stop_loss")
        if not has_take_profit:
            issues.append("missing_take_profit")
        by_symbol[symbol] = {
            "position_amt": amount,
            "has_stop_loss": has_stop,
            "has_take_profit": has_take_profit,
            "protected": not issues,
            "issues": issues,
        }
    unprotected = [symbol for symbol, item in by_symbol.items() if not item.get("protected")]
    return {
        "all_positions_protected": not unprotected,
        "unprotected_symbols": unprotected,
        "ignored_short_symbols": ignored_short_symbols,
        "symbols": by_symbol,
    }


def _is_safe_long_snapshot_protection(order: dict[str, Any], role: str, target_exposure: float) -> bool:
    if str(order.get("side") or "").upper() != "SELL":
        return False
    close_position = _boolish(order.get("closePosition") or order.get("close_position"))
    reduce_only = _boolish(order.get("reduceOnly") or order.get("reduce_only"))
    quantity = _optional_positive_number(order.get("origQty") or order.get("quantity") or order.get("executedQty"))
    covers_position = quantity is not None and quantity >= target_exposure * 0.999
    if role == "stop_loss":
        return close_position or (reduce_only and covers_position)
    if role == "take_profit":
        return _is_safe_long_snapshot_take_profit(order) and covers_position
    return False


def _is_safe_long_snapshot_take_profit(order: dict[str, Any]) -> bool:
    if str(order.get("side") or "").upper() != "SELL":
        return False
    if not _boolish(order.get("reduceOnly") or order.get("reduce_only")):
        return False
    return _optional_positive_number(order.get("origQty") or order.get("quantity") or order.get("executedQty")) is not None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _optional_positive_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def run_testnet_trading_cycle(
    symbols: Iterable[str],
    interval: str = "1h",
    limit: int = 240,
    runtime_record_file: str | os.PathLike[str] | None = None,
    save_runtime_record: bool = True,
    strategy_version: str = "ema50_ema200_atr_trend_testnet",
    config_version: str = "default",
    base_url: str = BINANCE_FAPI_BASE,
    risk_unit: float = 1.0,
    account_risk_fraction: float = 0.01,
    target_leverage: float = 2.0,
    testnet_base_url: str | None = None,
    dry_run: bool = True,
    max_order_notional: float = 1_000.0,
    max_symbol_exposure: float = 2_000.0,
    max_symbol_exposure_fraction: float | None = None,
    max_daily_loss: float = 100.0,
    max_order_count: int = 10,
    kill_switch: bool = False,
    testnet_http_client: Any | None = None,
    order_journal_path: str | os.PathLike[str] | None = None,
    refresh_exchange_rules: bool = True,
    sync_account_state: bool = False,
    track_order_lifecycle: bool = False,
) -> dict[str, Any]:
    """Run one shared trading cycle with Binance USDS-M futures testnet adapter.

    Defaults to dry-run: it builds auditable testnet execution events but does not
    sign or submit HTTP requests unless the caller explicitly disables dry-run.
    """
    try:
        from scripts.binance_trend_core.brokers import BinanceTestnetBroker, TestnetRiskLimits, resolve_binance_testnet_credentials
        from scripts.binance_trend_core.execution import PositionReconciliationExecutionEngine
        from scripts.binance_trend_core.loop import TradingCycleConfig, run_trading_cycle
        from scripts.binance_trend_core.risk import FunctionRiskManager
        from scripts.binance_trend_core.signals import FunctionSignalEngine
        from scripts.binance_trend_core.strategy import TrendParticipationStrategy
    except ModuleNotFoundError:
        from binance_trend_core.brokers import BinanceTestnetBroker, TestnetRiskLimits, resolve_binance_testnet_credentials
        from binance_trend_core.execution import PositionReconciliationExecutionEngine
        from binance_trend_core.loop import TradingCycleConfig, run_trading_cycle
        from binance_trend_core.risk import FunctionRiskManager
        from binance_trend_core.signals import FunctionSignalEngine
        from binance_trend_core.strategy import TrendParticipationStrategy

    selected_symbols = [validate_symbol(symbol) for symbol in symbols]
    interval = validate_interval(interval)
    candles_by_symbol = {
        symbol: fetch_klines(symbol, interval, limit, base_url)
        for symbol in selected_symbols
    }
    broker_kwargs: dict[str, Any] = {
        "credentials": resolve_binance_testnet_credentials(),
        "dry_run": dry_run,
        "risk_limits": TestnetRiskLimits.from_config(
            {
                "max_order_notional": max_order_notional,
                "max_symbol_exposure": max_symbol_exposure,
                "max_daily_loss": max_daily_loss,
                "max_order_count": max_order_count,
                "kill_switch": kill_switch,
            }
        ),
    }
    if testnet_http_client is not None:
        broker_kwargs["http_client"] = testnet_http_client
    if order_journal_path is not None:
        broker_kwargs["order_journal_path"] = str(order_journal_path)
    if testnet_base_url:
        broker_kwargs["base_url"] = testnet_base_url
    broker = BinanceTestnetBroker(**broker_kwargs)
    if refresh_exchange_rules:
        broker.refresh_exchange_rules(selected_symbols)
    account_sync_before = broker.fetch_signed_account_snapshot() if (sync_account_state or not dry_run) and selected_symbols else None
    if account_sync_before is not None:
        broker.load_positions_from_account_snapshot(account_sync_before)
    cycle = run_trading_cycle(
        TradingCycleConfig(
            symbols=selected_symbols,
            interval=interval,
            limit=limit,
            candles_by_symbol=candles_by_symbol,
            strategy_version=strategy_version,
            config_version=config_version,
        ),
        broker=broker,
        signal_engine=FunctionSignalEngine(
            decide_fn=lambda candles, symbol, interval, **kwargs: apply_account_risk_sizing_to_signal(
                decide(
                    candles,
                    symbol=symbol,
                    interval=interval,
                    risk_unit=risk_unit,
                    market_context=None,
                ),
                account_sync_before,
                account_risk_fraction=account_risk_fraction,
                target_leverage=target_leverage,
                max_order_notional=max_order_notional,
                max_symbol_exposure=max_symbol_exposure,
                max_symbol_exposure_fraction=max_symbol_exposure_fraction,
            ) if account_sync_before is not None else decide(
                candles,
                symbol=symbol,
                interval=interval,
                risk_unit=risk_unit,
                market_context=None,
            )
        ),
        strategy=TrendParticipationStrategy(),
        risk_manager=FunctionRiskManager(),
        execution_engine=PositionReconciliationExecutionEngine(min_delta=0.001),
    )
    if track_order_lifecycle and not dry_run:
        lifecycle_events = []
        for fill in cycle.get("fills", []):
            client_order_id = fill.get("client_order_id") if isinstance(fill, dict) else None
            symbol = fill.get("symbol") if isinstance(fill, dict) else None
            status = fill.get("status") if isinstance(fill, dict) else None
            instruction = fill.get("instruction") if isinstance(fill, dict) else None
            metadata = instruction.get("metadata") if isinstance(instruction, dict) else {}
            if not client_order_id or not symbol or status not in {"submitted", "submitted_confirmed"}:
                continue
            if isinstance(metadata, dict) and metadata.get("protective_order"):
                continue
            lifecycle_events.append(
                broker.track_order_lifecycle(
                    str(symbol),
                    str(client_order_id),
                    reference_price=float(fill.get("reference_price") or 0.0),
                )
            )
        cycle["testnet_order_lifecycle"] = lifecycle_events
        cycle["runtime_record"].setdefault("execution_events", {})["testnet_order_lifecycle"] = {
            "tracked_order_count": len(lifecycle_events),
            "filled_order_count": sum(1 for event in lifecycle_events if event.get("lifecycle_state") == "filled"),
            "net_pnl": round(sum(float(event.get("fills_summary", {}).get("net_pnl", 0.0)) for event in lifecycle_events), 8),
        }
    if sync_account_state and selected_symbols:
        account_sync_after = broker.fetch_signed_account_snapshot()
        open_orders = account_sync_after.get("open_orders", []) if isinstance(account_sync_after, dict) else []
        reconciliation = broker.reconcile_open_orders(account_sync_after)
        protection_verification = verify_position_protection(account_sync_after, selected_symbols)
        cycle["testnet_account_sync"] = {
            "environment": "testnet",
            "before": account_sync_before,
            "after": account_sync_after,
            "reconciliation": reconciliation,
            "protection_verification": protection_verification,
        }
        cycle["runtime_record"].setdefault("execution_events", {})["testnet_account_sync"] = {
            "before_open_orders_count": len(account_sync_before.get("open_orders", [])) if isinstance(account_sync_before, dict) else 0,
            "after_open_orders_count": len(open_orders) if isinstance(open_orders, list) else 0,
            "unknown_local_count": reconciliation.get("unknown_local_count", 0),
            "matched_open_order_client_ids": reconciliation.get("matched_open_order_client_ids", []),
            "missing_unknown_client_ids": reconciliation.get("missing_unknown_client_ids", []),
            "all_positions_protected": protection_verification.get("all_positions_protected", False),
            "unprotected_symbols": protection_verification.get("unprotected_symbols", []),
        }
    return _attach_cycle_runtime_record_receipt(
        cycle,
        runtime_record_file=runtime_record_file,
        save_runtime_record=save_runtime_record,
        change_mode="testnet",
    )


def _attach_cycle_runtime_record_receipt(
    cycle: dict[str, Any],
    *,
    runtime_record_file: str | os.PathLike[str] | None,
    save_runtime_record: bool,
    change_mode: str,
) -> dict[str, Any]:
    cycle["runtime_record_saved"] = False
    cycle["runtime_record_change"] = {
        "mode": change_mode,
        **now_stamps(),
        "schema_version": cycle["runtime_record"].get("schema_version"),
        "environment": cycle.get("environment"),
        "records_written": 0,
        "append_only": True,
    }
    if runtime_record_file and save_runtime_record:
        receipt = append_runtime_record(runtime_record_file, cycle["runtime_record"])
        cycle["runtime_record_saved"] = True
        cycle["runtime_record_file"] = receipt["path"]
        cycle["runtime_record_change"].update(receipt)
    elif runtime_record_file:
        cycle["runtime_record_file"] = str(runtime_record_file)
        cycle["runtime_record_change"]["path"] = str(runtime_record_file)
    return cycle


def replay_runtime_evidence(
    runtime_record_file: str | os.PathLike[str],
    max_drawdown_worsening_limit: float = 0.03,
) -> dict[str, Any]:
    """Run v1.6 strategy-evolution diagnostics from recorded runtime JSONL only."""
    try:
        from scripts.binance_trend_core.evolution import compare_runtime_strategy_variants, load_runtime_records
    except ModuleNotFoundError:
        from binance_trend_core.evolution import compare_runtime_strategy_variants, load_runtime_records

    records = load_runtime_records(Path(runtime_record_file))
    return compare_runtime_strategy_variants(
        records,
        max_drawdown_worsening_limit=max_drawdown_worsening_limit,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Binance USDS futures paper trend decision")
    parser.add_argument("--symbol", default="BTCUSDT", help="USDS futures symbol in configured universe")
    parser.add_argument("--interval", default="1h", help="K-line interval; must be >= 1h")
    parser.add_argument("--intervals", help="Comma-separated K-line intervals for v0.4 batch scan only, e.g. 1h,4h,1d")
    parser.add_argument("--limit", type=int, default=240, help="K-line count, 200-1500")
    parser.add_argument("--context-limit", type=int, default=30, help="Public factor sample count, 2-500")
    parser.add_argument("--risk-unit", type=float, default=1.0, help="Paper position sizing unit")
    parser.add_argument("--base-url", default=BINANCE_FAPI_BASE, help="Override Binance Futures base URL for tests")
    parser.add_argument("--no-context", action="store_true", help="Disable v0.2 public factor context fetch")
    parser.add_argument("--symbols", help="Comma-separated symbols for v0.3 batch scan; omit for single-symbol mode")
    parser.add_argument("--all-symbols", action="store_true", help="Scan the full configured universe")
    parser.add_argument("--top", type=int, default=5, help="Top N trends to include in v0.3 scan summary")
    parser.add_argument("--portfolio-risk-budget", type=float, help="Optional v0.5 total paper risk-unit budget for scan allocation")
    parser.add_argument("--max-symbol-risk", type=float, help="Optional v0.5 per-symbol paper risk-unit cap for scan allocation")
    parser.add_argument("--state-file", help="Optional v0.7 paper scan state JSON path; scan mode only")
    parser.add_argument("--no-save-state", action="store_true", help="Compute v0.7 state_change without writing --state-file")
    parser.add_argument("--lifecycle-file", help="Optional v1.1 paper lifecycle JSON path; scan mode only")
    parser.add_argument("--no-save-lifecycle", action="store_true", help="Compute v1.1 lifecycle_change without writing --lifecycle-file")
    parser.add_argument("--telegram-brief", action="store_true", help="Emit a compact v0.8 Telegram briefing instead of full JSON; scan mode only")
    parser.add_argument("--backtest", action="store_true", help="Run v0.9 paper-only historical backtest instead of current scan/decision")
    parser.add_argument("--compare-refinements", action="store_true", help="Run v1.0 paper-only evidence-based strategy refinement comparison")
    parser.add_argument("--run-paper-cycle", action="store_true", help="Run v1.5 shared trading loop with PaperBroker simulated fills")
    parser.add_argument("--run-testnet-cycle", action="store_true", help="Run v1.7 shared trading loop with Binance futures testnet adapter")
    parser.add_argument("--replay-runtime-evidence", action="store_true", help="Run v1.6 strategy evolution replay from recorded runtime evidence JSONL")
    parser.add_argument("--analyze-closed-orders", action="store_true", help="Analyze ended testnet order journal records into closed_order.v1 strategy-evolution evidence")
    parser.add_argument("--daily-analyze-runtime", action="store_true", help="Run read-only daily runtime/order-journal diagnosis without trading side effects")
    parser.add_argument("--analysis-window-hours", type=int, default=24, help="Lookback window for daily runtime analysis")
    parser.add_argument("--initial-equity", type=float, default=10_000.0, help="Paper initial equity per symbol for backtest/cycle")
    parser.add_argument("--fee-bps", type=float, default=4.0, help="Paper transaction fee in basis points for backtest turnover")
    parser.add_argument("--max-position-size", type=float, default=1.0, help="Max paper long exposure per symbol for backtest")
    parser.add_argument("--max-drawdown-worsening-limit", type=float, default=0.03, help="Max allowed absolute drawdown worsening for v1.0 refinement candidates")
    parser.add_argument("--runtime-record-file", help="Optional v1.3 append-only runtime evidence JSONL path; scan mode only")
    parser.add_argument("--runtime-environment", default="paper", choices=["paper"], help="Runtime evidence environment for scan evidence; scan supports paper only")
    parser.add_argument("--testnet-base-url", help="Override Binance Futures testnet base URL for tests; must stay on testnet host")
    parser.add_argument("--testnet-dry-run", action="store_true", help="For --run-testnet-cycle, build testnet events without signing/submitting; default safe behavior")
    parser.add_argument("--testnet-submit-signed", action="store_true", help="For --run-testnet-cycle, submit signed testnet orders; never mainnet/live")
    parser.add_argument("--testnet-max-order-notional", type=float, default=1_000.0, help="Max testnet order notional before rejection")
    parser.add_argument("--testnet-max-symbol-exposure", type=float, default=2_000.0, help="Max testnet symbol exposure before rejection")
    parser.add_argument("--testnet-max-symbol-exposure-fraction", type=float, help="Account-equity fraction cap for desired testnet symbol exposure, e.g. 0.10")
    parser.add_argument("--testnet-max-daily-loss", type=float, default=100.0, help="Max testnet daily loss before rejection")
    parser.add_argument("--testnet-max-order-count", type=int, default=10, help="Max testnet accepted order count per cycle")
    parser.add_argument("--account-risk-fraction", type=float, default=0.01, help="For testnet cycle account sizing: fraction of account equity risked to ATR stop distance")
    parser.add_argument("--target-leverage", type=float, default=2.0, help="For testnet cycle account sizing: target leverage cap used to derive max notional")
    parser.add_argument("--testnet-kill-switch", action="store_true", help="Reject all testnet execution before signing/submission")
    parser.add_argument("--testnet-risk-config-file", help="Optional JSON testnet risk config; supports max_* limits and kill_switch")
    parser.add_argument("--testnet-order-journal-file", help="Append-only JSONL order journal for signed testnet submissions")
    parser.add_argument("--testnet-sync-account-state", action="store_true", help="Fetch signed testnet account/position/open-order snapshots before and after the cycle")
    parser.add_argument("--testnet-track-order-lifecycle", action="store_true", help="After signed testnet submission, poll order/userTrades and attach lifecycle, PnL, fee, and slippage evidence")
    parser.add_argument("--strategy-version", default="ema50_ema200_atr_trend_paper", help="Strategy version label stored in v1.3 runtime evidence")
    parser.add_argument("--config-version", default="default", help="Config version label stored in v1.3 runtime evidence")
    parser.add_argument("--no-save-runtime-record", action="store_true", help="Build runtime evidence without appending --runtime-record-file")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        selected_modes = [bool(args.compare_refinements), bool(args.backtest), bool(args.run_paper_cycle), bool(args.run_testnet_cycle), bool(args.replay_runtime_evidence), bool(args.analyze_closed_orders), bool(args.daily_analyze_runtime)]
        if sum(selected_modes) > 1:
            raise ValueError("choose only one mode: --compare-refinements, --backtest, --run-paper-cycle, --run-testnet-cycle, --replay-runtime-evidence, --analyze-closed-orders, or --daily-analyze-runtime")
        if args.daily_analyze_runtime:
            if not args.runtime_record_file:
                raise ValueError("--daily-analyze-runtime requires --runtime-record-file")
            if not args.testnet_order_journal_file:
                raise ValueError("--daily-analyze-runtime requires --testnet-order-journal-file")
            if args.state_file:
                raise ValueError("--state-file is for scan state only; omit it for --daily-analyze-runtime")
            if args.lifecycle_file:
                raise ValueError("--lifecycle-file is for scan lifecycle only; omit it for --daily-analyze-runtime")
            if args.telegram_brief:
                raise ValueError("--telegram-brief is for scan briefings only; omit it for --daily-analyze-runtime")
            analysis = analyze_daily_runtime(args.runtime_record_file, args.testnet_order_journal_file, window_hours=args.analysis_window_hours)
            print(json.dumps({"ok": not bool(analysis["errors_count"]), "daily_runtime_analysis": analysis}, ensure_ascii=False, indent=2))
            return 0 if not analysis["errors_count"] else 1
        if args.analyze_closed_orders:
            if not args.testnet_order_journal_file:
                raise ValueError("--analyze-closed-orders requires --testnet-order-journal-file")
            if args.runtime_record_file:
                raise ValueError("--runtime-record-file is not used by --analyze-closed-orders")
            if args.state_file:
                raise ValueError("--state-file is for scan state only; omit it for --analyze-closed-orders")
            if args.lifecycle_file:
                raise ValueError("--lifecycle-file is for scan lifecycle only; omit it for --analyze-closed-orders")
            if args.telegram_brief:
                raise ValueError("--telegram-brief is for scan briefings only; omit it for --analyze-closed-orders")
            analysis = analyze_closed_orders(args.testnet_order_journal_file)
            print(json.dumps({"ok": not bool(analysis["errors_count"]), "closed_order_analysis": analysis}, ensure_ascii=False, indent=2))
            return 0 if not analysis["errors_count"] else 1
        if args.replay_runtime_evidence:
            if not args.runtime_record_file:
                raise ValueError("--replay-runtime-evidence requires --runtime-record-file")
            if args.state_file:
                raise ValueError("--state-file is for scan state only; omit it for --replay-runtime-evidence")
            if args.lifecycle_file:
                raise ValueError("--lifecycle-file is for scan lifecycle only; omit it for --replay-runtime-evidence")
            if args.telegram_brief:
                raise ValueError("--telegram-brief is for scan briefings only; omit it for --replay-runtime-evidence")
            evolution = replay_runtime_evidence(
                args.runtime_record_file,
                max_drawdown_worsening_limit=args.max_drawdown_worsening_limit,
            )
            print(json.dumps({"ok": not bool(evolution["errors_count"]), "runtime_evolution": evolution}, ensure_ascii=False, indent=2))
            return 0 if not evolution["errors_count"] else 1

        if args.compare_refinements:
            if args.backtest:
                raise ValueError("choose only one mode: --compare-refinements or --backtest")
            if args.state_file:
                raise ValueError("--state-file is for scan state only; omit it for --compare-refinements")
            if args.lifecycle_file:
                raise ValueError("--lifecycle-file is for scan lifecycle only; omit it for --compare-refinements")
            if args.telegram_brief:
                raise ValueError("--telegram-brief is for scan briefings only; omit it for --compare-refinements")
            if args.runtime_record_file:
                raise ValueError("--runtime-record-file is for scan runtime evidence only; omit it for --compare-refinements")
            if args.all_symbols:
                symbols = None
            elif args.symbols:
                symbols = [part.strip().upper() for part in args.symbols.split(",") if part.strip()]
            else:
                symbols = [args.symbol.upper()]
            refinement = compare_strategy_variants(
                symbols=symbols,
                interval=args.interval,
                limit=args.limit,
                initial_equity=args.initial_equity,
                fee_bps=args.fee_bps,
                base_url=args.base_url,
                max_drawdown_worsening_limit=args.max_drawdown_worsening_limit,
            )
            print(json.dumps({"ok": not bool(refinement["errors_count"]), "refinement": refinement}, ensure_ascii=False, indent=2))
            return 0 if not refinement["errors_count"] else 1

        if args.backtest:
            if args.state_file:
                raise ValueError("--state-file is for scan state only; omit it for --backtest")
            if args.lifecycle_file:
                raise ValueError("--lifecycle-file is for scan lifecycle only; omit it for --backtest")
            if args.telegram_brief:
                raise ValueError("--telegram-brief is for scan briefings only; omit it for --backtest")
            if args.runtime_record_file:
                raise ValueError("--runtime-record-file is for scan runtime evidence only; omit it for --backtest")
            if args.all_symbols:
                symbols = None
            elif args.symbols:
                symbols = [part.strip().upper() for part in args.symbols.split(",") if part.strip()]
            else:
                symbols = [args.symbol.upper()]
            backtest = backtest_symbols(
                symbols=symbols,
                interval=args.interval,
                limit=args.limit,
                initial_equity=args.initial_equity,
                fee_bps=args.fee_bps,
                max_position_size=args.max_position_size,
                risk_unit=args.risk_unit,
                base_url=args.base_url,
            )
            print(json.dumps({"ok": not bool(backtest["errors"]), "backtest": backtest}, ensure_ascii=False, indent=2))
            return 0 if not backtest["errors"] else 1

        if args.run_paper_cycle:
            if args.state_file:
                raise ValueError("--state-file is for scan state only; omit it for --run-paper-cycle")
            if args.lifecycle_file:
                raise ValueError("--lifecycle-file is for scan lifecycle only; omit it for --run-paper-cycle")
            if args.telegram_brief:
                raise ValueError("--telegram-brief is for scan briefings only; omit it for --run-paper-cycle")
            if args.intervals:
                raise ValueError("--run-paper-cycle uses one --interval; omit --intervals")
            if args.runtime_environment != "paper":
                raise ValueError("--run-paper-cycle supports --runtime-environment paper only")
            if args.all_symbols:
                symbols = list(DEFAULT_SYMBOLS)
            elif args.symbols:
                symbols = [part.strip().upper() for part in args.symbols.split(",") if part.strip()]
            else:
                symbols = [args.symbol.upper()]
            cycle = run_paper_trading_cycle(
                symbols=symbols,
                interval=args.interval,
                limit=args.limit,
                runtime_record_file=args.runtime_record_file,
                save_runtime_record=not args.no_save_runtime_record,
                strategy_version=args.strategy_version,
                config_version=args.config_version,
                base_url=args.base_url,
                risk_unit=args.risk_unit,
                initial_equity=args.initial_equity,
                fee_bps=args.fee_bps,
            )
            print(json.dumps({"ok": not bool(cycle["errors"]), "paper_cycle": cycle}, ensure_ascii=False, indent=2))
            return 0 if not cycle["errors"] else 1

        if args.run_testnet_cycle:
            if args.state_file:
                raise ValueError("--state-file is for scan state only; omit it for --run-testnet-cycle")
            if args.lifecycle_file:
                raise ValueError("--lifecycle-file is for scan lifecycle only; omit it for --run-testnet-cycle")
            if args.telegram_brief:
                raise ValueError("--telegram-brief is for scan briefings only; omit it for --run-testnet-cycle")
            if args.intervals:
                raise ValueError("--run-testnet-cycle uses one --interval; omit --intervals")
            if args.runtime_environment not in {"paper", "testnet"}:
                raise ValueError("unsupported --runtime-environment for --run-testnet-cycle")
            if args.testnet_dry_run and args.testnet_submit_signed:
                raise ValueError("choose only one: --testnet-dry-run or --testnet-submit-signed")
            if args.all_symbols:
                symbols = list(DEFAULT_SYMBOLS)
            elif args.symbols:
                symbols = [part.strip().upper() for part in args.symbols.split(",") if part.strip()]
            else:
                symbols = [args.symbol.upper()]
            try:
                from scripts.binance_trend_core.brokers import TestnetRiskLimits
            except ModuleNotFoundError:
                from binance_trend_core.brokers import TestnetRiskLimits
            risk_config: dict[str, Any] = {
                "max_order_notional": args.testnet_max_order_notional,
                "max_symbol_exposure": args.testnet_max_symbol_exposure,
                "max_daily_loss": args.testnet_max_daily_loss,
                "max_order_count": args.testnet_max_order_count,
                "kill_switch": args.testnet_kill_switch,
            }
            max_symbol_exposure_fraction = args.testnet_max_symbol_exposure_fraction
            if args.testnet_risk_config_file:
                loaded_risk_config = json.loads(Path(args.testnet_risk_config_file).read_text(encoding="utf-8"))
                if not isinstance(loaded_risk_config, dict):
                    raise ValueError("--testnet-risk-config-file must contain a JSON object")
                risk_config.update(loaded_risk_config)
                if "max_symbol_exposure_fraction" in loaded_risk_config:
                    max_symbol_exposure_fraction = float(loaded_risk_config["max_symbol_exposure_fraction"])
            risk_limits = TestnetRiskLimits.from_config(
                risk_config,
                kill_switch_env="BINANCE_TESTNET_KILL_SWITCH",
                kill_switch_file="state/binance-usds-futures-testnet.kill",
            )
            cycle = run_testnet_trading_cycle(
                symbols=symbols,
                interval=args.interval,
                limit=args.limit,
                runtime_record_file=args.runtime_record_file,
                save_runtime_record=not args.no_save_runtime_record,
                strategy_version=args.strategy_version,
                config_version=args.config_version,
                base_url=args.base_url,
                risk_unit=args.risk_unit,
                account_risk_fraction=args.account_risk_fraction,
                target_leverage=args.target_leverage,
                testnet_base_url=args.testnet_base_url,
                dry_run=not args.testnet_submit_signed,
                max_order_notional=risk_limits.max_order_notional,
                max_symbol_exposure=risk_limits.max_symbol_exposure,
                max_symbol_exposure_fraction=max_symbol_exposure_fraction,
                max_daily_loss=risk_limits.max_daily_loss,
                max_order_count=risk_limits.max_order_count,
                kill_switch=risk_limits.kill_switch,
                order_journal_path=args.testnet_order_journal_file,
                sync_account_state=args.testnet_sync_account_state,
                track_order_lifecycle=args.testnet_track_order_lifecycle,
            )
            print(json.dumps({"ok": not bool(cycle["errors"]), "testnet_risk_limits": risk_limits.sanitized_summary(), "testnet_cycle": cycle}, ensure_ascii=False, indent=2))
            return 0 if not cycle["errors"] else 1

        if args.all_symbols or args.symbols:
            symbols = None if args.all_symbols else [part.strip().upper() for part in args.symbols.split(",") if part.strip()]
            intervals = None if not args.intervals else [part.strip() for part in args.intervals.split(",") if part.strip()]
            scan = scan_symbols(
                symbols=symbols,
                interval=args.interval,
                intervals=intervals,
                limit=args.limit,
                context_limit=args.context_limit,
                risk_unit=args.risk_unit,
                base_url=args.base_url,
                include_context=not args.no_context,
                top=args.top,
                portfolio_risk_budget=args.portfolio_risk_budget,
                max_symbol_risk=args.max_symbol_risk,
            )
            if args.state_file:
                scan = apply_paper_state(scan, args.state_file, save_state=not args.no_save_state)
            if args.lifecycle_file:
                scan = apply_paper_lifecycle(scan, args.lifecycle_file, save_lifecycle=not args.no_save_lifecycle)
            if args.runtime_record_file:
                scan = apply_runtime_record(
                    scan,
                    args.runtime_record_file,
                    environment=args.runtime_environment,
                    strategy_version=args.strategy_version,
                    config_version=args.config_version,
                    save_runtime_record=not args.no_save_runtime_record,
                )
            if args.telegram_brief:
                print(build_telegram_briefing_zh(scan))
            else:
                print(json.dumps({"ok": not bool(scan["errors"]), "scan": scan}, ensure_ascii=False, indent=2))
            return 0 if not scan["errors"] else 1

        if args.state_file:
            raise ValueError("--state-file requires scan mode: use --all-symbols or --symbols")
        if args.lifecycle_file:
            raise ValueError("--lifecycle-file requires scan mode: use --all-symbols or --symbols")
        if args.telegram_brief:
            raise ValueError("--telegram-brief requires scan mode: use --all-symbols or --symbols")
        if args.runtime_record_file:
            raise ValueError("--runtime-record-file requires scan mode: use --all-symbols or --symbols")
        candles = fetch_klines(args.symbol, args.interval, args.limit, args.base_url)
        market_context = None if args.no_context else fetch_market_context(
            args.symbol,
            args.interval,
            args.context_limit,
            args.base_url,
        )
        decision = decide(candles, args.symbol, args.interval, args.risk_unit, market_context)
    except Exception as exc:  # CLI should return structured failure for cron/logging.
        print(json.dumps({"ok": False, "error": sanitize_error_message(exc), **now_stamps()}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "decision": decision}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
