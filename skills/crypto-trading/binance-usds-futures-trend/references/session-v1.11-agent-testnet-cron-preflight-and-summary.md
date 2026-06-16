# v1.11 Agent Testnet Cron: Signed Preflight, Reconciliation, and Safe Summary

Session lesson from operating the single agent-type Binance USDS-M futures testnet cron.

## Durable workflow

1. Load `.env` with `set -a; . ./.env; set +a; ...`, but never print secret values. Report only `LALA_KEY present/missing` and `LALA_SECRET present/missing`.
2. Before any signed cycle, instantiate `BinanceTestnetBroker` with `dry_run=False`, testnet-only defaults, and the same intended risk limits. Call `fetch_signed_account_snapshot('BTCUSDT')` as a read-only preflight.
3. If preflight fails, stop immediately and report only a sanitized error type/message via `scripts.binance_usds_futures_trend.sanitize_error_message`; do not submit orders.
4. If preflight succeeds, run the signed testnet cycle with the exact startup scope unless the user explicitly changes it later: `BTCUSDT`, `--interval 1h`, `--risk-unit 0.001`, `--testnet-max-order-count 1`, `--testnet-max-order-notional 200`, `--testnet-max-symbol-exposure 250`, `--testnet-max-daily-loss 10`, `--testnet-sync-account-state`, and `--testnet-track-order-lifecycle`.
5. Parse the CLI JSON and/or the last runtime JSONL record. Do not paste raw JSON. Summarize safe fields only: success, environment, whether real testnet orders were submitted, desired order count, submitted/accepted counts, lifecycle tracked/filled counts, current non-zero positions, open-order count, runtime file, and risk limits.
6. Always do a second signed `fetch_signed_account_snapshot('BTCUSDT')` after the cycle and summarize non-zero positions/open orders. This verifies position reconciliation and catches fills or open orders not obvious from CLI top-level output.

## Important interpretation

- `real_orders_submitted=false` with `desired_orders=[]` can be the correct safe outcome when the preflight/account-sync position already matches `desired_exposure` (for example existing `BTCUSDT` size `0.001` and risk unit `0.001`). Report this as reconciliation avoiding duplicate add-on, not as a failure.
- The current CLI output may be compact (`ok`, `testnet_cycle`, `testnet_risk_limits`) and omit convenient summary fields. The append-only runtime record contains richer fields such as `execution_events`, `portfolio_state.positions`, `risk.risk_results`, and timestamps.
- The strategy signal may still carry `mode: paper` inside signal metadata while the cycle environment is `testnet`; report the execution environment from the cycle/runtime record as `testnet`, and avoid implying live/mainnet execution.

## Safe reporting shape

Chinese brief should include:

- UTC and 北京时间（UTC+8） timestamps;
- Binance Futures Testnet only, no live/mainnet;
- credential presence only, no values;
- signed preflight status;
- whether any real testnet order was submitted;
- order/lifecycle status counts;
- current non-zero BTCUSDT position and BTCUSDT open-order count;
- runtime record path;
- fixed startup risk limits.
