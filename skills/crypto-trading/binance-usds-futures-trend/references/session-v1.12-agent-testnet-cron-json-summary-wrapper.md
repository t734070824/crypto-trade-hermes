# Session v1.12 — Agent Testnet Cron JSON Summary Wrapper

## Context

A single agent-mode Binance USDS-M Futures Testnet cron owns the startup signed-testnet operation:

- environment: Binance Futures Testnet endpoints only;
- public K-lines must also use `--base-url https://testnet.binancefuture.com` in this cron, not the default mainnet public base URL;
- interval: `1h`;
- BTC group: `BTCUSDT`, `risk_unit=0.001`, `--testnet-max-order-count 1`;
- Alt group: `ETHUSDT,SOLUSDT,BNBUSDT`, `risk_unit=0.1`, `--testnet-max-order-count 2`;
- shared limits: `--testnet-max-order-notional 200`, `--testnet-max-symbol-exposure 250`, `--testnet-max-daily-loss 10`;
- signed account sync before each cycle and signed snapshot again after the cycles;
- no raw JSON or signed request detail in the final Telegram-facing report.

The split groups avoid using one universal quantity across very different symbol prices and exchange minimums. Dry-run against testnet `exchangeInfo` before adding more recurring signed symbols.

## Reusable Cron Wrapper Pattern

Use a small Python/shell wrapper from the repository root after loading `.env` with `set -a; . ./.env; set +a; ...`.

1. Resolve credentials via `resolve_binance_testnet_credentials()` and report only `present`/`missing` for `LALA_KEY` and `LALA_SECRET`.
2. Instantiate `BinanceTestnetBroker(credentials=..., dry_run=False)`; the broker enforces the exact testnet hostname.
3. Run a read-only preflight using `fetch_signed_account_snapshot()` across the account.
4. If preflight fails, stop immediately; do not run `--testnet-submit-signed`.
5. Execute the conservative BTC group:

```bash
scripts/binance_usds_futures_trend.py \
  --run-testnet-cycle \
  --base-url https://testnet.binancefuture.com \
  --symbols BTCUSDT \
  --interval 1h \
  --limit 240 \
  --risk-unit 0.001 \
  --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl \
  --testnet-submit-signed \
  --testnet-sync-account-state \
  --testnet-track-order-lifecycle \
  --testnet-max-order-notional 200 \
  --testnet-max-symbol-exposure 250 \
  --testnet-max-daily-loss 10 \
  --testnet-max-order-count 1 \
  --testnet-order-journal-file state/binance-usds-futures-trend-testnet-orders.jsonl
```

6. Execute the conservative Alt group:

```bash
scripts/binance_usds_futures_trend.py \
  --run-testnet-cycle \
  --base-url https://testnet.binancefuture.com \
  --symbols ETHUSDT,SOLUSDT,BNBUSDT \
  --interval 1h \
  --limit 240 \
  --risk-unit 0.1 \
  --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl \
  --testnet-submit-signed \
  --testnet-sync-account-state \
  --testnet-track-order-lifecycle \
  --testnet-max-order-notional 200 \
  --testnet-max-symbol-exposure 250 \
  --testnet-max-daily-loss 10 \
  --testnet-max-order-count 2 \
  --testnet-order-journal-file state/binance-usds-futures-trend-testnet-orders.jsonl
```

7. Parse both stdout payloads as JSON, but summarize only safe fields. Do not paste raw cycle JSON into Telegram.
8. Query `fetch_signed_account_snapshot()` again after both cycles and summarize only selected-symbol non-zero positions plus open-order count.
9. Use `sanitize_error_message(...)` on any exception/output included in the report.

## Safe Field Extraction Notes

The cycle JSON can evolve as the shared loop changes, so a wrapper should avoid relying only on one exact top-level path. A robust summary can recursively search for keys such as:

- `environment` — confirm values are `testnet`;
- `real_order_submitted` / `real_orders_submitted` — true only when an actual signed testnet order was submitted;
- `desired_orders` — count planned reconciliation orders by group;
- `fills` / `order_events` — count order/fill events by group;
- `status` / `reason` on fills — distinguish accepted submissions from risk/exchange rejections;
- `order_lifecycle` / `lifecycle_events` / `tracked_orders` / `trade_fills` — count lifecycle/trade polling evidence when present.

Always prefer signed post-cycle snapshot values for the final current-position/open-order summary.

## Example Interpretation

A successful run can have:

- BTC group `desired_orders=[]` because existing BTCUSDT position already equals desired exposure;
- Alt group desired orders for ETH/SOL/BNB;
- only the first two Alt orders accepted because `--testnet-max-order-count 2` is reached;
- later desired orders rejected as `max_order_count_exceeded`.

This should be reported as successful gated operation, not as a failed cycle, when `ok=true`, `errors=[]`, and the rejections are expected risk-cap behavior.

## Reporting Requirements

The final report should be compact Chinese and include:

- UTC timestamp;
- 北京时间（UTC+8） timestamp;
- success/failure;
- Binance Futures Testnet endpoints only, no live/mainnet endpoint;
- credential presence only, never values;
- signed preflight status;
- selected symbol groups;
- whether real testnet orders were submitted;
- desired-order count, fill/order status counts, and lifecycle count by group when available;
- current non-zero selected-symbol positions and open-order count from post-cycle signed snapshot;
- runtime evidence file path;
- order journal file path;
- key risk limits.
