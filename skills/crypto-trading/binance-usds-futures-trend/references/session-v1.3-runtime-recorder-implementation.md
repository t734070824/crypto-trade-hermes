# Session v1.3 — Runtime Recorder Implementation Workflow

## Durable Pattern

When adding runtime evidence capture to the Binance USDS-M futures trend project, keep it as a sidecar around the existing paper scan path first. Do not turn it into a separate trading state machine and do not introduce signed/testnet/live order logic in the same change.

## Implementation Shape

1. Add a schema builder such as `build_runtime_record(scan, environment, strategy_version, config_version, run_id)`.
2. Restrict v1.3 environment to `paper`; reject non-paper environments until adapter isolation and risk gates exist.
3. Include enough evidence for future replay/comparison:
   - schema/environment/run metadata;
   - UTC and 北京时间（UTC+8） timestamps;
   - symbol universe and intervals;
   - market input metadata and errors;
   - ranked signals and factor flags;
   - portfolio allocation/risk skips/caps;
   - paper state and lifecycle snapshots;
   - paper execution intents with `real_orders_submitted=false`;
   - outcomes and error counts.
4. Add an append-only JSONL writer with parent-directory creation and one JSON object per line.
5. Add scan-only CLI switches for runtime recording; explicitly reject runtime-record options in backtest, refinement, and single-decision modes.
6. Add dry-run support (`--no-save-runtime-record`) that builds the record in output but writes no file.
7. Ignore local runtime datasets in git, including `/state/*.jsonl`, `/runtime/`, and `/runtime_data/`.

## Verification Pattern

Run all of these before commit/push:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py
git diff --check
```

Then run a real free-data dry run using only `>=1h` intervals and confirm:

- `mode=paper`;
- UTC and 北京时间（UTC+8） are present;
- `errors_count=0` or any API/network blocker is reported honestly;
- `runtime_record_saved=false` when `--no-save-runtime-record` is set;
- `execution_events.real_orders_submitted=false`.

Also verify a temp JSONL write path and confirm one parseable line with `schema_version=runtime.v1`, `environment=paper`, and no secret/order payload fields.

## Review Checklist

Before push, use an independent agent review focused on:

- paper-only safety boundary;
- no signed endpoints / HMAC / order submission;
- no secret values or signed payloads in records;
- `<1h` interval rejection still works;
- runtime files remain ignored and untracked;
- CLI behavior remains backward compatible;
- JSONL schema is append-only and contains strategy-evolution evidence.
