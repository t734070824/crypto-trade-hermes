# Session v1.30: Cron script paths are relative to profile `scripts/`

## What happened
A Hermes cron job failed with `ScriptNotFound` because the stored script path was `scripts/binance_usds_futures_testnet_hourly.sh`, which resolved to `/root/.hermes/profiles/crypto-trade-hermes/scripts/scripts/binance_usds_futures_testnet_hourly.sh`.

## Durable lesson
- In this profile, cron `script` values are resolved relative to the profile `scripts/` directory.
- For a file at `scripts/binance_usds_futures_testnet_hourly.sh`, store `script: "binance_usds_futures_testnet_hourly.sh"`.
- Do not prefix the stored cron `script` with `scripts/` unless the scheduler explicitly expects a full path.

## Verification used
- `test -x scripts/binance_usds_futures_testnet_hourly.sh`
- `bash scripts/binance_usds_futures_testnet_dry_run.sh --no-save-runtime-record`
- `git diff --cached --check`

## Related files
- `cron/jobs.json`
- `scripts/binance_usds_futures_testnet_hourly.sh`
- `skills/crypto-trading/binance-usds-futures-trend/SKILL.md`
