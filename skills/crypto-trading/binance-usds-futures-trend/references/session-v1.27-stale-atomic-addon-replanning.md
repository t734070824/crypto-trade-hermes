# Session v1.27 — stale atomic add-on replanning

## Durable lesson

When the strategy emits an atomic order group for an existing symbol, do not blindly execute the original entry/add quantity if the signed account snapshot already reflects the desired target exposure. In this codebase, `strategy.position_size` means **target total position**, not “additional quantity to buy now”. The execution layer must reconcile `desired_exposure - current_exposure` and submit only the delta that remains above exchange minimums.

## Correct handling pattern

- For existing-position atomic groups, refresh the signed account state before submission and replan from current exposure.
- Preserve priority ordering so repair/protection for existing positions is not displaced by same-symbol add-ons.
- For atomic add-on replans, filter duplicate protective orders instead of letting refreshed replans re-emit an entire duplicate SL/TP bundle.
- Leave new-entry atomic groups intact so first entry + stop + take-profit bundles still submit together.
- Treat `desired_orders=[]` / no real submission as success when reconciliation proves the current signed position already equals or exceeds target exposure.

## Regression shape

Add a focused regression where:

1. Strategy output requests an atomic add-on for a symbol.
2. `broker.get_account_state()` already reports the target position after earlier fills or remote state sync.
3. The loop replans and emits no duplicate add-on order.
4. Existing-position repair/protection priority still outranks same-symbol add-ons.

Then run the focused test plus the full Binance trend unittest suite before commit.

## Reporting guidance

In Telegram/user summaries, call this “delta-only reconciliation / duplicate-add prevention,” not a failed order cycle. Include a fresh signed post-cycle snapshot when available.