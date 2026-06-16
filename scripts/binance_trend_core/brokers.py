"""Broker adapter boundary for paper, testnet, and live execution isolation."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Mapping, Protocol

from .execution import OrderInstruction
from .portfolio import PortfolioPosition

BEIJING = timezone(timedelta(hours=8), name="UTC+8")
BINANCE_USDS_FUTURES_TESTNET_BASE_URL = "https://testnet.binancefuture.com"
_TESTNET_HOST_MARKER = "testnet.binancefuture.com"
_SENSITIVE_KEYS = {"apikey", "api_key", "x_mbx_apikey", "secret", "api_secret", "signature"}


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


@dataclass(frozen=True)
class BinanceTestnetCredentials:
    """Credential container for Binance USDS-M futures testnet only."""

    api_key: str
    api_secret: str

    def __post_init__(self) -> None:
        if not self.api_key or not self.api_secret:
            raise RuntimeError("missing Binance testnet credentials: set LALA_KEY and LALA_SECRET")


@dataclass(frozen=True)
class TestnetRiskLimits:
    """Fail-closed safety limits for signed testnet execution."""

    max_order_notional: float = 1_000.0
    max_symbol_exposure: float = 2_000.0
    max_daily_loss: float = 100.0
    max_order_count: int = 10
    kill_switch: bool = False


class UrllibHttpClient:
    """Tiny injectable HTTP client for signed testnet requests."""

    def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: int = 20) -> Any:
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def resolve_binance_testnet_credentials(env: Mapping[str, str] | None = None) -> BinanceTestnetCredentials:
    """Resolve testnet credentials from LALA_KEY/LALA_SECRET without exposing values."""

    source = os.environ if env is None else env
    api_key = str(source.get("LALA_KEY") or "")
    api_secret = str(source.get("LALA_SECRET") or "")
    missing = [name for name, value in (("LALA_KEY", api_key), ("LALA_SECRET", api_secret)) if not value]
    if missing:
        raise RuntimeError(f"missing Binance testnet credentials: set {', '.join(missing)}")
    return BinanceTestnetCredentials(api_key=api_key, api_secret=api_secret)


def redact_sensitive_testnet_fields(value: Any) -> Any:
    """Recursively redact API keys, secrets, and signatures from runtime evidence."""

    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            normalized = str(key).replace("-", "_").lower()
            if normalized in _SENSITIVE_KEYS or "secret" in normalized or "signature" in normalized:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_sensitive_testnet_fields(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_testnet_fields(item) for item in value]
    return value


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


@dataclass
class BinanceTestnetBroker:
    """Binance USDS-M futures testnet adapter with dry-run and fail-closed risk gates."""

    credentials: BinanceTestnetCredentials
    base_url: str = BINANCE_USDS_FUTURES_TESTNET_BASE_URL
    dry_run: bool = True
    risk_limits: TestnetRiskLimits = field(default_factory=TestnetRiskLimits)
    http_client: Any = field(default_factory=UrllibHttpClient)
    environment: str = "testnet"
    fills: list[dict[str, Any]] = field(default_factory=list)
    positions: dict[str, PortfolioPosition] = field(default_factory=dict)
    submitted_order_count: int = 0
    accepted_order_count: int = 0
    daily_realized_pnl: float = 0.0

    def __post_init__(self) -> None:
        if self.environment != "testnet":
            raise ValueError("BinanceTestnetBroker only supports environment=testnet")
        normalized = self.base_url.rstrip("/")
        parsed = urllib.parse.urlparse(normalized)
        if parsed.scheme != "https" or parsed.hostname != _TESTNET_HOST_MARKER:
            raise ValueError("BinanceTestnetBroker base_url must be Binance futures testnet only")
        self.base_url = normalized

    def submit_order(self, instruction: OrderInstruction | dict[str, Any]) -> dict[str, Any]:
        order = _coerce_instruction(instruction)
        symbol = order.symbol.upper()
        side = order.side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError(f"unsupported testnet side: {order.side}")
        quantity = float(order.quantity)
        if quantity <= 0:
            raise ValueError("testnet order quantity must be positive")
        reference_price = self._reference_price(order)
        global_rejection = self._global_risk_rejection()
        if global_rejection:
            event = self._base_event(order, reference_price or 0.0, abs(quantity * (reference_price or 0.0)))
            event.update({"status": "rejected", "reason": global_rejection, "real_order_submitted": False, "signed": False, "testnet_dry_run": self.dry_run})
            self.fills.append(event)
            return event
        if reference_price is None:
            event = self._base_event(order, 0.0, 0.0)
            event.update({"status": "rejected", "reason": "invalid_reference_price", "real_order_submitted": False, "signed": False, "testnet_dry_run": self.dry_run})
            self.fills.append(event)
            return event
        notional = abs(quantity * reference_price)
        rejection = self._risk_rejection(symbol=symbol, side=side, quantity=quantity, reference_price=reference_price, notional=notional)
        if rejection:
            event = self._base_event(order, reference_price, notional)
            event.update({"status": "rejected", "reason": rejection, "real_order_submitted": False, "signed": False, "testnet_dry_run": self.dry_run})
            self.fills.append(event)
            return event

        params = {
            "symbol": symbol,
            "side": side,
            "type": order.order_type.upper(),
            "quantity": _decimal_string(quantity),
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        }
        event = self._base_event(order, reference_price, notional)
        event["request"] = {"method": "POST", "path": "/fapi/v1/order", "params": redact_sensitive_testnet_fields(params)}
        if self.dry_run:
            event.update({"status": "dry_run", "testnet_dry_run": True, "signed": False, "simulated": True, "real_order_submitted": False})
            self.accepted_order_count += 1
            self._apply_position(symbol, side, quantity, reference_price)
            self.fills.append(event)
            return event

        signed_params = self._sign_params(params)
        event.update(
            {
                "request": {"method": "POST", "path": "/fapi/v1/order", "params": redact_sensitive_testnet_fields(signed_params)},
                "testnet_dry_run": False,
                "signed": True,
                "simulated": False,
                "attempted_real_order_submitted": True,
                "real_order_submitted": True,
            }
        )
        query = urllib.parse.urlencode(signed_params)
        url = f"{self.base_url}/fapi/v1/order?{query}"
        self.submitted_order_count += 1
        self.fills.append(event)
        try:
            response_payload = self.http_client.request("POST", url, headers={"X-MBX-APIKEY": self.credentials.api_key})
        except Exception as exc:
            event.update(
                {
                    "status": "submitted_unknown",
                    "error": "signed_testnet_submission_failed_sanitized",
                    "error_type": exc.__class__.__name__,
                    "response": None,
                }
            )
            return event
        self.accepted_order_count += 1
        self._apply_position(symbol, side, quantity, reference_price)
        event.update(
            {
                "status": "submitted",
                "response": redact_sensitive_testnet_fields(response_payload),
            }
        )
        return event

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return {"environment": self.environment, "order_id": order_id, "cancelled": False, "reason": "cancel not implemented in v1.7 testnet adapter skeleton"}

    def get_account_state(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            **_now_stamps(),
            "base_url": self.base_url,
            "dry_run": self.dry_run,
            "positions": {symbol: asdict(position) for symbol, position in self.positions.items()},
            "fills": list(self.fills),
            "submitted_order_count": self.submitted_order_count,
            "accepted_order_count": self.accepted_order_count,
            "real_orders_submitted": self.submitted_order_count > 0,
            "risk_limits": asdict(self.risk_limits),
        }

    def _global_risk_rejection(self) -> str | None:
        limits = self.risk_limits
        if limits.kill_switch:
            return "kill_switch_enabled"
        if max(self.accepted_order_count, self.submitted_order_count) >= limits.max_order_count:
            return "max_order_count_exceeded"
        if limits.max_daily_loss > 0 and self.daily_realized_pnl <= -abs(limits.max_daily_loss):
            return "max_daily_loss_exceeded"
        return None

    def _reference_price(self, order: OrderInstruction) -> float | None:
        raw = order.metadata.get("reference_price", order.metadata.get("entry_reference"))
        if raw is None:
            return None
        try:
            reference_price = float(raw)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(reference_price) or reference_price <= 0:
            return None
        return reference_price

    def _risk_rejection(self, *, symbol: str, side: str, quantity: float, reference_price: float, notional: float) -> str | None:
        limits = self.risk_limits
        global_rejection = self._global_risk_rejection()
        if global_rejection:
            return global_rejection
        if notional > limits.max_order_notional:
            return "max_order_notional_exceeded"
        current = self.positions.get(symbol, PortfolioPosition(symbol=symbol))
        signed_quantity = quantity if side == "BUY" else -quantity
        projected_notional = abs((current.size + signed_quantity) * reference_price)
        if projected_notional > limits.max_symbol_exposure:
            return "max_symbol_exposure_exceeded"
        return None

    def _sign_params(self, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        signature = hmac.new(self.credentials.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        return {**params, "signature": signature}

    def _apply_position(self, symbol: str, side: str, quantity: float, reference_price: float) -> None:
        position = self.positions.get(symbol, PortfolioPosition(symbol=symbol))
        signed_quantity = quantity if side == "BUY" else -quantity
        new_size = position.size + signed_quantity
        if abs(new_size) < 1e-12:
            new_size = 0.0
        if signed_quantity > 0:
            current_notional = position.size * (position.entry_price or reference_price)
            added_notional = signed_quantity * reference_price
            position.entry_price = (current_notional + added_notional) / max(position.size + signed_quantity, 1e-12)
        position.size = round(new_size, 8)
        position.metadata.update({"last_reference_price": round(reference_price, 8), "last_side": side, "environment": "testnet"})
        self.positions[symbol] = position

    def _base_event(self, order: OrderInstruction, reference_price: float, notional: float) -> dict[str, Any]:
        return {
            "environment": self.environment,
            **_now_stamps(),
            "symbol": order.symbol.upper(),
            "side": order.side.upper(),
            "quantity": round(float(order.quantity), 8),
            "order_type": order.order_type.upper(),
            "reference_price": round(reference_price, 8),
            "notional": round(notional, 8),
            "instruction": redact_sensitive_testnet_fields(_instruction_record(order)),
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


def _decimal_string(value: float) -> str:
    text = f"{float(value):.8f}".rstrip("0").rstrip(".")
    return text or "0"
