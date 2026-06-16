# Session v1.4 — Core Interface Extraction Workflow

## Durable Pattern

When moving the Binance USDS-M futures trend project from a scanner toward a shared realtime trading engine, first extract stable interfaces and lightweight dataclasses without changing CLI behavior or execution safety. Keep this as a boundary-setting refactor, not a strategy or broker implementation change.

## TDD Shape

1. Add RED tests before production code:
   - every new core module imports;
   - `BrokerAdapter` exposes `environment`, `submit_order`, `cancel_order`, and `get_account_state`;
   - existing scan CLI still emits `mode=paper`, `portfolio_allocation`, and `paper_lifecycle` when requested;
   - short interval rejection still applies through any wrapper path.
2. Run the targeted tests and confirm they fail because `scripts.binance_trend_core` is missing, not because of test typos.
3. Add minimal package skeleton under `scripts/binance_trend_core/`:
   - `types.py` for shared request/intent dataclasses;
   - `market_data.py` for free public market-data abstraction;
   - `signals.py` for wrappers around existing `decide` / scan functions;
   - `strategy.py`, `risk.py`, `portfolio.py`, `execution.py` for shared loop boundaries;
   - `brokers.py` for adapter isolation;
   - `runtime.py` for v1.3 runtime record builder/writer wrappers.
4. Use a safe default broker such as `RejectingBrokerAdapter` that exposes the future execution interface but raises on `submit_order`.
5. Do not wire testnet/live, HMAC, signed endpoints, or real order placement in the same change.

## Verification Pattern

Run all of these before commit/push:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
git diff --check
```

Then run a real Binance public-data no-write scan using only `>=1h` intervals and confirm:

- `mode=paper`;
- UTC and 北京时间（UTC+8） timestamps are present;
- `errors_count=0` or any network/API blocker is reported honestly;
- `runtime_record_saved=false` when `--no-save-runtime-record` is set;
- `execution_events.real_orders_submitted=false`.

## Review Checklist

Before push, independent review should verify:

- interface extraction stayed in v1.4 scope;
- no signed endpoint, HMAC, API key/secret, or order-submission path was added;
- paper/testnet/live divergence is isolated to `BrokerAdapter` design;
- `<1h` interval rejection still works;
- CLI JSON compatibility is preserved;
- docs/Skill version and roadmap reflect the implemented interface package;
- ignored runtime state or `__pycache__` files are not committed.
