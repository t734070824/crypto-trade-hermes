# v1.7 Binance Futures Testnet Adapter Workflow

Created: UTC 2026-06-16 01:35:05 / 北京时间（UTC+8）2026-06-16 09:35:05

## Purpose

Implement Binance USDS-M futures testnet execution plumbing without enabling live/mainnet execution. Paper and testnet must share `run_trading_cycle`; only the broker adapter and credential/config boundary differ.

## Implemented Components

- `BinanceTestnetCredentials`: maps `.env` / process env names `LALA_KEY` and `LALA_SECRET` to adapter credentials without printing values.
- `resolve_binance_testnet_credentials`: fail-closed resolver; missing variables raise a clear error mentioning variable names only.
- `BinanceTestnetBroker`: testnet-only adapter with `environment='testnet'`.
- `TestnetRiskLimits`: max order notional, max symbol exposure, max daily loss, max order count, kill switch.
- `redact_sensitive_testnet_fields`: recursive redaction for API key, secret, API key headers, and signature fields.
- CLI: `--run-testnet-cycle`, `--testnet-dry-run`, `--testnet-submit-signed`, and risk limit flags.

## Safety Boundaries

1. Default `--run-testnet-cycle` behavior is dry-run: no signing and no HTTP order submission.
2. Signed testnet submission requires explicit `--testnet-submit-signed`.
3. Base URL must parse to exact HTTPS host `testnet.binancefuture.com`; mainnet and lookalike hosts fail closed.
4. Live/mainnet adapter remains unimplemented and unauthorized.
5. Runtime evidence must not contain `LALA_KEY`, `LALA_SECRET`, API key values, secrets, signatures, or API key headers.
6. `<1h` intervals are rejected before broker execution.
7. Signed-path HTTP errors are recorded as `submitted_unknown` with sanitized error metadata only; never store raw exception text from lower HTTP layers.
8. Missing/zero/negative/non-finite `reference_price` / `entry_reference` rejects before signing so notional and exposure risk gates cannot be bypassed.

## Verification Commands

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
git diff --check
```

Dry-run smoke with real free public K-lines:

```bash
scripts/binance_usds_futures_trend.py --run-testnet-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file /tmp/binance-v17-testnet-runtime.jsonl --no-save-runtime-record --testnet-dry-run --testnet-max-order-notional 1000000
```

Expected smoke properties:

- `environment=testnet`
- `real_orders_submitted=false`
- `runtime_record_saved=false` when `--no-save-runtime-record` is used
- output includes UTC and 北京时间（UTC+8） timestamps
- output does not contain credential values or signed payload secrets

## Pitfalls Found

- Do not validate testnet URL with substring matching. Use URL parsing and exact hostname match to reject lookalike domains.
- Do not expand scan-mode `--runtime-environment` to `testnet`; testnet evidence should come from `--run-testnet-cycle`, not paper scan records.
- Dry-run must stop before signing, not merely before HTTP submission.
- Signed HTTP exceptions may include raw URLs, query signatures, or headers; store sanitized `submitted_unknown` only and count the request as submitted/attempted before the HTTP call.
- Never use a fallback price like `1.0` for signed testnet risk checks; missing or invalid reference prices must reject before signing.
