# Session v1.14 — Agent cron wrapper for signed testnet cycles and safe summaries

Use this note when operating the single agent-type Binance USDS-M Futures Testnet cron and the final delivery must be a concise Chinese Telegram-safe report rather than raw cycle JSON.

## Durable workflow

1. Load `.env` with `set -a; . ./.env; set +a; ...`, but only report `LALA_KEY` / `LALA_SECRET` as `present` or `missing`.
2. In Python, construct `BinanceTestnetCredentials(api_key=os.environ["LALA_KEY"], api_secret=os.environ["LALA_SECRET"])` and instantiate `BinanceTestnetBroker(dry_run=False, base_url="https://testnet.binancefuture.com")`.
3. Run `fetch_signed_account_snapshot()` before any cycle. If it fails, stop immediately and report only sanitized `error_type` / sanitized message.
4. Execute the required signed cycles sequentially, with public K-lines forced through `--base-url https://testnet.binancefuture.com` and signed broker endpoint guarded by the adapter/testnet default:
   - BTC group: `BTCUSDT`, `--risk-unit 0.001`, `--account-risk-fraction 0.003`, `--target-leverage 2`, `--testnet-max-order-count 3`.
   - Alt group: `ETHUSDT,SOLUSDT,BNBUSDT`, `--risk-unit 0.1`, `--account-risk-fraction 0.003`, `--target-leverage 2`, `--testnet-max-order-count 6`.
   - Shared risk: `--testnet-max-order-notional 200 --testnet-max-symbol-exposure 70 --testnet-max-daily-loss 10 --testnet-sync-account-state --testnet-track-order-lifecycle --testnet-order-journal-file state/binance-usds-futures-trend-testnet-orders.jsonl`.
5. Parse each cycle JSON in the wrapper and summarize only safe fields: `ok`, environment, symbols, interval, desired order count, fill count, fill status counts, lifecycle count, lifecycle filled count, real-order-submitted flag, error count, runtime record path, and sanitized risk limits.
6. Run runtime evidence replay after the cycles:
   `scripts/binance_usds_futures_trend.py --replay-runtime-evidence --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl --max-drawdown-worsening-limit 0.03`.
   Summarize `baseline_variant`, `selected_variant`, candidate eligibility/guardrail flags, `errors_count`, and `defaults_changed`; do not promote or edit strategy automatically.
7. Fetch a post-cycle signed snapshot independently and summarize only selected-symbol non-zero positions, ordinary open-order count, and open algo TP/SL count.
8. Verify append-only evidence files exist and print line-count/last-record metadata if useful:
   - `state/binance-usds-futures-trend-testnet-runtime.jsonl`
   - `state/binance-usds-futures-trend-testnet-orders.jsonl`

## Reporting pattern

- Chinese, concise, no raw JSON dumps.
- Every timestamp line must label both UTC and 北京时间（UTC+8）.
- Explicitly say when a successful cycle submitted no orders because position reconciliation found no delta; this is duplicate-add prevention, not a failed operation.
- Report rejected orders by count/status only unless a sanitized reason is needed.
- Never include signed request URLs, signatures, headers, API key values, or full account payloads.

## Pitfalls caught

- A cycle can be successful with `desired_orders=[]`, `fills=[]`, and `real_orders_submitted=false` when remote positions already match desired exposure.
- In multi-symbol alt cycles, accepted/submitted order count should be checked against `--testnet-max-order-count`; rejected protective/order events may appear in `fills` but should not be treated as accepted submissions.
- The runtime evolution command can return `ok=true` even when the selected diagnostic variant differs from baseline; this is evidence for review only and must not mutate defaults during cron.
