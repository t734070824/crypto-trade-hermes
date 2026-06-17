# Session v1.39 — Testnet protection reconciliation and submitted_unknown fixes

## Trigger

A `testnet-agent-hourly` review showed two related anomalies in recent output:

- protection status could be inconsistent between groups, e.g. a BTC-only cycle reflecting unrelated ETH/SOL/BNB account-wide protection gaps;
- the recent window contained `submitted_unknown` / `rejected` events involving protective orders.

## Durable root causes

1. **Account snapshot scope vs cycle scope**
   - Signed account snapshots are account-wide.
   - Hourly runner groups are cycle-scoped (`BTCUSDT` vs `ETHUSDT,SOLUSDT,BNBUSDT`).
   - Protection verification must filter positions to the current cycle's `selected_symbols`; otherwise one group's report can inherit another group's protection state.

2. **Binance conditional protection orders are algo orders**
   - STOP/TAKE_PROFIT protection submits through the futures algo endpoint and uses `clientAlgoId`.
   - Ordinary order confirmation with `/fapi/v1/order?origClientOrderId=...` is not the right confirmation path for these conditional algo orders.
   - When a POST times out or the response is ambiguous, conditional algo confirmation should query `/fapi/v1/algoOrder` with `clientAlgoId`.

3. **`submitted_unknown` reconciliation needs both open order namespaces**
   - Ordinary open orders expose `clientOrderId`.
   - Open algo orders expose `clientAlgoId`.
   - A local unknown event for a TP/SL order is safely matched only if reconciliation checks `open_algo_orders[].clientAlgoId` as well as `open_orders[].clientOrderId`.

## Implementation pattern

- Keep ordinary order behavior unchanged:
  - confirm via `/fapi/v1/order` with `origClientOrderId`.
- For conditional algo orders:
  - confirm via `/fapi/v1/algoOrder` with `clientAlgoId`.
- Feed the full signed `account_snapshot` into reconciliation, not only `open_orders`, so `open_algo_orders` are available.
- Call protection verification with `selected_symbols` for the current cycle.

## Regression tests to add/keep

- scoped protection verification ignores non-selected account positions;
- ordinary submitted-unknown still confirms by `origClientOrderId`;
- conditional algo submitted-unknown confirms by `clientAlgoId` on `/fapi/v1/algoOrder`;
- reconciliation matches unknown local algo orders against `open_algo_orders[].clientAlgoId`;
- hourly wrapper tests still pass.

## Review and git workflow note

Before push, stage only durable code/tests/skill-reference changes. Restore or exclude `cron/jobs.json` runtime timestamp/counter noise before independent review, and re-check again after push because the scheduler can rewrite it during tests or review.
