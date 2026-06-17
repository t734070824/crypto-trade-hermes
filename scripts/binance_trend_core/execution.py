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
        signal = intent.metadata.get("signal") if isinstance(intent.metadata, dict) else None
        add_blocked = _signal_blocks_new_add(signal) and desired_exposure > current_exposure
        effective_desired_exposure = current_exposure if add_blocked else desired_exposure
        delta = effective_desired_exposure - current_exposure
        metadata = {
            "intent": intent,
            "portfolio_state": portfolio_state,
            "current_exposure": current_exposure,
            "desired_exposure": desired_exposure,
            "effective_desired_exposure": effective_desired_exposure,
            "delta_exposure": delta,
        }
        if add_blocked:
            metadata["add_blocked"] = True
            metadata["add_blockers"] = _signal_add_blockers(signal)
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
                        "effective_desired_exposure": effective_desired_exposure,
                        "delta_exposure": delta,
                    },
                )
            )
        instructions.extend(_protective_orders(intent.symbol, effective_desired_exposure, current_exposure, signal, portfolio_state))
        if not instructions:
            reason = "add_blocked_by_signal" if add_blocked else "target_exposure_already_reached"
            return ExecutionPlan(instructions=[], metadata={**metadata, "skipped": True, "reason": reason})
        return ExecutionPlan(instructions=instructions, metadata=metadata)


def _signal_blocks_new_add(signal: Any) -> bool:
    return isinstance(signal, dict) and signal.get("add_allowed") is False


def _signal_add_blockers(signal: Any) -> list[str]:
    if not isinstance(signal, dict):
        return []
    blockers = signal.get("add_blockers")
    if isinstance(blockers, list):
        return [str(item) for item in blockers]
    return []


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
    stop_target_exposure = max(float(desired_exposure or 0.0), float(current_exposure or 0.0))
    take_profit_target_exposure = max(0.0, float(desired_exposure or 0.0))
    if stop_target_exposure <= 0 and take_profit_target_exposure <= 0:
        return []
    reference_price = _reference_price_from_signal(signal)
    stop_price = _positive_signal_price(signal.get("trailing_stop"))
    take_profit_1 = _positive_signal_price(signal.get("take_profit_1"))
    take_profit_2 = _positive_signal_price(signal.get("take_profit_2"))
    orders: list[OrderInstruction] = []
    existing_stops = _open_protections(portfolio_state, symbol, "stop_loss", target_exposure=stop_target_exposure)
    existing_stop = _tightest_long_stop(existing_stops)
    for stale_stop in existing_stops:
        if stale_stop is not existing_stop:
            orders.append(_cancel_algo_instruction(symbol, stale_stop, "stale_stop_loss_replacement"))
    if stop_price is not None and stop_target_exposure > 0:
        existing_stop_price = _positive_signal_price((existing_stop or {}).get("triggerPrice") or (existing_stop or {}).get("stopPrice"))
        if existing_stop is None:
            orders.append(_stop_loss_instruction(symbol, stop_target_exposure, reference_price, stop_price, trailing_replacement=False))
        elif existing_stop_price is not None and stop_price > existing_stop_price:
            # Fail-closed: submit the tighter stop without cancelling the older, lower stop in
            # the same blind instruction plan.  A later cycle that sees both accepted stops will
            # cancel the stale lower stop, so replacement never creates a naked long position.
            orders.append(_stop_loss_instruction(symbol, stop_target_exposure, reference_price, stop_price, trailing_replacement=True))
    configured_layers = _configured_take_profit_layers(take_profit_1, take_profit_2)
    stale_take_profits = _stale_take_profit_protections(portfolio_state, symbol, configured_layers, take_profit_target_exposure)
    stale_take_profit_keys = {_protection_key(item) for item in stale_take_profits}
    for stale_tp in stale_take_profits:
        orders.append(_cancel_algo_instruction(symbol, stale_tp, "stale_take_profit_replacement"))
    if take_profit_target_exposure <= 0:
        return orders
    existing_tp_coverage = _existing_take_profit_coverage(portfolio_state, symbol, take_profit_target_exposure, excluded_keys=stale_take_profit_keys)
    remaining_tp_exposure = max(0.0, take_profit_target_exposure - existing_tp_coverage)
    if remaining_tp_exposure > 0:
        if take_profit_1 is None and take_profit_2 is not None:
            coverage = _take_profit_coverage_at_price(portfolio_state, symbol, take_profit_2, take_profit_target_exposure, excluded_keys=stale_take_profit_keys)
            qty = min(max(0.0, take_profit_target_exposure - coverage), remaining_tp_exposure)
            if qty > 0:
                orders.append(_take_profit_instruction(symbol, qty, reference_price, take_profit_2, "take_profit_2"))
        else:
            per_layer_qty = take_profit_target_exposure / max(1, len(configured_layers))
            for role, price in configured_layers:
                coverage = _take_profit_coverage_at_price(portfolio_state, symbol, price, per_layer_qty, excluded_keys=stale_take_profit_keys)
                qty = min(max(0.0, per_layer_qty - coverage), remaining_tp_exposure)
                if qty > 0:
                    orders.append(_take_profit_instruction(symbol, qty, reference_price, price, role))
                    remaining_tp_exposure = max(0.0, remaining_tp_exposure - qty)
                if remaining_tp_exposure <= 0:
                    break
    return orders


def _configured_take_profit_layers(take_profit_1: float | None, take_profit_2: float | None) -> list[tuple[str, float]]:
    return [(role, price) for role, price in (("take_profit_1", take_profit_1), ("take_profit_2", take_profit_2)) if price is not None]


def _cancel_algo_instruction(symbol: str, item: dict[str, Any], reason: str) -> OrderInstruction:
    return OrderInstruction(
        symbol=symbol,
        side="SELL",
        quantity=0.0,
        order_type="CANCEL_ALGO_ORDER",
        metadata={
            "protective_order": True,
            "action": "cancel_protection",
            "cancel_reason": reason,
            "cancel_algo_id": item.get("algoId") or item.get("orderId"),
            "cancel_client_algo_id": item.get("clientAlgoId") or item.get("clientOrderId"),
        },
    )


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
    rows = _open_protections(portfolio_state, symbol, role, target_exposure=target_exposure)
    return rows[0] if rows else None


def _open_protections(portfolio_state: dict[str, Any], symbol: str, role: str, *, target_exposure: float | None = None) -> list[dict[str, Any]]:
    symbol = symbol.upper()
    wanted_types = {"stop_loss": {"STOP", "STOP_MARKET"}, "take_profit": {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"}}.get(role, set())
    rows: list[dict[str, Any]] = []
    for item in _protection_rows(portfolio_state, symbol):
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol", "")).upper() != symbol:
            continue
        order_type = str(item.get("type") or item.get("origType") or item.get("orderType") or "").upper()
        effective_target = target_exposure
        if role == "take_profit" and effective_target is None:
            effective_target = _positive_signal_price(item.get("origQty") or item.get("quantity") or item.get("executedQty"))
        if order_type in wanted_types and _is_safe_long_protection(item, role, target_exposure=effective_target):
            rows.append(item)
    return rows


def _tightest_long_stop(stops: list[dict[str, Any]]) -> dict[str, Any] | None:
    priced = [(item, _positive_signal_price(item.get("triggerPrice") or item.get("stopPrice"))) for item in stops]
    priced = [(item, price) for item, price in priced if price is not None]
    if not priced:
        return stops[0] if stops else None
    return max(priced, key=lambda pair: pair[1])[0]


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


def _existing_take_profit_coverage(
    portfolio_state: dict[str, Any],
    symbol: str,
    target_exposure: float,
    *,
    excluded_keys: set[tuple[str, str]] | None = None,
) -> float:
    symbol = symbol.upper()
    excluded_keys = excluded_keys or set()
    coverage = 0.0
    for item in _protection_rows(portfolio_state, symbol):
        if not isinstance(item, dict) or str(item.get("symbol", "")).upper() != symbol:
            continue
        if _protection_key(item) in excluded_keys:
            continue
        order_type = str(item.get("type") or item.get("origType") or item.get("orderType") or "").upper()
        quantity = _positive_signal_price(item.get("origQty") or item.get("quantity") or item.get("executedQty"))
        if order_type not in {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"} or quantity is None:
            continue
        if not _is_safe_long_protection(item, "take_profit", target_exposure=quantity):
            continue
        coverage += min(quantity, target_exposure)
    return min(coverage, target_exposure)


def _take_profit_coverage_at_price(
    portfolio_state: dict[str, Any],
    symbol: str,
    trigger_price: float,
    layer_target_exposure: float,
    *,
    excluded_keys: set[tuple[str, str]] | None = None,
) -> float:
    symbol = symbol.upper()
    excluded_keys = excluded_keys or set()
    coverage = 0.0
    for item in _protection_rows(portfolio_state, symbol):
        if not isinstance(item, dict) or str(item.get("symbol", "")).upper() != symbol:
            continue
        if _protection_key(item) in excluded_keys:
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


def _stale_take_profit_protections(
    portfolio_state: dict[str, Any],
    symbol: str,
    configured_layers: list[tuple[str, float]],
    target_exposure: float,
) -> list[dict[str, Any]]:
    if not configured_layers:
        return _open_protections(portfolio_state, symbol, "take_profit", target_exposure=None)
    if target_exposure <= 0:
        return _open_protections(portfolio_state, symbol, "take_profit", target_exposure=None)
    layer_target = target_exposure / max(1, len(configured_layers))
    stale: list[dict[str, Any]] = []
    for item in _open_protections(portfolio_state, symbol, "take_profit", target_exposure=None):
        existing_price = _positive_signal_price(item.get("triggerPrice") or item.get("stopPrice"))
        matching_layers = [
            role
            for role, configured_price in configured_layers
            if existing_price is not None and abs(existing_price - configured_price) <= max(1e-8, abs(configured_price) * 0.0001)
        ]
        if not matching_layers:
            stale.append(item)
            continue
        quantity = _positive_signal_price(item.get("origQty") or item.get("quantity") or item.get("executedQty"))
        if layer_target > 0 and quantity is not None and quantity > layer_target * 1.001:
            stale.append(item)
    return stale


def _protection_key(item: dict[str, Any]) -> tuple[str, str]:
    for key in ("algoId", "clientAlgoId", "orderId", "clientOrderId"):
        value = item.get(key)
        if value not in (None, ""):
            return key, str(value)
    return "object", str(id(item))


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
