# v0.6 Allocation Explainability Workflow

Created: UTC 2026-06-15 11:18:56 / 北京时间(UTC+8) 2026-06-15 19:18:56

## Trigger

Use this workflow when extending portfolio-level paper allocation with human-readable allocation and skip explanations.

## Steps

1. Follow TDD strictly:
   - first extend allocation tests to require `constraints_applied`, `allocation_explanation`, and `skipped_details`;
   - run the target test and confirm RED;
   - implement the smallest allocation changes needed to pass;
   - then add/extend a summary test for `分配说明` and confirm RED before changing summary rendering.
2. Keep allocation pure and paper-only:
   - no signed requests;
   - no `.env` secret reads;
   - no order placement.
3. For each skipped symbol, preserve the existing `skipped_symbols` list for backward compatibility and add structured `skipped_details`:
   - `not_hold_long`;
   - `non_positive_rank_score`;
   - `non_positive_position_size`;
   - `no_remaining_budget`;
   - `non_positive_allocation`.
4. For each allocated symbol, add:
   - `constraints_applied`;
   - `allocation_explanation` with rank score, requested size, allocated amount, constraints, and `paper only` text.
5. Update `summary_zh` with a compact `分配说明` line, limited to the first 3 allocations.
6. Verify with targeted tests, full unit suite, syntax compile, and real free Binance USDS-M public data.

## Pitfalls

- Do not remove `skipped_symbols`; existing consumers may depend on the simple list.
- Do not make `summary_zh` too long; Telegram briefings should stay concise.
- `position_size_reduced` can appear together with `max_symbol_risk_cap` or `remaining_budget_cap`; consumers should treat `constraints_applied` as a list, not an enum.
- Keep UTC and 北京时间（UTC+8） labels in user-facing run output.
