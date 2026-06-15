# Session Workflow — v1.1 Paper Trading Lifecycle

Created: UTC 2026-06-15 14:38:39 / 北京时间（UTC+8）2026-06-15 22:38:39

## Purpose

v1.1 converts consecutive scan outputs into a paper-only lifecycle state. It tracks what the scanner *would intend* to do next — entry, add, reduce, hold, or exit — without placing any Binance orders.

## Implementation Notes

1. Keep lifecycle separate from `paper_state`:
   - `paper_state` summarizes scan allocation/ranking changes.
   - `paper_lifecycle` summarizes per-symbol paper position status and intent.
2. Load the previous lifecycle file if present; missing files mean first run.
3. For current `hold_long` decisions:
   - no previous open paper position -> `entry`;
   - higher target size -> `add`;
   - lower target size -> `reduce`;
   - unchanged size -> `hold`.
4. Preserve original `entry_reference` for open positions.
5. Never lower an existing long `trailing_stop`; use the max of previous and current trailing stop.
6. Record take-profit tranche events when the current reference crosses the previous stored TP threshold.
7. If a previous open symbol flips to `flat`, mark the paper position `closed` with `last_intent=exit` and retain `exit_reason`.
8. If a previous open symbol disappears from the current scan, carry it as stale paper state rather than pretending an exit occurred.
9. Persist lifecycle JSON atomically via the same safe writer used by paper state.

## CLI Pattern

```bash
scripts/binance_usds_futures_trend.py \
  --all-symbols \
  --intervals 1h,4h,1d \
  --limit 240 \
  --context-limit 30 \
  --top 5 \
  --portfolio-risk-budget 3 \
  --max-symbol-risk 1 \
  --state-file state/binance-usds-futures-trend-paper-state.json \
  --lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json
```

Dry-run lifecycle without writing:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json --no-save-lifecycle
```

## Guardrails

- `paper_lifecycle.mode` must always be `paper`.
- Do not add signed endpoints, live order IDs, or API credentials.
- Do not use `<1h` intervals.
- Runtime lifecycle files should live under ignored `state/*.json`.
- Report lifecycle as paper intent, never as live execution.

## Review Follow-ups

Independent review passed the v1.1 change, with non-blocking hardening suggestions for future lifecycle work:

- Add light schema checks when loading lifecycle JSON: require `mode=paper` and object-like `positions_by_symbol` before treating it as a previous lifecycle.
- When carrying stale positions, rebuild from a whitelist of lifecycle fields instead of copying `dict(previous_position)`, so hand-edited unknown fields do not propagate forever.
- If new lifecycle dry-run flags are added, avoid silent no-ops; scan-mode-only flags should either require `--lifecycle-file` or emit a clear error.

## Tests Added

- First run creates entry intent and persists snapshot.
- Consecutive run updates trailing stop and records TP tranche / reduce intent.
- Signal flip to flat closes an open paper position with exit reason.
- CLI scan mode supports `--lifecycle-file` and `--no-save-lifecycle`.
