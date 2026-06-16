# Session v1.15 — Testnet open-algo TP/SL reconciliation and account-risk sizing

Use this note when operating or modifying the Binance USDS-M Futures testnet agent cron and execution loop.

## Durable lessons

1. **TP/SL may be invisible in ordinary open-order queries.** On Binance USDS-M Futures testnet, position protection can live under the algo-order API rather than `/fapi/v1/openOrders`. A snapshot that only checks ordinary open orders can falsely report “no stop loss / take profit.” Always include open algo orders when verifying protection.

2. **Protective conditional orders must be reconciled before creating new ones.** If an existing position already has `STOP_MARKET` and `TAKE_PROFIT_MARKET` algo orders with `closePosition=true` / reduce-only semantics, the execution loop should avoid duplicating protection orders.

3. **Open-algo query failures must fail closed.** Do not interpret failure to query open algo orders as “no protection exists.” Surface the error and prevent unsafe duplicate/unprotected signed actions unless explicitly handled.

4. **Cron summaries need post-run independent signed verification.** After a signed testnet cron claims a position is protected or no-op reconciled, independently check selected-symbol position, ordinary open orders, open algo orders, and latest runtime/order-journal evidence before reporting final status.

5. **Sizing should be account/risk based, not fixed quantity first.** Keep `risk_unit` only as a legacy/default floor or compatibility input. Prefer sizing from account equity, `account_risk_fraction`, target leverage, symbol exposure cap, max order notional, max daily loss, exchange `minQty/stepSize/MIN_NOTIONAL`, and current remote position. Submit only the delta between desired exposure and Binance-confirmed position.

## Verification checklist for future sessions

- Signed account snapshot includes positions, ordinary open orders, and open algo orders.
- BTC/alt position reports distinguish testnet from live/mainnet.
- TP/SL status is derived from algo-order state when applicable.
- Existing TP/SL prevents duplicate protective order creation.
- Dry-run/no-op cycles explain whether no orders were submitted because desired exposure already matched current position.
- Risk sizing output shows account-risk fraction, target leverage, exposure cap, max order notional, max daily loss, and current notional exposure.
- Telegram-safe summaries include only safe fields and explicit UTC / 北京时间（UTC+8） labels; never paste raw signed payloads or request URLs.
