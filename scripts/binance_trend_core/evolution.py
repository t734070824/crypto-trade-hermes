"""Strategy evolution replay from recorded runtime evidence.

This module evaluates candidate paper strategy variants against identical captured
runtime records. It never fetches fresh market data and never promotes defaults.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

BEIJING = timezone(timedelta(hours=8), name="UTC+8")
REQUIRED_RUNTIME_FIELDS = ("schema_version", "environment", "generated_at_utc", "generated_at_beijing")
_SHORT_INTERVALS = {"1m", "3m", "5m", "10m", "15m", "30m"}
_ALLOWED_INTERVALS = {"1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}


@dataclass(frozen=True)
class RuntimeVariantConfig:
    name: str
    description: str
    exposure_multiplier: float


DEFAULT_RUNTIME_VARIANTS = (
    RuntimeVariantConfig(
        name="baseline",
        description="recorded runtime baseline exposure from paper/testnet/live evidence schema",
        exposure_multiplier=1.0,
    ),
    RuntimeVariantConfig(
        name="trend_hold_bias",
        description="diagnostic candidate that keeps stronger participation in recorded hold_long trends",
        exposure_multiplier=1.15,
    ),
    RuntimeVariantConfig(
        name="risk_capped",
        description="diagnostic candidate that caps participation to reduce drawdown",
        exposure_multiplier=0.75,
    ),
)


def now_stamps() -> dict[str, str]:
    now_utc = datetime.now(UTC).replace(microsecond=0)
    return {
        "generated_at_utc": now_utc.isoformat(),
        "generated_at_beijing": now_utc.astimezone(BEIJING).isoformat(),
    }


def load_runtime_records(path: str | Path) -> list[dict[str, Any]]:
    """Load and validate append-only runtime evidence JSONL records."""
    runtime_path = Path(path)
    records: list[dict[str, Any]] = []
    with runtime_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSONL runtime record: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"line {line_number}: runtime record must be a JSON object")
            _validate_runtime_record(record, line_number=line_number)
            records.append(record)
    if not records:
        raise ValueError("runtime evidence file contains no records")
    return records


def build_runtime_replay_dataset(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic replay dataset from already captured runtime inputs."""
    validated = [_validate_runtime_record(dict(record), line_number=index) for index, record in enumerate(records, start=1)]
    if not validated:
        raise ValueError("runtime replay requires at least one record")
    replay_inputs = [_captured_input(record) for record in validated]
    fingerprint = _fingerprint(replay_inputs)
    symbols = sorted({symbol for record in validated for symbol in _symbols(record)})
    intervals = sorted({interval for record in validated for interval in _intervals(record)})
    environments = sorted({str(record.get("environment")) for record in validated})
    return {
        "records": validated,
        "records_loaded": len(validated),
        "captured_inputs": replay_inputs,
        "captured_input_fingerprint": fingerprint,
        "symbols": symbols,
        "intervals": intervals,
        "environments": environments,
    }


def compare_runtime_strategy_variants(
    records: Iterable[dict[str, Any]],
    *,
    max_drawdown_worsening_limit: float = 0.03,
) -> dict[str, Any]:
    """Replay candidate variants on identical runtime evidence and report diagnostics."""
    if max_drawdown_worsening_limit < 0:
        raise ValueError("max_drawdown_worsening_limit must be non-negative")
    dataset = build_runtime_replay_dataset(records)
    variants: list[dict[str, Any]] = []
    baseline_score = 0.0
    baseline_drawdown = 0.0
    baseline_metrics: dict[str, Any] | None = None

    for config in DEFAULT_RUNTIME_VARIANTS:
        metrics = _runtime_variant_metrics(dataset["records"], config.exposure_multiplier)
        score = _runtime_evidence_score(metrics)
        eligible = True
        guardrail_flags: list[str] = []
        if config.name == "baseline":
            baseline_score = score
            baseline_drawdown = abs(float(metrics.get("max_drawdown", 0.0)))
            baseline_metrics = metrics
        else:
            candidate_drawdown = abs(float(metrics.get("max_drawdown", 0.0)))
            if candidate_drawdown > baseline_drawdown + max_drawdown_worsening_limit:
                eligible = False
                guardrail_flags.append("drawdown_guardrail")
        variants.append(
            {
                "variant": config.name,
                "description": config.description,
                "mode": "paper",
                "exposure_multiplier": round(config.exposure_multiplier, 8),
                "metrics": metrics,
                "evidence_score": score,
                "eligible": eligible,
                "guardrail_flags": guardrail_flags,
                "captured_input_fingerprint": dataset["captured_input_fingerprint"],
                "selected": False,
            }
        )

    selected_index = 0
    for index, item in enumerate(variants[1:], start=1):
        if item["eligible"] and float(item["evidence_score"]) > baseline_score:
            if float(item["evidence_score"]) > float(variants[selected_index]["evidence_score"]):
                selected_index = index
    variants[selected_index]["selected"] = True

    report: dict[str, Any] = {
        "mode": "paper",
        **now_stamps(),
        "strategy": "runtime_evidence_replay_diagnostic",
        "records_loaded": dataset["records_loaded"],
        "symbols": dataset["symbols"],
        "intervals": dataset["intervals"],
        "environments": dataset["environments"],
        "captured_input_fingerprint": dataset["captured_input_fingerprint"],
        "baseline_variant": "baseline",
        "baseline_metrics": baseline_metrics or {},
        "selected_variant": variants[selected_index]["variant"],
        "selection_policy": {
            "score": "return_proxy - abs(max_drawdown)*0.5 - turnover*0.01 - premature_exit_rate*0.05",
            "candidate_must_beat_baseline_score": True,
            "max_drawdown_worsening_limit": round(float(max_drawdown_worsening_limit), 8),
            "auto_promote_defaults": False,
        },
        "defaults_changed": False,
        "variants": variants,
        "errors_count": 0,
    }
    report["summary_zh"] = _build_runtime_evolution_summary_zh(report)
    return report


def _validate_runtime_record(record: dict[str, Any], *, line_number: int) -> dict[str, Any]:
    for field in REQUIRED_RUNTIME_FIELDS:
        if not record.get(field):
            raise ValueError(f"line {line_number}: runtime record missing required field: {field}")
    if not str(record.get("schema_version", "")).startswith("runtime."):
        raise ValueError(f"line {line_number}: unsupported schema_version: {record.get('schema_version')}")
    if not isinstance(record.get("market_inputs", {}), dict):
        raise ValueError(f"line {line_number}: market_inputs must be an object")
    if not isinstance(record.get("signals", []), list):
        raise ValueError(f"line {line_number}: signals must be a list")
    for interval in _intervals(record):
        _validate_runtime_interval(interval, line_number=line_number)
    return record


def _validate_runtime_interval(interval: str, *, line_number: int) -> str:
    if interval in _SHORT_INTERVALS:
        raise ValueError(f"line {line_number}: short interval is forbidden by policy: {interval}; use >= 1h")
    if interval not in _ALLOWED_INTERVALS:
        raise ValueError(f"line {line_number}: unsupported interval in runtime evidence: {interval}; allowed: {sorted(_ALLOWED_INTERVALS)}")
    return interval


def _captured_input(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": record.get("schema_version"),
        "environment": record.get("environment"),
        "run_id": record.get("run_id"),
        "generated_at_utc": record.get("generated_at_utc"),
        "generated_at_beijing": record.get("generated_at_beijing"),
        "symbol_universe": _symbols(record),
        "intervals": _intervals(record),
        "market_inputs": record.get("market_inputs", {}),
        "signals": record.get("signals", []),
        "risk": record.get("risk", {}),
        "execution_events": record.get("execution_events", {}),
        "outcomes": record.get("outcomes", {}),
    }


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _symbols(record: dict[str, Any]) -> list[str]:
    raw_symbols = record.get("symbol_universe") or (record.get("market_inputs") or {}).get("symbols") or []
    return [str(symbol) for symbol in raw_symbols if symbol]


def _intervals(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(record.get("intervals") or [])
    market_inputs = record.get("market_inputs") or {}
    primary_interval = market_inputs.get("primary_interval")
    if primary_interval:
        values.append(primary_interval)
    values.extend(market_inputs.get("intervals") or [])
    for signal in record.get("signals") or []:
        if isinstance(signal, dict) and signal.get("interval"):
            values.append(signal.get("interval"))
    result: list[str] = []
    seen: set[str] = set()
    for interval in values:
        if not interval:
            continue
        text = str(interval)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _runtime_variant_metrics(records: list[dict[str, Any]], exposure_multiplier: float) -> dict[str, Any]:
    equity = 1.0
    peak = 1.0
    worst_drawdown = 0.0
    total_return_proxy = 0.0
    total_turnover = 0.0
    previous_exposure = 0.0
    holding_periods = 0
    missed_trend_periods = 0
    premature_exit_periods = 0

    for record in records:
        base_return = _record_return_proxy(record)
        desired_exposure = _record_desired_exposure(record) * exposure_multiplier
        if desired_exposure > 0:
            holding_periods += 1
        if _record_has_trend(record) and desired_exposure < 1.0:
            missed_trend_periods += 1
        if _record_has_trend(record) and previous_exposure > 0 and desired_exposure <= 0:
            premature_exit_periods += 1
        total_turnover += abs(desired_exposure - previous_exposure)
        previous_exposure = desired_exposure
        period_return = base_return * desired_exposure
        total_return_proxy += period_return
        equity = max(equity * (1.0 + period_return), 1e-12)
        peak = max(peak, equity)
        worst_drawdown = min(worst_drawdown, equity / peak - 1.0)

    periods = max(len(records), 1)
    missed_trend_rate = missed_trend_periods / periods
    premature_exit_rate = premature_exit_periods / periods
    return {
        "return_proxy": round(total_return_proxy, 8),
        "final_equity_proxy": round(equity, 8),
        "max_drawdown": round(worst_drawdown, 8),
        "turnover": round(total_turnover, 8),
        "average_holding_periods": round(float(holding_periods), 8),
        "missed_trend_count": missed_trend_periods,
        "missed_trend_rate": round(missed_trend_rate, 8),
        "premature_exit_count": premature_exit_periods,
        "premature_exit_rate": round(premature_exit_rate, 8),
    }


def _record_return_proxy(record: dict[str, Any]) -> float:
    outcomes = record.get("outcomes") or {}
    if outcomes.get("return_proxy") is not None:
        return float(outcomes["return_proxy"])
    by_symbol = outcomes.get("return_proxy_by_symbol") or {}
    if by_symbol:
        return sum(float(value) for value in by_symbol.values()) / max(len(by_symbol), 1)
    signals = record.get("signals") or []
    values = [float(signal.get("return_proxy")) for signal in signals if signal.get("return_proxy") is not None]
    if values:
        return sum(values) / len(values)
    return 0.0


def _record_desired_exposure(record: dict[str, Any]) -> float:
    signals = record.get("signals") or []
    exposures = []
    for signal in signals:
        action = str(signal.get("action", signal.get("primary_trend", "")))
        if action == "hold_long":
            exposures.append(float(signal.get("position_size", 1.0) or 1.0))
    if exposures:
        return sum(exposures) / len(exposures)
    return 0.0


def _record_has_trend(record: dict[str, Any]) -> bool:
    return any(str(signal.get("action", signal.get("primary_trend", ""))) == "hold_long" for signal in record.get("signals") or [])


def _runtime_evidence_score(metrics: dict[str, Any]) -> float:
    return_proxy = float(metrics.get("return_proxy", 0.0))
    drawdown = abs(float(metrics.get("max_drawdown", 0.0)))
    turnover = float(metrics.get("turnover", 0.0))
    premature_exit_rate = float(metrics.get("premature_exit_rate", 0.0))
    return round(return_proxy - 0.5 * drawdown - 0.01 * turnover - 0.05 * premature_exit_rate, 8)


def _build_runtime_evolution_summary_zh(report: dict[str, Any]) -> str:
    lines = [
        "Binance USDS-M runtime evidence 策略回放（paper/testnet/live schema；diagnostic only）",
        f"UTC: {report.get('generated_at_utc')}",
        f"北京时间（UTC+8）: {report.get('generated_at_beijing')}",
        f"records={report.get('records_loaded')}; intervals={','.join(report.get('intervals') or [])}; selected={report.get('selected_variant')}",
    ]
    for item in report.get("variants", []):
        metrics = item.get("metrics") or {}
        eligibility = "eligible" if item.get("eligible") else "blocked"
        lines.append(
            f"{item.get('variant')}: {eligibility}; score={item.get('evidence_score')}; "
            f"return_proxy={metrics.get('return_proxy')}; max_drawdown={metrics.get('max_drawdown')}; "
            f"turnover={metrics.get('turnover')}; missed_trend={metrics.get('missed_trend_count')}; "
            f"premature_exit={metrics.get('premature_exit_count')}"
        )
    lines.append("安全: 仅回放已记录 runtime evidence；不抓取新样本；不自动推广默认参数；未下真实订单。")
    return "\n".join(lines)
