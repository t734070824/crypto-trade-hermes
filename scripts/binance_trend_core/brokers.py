"""Broker adapter boundary for paper, testnet, and live execution isolation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Protocol

from .execution import OrderInstruction
from .portfolio import PortfolioPosition

BEIJING = timezone(timedelta(hours=8), name="UTC+8")


def _now_stamps() -> dict[str, str]:
    now_utc = datetime.now(UTC).replace(microsecond=0)
    return {
        "generated_at_utc": now_utc.isoformat(),
        "generated_at_beijing": now_utc.astimezone(BEIJING).isoformat(),
    }


class BrokerAdapter(Protocol):
    @property
    def environment(self) -> str:
        """Execution environment name: paper, testnet, or live."""
        ...

    def submit_order(self, instruction: dict[str, Any] | Any) -> dict[str, Any]:
        """Submit one broker-specific order instruction."""
        ...

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel one broker-specific order by adapter-local ID."""
        ...

    def get_account_state(self) -> dict[str, Any]:
        """Return adapter-local account/balance/position state."""
        ...


@dataclass
class RejectingBrokerAdapter:
    """Safe default adapter: exposes the boundary but never submits orders."""

    environment: str = "paper"
    account_state: dict[str, Any] = field(default_factory=dict)

    def submit_order(self, instruction: dict[str, Any] | Any) -> dict[str, Any]:
        raise RuntimeError(f"{self.environment} rejecting broker cannot submit orders")

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return {"environment": self.environment, "order_id": order_id, "cancelled": False, "reason": "rejecting broker"}

    def get_account_state(self) -> dict[str, Any]:
        return {"environment": self.environment, **self.account_state}


@dataclass
class PaperBroker:
    """Paper broker adapter with deterministic simulated fills and no network calls."""

    initial_equity: float = 10_000.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    environment: str = "paper"
    positions: dict[str, PortfolioPosition] = field(default_factory=dict)
    fills: list[dict[str, Any]] = field(default_factory=list)
    cash_balance: float | None = None

    def __post_init__(self) -> None:
        if self.environment != "paper":
            raise ValueError("PaperBroker only supports environment=paper")
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be positive")
        if self.fee_bps < 0 or self.slippage_bps < 0:
            raise ValueError("paper fee_bps and slippage_bps must be non-negative")
        if self.cash_balance is None:
            self.cash_balance = float(self.initial_equity)

    def submit_order(self, instruction: OrderInstruction | dict[str, Any]) -> dict[str, Any]:
        order = _coerce_instruction(instruction)
        symbol = order.symbol.upper()
        side = order.side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError(f"unsupported paper side: {order.side}")
        quantity = float(order.quantity)
        if quantity <= 0:
            raise ValueError("paper order quantity must be positive")
        reference_price = float(order.metadata.get("reference_price") or order.metadata.get("entry_reference") or 1.0)
        slippage_multiplier = 1.0 + self.slippage_bps / 10_000.0 if side == "BUY" else 1.0 - self.slippage_bps / 10_000.0
        fill_price = max(reference_price * slippage_multiplier, 0.0)
        notional = abs(quantity) * fill_price
        fee = notional * self.fee_bps / 10_000.0
        position = self.positions.get(symbol, PortfolioPosition(symbol=symbol))
        signed_quantity = quantity if side == "BUY" else -quantity
        new_size = position.size + signed_quantity
        if abs(new_size) < 1e-12:
            new_size = 0.0
        if signed_quantity > 0:
            current_notional = position.size * (position.entry_price or fill_price)
            added_notional = signed_quantity * fill_price
            position.entry_price = (current_notional + added_notional) / max(position.size + signed_quantity, 1e-12)
        position.size = round(new_size, 8)
        position.metadata.update({"last_fill_price": round(fill_price, 8), "last_side": side})
        self.positions[symbol] = position
        self.cash_balance = float(self.cash_balance or 0.0) - fee
        fill = {
            "environment": self.environment,
            **_now_stamps(),
            "symbol": symbol,
            "side": side,
            "quantity": round(quantity, 8),
            "fill_price": round(fill_price, 8),
            "reference_price": round(reference_price, 8),
            "fee": round(fee, 8),
            "fee_bps": round(self.fee_bps, 8),
            "slippage_bps": round(self.slippage_bps, 8),
            "simulated": True,
            "real_order_submitted": False,
            "paper_order_id": f"paper-{len(self.fills) + 1}",
            "instruction": _instruction_record(order),
        }
        self.fills.append(fill)
        return fill

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return {"environment": self.environment, "order_id": order_id, "cancelled": False, "reason": "paper market orders fill immediately"}

    def get_account_state(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            **_now_stamps(),
            "initial_equity": round(float(self.initial_equity), 8),
            "cash_balance": round(float(self.cash_balance or 0.0), 8),
            "equity": round(float(self.cash_balance or 0.0), 8),
            "positions": {symbol: asdict(position) for symbol, position in self.positions.items()},
            "fills": list(self.fills),
            "real_orders_submitted": False,
        }


def _coerce_instruction(instruction: OrderInstruction | dict[str, Any]) -> OrderInstruction:
    if isinstance(instruction, OrderInstruction):
        return instruction
    return OrderInstruction(
        symbol=str(instruction["symbol"]),
        side=str(instruction["side"]),
        quantity=float(instruction["quantity"]),
        order_type=str(instruction.get("order_type", "MARKET")),
        metadata=dict(instruction.get("metadata") or {}),
    )


def _instruction_record(instruction: OrderInstruction) -> dict[str, Any]:
    return {
        "symbol": instruction.symbol,
        "side": instruction.side,
        "quantity": round(float(instruction.quantity), 8),
        "order_type": instruction.order_type,
        "metadata": dict(instruction.metadata),
    }
