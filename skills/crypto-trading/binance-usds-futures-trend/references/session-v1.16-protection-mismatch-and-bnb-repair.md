# Session v1.16 — Protection mismatch and symbol-scoped repair

## Durable lesson

When a Binance USDS-M Futures testnet position is reported as missing TP/SL, verify with signed account snapshot that includes both ordinary `openOrders` and algo `openAlgoOrders`. Protective stop/take-profit orders may exist only under the Algo Order API.

## Protection mismatch definition

For a long position, protective orders are expected to be algo conditional SELL orders:

- `STOP_MARKET` for stop loss;
- `TAKE_PROFIT_MARKET` for take profit;
- `closePosition=true` and/or `reduceOnly=true` semantics;
- trigger prices consistent with the current strategy signal/lifecycle state.

Mismatch classes:

1. Missing protection: non-zero position but no stop-loss and/or take-profit algo order.
2. Wrong side/type: e.g. long position protected by BUY order or missing expected order type.
3. Unsafe close semantics: not close-only/reduce-only when it should protect an existing position.
4. Stale trigger price: remote trigger is materially different from the current desired stop/take-profit.
5. Duplicate/stale groups: multiple old TP/SL groups can produce unpredictable exits.

Current implementation repairs missing protection and has a conservative trailing-stop supplement path: if an existing stop-loss algo order is found and the newly computed trailing stop is higher, it submits an additional tighter `STOP_MARKET` rather than cancelling the old stop first. It does not loosen stops, broadly deduplicate stale TP groups, or cancel/replace existing take-profit ladders.

## Safe repair pattern used

1. Fetch signed snapshot for the affected symbol only.
2. Confirm non-zero position and missing `open_algo_orders`.
3. Run a symbol-scoped signed testnet cycle for that symbol with tight caps and account sync/lifecycle tracking, e.g. `--symbols BNBUSDT --run-testnet-cycle --testnet-submit-signed --testnet-sync-account-state --testnet-track-order-lifecycle` plus the standard testnet endpoint/risk flags.
4. Independently fetch another signed snapshot for the same symbol.
5. Report only safe fields: UTC/北京时间 timestamps, position size/entry/mark/notional/leverage/margin type, counts, order types, side, trigger price, closePosition/reduceOnly, clientAlgoId/algoId if useful. Never paste raw signed URLs or credentials.

## Reporting guidance

Explain to the user that:

- “保护单失配” means remote TP/SL protection and the desired/current position protection disagree.
- Missing TP/SL is the urgent repair case.
- Existing code can supplement missing `STOP_MARKET`/`TAKE_PROFIT_MARKET`; full stale-price replacement requires explicit cancel/replace logic.
