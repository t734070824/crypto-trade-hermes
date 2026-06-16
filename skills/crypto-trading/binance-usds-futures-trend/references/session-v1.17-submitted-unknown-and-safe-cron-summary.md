# Session v1.17 — submitted_unknown handling and safe signed-cron summaries

## Context

A single agent-type Binance USDS-M Futures testnet cron ran the required sequence:

1. Load `.env` without printing secrets.
2. Build `BinanceTestnetCredentials` from `LALA_KEY` / `LALA_SECRET`.
3. Use `BinanceTestnetBroker(..., dry_run=False, base_url="https://testnet.binancefuture.com")` for signed account preflight.
4. Run BTC and Alt signed testnet cycles on `--interval 1h` with `--base-url https://testnet.binancefuture.com`.
5. Replay runtime evidence.
6. Post-run signed snapshot for selected symbols.

## Durable lessons

- Treat `submitted_unknown` as **attempted but not exchange-confirmed**. Do not count it as accepted/filled even if `real_order_submitted=true`; report it separately as an uncertain signed submission requiring reconciliation.
- If `confirm_status=failed` and `confirm_error_type=HTTPError`, say exactly that in sanitized form. Do not infer order acceptance, open-order presence, or fill lifecycle from the attempted POST.
- For Telegram-safe summaries, include both counts:
  - `real_order_events_count` / attempted signed requests; and
  - confirmed accepted/acknowledged/fill lifecycle counts.
  If the latter is zero, say confirmed accepted=0.
- After signed cycles, inspect post-run signed snapshot plus latest runtime/order-journal evidence. Runtime evidence gives grouped statuses/reasons; order journal gives per-order `status`, `error_type`, `confirm_status`, and `order_type` without exposing signatures.
- If existing positions already have open algo TP/SL, report ordinary open orders and open algo order counts separately. Do not claim missing protection from `/fapi/v1/openOrders` alone.
- Rejections such as `max_symbol_exposure_exceeded` and `exchange_min_qty_not_met` are useful evidence, not cron failure by themselves when the cycle returns `ok=true` and errors_count=0.

## Safe summary wording

Use wording like:

> 本轮真实 testnet 下单请求有 attempted=N，但状态为 `submitted_unknown` 且 confirm 失败；因此 confirmed accepted=0，不视为已成交或已 accepted。

## Command-building pitfall

When constructing signed-cycle commands programmatically, preserve option/value pairs exactly. A malformed list that leaves `--base-url` without its URL causes argparse failure before any trading cycle runs. If that happens, correct the command and rerun; do not report the argparse attempt as a trading result.
