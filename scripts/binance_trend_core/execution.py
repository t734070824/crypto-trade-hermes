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
    take_profit_1 = _positive_signal_price(signal.get("take_profit_1"))
    take_profit_2 = _positive_signal_price(signal.get("take_profit_2"))
    orders: list[OrderInstruction] = []
    existing_stop = _find_open_protection(portfolio_state, symbol, "stop_loss", target_exposure=target_exposure)
    if stop_price is not None:
        existing_stop_price = _positive_signal_price((existing_stop or {}).get("triggerPrice") or (existing_stop or {}).get("stopPrice"))
        if existing_stop is None:
            orders.append(_stop_loss_instruction(symbol, target_exposure, reference_price, stop_price, trailing_replacement=False))
        elif existing_stop_price is not None and stop_price > existing_stop_price:
            # Fail-closed: submit the tighter stop without cancelling the older, lower stop in
            # the same blind instruction plan.  This can leave duplicate stop protection, but
            # never creates a naked long position if the replacement is rejected or unknown.
            orders.append(_stop_loss_instruction(symbol, target_exposure, reference_price, stop_price, trailing_replacement=True))
    existing_tp_coverage = _existing_take_profit_coverage(portfolio_state, symbol, target_exposure)
    remaining_tp_exposure = max(0.0, target_exposure - existing_tp_coverage)
    if remaining_tp_exposure > 0:
        if take_profit_1 is None and take_profit_2 is not None:
            coverage = _take_profit_coverage_at_price(portfolio_state, symbol, take_profit_2, target_exposure)
            qty = min(max(0.0, target_exposure - coverage), remaining_tp_exposure)
            if qty > 0:
                orders.append(_take_profit_instruction(symbol, qty, reference_price, take_profit_2, "take_profit_2"))
        else:
            configured_layers = [("take_profit_1", take_profit_1), ("take_profit_2", take_profit_2)]
            configured_layers = [(role, price) for role, price in configured_layers if price is not None]
            per_layer_qty = target_exposure / max(1, len(configured_layers))
            for role, price in configured_layers:
                coverage = _take_profit_coverage_at_price(portfolio_state, symbol, price, per_layer_qty)
                qty = min(max(0.0, per_layer_qty - coverage), remaining_tp_exposure)
                if qty > 0:
                    orders.append(_take_profit_instruction(symbol, qty, reference_price, price, role))
                    remaining_tp_exposure = max(0.0, remaining_tp_exposure - qty)
                if remaining_tp_exposure <= 0:
                    break
    return orders


def _stop_loss_instruction(symbol: str, target_exposure: float, reference_price: float, stop_price: float, *, trailing_replacement: bool) -> OrderInstruction:
    return OrderInstruction(
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
            "trailing_stop_replacement": trailing_replacement,
        },
    )


def _take_profit_instruction(symbol: str, quantity: float, reference_price: float, take_profit_price: float, role: str) -> OrderInstruction:
    return OrderInstruction(
        symbol=symbol,
        side="SELL",
        quantity=abs(quantity),
        order_type="TAKE_PROFIT_MARKET",
        metadata={
            "protective_order": True,
            "protection_role": role,
            "reduce_only": True,
            "working_type": "MARK_PRICE",
            "stop_price": take_profit_price,
            "reference_price": reference_price,
            "action": "protect_long",
        },
    )


def _positive_signal_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _protection_rows(portfolio_state: dict[str, Any], symbol: str) -> list[Any]:
    symbol = symbol.upper()
    rows: list[Any] = []
    for key in ("open_orders", "openOrders", "open_algo_orders", "openAlgoOrders"):
        value = portfolio_state.get(key) or []
        if isinstance(value, dict):
            value = value.get(symbol) or value.get(symbol.upper()) or []
        if isinstance(value, list):
            rows.extend(value)
    return rows


def _find_open_protection(portfolio_state: dict[str, Any], symbol: str, role: str, *, target_exposure: float | None = None) -> dict[str, Any] | None:
    symbol = symbol.upper()
    wanted_types = {"stop_loss": {"STOP", "STOP_MARKET"}, "take_profit": {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"}}.get(role, set())
    for item in _protection_rows(portfolio_state, symbol):
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol", "")).upper() != symbol:
            continue
        order_type = str(item.get("type") or item.get("origType") or item.get("orderType") or "").upper()
        if order_type in wanted_types and _is_safe_long_protection(item, role, target_exposure=target_exposure):
            return item
    return None


def _has_open_protection(portfolio_state: dict[str, Any], symbol: str, role: str, *, target_exposure: float | None = None) -> bool:
    return _find_open_protection(portfolio_state, symbol, role, target_exposure=target_exposure) is not None


def _has_matching_take_profit(portfolio_state: dict[str, Any], symbol: str, trigger_price: float, *, target_exposure: float | None = None) -> bool:
    symbol = symbol.upper()
    for item in _protection_rows(portfolio_state, symbol):
        if not isinstance(item, dict) or str(item.get("symbol", "")).upper() != symbol:
            continue
        order_type = str(item.get("type") or item.get("origType") or item.get("orderType") or "").upper()
        if order_type not in {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"} or not _is_safe_long_protection(item, "take_profit", target_exposure=target_exposure):
            continue
        existing_price = _positive_signal_price(item.get("triggerPrice") or item.get("stopPrice"))
        if existing_price is not None and abs(existing_price - trigger_price) <= max(1e-8, abs(trigger_price) * 0.0001):
            return True
    return False


def _existing_take_profit_coverage(portfolio_state: dict[str, Any], symbol: str, target_exposure: float) -> float:
    symbol = symbol.upper()
    coverage = 0.0
    for item in _protection_rows(portfolio_state, symbol):
        if not isinstance(item, dict) or str(item.get("symbol", "")).upper() != symbol:
            continue
        order_type = str(item.get("type") or item.get("origType") or item.get("orderType") or "").upper()
        quantity = _positive_signal_price(item.get("origQty") or item.get("quantity") or item.get("executedQty"))
        if order_type not in {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"} or quantity is None:
            continue
        if not _is_safe_long_protection(item, "take_profit", target_exposure=quantity):
            continue
        coverage += min(quantity, target_exposure)
    return min(coverage, target_exposure)


def _take_profit_coverage_at_price(portfolio_state: dict[str, Any], symbol: str, trigger_price: float, layer_target_exposure: float) -> float:
    symbol = symbol.upper()
    coverage = 0.0
    for item in _protection_rows(portfolio_state, symbol):
        if not isinstance(item, dict) or str(item.get("symbol", "")).upper() != symbol:
            continue
        order_type = str(item.get("type") or item.get("origType") or item.get("orderType") or "").upper()
        quantity = _positive_signal_price(item.get("origQty") or item.get("quantity") or item.get("executedQty"))
        if order_type not in {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"} or quantity is None:
            continue
        if not _is_safe_long_protection(item, "take_profit", target_exposure=quantity):
            continue
        existing_price = _positive_signal_price(item.get("triggerPrice") or item.get("stopPrice"))
        if existing_price is None or abs(existing_price - trigger_price) > max(1e-8, abs(trigger_price) * 0.0001):
            continue
        coverage += min(quantity, layer_target_exposure)
    return min(coverage, layer_target_exposure)


def _is_safe_long_protection(item: dict[str, Any], role: str, *, target_exposure: float | None = None) -> bool:
    if str(item.get("side", "")).upper() != "SELL":
        return False
    close_position = _truthy(item.get("closePosition") or item.get("close_position"))
    reduce_only = _truthy(item.get("reduceOnly") or item.get("reduce_only"))
    if role == "stop_loss":
        return close_position or (reduce_only and _quantity_covers(item, target_exposure))
    if role == "take_profit":
        return reduce_only and _quantity_covers(item, target_exposure)
    return False


def _quantity_covers(item: dict[str, Any], target_exposure: float | None) -> bool:
    if target_exposure is None or target_exposure <= 0:
        return False
    quantity = _positive_signal_price(item.get("origQty") or item.get("quantity") or item.get("executedQty"))
    return quantity is not None and quantity >= target_exposure * 0.999


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
