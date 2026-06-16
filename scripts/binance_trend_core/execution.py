"""Execution boundary: convert approved intents into broker instructions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .types import StrategyIntent


@dataclass(frozen=True)
class OrderInstruction:
    symbol: str
    side: str
    quantity: float
    order_type: str = "MARKET"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionPlan:
    instructions: list[OrderInstruction]
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionEngine(Protocol):
    def plan_orders(self, intent: StrategyIntent, risk_result: dict[str, Any], portfolio_state: dict[str, Any]) -> ExecutionPlan:
        """Return order instructions needed to reconcile desired and current state."""
        ...


@dataclass
class PaperIntentExecutionEngine:
    """Minimal paper-only planner; future engines can submit via BrokerAdapter."""

    def plan_orders(self, intent: StrategyIntent, risk_result: dict[str, Any], portfolio_state: dict[str, Any]) -> ExecutionPlan:
        if not risk_result.get("approved", False):
            return ExecutionPlan(instructions=[], metadata={"skipped": True, "risk_result": risk_result})
        if intent.desired_exposure <= 0:
            side = "SELL" if intent.action == "flat" else "NONE"
        else:
            side = "BUY"
        if side == "NONE":
            return ExecutionPlan(instructions=[], metadata={"intent": intent, "portfolio_state": portfolio_state})
        signal = intent.metadata.get("signal") if isinstance(intent.metadata, dict) else None
        reference_price = _reference_price_from_signal(signal)
        return ExecutionPlan(
            instructions=[
                OrderInstruction(
                    symbol=intent.symbol,
                    side=side,
                    quantity=abs(intent.desired_exposure),
                    metadata={
                        "paper_intent": True,
                        "action": intent.action,
                        "reference_price": reference_price,
                    },
                )
            ],
            metadata={"intent": intent, "portfolio_state": portfolio_state},
        )


@dataclass
class PositionReconciliationExecutionEngine:
    """Plan only the delta between desired exposure and current broker state.

    This is used for signed testnet/live-like execution so a recurring cycle does
    not repeatedly submit the full target exposure when an equivalent position is
    already open.
    """

    min_delta: float = 1e-12

    def plan_orders(self, intent: StrategyIntent, risk_result: dict[str, Any], portfolio_state: dict[str, Any]) -> ExecutionPlan:
        if not risk_result.get("approved", False):
            return ExecutionPlan(instructions=[], metadata={"skipped": True, "risk_result": risk_result})
        current_exposure = _current_symbol_exposure(portfolio_state, intent.symbol)
        desired_exposure = float(intent.desired_exposure or 0.0)
        delta = desired_exposure - current_exposure
        metadata = {
            "intent": intent,
            "portfolio_state": portfolio_state,
            "current_exposure": current_exposure,
            "desired_exposure": desired_exposure,
            "delta_exposure": delta,
        }
        signal = intent.metadata.get("signal") if isinstance(intent.metadata, dict) else None
        instructions: list[OrderInstruction] = []
        if abs(delta) > self.min_delta:
            instructions.append(
                OrderInstruction(
                    symbol=intent.symbol,
                    side="BUY" if delta > 0 else "SELL",
                    quantity=abs(delta),
                    metadata={
                        "position_reconciliation": True,
                        "action": intent.action,
                        "reference_price": _reference_price_from_signal(signal),
                        "current_exposure": current_exposure,
                        "desired_exposure": desired_exposure,
                        "delta_exposure": delta,
                    },
                )
            )
        instructions.extend(_protective_orders(intent.symbol, desired_exposure, current_exposure, signal, portfolio_state))
        if not instructions:
            return ExecutionPlan(instructions=[], metadata={**metadata, "skipped": True, "reason": "target_exposure_already_reached"})
        return ExecutionPlan(instructions=instructions, metadata=metadata)


def _reference_price_from_signal(signal: Any) -> float:
    reference_price = 1.0
    if isinstance(signal, dict):
        reference_price = float(signal.get("entry_reference") or signal.get("close") or reference_price)
    return reference_price


def _current_symbol_exposure(portfolio_state: dict[str, Any], symbol: str) -> float:
    symbol = symbol.upper()
    positions = portfolio_state.get("positions")
    if isinstance(positions, dict):
        item = positions.get(symbol)
        if isinstance(item, dict):
            return float(item.get("size") or item.get("positionAmt") or item.get("position_amt") or 0.0)
    if isinstance(positions, list):
        for item in positions:
            if not isinstance(item, dict) or str(item.get("symbol", "")).upper() != symbol:
                continue
            return float(item.get("positionAmt") or item.get("position_amt") or item.get("size") or 0.0)
    positions_by_symbol = portfolio_state.get("positions_by_symbol")
    if isinstance(positions_by_symbol, dict):
        item = positions_by_symbol.get(symbol)
        if isinstance(item, dict):
            return float(item.get("size") or item.get("positionAmt") or item.get("position_amt") or 0.0)
    return 0.0


def _protective_orders(
    symbol: str,
    desired_exposure: float,
    current_exposure: float,
    signal: Any,
    portfolio_state: dict[str, Any],
) -> list[OrderInstruction]:
    if not isinstance(signal, dict):
        return []
    target_exposure = max(float(desired_exposure or 0.0), float(current_exposure or 0.0))
    if target_exposure <= 0:
        return []
    reference_price = _reference_price_from_signal(signal)
    stop_price = _positive_signal_price(signal.get("trailing_stop"))
    take_profit_price = _positive_signal_price(signal.get("take_profit_2") or signal.get("take_profit_1"))
    orders: list[OrderInstruction] = []
    if stop_price is not None and not _has_open_protection(portfolio_state, symbol, "stop_loss"):
        orders.append(
            OrderInstruction(
                symbol=symbol,
                side="SELL",
                quantity=abs(target_exposure),
                order_type="STOP_MARKET",
                metadata={
                    "protective_order": True,
                    "protection_role": "stop_loss",
                    "close_position": True,
                    "working_type": "MARK_PRICE",
                    "stop_price": stop_price,
                    "reference_price": reference_price,
                    "action": "protect_long",
                },
            )
        )
    if take_profit_price is not None and not _has_open_protection(portfolio_state, symbol, "take_profit"):
        orders.append(
            OrderInstruction(
                symbol=symbol,
                side="SELL",
                quantity=abs(target_exposure),
                order_type="TAKE_PROFIT_MARKET",
                metadata={
                    "protective_order": True,
                    "protection_role": "take_profit",
                    "close_position": True,
                    "working_type": "MARK_PRICE",
                    "stop_price": take_profit_price,
                    "reference_price": reference_price,
                    "action": "protect_long",
                },
            )
        )
    return orders


def _positive_signal_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _has_open_protection(portfolio_state: dict[str, Any], symbol: str, role: str) -> bool:
    symbol = symbol.upper()
    wanted_types = {"stop_loss": {"STOP", "STOP_MARKET"}, "take_profit": {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"}}.get(role, set())
    rows: list[Any] = []
    for key in ("open_orders", "openOrders", "open_algo_orders", "openAlgoOrders"):
        value = portfolio_state.get(key) or []
        if isinstance(value, dict):
            value = value.get(symbol) or value.get(symbol.upper()) or []
        if isinstance(value, list):
            rows.extend(value)
    for item in rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol", "")).upper() != symbol:
            continue
        order_type = str(item.get("type") or item.get("origType") or item.get("orderType") or "").upper()
        if order_type in wanted_types and str(item.get("side", "SELL")).upper() == "SELL":
            return True
    return False
