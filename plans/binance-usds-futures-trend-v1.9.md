# Binance USDS-M Futures Trend v1.9 — Signed Testnet Order Lifecycle Evidence

Created: UTC 2026-06-16 / 北京时间（UTC+8）2026-06-16

## Goal

Extend the signed **testnet** path so a submitted order is not treated as a fill until Binance confirms lifecycle and trade data. Record exchange-confirmed lifecycle, fills, fees, realized/net PnL, and slippage as runtime evidence.

Live/mainnet execution remains unimplemented and unauthorized.

## Scope

- Add `BinanceTestnetBroker.track_order_lifecycle(symbol, client_order_id, reference_price)`.
- Query signed testnet endpoints only:
  - `GET /fapi/v1/order` by `origClientOrderId`;
  - `GET /fapi/v1/userTrades` by `orderId`.
- Map Binance order statuses to internal lifecycle states:
  - `NEW -> acknowledged`
  - `PARTIALLY_FILLED -> partially_filled`
  - `FILLED -> filled`
  - `CANCELED -> canceled`
  - `REJECTED -> rejected`
  - `EXPIRED -> expired`
- Compute fill metrics from exchange-confirmed trades:
  - filled quantity;
  - average fill price;
  - realized PnL;
  - fees;
  - net PnL;
  - adverse slippage absolute value and bps using side-aware direction (`BUY: fill - reference`, `SELL: reference - fill`);
  - trade count.
- Append lifecycle records to the existing order journal with `event_type=order_lifecycle`.
- Add explicit CLI flag `--testnet-track-order-lifecycle`.
- Integrate lifecycle tracking into `run_testnet_trading_cycle` only when:
  - signed testnet submission is explicitly enabled via `--testnet-submit-signed` / `dry_run=False`; and
  - lifecycle tracking is explicitly enabled.

## Non-goals

- No live/mainnet order submission.
- No default signed testnet submission.
- No lifecycle polling during dry-run.
- No websocket user stream yet; this version uses REST polling only.
- No committed runtime order/fill state from real accounts.

## Safety Invariants

- `--run-testnet-cycle` remains dry-run by default.
- Signed testnet orders still require explicit `--testnet-submit-signed`.
- Lifecycle polling requires an additional explicit flag.
- All evidence must redact signatures, headers, API keys, and secrets.
- Runtime evidence must include UTC and 北京时间（UTC+8） timestamps.
- Trading intervals remain `>=1h`.

## Tests

Add RED/GREEN coverage for:

1. Direct broker lifecycle tracking:
   - polls `/fapi/v1/order` by `origClientOrderId`;
   - polls `/fapi/v1/userTrades` by `orderId`;
   - maps `FILLED` to `filled`;
   - computes quantity, average fill price, realized PnL, fees, net PnL, and slippage;
   - writes redacted order journal lifecycle row.
2. Shared testnet cycle integration:
   - after signed testnet order submission, lifecycle tracking attaches `testnet_order_lifecycle`;
   - runtime record includes tracked/filled order counts and aggregate net PnL;
   - `userTrades` is queried only when explicit lifecycle tracking is enabled.

## Verification

Run:

```bash
python3 -m unittest tests.test_binance_usds_futures_trend.BinanceUsdsFuturesTrendTests.test_testnet_broker_tracks_filled_order_lifecycle_with_trade_pnl_and_slippage -v
python3 -m unittest tests.test_binance_usds_futures_trend.BinanceUsdsFuturesTrendTests.test_run_testnet_trading_cycle_tracks_signed_order_lifecycle_when_enabled -v
python3 -m unittest tests.test_binance_usds_futures_trend -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
git diff --check
```
