"""Portfolio state containers shared by future paper/testnet/live loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PortfolioPosition:
    symbol: str
    size: float = 0.0
    entry_price: float | None = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioState:
    environment: str = "paper"
    cash_balance: float | None = None
    equity: float | None = None
    positions_by_symbol: dict[str, PortfolioPosition] = field(default_factory=dict)
    open_orders: list[dict[str, Any]] = field(default_factory=list)
    fills: list[dict[str, Any]] = field(default_factory=list)
    lifecycle: dict[str, Any] = field(default_factory=dict)
    generated_at_utc: str | None = None
    generated_at_beijing: str | None = None

    def as_record(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "cash_balance": self.cash_balance,
            "equity": self.equity,
            "positions_by_symbol": {symbol: position.__dict__ for symbol, position in self.positions_by_symbol.items()},
            "open_orders": self.open_orders,
            "fills": self.fills,
            "lifecycle": self.lifecycle,
            "generated_at_utc": self.generated_at_utc,
            "generated_at_beijing": self.generated_at_beijing,
        }
