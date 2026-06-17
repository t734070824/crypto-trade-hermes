# v1.35 CAGR optimization plan review against current chain

Use when reviewing or updating `plans/trading-chain-cagr-optimization.md` or similar CAGR/hold-style optimization plans.

## Current-chain correction

The current trading chain is no longer just a basic signal → intent → delta execution path. It includes:

- public Binance USDS-M K-lines on intervals `>=1h`;
- `decide()` signal generation;
- account-risk sizing via `apply_account_risk_sizing_to_signal()` using equity/available balance, stop distance, leverage, max notional, max exposure, and exposure-fraction caps;
- `TrendParticipationStrategy`, whose `position_size` is target total exposure;
- `FunctionRiskManager`;
- `PositionReconciliationExecutionEngine`, which submits only `desired_exposure - current_exposure` and also plans protection repair;
- `BinanceTestnetBroker` with signed testnet gates, exchange rules, order journal, account/open-order/open-algo sync, lifecycle tracking, and redaction;
- script-owned hourly hot path via `scripts/binance_usds_futures_testnet_hourly.py/.sh` under `no_agent=true`;
- runtime JSONL + order journal evidence;
- separate daily read-only replay diagnostics agent.

## Planning implications

When updating the CAGR optimization plan, do not propose rebuilding already-present foundations. Adjust the plan around these deltas:

1. Reframe sizing work as upgrading existing account-risk sizing with regime multiplier, trend-quality score, compounding headroom, tranche budget, and portfolio heat.
2. Put regime/persistence scoring before sizing changes, because sizing/add/trim need a reliable graded input.
3. Keep target-total exposure semantics explicit: add-ons are produced by increasing target total exposure; execution submits only the delta. Never treat `position_size` as “buy this much more”.
4. Lifecycle improvements should manage entry/add/hold/trim/harvest/exit state while preserving duplicate-add prevention and intact protection bundles.
5. Execution work should refine existing delta/protection reconciliation: min effective delta after exchange rules, explicit skip reasons, protection budget reporting, and fail-closed open-algo verification.
6. Runtime promotion gates should consume real testnet evidence, not only proxy replay metrics: order journal, lifecycle tracked/filled counts, fees, net PnL, slippage, rejected/skipped reasons, no-op cycles, target-vs-actual exposure gap, and protection friction.
7. Cron/ops changes must respect the current boundary: hourly trading is script-owned `no_agent=true`; daily analyzer is read-only agent mode. Prompt prose does not change hot-path behavior unless corresponding CLI flags or engine code change.

## Suggested updated priority order

1. Baseline bottleneck measurement from current runtime/order-journal evidence.
2. Regime / persistence / trend-quality score.
3. Regime-aware account-risk sizing and compounding headroom.
4. Explicit lifecycle state for add/trim/trail/harvest.
5. Pyramiding and partial harvesting under target-total semantics.
6. Execution/protection observability and skip-reason refinement.
7. Runtime/testnet evidence promotion gate.
8. Script-owned hourly report and read-only daily analyzer improvements.
9. Only then consider testnet scope expansion; live/mainnet remains out of scope unless separately authorized.

## Pitfalls

- Do not treat `position_size` as additive quantity.
- Do not assume changing a cron prompt changes a `no_agent=true` script-owned hot path.
- Do not describe account-risk sizing as absent; it exists and needs regime-aware refinement.
- Do not use proxy replay metrics alone as evidence for CAGR improvement.
- Do not fold live/mainnet work into CAGR optimization plans.
