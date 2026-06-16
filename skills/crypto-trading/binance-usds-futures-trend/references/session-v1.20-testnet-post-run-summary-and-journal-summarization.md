# Session v1.20: Testnet post-run summary from runtime journals

This note captures a durable workflow lesson from a signed Binance USDS-M futures testnet cron run.

## What happened

- The cycle command output was very large and partially truncated in terminal capture.
- The authoritative result was reconstructed from:
  - `state/binance-usds-futures-trend-testnet-runtime.jsonl`
  - `state/binance-usds-futures-trend-testnet-orders.jsonl`
  - a fresh signed post-cycle account snapshot
  - `--replay-runtime-evidence` output saved to a file

## Durable workflow lesson

For signed testnet runs, do **not** rely on raw CLI stdout for the final report if the output may be truncated.
Instead, summarize from these sources:

1. runtime JSONL: counts of desired orders, fills, accepted/submitted vs rejected, lifecycle evidence, runtime timestamps
2. order journal JSONL: order submission/request/response records and rejection reasons
3. signed post-cycle snapshot: non-zero positions, ordinary open orders, open algo TP/SL counts
4. replay diagnostic JSON: baseline/candidate/selected variant, guardrail status, and errors_count

## Safe summary fields

Use only:

- UTC and 北京时间（UTC+8） timestamps
- environment (`testnet`)
- per-group symbol list
- desired_orders / fills / lifecycle counts
- accepted/submitted vs rejected order counts
- fill rejection reasons
- non-zero positions and open algo counts by symbol
- replay result fields: baseline, candidate, selected, guardrail, errors_count

Do not paste:

- raw signed request payloads
- API key values or headers
- full raw JSON blobs when a compact summary is enough

## Observed testnet-specific behaviors

- `max_order_count` can reject later protective or entry orders even when earlier ones were accepted/submitted.
- Exchange rule adaptation can reduce quantities enough to trip `MIN_NOTIONAL` on smaller take-profit tranches.
- A successful `real_orders_submitted=true` cycle still needs post-cycle signed verification; it does not imply all protective orders were accepted.
