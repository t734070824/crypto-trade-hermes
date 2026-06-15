"""Runtime evidence recorder boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


class RuntimeRecorder(Protocol):
    def build_record(self, scan: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Build a schema-compatible runtime evidence record."""
        ...

    def append_record(self, path: str | Path, record: dict[str, Any]) -> dict[str, Any]:
        """Append one runtime record to durable storage."""
        ...


@dataclass
class FunctionRuntimeRecorder:
    build_record_fn: Callable[..., dict[str, Any]]
    append_record_fn: Callable[..., dict[str, Any]]

    def build_record(self, scan: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return self.build_record_fn(scan, **kwargs)

    def append_record(self, path: str | Path, record: dict[str, Any]) -> dict[str, Any]:
        return self.append_record_fn(path, record)
