"""Broker adapter boundary for paper, testnet, and live execution isolation."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import pathlib
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_DOWN
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

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any] | None,
        *,
        kill_switch_env: str | None = None,
        kill_switch_file: str | None = None,
    ) -> "TestnetRiskLimits":
        data = dict(config or {})
        kill_switch = _config_bool(data.get("kill_switch", False))
        if kill_switch_env and _env_bool(os.environ.get(kill_switch_env)):
            kill_switch = True
        if kill_switch_file and pathlib.Path(kill_switch_file).exists():
            kill_switch = True
        return cls(
            max_order_notional=_positive_float(data.get("max_order_notional", cls.max_order_notional), "max_order_notional"),
            max_symbol_exposure=_positive_float(data.get("max_symbol_exposure", cls.max_symbol_exposure), "max_symbol_exposure"),
            max_daily_loss=_positive_float(data.get("max_daily_loss", cls.max_daily_loss), "max_daily_loss"),
            max_order_count=_positive_int(data.get("max_order_count", cls.max_order_count), "max_order_count"),
            kill_switch=kill_switch,
        )

    def sanitized_summary(self) -> dict[str, Any]:
        return {"source": "testnet_risk_limits", **asdict(self)}


@dataclass(frozen=True)
class SymbolExchangeRules:
    """Binance exchangeInfo order rules for one symbol."""

    symbol: str
    min_qty: Decimal | None = None
    step_size: Decimal | None = None
    tick_size: Decimal | None = None
    min_notional: Decimal | None = None

    @classmethod
    def from_exchange_info(cls, symbol: str, payload: Mapping[str, Any]) -> "SymbolExchangeRules":
        filters = {str(item.get("filterType")): item for item in payload.get("filters", [])}
        lot = filters.get("LOT_SIZE") or {}
        price = filters.get("PRICE_FILTER") or {}
        min_notional = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
        return cls(
            symbol=symbol.upper(),
            min_qty=_optional_decimal(lot.get("minQty")),
            step_size=_optional_decimal(lot.get("stepSize")),
            tick_size=_optional_decimal(price.get("tickSize")),
            min_notional=_optional_decimal(min_notional.get("notional") or min_notional.get("minNotional")),
        )

    def adapt(self, quantity: float, reference_price: float) -> tuple[float, float, dict[str, float]]:
        original_quantity = Decimal(str(quantity))
        original_reference_price = Decimal(str(reference_price))
        adjusted_quantity = _floor_to_step(original_quantity, self.step_size)
        adjusted_reference_price = _floor_to_step(original_reference_price, self.tick_size)
        return (
            float(adjusted_quantity),
            float(adjusted_reference_price),
            {
                "quantity_before": float(original_quantity),
                "quantity_after": float(adjusted_quantity),
                "reference_price_before": float(original_reference_price),
                "reference_price_after": float(adjusted_reference_price),
            },
        )

    def validate(self, quantity: float, reference_price: float) -> str | None:
        quantity_dec = Decimal(str(quantity))
        price_dec = Decimal(str(reference_price))
        if self.min_qty is not None and quantity_dec < self.min_qty:
            return "exchange_min_qty_not_met"
        if self.min_notional is not None and quantity_dec * price_dec < self.min_notional:
            return "exchange_min_notional_not_met"
        return None


class UrllibHttpClient:
    """Tiny injectable HTTP client for signed testnet requests."""

    def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: int = 20) -> Any:
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _optional_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _floor_to_step(value: Decimal, step: Decimal | None) -> Decimal:
    if step is None or step == 0:
        return value
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


def _config_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _env_bool(value: str | None) -> bool:
    return value is not None and _config_bool(value)


def _positive_float(value: Any, name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return parsed


def _positive_int(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


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
    exchange_rules_by_symbol: dict[str, SymbolExchangeRules] = field(default_factory=dict)
    order_journal_path: str | None = None
    client_order_id_prefix: str = "hermes"
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
        if not math.isfinite(quantity):
            event = self._base_event(order, self._reference_price(order) or 0.0, 0.0)
            event.update({"status": "rejected", "reason": "non_finite_quantity", "real_order_submitted": False, "signed": False, "testnet_dry_run": self.dry_run})
            self.fills.append(event)
            return event
        if quantity <= 0:
            event = self._base_event(order, self._reference_price(order) or 0.0, 0.0)
            event.update({"status": "rejected", "reason": "non_positive_quantity", "real_order_submitted": False, "signed": False, "testnet_dry_run": self.dry_run})
            self.fills.append(event)
            return event
        client_order_id = self._build_client_order_id(symbol)
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
        exchange_rule_adjustments: dict[str, float] | None = None
        rules = self.exchange_rules_by_symbol.get(symbol)
        if rules is not None:
            quantity, reference_price, exchange_rule_adjustments = rules.adapt(quantity, reference_price)
            order = OrderInstruction(
                symbol=order.symbol,
                side=order.side,
                quantity=quantity,
                order_type=order.order_type,
                metadata={**order.metadata, "reference_price": reference_price},
            )
            if not math.isfinite(quantity):
                event = self._base_event(order, reference_price if math.isfinite(reference_price) else 0.0, 0.0)
                event.update({"status": "rejected", "reason": "exchange_quantity_not_finite_after_adaptation", "real_order_submitted": False, "signed": False, "testnet_dry_run": self.dry_run, "exchange_rule_adjustments": exchange_rule_adjustments})
                self.fills.append(event)
                return event
            if not math.isfinite(reference_price) or reference_price <= 0:
                event = self._base_event(order, 0.0, 0.0)
                event.update({"status": "rejected", "reason": "exchange_reference_price_invalid_after_adaptation", "real_order_submitted": False, "signed": False, "testnet_dry_run": self.dry_run, "exchange_rule_adjustments": exchange_rule_adjustments})
                self.fills.append(event)
                return event
            exchange_rejection = rules.validate(quantity, reference_price)
            if not exchange_rejection and quantity <= 0:
                event = self._base_event(order, reference_price, 0.0)
                event.update({"status": "rejected", "reason": "exchange_quantity_not_positive_after_adaptation", "real_order_submitted": False, "signed": False, "testnet_dry_run": self.dry_run, "exchange_rule_adjustments": exchange_rule_adjustments})
                self.fills.append(event)
                return event
            if exchange_rejection:
                event = self._base_event(order, reference_price, abs(quantity * reference_price))
                event.update(
                    {
                        "status": "rejected",
                        "reason": exchange_rejection,
                        "real_order_submitted": False,
                        "signed": False,
                        "testnet_dry_run": self.dry_run,
                        "exchange_rule_adjustments": exchange_rule_adjustments,
                    }
                )
                self.fills.append(event)
                return event
        notional = abs(quantity * reference_price)
        rejection = self._risk_rejection(symbol=symbol, side=side, quantity=quantity, reference_price=reference_price, notional=notional)
        if rejection:
            event = self._base_event(order, reference_price, notional)
            event.update({"status": "rejected", "reason": rejection, "real_order_submitted": False, "signed": False, "testnet_dry_run": self.dry_run})
            if exchange_rule_adjustments is not None:
                event["exchange_rule_adjustments"] = exchange_rule_adjustments
            self.fills.append(event)
            return event

        params = {
            "symbol": symbol,
            "side": side,
            "type": order.order_type.upper(),
            "quantity": _decimal_string(quantity),
            "newClientOrderId": client_order_id,
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        }
        event = self._base_event(order, reference_price, notional)
        event["client_order_id"] = client_order_id
        if exchange_rule_adjustments is not None:
            event["exchange_rule_adjustments"] = exchange_rule_adjustments
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
            try:
                confirmed_payload = self._confirm_order_by_client_order_id(symbol, client_order_id)
            except Exception as confirm_exc:
                event.update({"confirm_status": "failed", "confirm_error_type": confirm_exc.__class__.__name__})
                self._append_order_journal(event)
                return event
            self.accepted_order_count += 1
            self._apply_position(symbol, side, quantity, reference_price)
            event.update(
                {
                    "status": "submitted_confirmed",
                    "confirm_status": "found",
                    "response": redact_sensitive_testnet_fields(confirmed_payload),
                }
            )
            self._append_order_journal(event)
            return event
        self.accepted_order_count += 1
        self._apply_position(symbol, side, quantity, reference_price)
        event.update(
            {
                "status": "submitted",
                "response": redact_sensitive_testnet_fields(response_payload),
            }
        )
        self._append_order_journal(event)
        return event

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return {"environment": self.environment, "order_id": order_id, "cancelled": False, "reason": "cancel not implemented in v1.7 testnet adapter skeleton"}

    def refresh_exchange_rules(self, symbols: list[str] | tuple[str, ...] | set[str] | None = None) -> dict[str, SymbolExchangeRules]:
        wanted = {item.upper() for item in symbols} if symbols is not None else None
        payload = self.http_client.request("GET", f"{self.base_url}/fapi/v1/exchangeInfo")
        loaded: dict[str, SymbolExchangeRules] = {}
        for item in payload.get("symbols", []):
            symbol = str(item.get("symbol", "")).upper()
            if not symbol or (wanted is not None and symbol not in wanted):
                continue
            loaded[symbol] = SymbolExchangeRules.from_exchange_info(symbol, item)
        self.exchange_rules_by_symbol.update(loaded)
        return loaded

    def fetch_signed_account_snapshot(self, symbol: str | None = None) -> dict[str, Any]:
        symbol_param = {"symbol": symbol.upper()} if symbol else None
        account = self._signed_get("/fapi/v2/account")
        positions = self._signed_get("/fapi/v2/positionRisk", symbol_param)
        open_orders = self._signed_get("/fapi/v1/openOrders", symbol_param)
        return {
            "environment": self.environment,
            **_now_stamps(),
            "account": redact_sensitive_testnet_fields(account),
            "positions": redact_sensitive_testnet_fields(positions),
            "open_orders": redact_sensitive_testnet_fields(open_orders),
        }

    def reconcile_open_orders(self, open_orders: list[dict[str, Any]]) -> dict[str, Any]:
        remote_client_ids = {str(order.get("clientOrderId")) for order in open_orders if order.get("clientOrderId")}
        unknown_local_ids = [str(event.get("client_order_id")) for event in self.fills if event.get("status") == "submitted_unknown" and event.get("client_order_id")]
        matched = [client_id for client_id in unknown_local_ids if client_id in remote_client_ids]
        missing = [client_id for client_id in unknown_local_ids if client_id not in remote_client_ids]
        return {
            "environment": self.environment,
            **_now_stamps(),
            "unknown_local_count": len(unknown_local_ids),
            "matched_open_order_client_ids": matched,
            "missing_unknown_client_ids": missing,
        }

    def _build_client_order_id(self, symbol: str) -> str:
        sequence = len(self.fills) + self.submitted_order_count + self.accepted_order_count + 1
        return f"{self.client_order_id_prefix}-{sequence}"

    def _append_order_journal(self, event: dict[str, Any]) -> None:
        if not self.order_journal_path:
            return
        path = pathlib.Path(self.order_journal_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = redact_sensitive_testnet_fields(event)
        params = record.get("request", {}).get("params") if isinstance(record, dict) else None
        if isinstance(params, dict):
            params.pop("signature", None)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def track_order_lifecycle(self, symbol: str, client_order_id: str, reference_price: float | None = None) -> dict[str, Any]:
        order_payload = self._signed_get("/fapi/v1/order", {"symbol": symbol.upper(), "origClientOrderId": client_order_id})
        order_id = order_payload.get("orderId")
        current_status = str(order_payload.get("status", "UNKNOWN")).upper()
        trades_payload = self._signed_get("/fapi/v1/userTrades", {"symbol": symbol.upper(), "orderId": order_id}) if order_id is not None else []
        trades = trades_payload if isinstance(trades_payload, list) else []
        fill_quantity = sum(float(trade.get("qty", 0.0)) for trade in trades)
        average_fill_price = _weighted_average([(float(trade.get("qty", 0.0)), float(trade.get("price", 0.0))) for trade in trades]) if trades else float(order_payload.get("avgPrice") or 0.0)
        realized_pnl = sum(float(trade.get("realizedPnl", 0.0)) for trade in trades)
        fees = sum(float(trade.get("commission", 0.0)) for trade in trades)
        net_pnl = realized_pnl - fees
        reference = float(reference_price or order_payload.get("price") or order_payload.get("avgPrice") or 0.0)
        side = str(order_payload.get("side") or (trades[0].get("side") if trades else "BUY")).upper()
        if side == "SELL":
            slippage_abs = reference - average_fill_price if reference else 0.0
        else:
            slippage_abs = average_fill_price - reference if reference else 0.0
        slippage_bps = (slippage_abs / reference * 10_000.0) if reference else 0.0
        lifecycle_state = {
            "NEW": "acknowledged",
            "PARTIALLY_FILLED": "partially_filled",
            "FILLED": "filled",
            "CANCELED": "canceled",
            "REJECTED": "rejected",
            "EXPIRED": "expired",
        }.get(current_status, "unknown")
        event = {
            "event_type": "order_lifecycle",
            "environment": self.environment,
            **_now_stamps(),
            "symbol": symbol.upper(),
            "client_order_id": client_order_id,
            "order_id": order_id,
            "current_status": current_status,
            "lifecycle_state": lifecycle_state,
            "fills_summary": {
                "fill_quantity": round(fill_quantity, 8),
                "average_fill_price": round(average_fill_price, 8),
                "realized_pnl": round(realized_pnl, 8),
                "fees": round(fees, 8),
                "net_pnl": round(net_pnl, 8),
                "slippage_abs": round(slippage_abs, 8),
                "slippage_bps": round(slippage_bps, 8),
                "trade_count": len(trades),
            },
            "order": redact_sensitive_testnet_fields(order_payload),
            "trades": redact_sensitive_testnet_fields(trades),
        }
        self._append_order_journal(event)
        return event

    def _confirm_order_by_client_order_id(self, symbol: str, client_order_id: str) -> Any:
        return self._signed_get("/fapi/v1/order", {"symbol": symbol.upper(), "origClientOrderId": client_order_id})

    def _signed_get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        signed_params = self._sign_params({**(dict(params or {})), "timestamp": int(datetime.now(UTC).timestamp() * 1000)})
        query = urllib.parse.urlencode(signed_params)
        return self.http_client.request("GET", f"{self.base_url}{path}?{query}", headers={"X-MBX-APIKEY": self.credentials.api_key})

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


def _weighted_average(pairs: list[tuple[float, float]]) -> float:
    numerator = sum(quantity * price for quantity, price in pairs)
    denominator = sum(quantity for quantity, _ in pairs)
    return numerator / denominator if denominator else 0.0


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
