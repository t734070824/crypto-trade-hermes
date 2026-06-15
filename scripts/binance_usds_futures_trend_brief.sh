#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

exec scripts/binance_usds_futures_trend.py \
  --all-symbols \
  --intervals 1h,4h,1d \
  --limit 240 \
  --context-limit 30 \
  --top 5 \
  --portfolio-risk-budget 3 \
  --max-symbol-risk 1 \
  --state-file state/binance-usds-futures-trend-paper-state.json \
  --telegram-brief
