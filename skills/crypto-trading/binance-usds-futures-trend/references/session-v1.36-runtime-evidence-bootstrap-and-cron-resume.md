# v1.36 Runtime evidence bootstrap and cron resume

## Trigger

Use this note when a CAGR/strategy-optimization plan assumes runtime/order-journal evidence, but the canonical runtime files are empty or the relevant cron jobs are paused.

## Durable lesson

Do **not** start regime/sizing/lifecycle optimization from intuition when there is no current runtime evidence. First restore deterministic evidence collection, verify it is scheduled, and only then run bottleneck analysis after enough cycles have accumulated.

Canonical files to check before evidence-driven analysis:

- `state/binance-usds-futures-trend-testnet-runtime.jsonl`
- `state/binance-usds-futures-trend-testnet-orders.jsonl`
- legacy near-miss files only for reconciliation, not as the preferred target:
  - `state/binance-usds-futures-testnet-runtime.jsonl`
  - `state/binance-usds-futures-testnet-orders.jsonl`
  - `state/testnet-orders.jsonl`

If canonical files are `0 bytes / 0 lines`, Task 1 in a CAGR plan becomes an evidence-bootstrap task, not a bottleneck-statistics task.

## Bootstrap workflow

1. List cron jobs before changing anything.
2. Identify the split ownership boundary:
   - hourly testnet hot path: `no_agent=true`, script-owned, deterministic stdout delivery;
   - daily replay diagnostics: agent-owned, read-only, no signed order placement/cancelation.
3. Resume the paused jobs rather than recreating duplicates when the existing job IDs and scripts are correct.
4. Verify scheduler health with `hermes cron status` or equivalent evidence that the gateway scheduler is running.
5. Verify `next_run_at` with explicit timezone labels, preferably 北京时间（UTC+8） and UTC when reporting.
6. For wall-clock daily analyzer schedules, prefer a cron expression (for example `37 18 * * *`) over `every 1440m` so the job remains aligned to a stable clock time instead of drifting from resume time.
7. After resume, report separately:
   - planned trigger time;
   - eventual execution-completion time from cron/runtime evidence;
   - message delivery time if diagnosing latency.
8. Commit/push durable `cron/jobs.json` state only after independent review. Treat unrelated scheduler timestamp rewrites as runtime noise unless they are part of the intentional resume state.

## Planning correction

When no runtime evidence exists yet, the correct sequence is:

1. restore/verify cron evidence collection;
2. wait for at least 24h of hourly runs, preferably 72h for more useful signal;
3. run bottleneck counts from runtime/order journal and cron output;
4. only then choose whether to implement regime scoring, sizing refinement, lifecycle add/trim/harvest, or execution min-delta/protection observability.

## Pitfalls

- Do not present empty runtime files as evidence.
- Do not infer bottleneck counts from strategy intuition when the plan explicitly calls for runtime/order-journal counts.
- Do not recreate cron jobs if the existing paused jobs can be safely resumed.
- Do not assume a resumed `no_agent=true` hourly job will execute prompt prose; behavior must live in the script/CLI/engine path.
- Do not call daily replay diagnostics meaningful until the hourly hot path has produced actual runtime records.
