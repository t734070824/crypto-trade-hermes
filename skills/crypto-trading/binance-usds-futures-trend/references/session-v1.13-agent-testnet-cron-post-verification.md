# Session v1.13 — Agent testnet cron post-verification and safe summarization

## Context

During a single-agent signed Binance Futures Testnet cron run, the operational wrapper completed the required flow:

1. load `.env` without printing secrets;
2. signed read-only account preflight with `BinanceTestnetBroker(..., dry_run=False).fetch_signed_account_snapshot()`;
3. signed BTC group cycle on `BTCUSDT` with account-risk sizing (`risk_unit=0.001`, `account_risk_fraction=0.003`, `target_leverage=2`, current conservative `max_symbol_exposure=70`, `max_order_count=3`);
4. signed Alt group cycle on `ETHUSDT,SOLUSDT,BNBUSDT` with account-risk sizing (`risk_unit=0.1`, `account_risk_fraction=0.003`, `target_leverage=2`, current conservative `max_symbol_exposure=70`, `max_order_count=6`);
5. post-cycle signed account snapshot;
6. Chinese Telegram-safe summary without raw JSON.

The run produced a safe summary, but a tool transport anomaly reported corrupted terminal arguments while still returning command output. The follow-up verification used separate signed snapshot and runtime/journal parsing probes before final reporting.

## Durable workflow lesson

For signed-testnet cron summaries, do not rely solely on the first wrapper's prose when any anomaly appears in tool output. Add a short independent verification pass before final delivery:

- signed post-snapshot probe against `https://testnet.binancefuture.com` for selected symbols only;
- parse the latest runtime JSONL records for `environment`, `symbols`, `primary_interval`, `desired_orders`, lifecycle summary, and schema version;
- parse the latest order journal events for broker order statuses and lifecycle states;
- report only safe aggregate fields, never raw cycle JSON, signed URLs, signatures, headers, API-key values, or full account payloads.

## Safe verification snippets

Use these patterns inside a shell that has loaded `.env` with `set -a; . ./.env; set +a; ...`; never print secret values.

### Post-cycle selected-symbol snapshot

```python
from scripts.binance_trend_core.brokers import BinanceTestnetBroker, resolve_binance_testnet_credentials
from scripts.binance_usds_futures_trend import sanitize_error_message

selected = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}
broker = BinanceTestnetBroker(
    credentials=resolve_binance_testnet_credentials(),
    dry_run=False,
    base_url="https://testnet.binancefuture.com",
)
snapshot = broker.fetch_signed_account_snapshot()
positions = snapshot.get("positions", []) if isinstance(snapshot, dict) else []
open_orders = snapshot.get("open_orders", []) if isinstance(snapshot, dict) else []
nonzero = []
for row in positions if isinstance(positions, list) else []:
    symbol = str(row.get("symbol", "")).upper()
    if symbol not in selected:
        continue
    amount = float(row.get("positionAmt") or 0.0)
    if abs(amount) > 1e-12:
        nonzero.append({
            "symbol": symbol,
            "positionAmt": str(row.get("positionAmt")),
            "entryPrice": str(row.get("entryPrice")),
            "unRealizedProfit": str(row.get("unRealizedProfit")),
        })
selected_open_orders = [
    row for row in open_orders
    if isinstance(row, dict) and str(row.get("symbol", "")).upper() in selected
] if isinstance(open_orders, list) else []
```

### Runtime + order journal cross-check

```python
import json
from pathlib import Path

runtime = Path("state/binance-usds-futures-trend-testnet-runtime.jsonl")
journal = Path("state/binance-usds-futures-trend-testnet-orders.jsonl")

def load_last(path: Path, n: int):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except Exception as exc:
            out.append({"parse_error": exc.__class__.__name__})
    return out

records = load_last(runtime, 2)
journal_events = load_last(journal, 6)
```

## Interpretation notes

- `runtime_record.execution_events.testnet_order_lifecycle` is the safest compact lifecycle source for tracked/filled counts and net PnL.
- If runtime JSONL omits full fill details in the compact record, use the order journal for broker-level submitted/rejected statuses and lifecycle events.
- A BTC group with `desired_orders=0`, no real order, and an existing BTC position is a successful reconciliation no-op, not a failed operation.
- If the wrapper output contains an odd secret-status string (for example masked text instead of `present`/`missing`), verify credential presence separately and report only `present`/`missing`.
