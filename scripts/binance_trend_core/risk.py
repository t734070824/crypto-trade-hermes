"""Risk manager boundary for portfolio caps and kill-switch hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .types import StrategyIntent


class RiskManager(Protocol):
    def approve(self, intent: StrategyIntent, portfolio_state: dict[str, Any]) -> dict[str, Any]:
        """Return approval/rejection metadata for an intent."""
        ...


@dataclass
class FunctionRiskManager:
    approve_fn: Callable[[StrategyIntent, dict[str, Any]], dict[str, Any]] | None = None
    kill_switch_enabled: bool = False

    def approve(self, intent: StrategyIntent, portfolio_state: dict[str, Any]) -> dict[str, Any]:
        if self.kill_switch_enabled:
            return {"approved": False, "reason": "kill switch enabled", "intent": intent}
        if self.approve_fn is not None:
            return self.approve_fn(intent, portfolio_state)
        return {"approved": True, "reason": "approved by default paper risk boundary", "intent": intent}
