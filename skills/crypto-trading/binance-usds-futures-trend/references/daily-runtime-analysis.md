# Daily runtime analysis notes

## What the analyzer must read
- `state/binance-usds-futures-trend-testnet-runtime.jsonl`
- `state/binance-usds-futures-trend-testnet-orders.jsonl`
- `closed_order_analysis.v1` is useful for attribution, but it is *not* the only source of execution-health evidence.

## Important lesson
Do **not** derive execution health only from `closed_order.v1` / `closed_order_analysis.v1`.

Reason: `analyze_closed_orders()` intentionally filters the journal to finalized records such as FILLED/CANCELED/REJECTED/EXPIRED. That means broker submission outcomes like `submitted_unknown` can be missed if the analyzer only inspects closed orders.

The daily analyzer should therefore:
1. load the raw order journal;
2. inspect raw journal statuses for execution anomalies;
3. combine that with closed-order attribution for the strategy layer.

## Reproduction pattern
Run the read-only analyzer against local evidence:

```bash
python3 scripts/binance_usds_futures_trend.py \
  --daily-analyze-runtime \
  --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl \
  --testnet-order-journal-file state/binance-usds-futures-trend-testnet-orders.jsonl \
  --analysis-window-hours 24
```

## Expected outputs
- `system_health.status`
- `system_health.issues`
- `order_attribution.by_close_reason`
- `strategy_diagnosis.findings`
- `recommendations`

## Guardrail
This path is strictly read-only. It must not sign, submit, cancel, or trigger cron.