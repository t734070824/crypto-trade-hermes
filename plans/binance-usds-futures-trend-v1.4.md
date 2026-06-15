# Binance USDS-M Futures Trend v1.4 Plan — Core Interface Extraction

Created: UTC 2026-06-15 15:44:10 / 北京时间（UTC+8）2026-06-15 23:44:10

## Goal

从大脚本中抽象实时交易引擎核心接口，但保持现有 CLI 行为完全不变。

## Architecture

v1.4 只拆接口和轻量 dataclass/Protocol，不接 testnet/live。现有函数可继续留在脚本中，但新模块应让 scanner 逻辑逐步变成 `SignalEngine`，并为 shared trading loop 准备稳定边界。

## Scope

Create package skeleton:

- `scripts/binance_trend_core/__init__.py`
- `scripts/binance_trend_core/types.py`
- `scripts/binance_trend_core/market_data.py`
- `scripts/binance_trend_core/signals.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/risk.py`
- `scripts/binance_trend_core/portfolio.py`
- `scripts/binance_trend_core/execution.py`
- `scripts/binance_trend_core/brokers.py`
- `scripts/binance_trend_core/runtime.py`

Core interfaces:

- `MarketData`：public candles/context fetch abstraction；
- `SignalEngine`：wrap current decide/enrich/ranking behavior；
- `Strategy`：desired exposure / intent from signals；
- `RiskManager`：portfolio caps, rejects/skips, kill switch hooks；
- `PortfolioState`：positions, orders, fills, lifecycle, PnL fields；
- `ExecutionEngine`：desired state -> broker instructions；
- `BrokerAdapter`：paper/testnet/live adapter boundary；
- `RuntimeRecorder`：schema-compatible runtime evidence writer。

## Non-Goals

- 不改策略参数。
- 不迁移全部实现。
- 不下单。
- 不改变 CLI JSON contract。

## TDD Tasks

1. Add tests that import every new interface module.
2. Add tests proving `BrokerAdapter` exposes `environment`, `submit_order`, `cancel_order`, `get_account_state` signatures.
3. Add tests proving existing CLI scan still returns `mode=paper`, `portfolio_allocation`, `paper_lifecycle` when requested.
4. Add tests proving short interval rejection still applies through the new wrapper path.
5. Implement minimal interfaces and wrapper adapters around existing functions.

## Verification

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
git diff --check
```

Real free-data smoke test must match v1.3 scan behavior except for optional new metadata.

## Acceptance

- New interfaces exist and are tested.
- Existing CLI commands remain backward compatible.
- Paper/testnet/live divergence is isolated to `BrokerAdapter` design.
- No signed Binance endpoint is used.

## Implementation Status

Completed in v1.4 change set:

- Added `scripts/binance_trend_core/` package skeleton and module imports.
- Added lightweight Protocol/dataclass boundaries for market data, signals, strategy, risk, portfolio state, execution, brokers, and runtime recording.
- Added `RejectingBrokerAdapter` as safe default; it exposes the adapter boundary but never submits orders.
- Added tests for importability, broker interface signatures, wrapper short-interval rejection, and scan CLI compatibility.
- Preserved current CLI behavior and paper-only runtime; no signed Binance endpoints were added.
