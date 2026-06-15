# v0.7 Paper State Persistence Workflow

Created: UTC 2026-06-15 12:42:55 / 北京时间(UTC+8) 2026-06-15 20:42:55

## Goal

Add optional paper state persistence to the Binance USDS-M futures trend scanner so consecutive scans can report allocation/ranking/action/bucket changes without enabling any live trading.

## Implementation Summary

1. Added v0.7 plan: `plans/binance-usds-futures-trend-v0.7.md`.
2. Followed TDD:
   - RED: `apply_paper_state` tests failed because the function did not exist.
   - GREEN: implemented snapshot building, state loading/saving, change computation, and CLI wiring.
3. Added ignored runtime state policy:
   - real state files should live under `state/*.json`;
   - `.gitignore` ignores `/state/*.json`;
   - tests use temporary directories.
4. Added CLI flags:
   - `--state-file PATH` enables state comparison/persistence in scan mode;
   - `--no-save-state` computes `state_change` without writing.

## State Snapshot Fields

`scan.paper_state` stores only paper scan summaries:

- `mode=paper`;
- UTC and 北京时间（UTC+8） timestamps;
- `interval`, `intervals`, `primary_interval`;
- `top_trends`;
- `portfolio_allocation`;
- `allocations_by_symbol`;
- `skipped_details`;
- `errors_count`;
- `results_by_symbol` with rank/action/bucket diagnostics.

No API key, secret, or environment variable values are stored.

## State Change Fields

`scan.state_change` includes:

- `first_run`;
- `previous_state_loaded`;
- `current_errors_count`;
- `added_allocations`;
- `removed_allocations`;
- `changed_allocations`;
- `ranking_changes`;
- `action_changes`;
- `bucket_changes`;
- optional `state_file_error` when an existing state file is corrupt/unreadable.

Missing state files are treated as first run. Corrupted JSON is reported in `state_file_error` and replaced by the current valid paper snapshot when saving is enabled.

## Verification Commands

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py
git diff --check
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json
```

## Pitfalls

- Do not make state persistence implicit for every scan; it should require `--state-file`.
- Do not commit real runtime state; keep it under ignored `state/*.json`.
- Do not use state changes to place orders. This remains paper-only.
- Keep UTC and 北京时间（UTC+8） labels in user-facing output.
