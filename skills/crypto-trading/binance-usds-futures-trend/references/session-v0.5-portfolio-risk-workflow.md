# v0.5 Portfolio Risk Allocation Workflow

Created: UTC 2026-06-15 11:05:28 / 北京时间(UTC+8) 2026-06-15 19:05:28

## Trigger

Use this workflow when extending the Binance USDS-M futures paper scanner from ranked signals into portfolio-level paper allocation.

## Steps

1. Follow TDD strictly:
   - write tests for total budget cap, per-symbol cap, rank ordering, and invalid constraints;
   - run the new tests first and confirm RED;
   - implement only enough production code to pass;
   - run the targeted tests and then the full suite.
2. Add a pure allocation function before wiring CLI:
   - input: ranked decision list, `total_risk_budget`, `max_symbol_risk`;
   - only allocate to `hold_long` decisions with positive `rank_score` and positive `position_size`;
   - sort by `rank_score` descending;
   - allocate `min(position_size, max_symbol_risk, remaining_budget)`;
   - never exceed total budget.
3. Wire allocation into scan mode only when either `portfolio_risk_budget` or `max_symbol_risk` is provided.
4. Keep output `paper` and include UTC + 北京时间（UTC+8） timestamps in allocation output.
5. Update `summary_zh` with a compact allocation line.
6. Verify with both synthetic tests and real free Binance public data.

## Pitfalls

- Do not let portfolio allocation increase a symbol above its existing `position_size`; `position_size` already includes confidence and extension risk adjustments.
- Do not treat `portfolio_allocation` as live execution. It is a paper target only.
- If synthetic tests unexpectedly under-allocate, inspect whether the old extension rule reduced `position_size` before changing production code.
