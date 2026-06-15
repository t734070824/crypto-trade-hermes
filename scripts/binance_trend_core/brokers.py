"""Broker adapter boundary for paper, testnet, and live execution isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


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
