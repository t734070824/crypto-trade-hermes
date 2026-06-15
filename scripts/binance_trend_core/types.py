"""Shared lightweight dataclasses for the realtime trend engine boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str
    interval: str
    limit: int
    context_limit: int | None = None


@dataclass(frozen=True)
class StrategyIntent:
    symbol: str
    desired_exposure: float
    action: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
