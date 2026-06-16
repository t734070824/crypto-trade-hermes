# Binance USDS-M Futures Trend v1.5 Plan — Shared Trading Loop + PaperBroker

Created: UTC 2026-06-15 15:44:10 / 北京时间（UTC+8）2026-06-15 23:44:10

## Status

Implemented: UTC 2026-06-16 00:21:00 / 北京时间（UTC+8）2026-06-16 08:21:00

## Goal

实现第一版 shared trading loop，并用 `PaperBroker` 跑 paper；paper 不再只是独立 scanner，而是 broker adapter 上的同一套执行循环。

## Architecture

Trading loop order:

1. MarketData fetches public data.
2. SignalEngine builds signals.
3. Strategy converts signals to desired exposure/intents.
4. RiskManager approves, caps, or rejects intents.
5. ExecutionEngine reconciles desired state with PortfolioState.
6. BrokerAdapter executes/simulates orders.
7. RuntimeRecorder stores evidence.
8. Observability emits Telegram/summary around the loop.

## Scope

- Implement `PaperBroker` with simulated fills, fee/slippage assumptions, and no external side effects.
- Implement `run_trading_cycle(config, broker, recorder)`.
- Add CLI mode `--run-paper-cycle` or equivalent while preserving old scan commands.
- Runtime records must include desired orders and simulated fills.

## Non-Goals

- 不接 testnet/live。
- 不使用 leverage 或真实账户余额。
- 不自动调参。

## TDD Tasks

1. Test `PaperBroker.submit_order` creates simulated fill and never calls network.
2. Test `ExecutionEngine` turns paper intents into broker instructions.
3. Test one paper cycle produces PortfolioState + runtime record.
4. Test replacing broker with a fake testnet adapter uses the same loop interface without signed calls.
5. Test short intervals are rejected before broker execution.

## Verification

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
git diff --check
```

Real free-data paper cycle smoke test must show:
- `environment=paper`；
- `real_orders_submitted=false`；
- simulated fills only；
- runtime evidence written to ignored path or dry-run output。

## Acceptance

- Paper cycle runs through shared engine.
- Broker adapter is the only execution-specific component.
- Existing scanner/backtest/brief still work.
