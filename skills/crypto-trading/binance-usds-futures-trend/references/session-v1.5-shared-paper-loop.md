# Session v1.5 — Shared Paper Trading Loop + PaperBroker Workflow

Created: UTC 2026-06-16 00:17:09 / 北京时间（UTC+8）2026-06-16 08:17:09

## Durable Pattern

When adding execution plumbing to the Binance USDS-M futures trend project, keep strategy/risk/execution orchestration shared and isolate environment-specific behavior inside the broker adapter. Paper mode should run the same loop shape as future testnet/live, but with simulated fills and no signed Binance calls.

## TDD Shape

1. Add RED tests before production code:
   - `PaperBroker.submit_order` creates a simulated fill and account-state position without network, API keys, signed payloads, or real order IDs;
   - `PaperIntentExecutionEngine` converts `StrategyIntent` into broker `OrderInstruction` objects;
   - one shared paper cycle returns portfolio state plus runtime evidence with desired orders and simulated fills;
   - replacing `PaperBroker` with a fake testnet adapter uses the same `run_trading_cycle` interface;
   - short intervals below `1h` are rejected before broker execution;
   - CLI `--run-paper-cycle` can run no-write runtime evidence.
2. Verify RED by running only the new tests and confirming failures are from missing `PaperBroker`, missing `loop`, or missing CLI option.
3. Implement minimal GREEN:
   - `scripts/binance_trend_core/brokers.py`: add `PaperBroker` with deterministic fee/slippage simulated market fills;
   - `scripts/binance_trend_core/execution.py`: include a paper reference price in order metadata;
   - `scripts/binance_trend_core/loop.py`: add `TradingCycleConfig`, `validate_cycle_interval`, and `run_trading_cycle`;
   - `scripts/binance_usds_futures_trend.py`: add `run_paper_trading_cycle` and `--run-paper-cycle` while preserving old scan/backtest/refinement behavior.
4. Keep testnet/live, HMAC signing, leverage, and real balances out of v1.5.

## Verification Pattern

Run all of these before commit/push:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
git diff --check
scripts/binance_usds_futures_trend.py --run-paper-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl --no-save-runtime-record
```

The real Binance public-data smoke must show:

- `paper_cycle.environment=paper`;
- `paper_cycle.real_orders_submitted=false`;
- `paper_cycle.runtime_record_saved=false` when `--no-save-runtime-record` is set;
- `paper_cycle.runtime_record.execution_events.simulated_fills_count` is present;
- UTC and 北京时间（UTC+8） timestamps are present;
- no signed endpoint, API key, secret, or paid API is required.

## Review Checklist

Before push, independent review should verify:

- `PaperBroker` is simulated-only and cannot submit live/testnet orders;
- `run_trading_cycle` depends on broker interface methods instead of paper-specific branches;
- short intervals are rejected before `broker.submit_order`;
- runtime evidence includes desired orders and simulated fills;
- old scanner/backtest/brief contracts still pass tests;
- no runtime `state/*.json`, `state/*.jsonl`, cron output, or `__pycache__` files are committed;
- `cron/jobs.json` runtime counter changes are not mixed into the feature commit.
