# Session v1.21 — single-agent signed testnet cron execution summary harness

## Context

A scheduled agent-mode cron ran the Binance USDS-M Futures Testnet workflow end-to-end for the fixed startup scope:

- BTC group: `BTCUSDT`, `--risk-unit 0.001`, `--account-risk-fraction 0.003`, `--target-leverage 2`, `--testnet-max-order-count 3`.
- Alt group: `ETHUSDT,SOLUSDT,BNBUSDT`, `--risk-unit 0.1`, `--account-risk-fraction 0.003`, `--target-leverage 2`, `--testnet-max-order-count 6`.
- Shared endpoint and risk caps: `--base-url https://testnet.binancefuture.com`, `max_order_notional=200`, `max_symbol_exposure=70`, `max_daily_loss=10`, `--interval 1h`.

The user required a Telegram-safe Chinese summary, no raw JSON, no secret disclosure, signed preflight before any order path, post-run signed snapshot, and runtime replay after cycles.

## Reusable harness pattern

When stdout may be too large or unsafe to paste, run a small Python harness from the repo after loading `.env`:

1. Load `.env` into environment with `set -a; . ./.env; set +a; ...` but never print values.
2. Build `BinanceTestnetCredentials(api_key=os.environ["LALA_KEY"], api_secret=os.environ["LALA_SECRET"])` and `BinanceTestnetBroker(..., dry_run=False, base_url="https://testnet.binancefuture.com")`.
3. Call `fetch_signed_account_snapshot()` before cycles; if it fails, stop before orders and report only sanitized error type/message via `sanitize_error_message`.
4. Run the BTC and Alt CLI commands via `subprocess.run(..., stdout=PIPE, stderr=PIPE)`, parse JSON in-memory, and summarize safe fields only.
5. Count both:
   - `attempted_real_order_count`: fills with `attempted_real_order_submitted` or `real_order_submitted`.
   - `exchange_confirmed_count`: fills with status `submitted` or `submitted_confirmed`.
   Treat `submitted_unknown` as attempted but not exchange-confirmed.
6. Run `--replay-runtime-evidence` read-only and summarize `baseline_variant`, `selected_variant`, variants, guardrail flags, `errors_count`, records, symbols, intervals, and environments.
7. Fetch a fresh post-cycle signed snapshot and summarize only selected-symbol position amount, entry price, unrealized PnL, ordinary open-order count, open-algo count, stop count, and take-profit count.
8. Include runtime record and order journal paths plus file existence/line counts. Do not paste raw runtime/order-journal JSON.

## Observed reporting nuance

A successful CLI exit with `ok=true` can still contain operational warnings:

- `submitted_unknown` means a signed request was attempted, but acceptance/fill is not exchange-confirmed unless later confirmation finds it.
- `protection_verification.all_positions_protected=false` should be reported even if some protective algo orders exist. The summary should list per-symbol stop and take-profit counts from `/fapi/v1/openAlgoOrders`.
- Per-cycle `--testnet-max-order-count` can cap accepted/submitted operations before all desired entry/stop/TP instructions are accepted. Do not equate `desired_orders_count` with accepted protection.

## Safe final report fields

For each group, report:

- symbols and interval;
- success/returncode/parsed JSON status;
- desired orders count;
- fills count;
- fills by status and order type;
- attempted real order count;
- exchange-confirmed submitted/submitted_confirmed count;
- lifecycle event count and lifecycle states;
- runtime record saved/path;
- risk limits;
- `all_positions_protected` and `unprotected_symbols` when present.

For the post snapshot, report only selected-symbol non-zero positions and counts of ordinary orders/open-algo TP/SL. Keep all timestamps labeled UTC and 北京时间（UTC+8）.
