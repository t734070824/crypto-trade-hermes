"""Strategy boundary: signals to desired exposure/intents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .types import StrategyIntent


class Strategy(Protocol):
    def generate_intent(self, signal: dict[str, Any]) -> StrategyIntent:
        """Convert one signal into a desired exposure intent."""
        ...


@dataclass
class TrendParticipationStrategy:
    """Minimal wrapper preserving current paper trend participation semantics."""

    def generate_intent(self, signal: dict[str, Any]) -> StrategyIntent:
        action = str(signal.get("action", "flat"))
        desired_exposure = float(signal.get("position_size", 0.0) or 0.0)
        if action == "flat":
            desired_exposure = 0.0
        return StrategyIntent(
            symbol=str(signal.get("symbol", "")),
            desired_exposure=desired_exposure,
            action=action,
            reason=str(signal.get("reason", "")),
            metadata={"signal": signal},
        )
