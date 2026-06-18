# Session v1.48 — short evidence collection via dry-run-only testnet cron

## Context

After enabling the minimal long/flat/short dry-run path, the next operational question was whether to immediately run signed short on Binance Futures Testnet. The safer choice was to **not** enable signed short yet. Instead, preserve the signed hourly job paused and collect runtime evidence through a separate dry-run-only cron.

## Durable workflow lesson

When a newly added short path has passed unit tests and local dry-run probes but has not accumulated real market runtime evidence:

1. Do **not** resume or mutate the existing signed hourly job just to gather evidence.
2. Add a separate script-owned `no_agent=true` cron that forces dry-run at the wrapper level.
3. Keep signed short gated by code/config (`--allow-testnet-signed-short`), not by prompt prose.
4. Let the dry-run cron write normal runtime/order evidence so the daily read-only analyzer can evaluate real market signals without placing orders.
5. Only consider a single-symbol signed-short grey run after 24h/72h evidence review and current-turn user authorization.

## Wrapper pattern

A minimal wrapper is safer than relying on a cron prompt to remember dry-run semantics:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"
python3 scripts/binance_usds_futures_testnet_hourly.py --dry-run "$@"
```

Verification pattern before scheduling:

```bash
chmod +x scripts/binance_usds_futures_testnet_hourly_dry_run.sh
scripts/binance_usds_futures_testnet_hourly_dry_run.sh --no-save-runtime-record
```

Expected dry-run summary properties:

- `ok=true`
- `dry_run=true`
- `preflight_ok=true` and `postflight_ok=true` are skipped in dry-run mode (`dry_run_skips_signed_preflight` / `dry_run_skips_signed_postflight`) so the evidence cron does not depend on signed account snapshots
- `signed_count=0`
- `attempted_real_order_count=0`
- `real_submitted_count=0`
- with `--no-save-runtime-record`, `runtime_record.saved=false`

## Cron pattern

Create a separate hourly job, e.g. `testnet-dry-run-hourly`, with:

- `no_agent=true`
- script: `binance_usds_futures_testnet_hourly_dry_run.sh`
- schedule separated from the paused/production signed job, e.g. minute `:25`
- deliver to the current origin if the user wants evidence in the active chat

Do not use `cronjob(action="run")` or resume the paused signed hourly job unless the user explicitly asks to trigger execution now.

## Review checklist

Before commit/push and scheduling:

- independent review confirms the wrapper cannot submit orders;
- wrapper itself contains no secrets;
- output redaction remains in the underlying harness;
- repository change is committed and pushed before relying on the cron;
- `cronjob(action="list")` confirms the old signed hourly job remains paused and the new dry-run job is scheduled.
