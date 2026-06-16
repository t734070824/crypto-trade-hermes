# Session v1.19 — Pause cron and reset testnet/simulated trading state

Use this reference when the user says they cleared simulated/testnet positions and wants the trading system reset before resuming operations.

## Durable workflow

1. Pause all operational cron jobs that could mutate trading state before touching local runtime files.
   - At minimum: the hourly single-agent testnet trading cron.
   - Also pause read-only/replay diagnostics if the user wants a quiet reset window, so reports do not interpret partially reset evidence.
2. Verify cron state is `paused` after the pause call.
3. Treat local runtime evidence as valuable: archive first, then clear.
   - Create a timestamped directory under `state/archive/reset-<UTC timestamp>/`.
   - Copy runtime/order journals there.
   - Write a `MANIFEST.json` with UTC and 北京时间（UTC+8） reset timestamps, original sizes, line counts, and SHA256 hashes.
4. Clear only local ignored runtime/order evidence files needed for a clean simulated/testnet starting point.
   - Do not touch `.env` or secrets.
   - Do not place or cancel exchange orders as part of local reset unless the user explicitly asks in the current turn.
5. Verify post-reset file sizes are zero or otherwise match the intended clean state.
6. Check git status afterwards.
   - `cron/jobs.json` changes may be real when pausing jobs.
   - Runtime files under `state/` should remain ignored and uncommitted.
   - Do not mix unrelated memory/skill/cron noise into a reset commit without review.

## Files commonly involved

- `state/binance-usds-futures-trend-testnet-runtime.jsonl`
- `state/binance-usds-futures-trend-testnet-orders.jsonl`
- `state/testnet-orders.jsonl`

## Safety notes

- A local reset is not an exchange reset. If the user has already manually cleared testnet positions, local evidence can be reset; otherwise signed account/position reconciliation is required before resuming trading.
- Never infer that exchange positions are flat from empty local JSONL files.
- Keep all time-related report lines labeled with UTC or 北京时间（UTC+8）.
