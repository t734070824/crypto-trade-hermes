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


@dataclass(frozen=True)
class _PlannedInstructionGroup:
    priority_key: tuple[int, int, int, int]
    instructions: list[OrderInstruction]
    atomic_budget_group: bool = False
    intent: Any | None = None
    filter_protective_on_replan: bool = False


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
    planned_groups: list[_PlannedInstructionGroup] = []
    instruction_index = 0

    for symbol_index, symbol in enumerate(config.symbols):
        try:
            candles = config.candles_by_symbol[symbol]
            signal = signal_engine.generate_signal(candles, symbol=symbol, interval=interval)
            signals.append(signal)
            intent = strategy.generate_intent(signal)
            intents.append(intent)
            risk_result = risk_manager.approve(intent, account_state)
            risk_results.append(_json_safe_risk_result(risk_result))
            plan = execution_engine.plan_orders(intent, risk_result, account_state)
            plan_metadata = dict(plan.metadata or {}) if isinstance(plan.metadata, dict) else {}
            current_exposure = float(plan_metadata.get("current_exposure") or 0.0)
            delta_exposure = float(plan_metadata.get("delta_exposure") or 0.0)
            plan_instructions = list(plan.instructions)
            if not plan_instructions:
                continue
            if delta_exposure > 1e-12 and abs(current_exposure) <= 1e-12:
                priority_key = (2, symbol_index, 0, instruction_index)
                planned_groups.append(_PlannedInstructionGroup(priority_key, plan_instructions, True, intent))
                instruction_index += len(plan_instructions)
                continue
            for local_index, instruction in enumerate(plan_instructions):
                priority_key = _order_submission_priority_key(instruction, current_exposure, delta_exposure, symbol_index, local_index, instruction_index)
                metadata = dict(getattr(instruction, "metadata", {}) or {})
                atomic_budget_group = delta_exposure > 1e-12 and not bool(metadata.get("protective_order"))
                planned_groups.append(
                    _PlannedInstructionGroup(
                        priority_key,
                        [instruction],
                        atomic_budget_group,
                        intent if atomic_budget_group else None,
                        atomic_budget_group,
                    )
                )
                instruction_index += 1
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    for group in sorted(planned_groups, key=lambda item: item.priority_key):
        instructions = group.instructions
        if group.atomic_budget_group and group.intent is not None:
            account_state = broker.get_account_state()
            recheck = risk_manager.approve(group.intent, account_state)
            if not recheck.get("approved", False):
                for instruction in instructions:
                    desired_orders.append(_instruction_record(instruction))
                    fills.append(_skipped_order_record(instruction, environment, "risk_recheck_rejected_before_atomic_entry_group"))
                continue
            replanned = execution_engine.plan_orders(group.intent, recheck, account_state)
            replanned_instructions = list(replanned.instructions)
            if group.filter_protective_on_replan:
                replanned_instructions = [
                    instruction
                    for instruction in replanned_instructions
                    if _is_positive_exposure_delta_instruction(instruction)
                ]
            if not replanned_instructions:
                for instruction in instructions:
                    desired_orders.append(_instruction_record(instruction))
                    fills.append(_skipped_order_record(instruction, environment, "stale_atomic_entry_group_no_longer_needed"))
                continue
            instructions = replanned_instructions
        remaining_budget = _remaining_broker_order_budget(broker)
        if group.atomic_budget_group and remaining_budget is not None and len(instructions) > remaining_budget:
            for instruction in instructions:
                desired_orders.append(_instruction_record(instruction))
                fills.append(_skipped_order_record(instruction, environment, "insufficient_order_budget_for_atomic_entry_protection_group"))
            continue
        for instruction in instructions:
            try:
                desired_orders.append(_instruction_record(instruction))
                fill = broker.submit_order(instruction)
                fills.append(fill)
            except Exception as exc:
                errors.append({"symbol": str(getattr(instruction, "symbol", "")), "error": str(exc)})

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


def _order_submission_priority_key(
    instruction: OrderInstruction | Any,
    current_exposure: float,
    delta_exposure: float,
    symbol_index: int,
    local_index: int,
    global_index: int,
) -> tuple[int, int, int, int]:
    """Order submissions safely under a global broker order budget.

    Priorities are intentionally narrow:
    1. Net exposure reductions/flat exits for already-open positions.
    2. Missing protective repairs for already-open positions.
    3. Normal per-symbol plans, preserving entry -> new protection order.
    """
    metadata = dict(getattr(instruction, "metadata", {}) or {})
    protective_order = bool(metadata.get("protective_order"))
    has_position = abs(float(current_exposure or 0.0)) > 1e-12
    instruction_delta = float(metadata.get("delta_exposure") or delta_exposure or 0.0)
    reduces_existing_position = has_position and not protective_order and instruction_delta < -1e-12
    if reduces_existing_position:
        return (0, symbol_index, local_index, global_index)
    if protective_order and has_position:
        return (1, symbol_index, local_index, global_index)
    return (2, symbol_index, local_index, global_index)


def _remaining_broker_order_budget(broker: Any) -> int | None:
    limits = getattr(broker, "risk_limits", None)
    max_order_count = getattr(limits, "max_order_count", None)
    if max_order_count is None:
        return None
    try:
        limit = int(max_order_count)
        accepted = int(getattr(broker, "accepted_order_count", 0) or 0)
        submitted = int(getattr(broker, "submitted_order_count", 0) or 0)
    except (TypeError, ValueError):
        return None
    return max(0, limit - max(accepted, submitted))


def _is_positive_exposure_delta_instruction(instruction: OrderInstruction | Any) -> bool:
    metadata = dict(getattr(instruction, "metadata", {}) or {})
    if metadata.get("protective_order"):
        return False
    delta = metadata.get("delta_exposure")
    if delta is None:
        return True
    try:
        return float(delta) > 1e-12
    except (TypeError, ValueError):
        return False


def _skipped_order_record(instruction: OrderInstruction | Any, environment: str, reason: str) -> dict[str, Any]:
    return {
        "environment": environment,
        "symbol": str(getattr(instruction, "symbol", "")),
        "side": str(getattr(instruction, "side", "")),
        "quantity": round(float(getattr(instruction, "quantity", 0.0) or 0.0), 8),
        "order_type": str(getattr(instruction, "order_type", "MARKET")),
        "status": "skipped",
        "reason": reason,
        "real_order_submitted": False,
        "signed": False,
        "instruction": _instruction_record(instruction),
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
