# Session v1.24: testnet order-budget and post-run reconstruction notes

## What changed this session
- Signed testnet cycles can pass risk sizing yet still reject a later protective tranche when `max_order_count` is consumed by the entry and earlier protection orders.
- The BTC group ran with `max_order_count=3`; entry + stop + first TP already used the order budget, so the second TP was rejected with `max_order_count_exceeded`.
- Post-cycle reporting was reconstructed from three sources rather than stdout alone:
  1. runtime JSONL,
  2. append-only order journal,
  3. fresh signed account snapshot.
- `submitted_unknown` must stay counted as attempted but not exchange-confirmed.
- A fresh signed snapshot is still required after the cycle to verify non-zero positions, ordinary open orders, and `openAlgoOrders` protection counts.

## Durable operating lesson
When using account-risk sizing plus tranches, budget order count explicitly for the full lifecycle plan:
- entry,
- stop loss,
- each take-profit tranche,
- any replacement/repair order.

If the order budget is tight, the engine should either:
- reduce the number of TP tranches, or
- lower the entry/protection order count before submission.

Do not treat a risk-correct position size as sufficient if the order-count cap can still reject protection.
