# Session v1.37 — Diagnosing unexpected cron notification time

## Trigger

Use this note when `testnet-agent-hourly` sends a Telegram cron notification outside its normal `5 * * * *` schedule, for example a message shown around 北京时间（UTC+8）13:17 even though the normal hourly run is expected at 13:05 / 14:05.

## Durable lesson

A cron notification timestamp is not the same thing as the scheduled trigger time. For Hermes cron jobs, separate these clocks before explaining a "late" or unexpected message:

1. **Configured schedule / next planned run** — from the cron job definition, e.g. `5 * * * *` and `next_run_at`.
2. **Actual job start / script evidence time** — from the script's own `generated_at_utc` / `generated_at_beijing` fields in `cron/output/<job_id>/*.md`.
3. **Cron output write / completion time** — from the output file name and `Run Time` header, plus `last_run_at` in the job definition.
4. **Telegram delivery/display time** — when the user actually sees the message; Telegram may display only minute-level time.

If output files appear at non-scheduled minutes, such as `13-15-30.md` or `13-16-30.md` for a job scheduled at minute `05`, treat them as evidence of an extra immediate/manual run-on-next-tick unless logs prove a scheduler bug or delivery retry.

## Diagnostic checklist

Read-only commands/actions only unless the user explicitly asks to trigger execution now, e.g. “手动运行”, “立即运行”, “触发一次”, “manual run”, “run it now”, or “trigger once”.

Allowed while diagnosing:

- `cronjob(action="list")`;
- read `cron/jobs.json`;
- list/read `cron/output/<job_id>/*.md`;
- read runtime/order JSONL evidence;
- inspect gateway/cron logs.

Forbidden while diagnosing timing:

- `cronjob(action="run")`;
- `hermes cron run`;
- resume/update a job merely to make it fire;
- signed testnet cycles;
- order placement or order cancellation.

Evidence steps:

- Confirm the job schedule and `next_run_at` from the job record.
- List recent `cron/output/<job_id>/*.md` files and compare file names to the schedule.
- Read the matching output file and compare:
  - `Run Time` header;
  - script `generated_at_utc` / `generated_at_beijing`;
  - final summary `total_duration_seconds`;
  - job `last_run_at` / `last_status`.
- If the output exists at a non-schedule minute and `last_status=ok`, explain it as an extra manual/immediate run and then delivery after completion, not as the normal hourly schedule drifting.
- Do not use `cronjob(action="run")` or `hermes cron run` while only diagnosing timing; those commands intentionally create another immediate run and another Telegram notification.

## Reporting template

- Planned schedule: `...` UTC / 北京时间（UTC+8）
- Actual script evidence time: `...` UTC / 北京时间（UTC+8）
- Cron completion/output time: `...` UTC / 北京时间（UTC+8）
- Telegram delivery/display time: `...` UTC / 北京时间（UTC+8）
- Classification: normal scheduled run / manual immediate run / delivery delay / unknown
- Evidence: output file path, `last_run_at`, `last_status`, and `next_run_at`
