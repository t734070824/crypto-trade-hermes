#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROFILE_ENV="${REPO_ROOT}/.env"
RUNTIME_FILE="${REPO_ROOT}/state/binance-usds-futures-trend-testnet-runtime.jsonl"
ORDER_JOURNAL_FILE="${REPO_ROOT}/state/binance-usds-futures-trend-testnet-orders.jsonl"

cd "${REPO_ROOT}"
if [[ -f "${PROFILE_ENV}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${PROFILE_ENV}"
  set +a
fi

python3 scripts/binance_usds_futures_trend.py \
  --run-testnet-cycle \
  --all-symbols \
  --interval 1h \
  --limit 240 \
  --runtime-record-file "${RUNTIME_FILE}" \
  --testnet-order-journal-file "${ORDER_JOURNAL_FILE}" \
  --testnet-dry-run >/tmp/binance-testnet-dry-run.out

UTC_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BJ_NOW="$(TZ=Asia/Shanghai date +%Y-%m-%dT%H:%M:%S%z)"
SUMMARY="$(python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/binance-testnet-dry-run.out').read_text(encoding='utf-8'))
cycle = payload.get('testnet_cycle', {})
change = cycle.get('runtime_record_change', {})
print(f"ok={payload.get('ok')} errors_count={cycle.get('errors_count')} records_written={change.get('records_written')}")
PY
)"

printf 'UTC %s / 北京时间（UTC+8） %s testnet dry-run complete; runtime_record=%s; %s\n' "${UTC_NOW}" "${BJ_NOW}" "${RUNTIME_FILE}" "${SUMMARY}"
