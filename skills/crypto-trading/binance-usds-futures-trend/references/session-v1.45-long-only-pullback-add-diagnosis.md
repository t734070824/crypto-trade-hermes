# Session v1.45 — Long-only pullback add diagnosis

## Durable lesson

When the user asks why recent testnet adds are all `long` while the 1h chart looks downward, diagnose the signal semantics before assuming execution error.

Current trend signal is long-only and slow by design: `hold_long` is emitted when the major trend filter remains valid (`close > EMA200` and `EMA50 > EMA200`). This can coexist with a local 1h pullback where price is below EMA50 or the recent 6h/12h slope is negative.

## Diagnostic pattern

1. Read runtime/order-journal evidence to separate actual BUY/adds from SELL reductions/rebalances.
2. For each BUY/add, inspect the linked signal metadata: action, `current_exposure`, `desired_exposure`, EMA50/EMA200, reference close, and candle time.
3. Recompute or inspect 1h candles using the same candle semantics as the engine.
4. Explicitly check whether the latest Binance 1h candle was still open at the cron run time. A run at `HH:05` may be using a just-opened incomplete `HH:00` candle unless code drops it.
5. Explain the distinction:
   - major trend long: close above EMA200 and EMA50 above EMA200;
   - local pullback/downtrend: close below EMA50 or recent slope negative;
   - execution add: `desired_exposure - current_exposure > exchange minimum`.

## Strategy implication

If the intent is to avoid adding during visible 1h declines while still staying in the main trend, do not simply flip to `flat` or `short`. Current code implements the safer first step:

- use only closed 1h candles for signal generation by dropping the currently forming Binance candle;
- allow existing long holds when major trend remains valid, but block new/additional long exposure if `close < EMA50` or recent 6/12-candle slope is negative;
- split signal/execution semantics with `add_allowed`, `add_blockers`, `hold_existing_allowed`, and `market_regime` fields rather than treating every `hold_long` as add permission;
- position reconciliation clips positive deltas back to current exposure when `add_allowed=false`, while still allowing reductions and protection repair;
- keep strategy evidence-based: compare future candidate rules through runtime replay/order-journal evidence before promotion.

## Reporting guidance

For user-facing explanations, be concise and label times in UTC and 北京时间（UTC+8）. State whether the issue is strategy logic, execution reconciliation, or data/candle timing. In this pattern, the root cause is usually strategy logic/candle semantics, not Binance or cron failure.