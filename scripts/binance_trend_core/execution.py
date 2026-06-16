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
        reference_price = 1.0
        if isinstance(signal, dict):
            reference_price = float(signal.get("entry_reference") or signal.get("close") or reference_price)
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
