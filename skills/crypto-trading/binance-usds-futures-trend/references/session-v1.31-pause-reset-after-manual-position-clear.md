# Session v1.31 — Pause and reset after manual testnet position clear

## Trigger

Use this when the user says they have already manually cleared simulated/testnet positions and asks to pause scheduled operation and reset the local simulated trading state.

## Operational pattern

1. Pause mutating cron jobs first, especially `testnet-agent-hourly`.
2. Also pause read-only diagnostics such as `replay-diagnostics-daily` when the user asks for a reset/quiet window; otherwise the diagnostic job may interpret partially reset local evidence.
3. Archive local runtime/order evidence before clearing it.
4. Clear only local ignored evidence files under `state/`; do not touch `.env`, credentials, exchange positions, or exchange orders.
5. Treat the user's manual position clear as exchange-side context, but still state clearly that the local reset did not modify exchange state.
6. Verify the cron jobs are paused and the local evidence files are zero bytes.
7. Commit durable cron pause state separately from any skill-library/doc updates; do not mix reset operations with unrelated skill-reference changes.

## Files to include in the archive/reset sweep

Canonical current files:

- `state/binance-usds-futures-trend-testnet-runtime.jsonl`
- `state/binance-usds-futures-trend-testnet-orders.jsonl`

Legacy/near-miss files that may still contain evidence and should be archived/cleared during a clean reset:

- `state/binance-usds-futures-testnet-runtime.jsonl`
- `state/binance-usds-futures-testnet-orders.jsonl`
- `state/testnet-orders.jsonl`

## Manifest requirements

Write `state/archive/reset-<UTC timestamp>/MANIFEST.json` with:

- reset timestamp in UTC;
- reset timestamp in 北京时间（UTC+8）;
- original path;
- existence;
- size before/after;
- line count before/after;
- SHA256 before/after;
- archive path;
- note that this is a local evidence reset only.

## Reporting language

Keep the final user report short:

- both paused cron jobs;
- archive path;
- zero-byte verification;
- UTC and 北京时间（UTC+8） reset time;
- explicit note that no exchange position/order was modified by the reset script.
