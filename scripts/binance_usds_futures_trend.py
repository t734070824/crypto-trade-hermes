#!/usr/bin/env python3
"""Binance USDS futures trend-following paper decision helper.

Uses only free public Binance Futures data. It does not place orders.
All generated timestamps explicitly include UTC and Beijing time (UTC+8).
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
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
    for decision in decisions:
        symbol = str(decision.get("symbol", ""))
        rank_score = float(decision.get("rank_score") or 0.0)
        position_size = float(decision.get("position_size") or 0.0)
        if decision.get("action") == "hold_long" and rank_score > 0 and position_size > 0:
            eligible.append(decision)
        elif symbol:
            skipped_symbols.append(symbol)

    ranked = sorted(eligible, key=lambda item: (float(item.get("rank_score") or 0.0), item.get("symbol", "")), reverse=True)
    remaining = float(total_risk_budget)
    allocations: list[dict[str, Any]] = []
    for decision in ranked:
        symbol = str(decision.get("symbol", ""))
        if remaining <= 1e-12:
            if symbol:
                skipped_symbols.append(symbol)
            continue
        desired = min(float(decision.get("position_size") or 0.0), float(max_symbol_risk), remaining)
        if desired <= 0:
            if symbol:
                skipped_symbols.append(symbol)
            continue
        paper_risk_units = round(desired, 8)
        allocations.append(
            {
                "symbol": symbol,
                "paper_risk_units": paper_risk_units,
                "rank_score": decision.get("rank_score", 0.0),
                "position_size": decision.get("position_size", 0.0),
                "ranking_bucket": decision.get("ranking_bucket"),
                "timeframe_agreement_score": decision.get("timeframe_agreement_score"),
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
    }


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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
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
            print(json.dumps({"ok": not bool(scan["errors"]), "scan": scan}, ensure_ascii=False, indent=2))
            return 0 if not scan["errors"] else 1

        candles = fetch_klines(args.symbol, args.interval, args.limit, args.base_url)
        market_context = None if args.no_context else fetch_market_context(
            args.symbol,
            args.interval,
            args.context_limit,
            args.base_url,
        )
        decision = decide(candles, args.symbol, args.interval, args.risk_unit, market_context)
    except Exception as exc:  # CLI should return structured failure for cron/logging.
        print(json.dumps({"ok": False, "error": str(exc), **now_stamps()}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "decision": decision}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
