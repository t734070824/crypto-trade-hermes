# Session v1.18 — Single-agent signed testnet cron JSON harness

## Context

A scheduled agent cron ran the Binance USDS-M Futures testnet operations loop end-to-end with the `binance-usds-futures-trend` Skill loaded. The user required a compact Chinese final report only; no direct Telegram/send-message call.

Hard runtime constraints used:

- testnet-only endpoint for public K-lines and signed endpoints: `--base-url https://testnet.binancefuture.com` plus broker default/testnet guard;
- signed account preflight before any cycle;
- BTC group: `BTCUSDT`, `--risk-unit 0.001`, `--account-risk-fraction 0.003`, `--target-leverage 2`, max 3 orders;
- Alt group: `ETHUSDT,SOLUSDT,BNBUSDT`, `--risk-unit 0.1`, same account risk/leverage, max 6 orders;
- shared limits: max order notional 200, max symbol exposure 70, max daily loss 10;
- runtime evidence replay after both cycles;
- post-cycle signed snapshot verification for selected-symbol positions, ordinary open orders, and open algo orders.

## Reusable pattern

For agent cron runs, a short Python harness is safer than pasting raw CLI JSON into the final report:

1. `set -a; . ./.env; set +a; python3 - <<'PY' ... PY` so credentials are loaded but never printed.
2. Import and use:
   - `BinanceTestnetCredentials(api_key=os.environ["LALA_KEY"], api_secret=os.environ["LALA_SECRET"])`;
   - `BinanceTestnetBroker(..., dry_run=False, base_url="https://testnet.binancefuture.com").fetch_signed_account_snapshot()`;
   - `sanitize_error_message` for any exception or stderr text included in the report.
3. Run each cycle with `subprocess.run(..., capture_output=True)` and parse stdout as JSON.
4. Summarize only safe fields: `ok`, `environment`, `symbols`, `interval`, `desired_orders` count, `fills` count, fill status counts, lifecycle count, runtime record path, risk limits, account sync summaries, reconciliation, and protection verification.
5. Treat `submitted_unknown` as attempted but not exchange-confirmed unless independent confirmation finds the order. Report `missing_unknown_client_ids` but never raw signed request/query details.
6. Run `--replay-runtime-evidence` after cycles and report only baseline/candidate/selected/guardrail/errors fields.
7. Fetch a fresh signed snapshot after cycles and summarize selected-symbol non-zero positions plus counts of ordinary open orders and open algo orders.

## Pitfalls reinforced

- `openAlgoOrders` count is not the same thing as confirmed protection. If `verify_position_protection` reports `missing_take_profit` despite open algo orders, report the mismatch as fail-closed; do not claim the position is fully protected.
- Lifecycle tracking may legitimately be zero when only protective algo orders are submitted/attempted or when submitted orders remain unconfirmed. Do not infer fills from submission attempts.
- For scheduled delivery, produce the final report directly. Do not call any messaging/send tool; the scheduler delivers the final response.
- Use both UTC and 北京时间（UTC+8） labels in final reports and in any parsed timestamps.
