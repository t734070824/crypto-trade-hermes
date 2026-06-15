"""Market data boundary for free Binance public data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .types import MarketDataRequest


class MarketData(Protocol):
    def fetch_candles(self, request: MarketDataRequest) -> list[dict[str, Any]]:
        """Return normalized OHLCV-like candles for a request."""
        ...

    def fetch_context(self, request: MarketDataRequest) -> dict[str, Any]:
        """Return optional public context factors for a request."""
        ...


@dataclass
class FunctionMarketData:
    fetch_candles_fn: Callable[..., list[dict[str, Any]]]
    fetch_context_fn: Callable[..., dict[str, Any]] | None = None

    def fetch_candles(self, request: MarketDataRequest) -> list[dict[str, Any]]:
        return self.fetch_candles_fn(request.symbol, request.interval, request.limit)

    def fetch_context(self, request: MarketDataRequest) -> dict[str, Any]:
        if self.fetch_context_fn is None:
            return {}
        return self.fetch_context_fn(request.symbol, request.interval, request.context_limit)
