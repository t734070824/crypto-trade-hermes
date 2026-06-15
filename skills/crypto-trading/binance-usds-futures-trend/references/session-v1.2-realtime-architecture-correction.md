# Session v1.2 — Real-Time Trading Architecture Correction

## Trigger

The user corrected the prior direction: the project should not evolve as a report-style paper scanner. The intended future is a Hermes Skill that performs real-time Binance USDS-M futures trading.

## Durable Lesson

Paper trading is not a separate product or reporting workflow. It should be one execution environment for the same trading system that later runs against Binance testnet and live execution.

## Architecture Rule

Design future work around a shared real-time trading loop:

1. `Strategy` produces desired exposure / intents from market data.
2. `RiskManager` validates sizing, leverage, drawdown, symbol caps, and kill-switch constraints.
3. `PortfolioState` owns positions, lifecycle, realized/unrealized PnL, orders, fills, and timestamps.
4. `ExecutionEngine` reconciles desired state with current state and creates/cancels/replaces orders.
5. `BrokerAdapter` isolates environment-specific execution:
   - `PaperBroker` simulates fills and fees.
   - `BinanceTestnetBroker` uses signed testnet endpoints.
   - `BinanceLiveBroker` uses signed live endpoints behind stricter safety gates.

Only the broker/fill adapter and environment configuration should change between paper/testnet/live. Strategy, risk, state transitions, and orchestration should stay on the same path.

## How to Treat Existing Scanner Code

Existing scan/ranking/lifecycle code can be reused as:

- signal generation;
- diagnostics;
- historical research;
- Telegram observability around the trading loop.

It should not remain the main architecture for paper trading if that causes divergence from future testnet/live execution.

## Pitfall to Avoid

Do not continue adding reporting-only paper features just because they are safe. Safety should come from adapter isolation, testnet-first validation, kill switches, and explicit live gates — not from building a separate paper-only system that cannot become live without a rewrite.
