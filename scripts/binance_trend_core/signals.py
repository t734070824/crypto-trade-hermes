"""SignalEngine interfaces and wrappers around existing scanner functions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


class SignalEngine(Protocol):
    def generate_signal(self, candles: list[dict[str, Any]], *, symbol: str, interval: str, **kwargs: Any) -> dict[str, Any]:
        """Convert normalized candles into a symbol signal/decision."""
        ...

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        """Run a multi-symbol signal scan."""
        ...


@dataclass
class FunctionSignalEngine:
    decide_fn: Callable[..., dict[str, Any]]
    scan_fn: Callable[..., dict[str, Any]] | None = None

    def generate_signal(self, candles: list[dict[str, Any]], *, symbol: str, interval: str, **kwargs: Any) -> dict[str, Any]:
        return self.decide_fn(candles, symbol=symbol, interval=interval, **kwargs)

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        if self.scan_fn is None:
            raise NotImplementedError("scan_fn is required for multi-symbol scans")
        return self.scan_fn(**kwargs)
