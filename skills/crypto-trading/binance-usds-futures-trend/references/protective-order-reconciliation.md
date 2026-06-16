# Protective order reconciliation: stale TP replacement and stop dedup

Use this reference when debugging Binance USDS-M testnet/live cycles that show duplicate `STOP_MARKET` / `TAKE_PROFIT_MARKET` algo orders, repeated trigger lines, or protective-order drift after a sizing/risk cap change.

## Durable pattern

- Treat strategy output `position_size` / `desired_exposure` as the target total position. Execution should reconcile delta only against current remote exposure.
- Before planning new take-profit coverage, classify existing TP algo orders:
  - If TP trigger price still matches a currently configured TP layer, keep it and count its quantity toward layer coverage.
  - If TP trigger price no longer matches any configured layer, mark it stale, emit a `CANCEL_ALGO_ORDER`, and exclude it from TP coverage so replacements are planned.
  - Do **not** cancel same-price undercovered TP layers; top them up. This preserves the existing partial-fill/top-up behavior.
- For long stop-loss protection:
  - Gather all safe SELL close-position/reduce-only `STOP` / `STOP_MARKET` orders.
  - Keep the tightest long stop: highest trigger price.
  - Cancel only looser duplicate stops that are already redundant because a tighter safe stop is visible in portfolio state.
  - When trailing stop moves up, submit the tighter stop first and do not cancel the older lower stop in the same blind plan. A later reconciliation cycle can remove the lower duplicate after the tighter stop is confirmed visible.

## Safety notes

- TP cancel-before-replace is acceptable because TP absence does not create downside naked-long risk as long as stop-loss protection remains present.
- Stop-loss replacement must remain fail-closed/add-before-remove; never leave a long position without a safe stop because a replacement order might be rejected or end unknown.
- Use stable protection keys (`algoId`, `clientAlgoId`, `orderId`, `clientOrderId`) to exclude stale orders from coverage calculations without excluding unrelated valid protection.

## Regression tests to add/keep

- Stale TP layers: old TP trigger prices are slightly different from new configured layers; plan should include `CANCEL_ALGO_ORDER` for stale TPs plus replacement TP orders for full target coverage.
- Duplicate stop-loss: two safe long stops exist; plan should cancel only the lower/looser stop and should not submit another stop if the tightest stop already matches the current trailing stop.
- Existing top-up behavior: same-price but undercovered TP layers should not be cancelled; plan should add only missing quantities.

## Verification command

```bash
python3 -m unittest tests.test_binance_usds_futures_trend -v
```

Expected after the June 2026 fix: all tests in that module pass, including protective-order reconciliation, TP top-up, and testnet broker/journal coverage.
