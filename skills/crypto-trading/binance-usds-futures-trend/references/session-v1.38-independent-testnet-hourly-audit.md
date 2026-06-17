# Session v1.38 — Independent read-only audit of `testnet-agent-hourly`

## Context

The user asked to use an independent agent to review whether `testnet-agent-hourly` run results were normal. This is an audit request, not authorization to trigger a new run.

Relevant current job shape:

- job name: `testnet-agent-hourly`
- job id seen in this session: `f7201d6c1c57`
- schedule: `5 * * * *`
- runner: script-owned / `no_agent=true`
- script: `binance_usds_futures_testnet_hourly.sh`

## Durable workflow

For future `testnet-agent-hourly` reviews:

1. Use an independent agent when the user asks for independent review, but explicitly instruct it to be read-only.
2. Do **not** call `cronjob(action="run")`, `hermes cron run`, `hermes cron resume` for triggering, or any signed testnet cycle unless the current user message explicitly asks to execute now.
3. Review existing artifacts only:
   - `cron/jobs.json` or `cronjob(action="list")`;
   - `cron/output/<job_id>/*.md`;
   - `state/binance-usds-futures-trend-testnet-runtime.jsonl`;
   - `state/binance-usds-futures-trend-testnet-orders.jsonl`;
   - gateway/cron logs only if needed for delivery timing.
4. Require the reviewer to separate time axes:
   - configured schedule / `next_run_at`;
   - script evidence time inside output/runtime records;
   - cron output/completion/status-update time;
   - Telegram delivery/display time, or explicitly say it cannot be confirmed from local evidence.
5. Label all times in UTC and 北京时间（UTC+8）.
6. Classify the result as `正常`, `部分正常`, or `异常` rather than only pass/fail.

## Evaluation checklist

A run can be considered operationally normal only if most of these are true:

- the latest output aligns with the configured schedule, e.g. minute `05` for `5 * * * *`;
- `last_status=ok`, `last_error=null`, and `last_delivery_error=null`;
- `next_run_at` points to the next expected scheduled tick;
- runtime JSONL and order journal are updated for the latest run;
- `errors_count=0` and `error_types=[]` for each cycle;
- attempted/submitted/rejected/submitted_unknown counts are explicitly reported;
- protection status is consistent and `all_positions_protected=true` for nonzero positions;
- no unexpected extra output files exist at non-scheduled minutes.

Use `部分正常` when the hot path succeeded and evidence was recorded, but there are non-fatal anomalies such as:

- extra non-scheduled output files suggesting a manual/immediate run;
- `submitted_unknown` or repeated `HTTPError` in the recent window;
- nonzero `rejected` counts with otherwise successful top-level status;
- inconsistent protection fields, e.g. one group reports `all_positions_protected=false` while another reports true;
- Telegram delivery/display time cannot be verified from local evidence.

Use `异常` when cron status is failing, runtime/order evidence is missing, schedule progression is broken, protection is persistently missing for live testnet positions, or signed order state is ambiguous enough to require human intervention.

## Response pattern

Report concisely in Chinese:

- top-line classification;
- schedule/latest-run timing with UTC and 北京时间（UTC+8）;
- runtime/order journal write status;
- errors/rejections/submitted_unknown/protection status;
- whether Telegram delivery time is locally confirmable;
- recommended next action, usually “do not trigger a new run; wait for the next scheduled tick and re-check.”

## Related pitfall

The phrase “运行结果” means run results/evidence, not “run it now.” Treat review/audit requests as read-only unless the user explicitly says “手动运行”, “立即运行”, “触发一次”, “run it now”, or equivalent execution-now wording.
