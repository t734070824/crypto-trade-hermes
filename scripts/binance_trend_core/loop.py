"""Shared trading loop for paper/testnet/live adapter orchestration.

PaperBroker simulates fills. BinanceTestnetBroker can use the same loop while
keeping signed testnet execution isolated behind the broker adapter. Live remains
unimplemented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from .execution import ExecutionEngine, OrderInstruction
from .risk import RiskManager
from .signals import SignalEngine
from .strategy import Strategy

BEIJING = timezone(timedelta(hours=8), name="UTC+8")
_SHORT_INTERVALS = {"1m", "3m", "5m", "10m", "15m", "30m"}
_ALLOWED_INTERVALS = {"1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}


@dataclass(frozen=True)
class TradingCycleConfig:
    symbols: list[str]
    interval: str = "1h"
    limit: int = 240
    context_limit: int = 30
    candles_by_symbol: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    strategy_version: str = "ema50_ema200_atr_trend_paper"
    config_version: str = "default"
    run_id: str | None = None


def validate_cycle_interval(interval: str) -> str:
    if interval in _SHORT_INTERVALS:
        raise ValueError(f"short interval is forbidden by policy: {interval}; use >= 1h")
    if interval not in _ALLOWED_INTERVALS:
        raise ValueError(f"unsupported interval: {interval}; allowed: {sorted(_ALLOWED_INTERVALS)}")
    return interval


def now_stamps() -> dict[str, str]:
    now_utc = datetime.now(UTC).replace(microsecond=0)
    return {
        "generated_at_utc": now_utc.isoformat(),
        "generated_at_beijing": now_utc.astimezone(BEIJING).isoformat(),
    }


def run_trading_cycle(
    config: TradingCycleConfig,
    *,
    broker: Any,
    signal_engine: SignalEngine,
    strategy: Strategy,
    risk_manager: RiskManager,
    execution_engine: ExecutionEngine,
) -> dict[str, Any]:
    """Run one shared trading cycle through signal, risk, execution, broker, runtime evidence."""
    interval = validate_cycle_interval(config.interval)
    stamps = now_stamps()
    environment = str(getattr(broker, "environment", "unknown"))
    signals: list[dict[str, Any]] = []
    intents: list[Any] = []
    risk_results: list[dict[str, Any]] = []
    desired_orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    account_state = broker.get_account_state()

    for symbol in config.symbols:
        try:
            candles = config.candles_by_symbol[symbol]
            signal = signal_engine.generate_signal(candles, symbol=symbol, interval=interval)
            signals.append(signal)
            intent = strategy.generate_intent(signal)
            intents.append(intent)
            risk_result = risk_manager.approve(intent, account_state)
            risk_results.append(_json_safe_risk_result(risk_result))
            plan = execution_engine.plan_orders(intent, risk_result, account_state)
            for instruction in plan.instructions:
                desired_orders.append(_instruction_record(instruction))
                fill = broker.submit_order(instruction)
                fills.append(fill)
            account_state = broker.get_account_state()
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    account_state = broker.get_account_state()
    real_orders_submitted = any(bool(fill.get("real_order_submitted")) for fill in fills)
    runtime_record = {
        "schema_version": "runtime.v1",
        "environment": environment,
        "run_id": config.run_id or f"{environment}-{stamps['generated_at_utc']}",
        "strategy_version": config.strategy_version,
        "config_version": config.config_version,
        **stamps,
        "symbol_universe": list(config.symbols),
        "intervals": [interval],
        "market_inputs": {
            "source": "binance_free_public_usds_futures_or_injected_cycle_candles",
            "symbols": list(config.symbols),
            "primary_interval": interval,
            "errors": list(errors),
        },
        "signals": list(signals),
        "risk": {"risk_results": risk_results},
        "portfolio_state": account_state,
        "execution_events": {
            "environment": environment,
            "desired_orders": desired_orders,
            "simulated_fills": list(fills),
            "simulated_fills_count": len(fills),
            "real_orders_submitted": real_orders_submitted,
        },
        "outcomes": {
            "errors_count": len(errors),
            "runtime_summary": f"{environment} shared trading cycle completed; real_orders_submitted={real_orders_submitted}",
        },
    }
    return {
        "mode": "paper" if environment == "paper" else environment,
        "environment": environment,
        **stamps,
        "symbols": list(config.symbols),
        "interval": interval,
        "signals": signals,
        "intents": [_intent_record(intent) for intent in intents],
        "risk_results": risk_results,
        "desired_orders": desired_orders,
        "fills": fills,
        "simulated_fills": fills,
        "simulated_fills_count": len(fills),
        "portfolio_state": account_state,
        "runtime_record": runtime_record,
        "real_orders_submitted": real_orders_submitted,
        "errors": errors,
        "errors_count": len(errors),
    }


def _instruction_record(instruction: OrderInstruction | Any) -> dict[str, Any]:
    return {
        "symbol": str(getattr(instruction, "symbol")),
        "side": str(getattr(instruction, "side")),
        "quantity": round(float(getattr(instruction, "quantity")), 8),
        "order_type": str(getattr(instruction, "order_type", "MARKET")),
        "metadata": dict(getattr(instruction, "metadata", {}) or {}),
    }


def _intent_record(intent: Any) -> dict[str, Any]:
    return {
        "symbol": str(getattr(intent, "symbol", "")),
        "desired_exposure": round(float(getattr(intent, "desired_exposure", 0.0)), 8),
        "action": str(getattr(intent, "action", "")),
        "reason": str(getattr(intent, "reason", "")),
        "metadata": dict(getattr(intent, "metadata", {}) or {}),
    }


def _json_safe_risk_result(risk_result: dict[str, Any]) -> dict[str, Any]:
    safe = dict(risk_result)
    if "intent" in safe:
        safe["intent"] = _intent_record(safe["intent"])
    return safe
