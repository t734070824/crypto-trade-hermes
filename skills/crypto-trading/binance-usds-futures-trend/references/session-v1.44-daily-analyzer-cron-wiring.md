# Session v1.44 — Daily analyzer cron wiring

## Durable lesson

When the daily read-only diagnostic job exists, its prompt should treat `--daily-analyze-runtime` as the primary diagnostic contract and use `--replay-runtime-evidence` only as a strategy-candidate comparison. Replay alone can summarize variants but can miss raw execution-health anomalies that are visible only in the order journal.

## Safe update pattern

1. Update the live agent-mode cron job prompt with `cronjob(action="update")`; do **not** use `cronjob(action="run")` unless the user explicitly asks to trigger an immediate run.
2. Keep the job `no_agent=false`, with `skills=["binance-usds-futures-trend"]`, `script=null`, and limited toolsets such as `terminal,file,skills`.
3. Require these read-only commands in the prompt:
   - `python3 scripts/binance_usds_futures_trend.py --daily-analyze-runtime --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl --testnet-order-journal-file state/binance-usds-futures-trend-testnet-orders.jsonl --analysis-window-hours 24`
   - `python3 scripts/binance_usds_futures_trend.py --replay-runtime-evidence --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl`
4. Regenerate/sync `cron/jobs.template.json` from live `cron/jobs.json` while stripping runtime-only fields such as `next_run_at`, `last_run_at`, `last_status`, `last_error`, `last_delivery_error`, `repeat.completed`, `origin`, and top-level `updated_at`.
5. Do not restore live `cron/jobs.json` while enabled jobs are active; it can perturb scheduler timing.

## Verification details

The daily analyzer CLI wraps the actual contract under the top-level key:

```json
{
  "ok": true,
  "daily_runtime_analysis": {
    "schema_version": "daily_runtime_analysis.v1"
  }
}
```

So validation scripts must inspect `data["daily_runtime_analysis"]`, not top-level `schema_version` or top-level `system_health`.

Minimum read-only validation:

```bash
python3 scripts/binance_usds_futures_trend.py \
  --daily-analyze-runtime \
  --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl \
  --testnet-order-journal-file state/binance-usds-futures-trend-testnet-orders.jsonl \
  --analysis-window-hours 24 >/tmp/daily_analyzer_verify.json
python3 - <<'PY'
import json
root = json.load(open('/tmp/daily_analyzer_verify.json'))
d = root['daily_runtime_analysis']
assert root.get('ok') is True
assert d['schema_version'] == 'daily_runtime_analysis.v1'
assert d['generated_at_utc'] and d['generated_at_beijing']
assert d['system_health']['status'] in {'ok', 'degraded', 'blocked'}
print(d['system_health']['status'], d['system_health'].get('issues', []))
PY
```

## Review/commit checklist

- Include both the Skill pointer and any new `references/*.md` support file in the commit.
- Validate `cron/jobs.template.json` as JSON and check it contains no live `origin`, `next_run_at`, or `last_run_at` fields.
- Run `git diff --check` and Skill markdown validation.
- Get independent review before commit/push.
- Commit and push by default when the user has asked to continue the repository workflow.
