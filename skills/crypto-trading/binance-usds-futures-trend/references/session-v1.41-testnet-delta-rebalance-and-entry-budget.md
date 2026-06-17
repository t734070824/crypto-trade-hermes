# Session v1.41 — Testnet Delta Rebalance and Entry Budget Audit

Date: UTC 2026-06-17 / 北京时间（UTC+8）2026-06-17

## Trigger

User asked for an independent-agent explanation of the `testnet-agent-hourly` run at 北京时间（UTC+8）2026-06-17 15:05 / UTC 2026-06-17 07:05:

1. Why SOLUSDT and ETHUSDT were reduced.
2. Why no other symbols entered.

This was a read-only audit. Do not trigger `cronjob(action="run")`, `hermes cron run`, signed testnet cycles, order placement, or order cancellation for this class of timing/execution explanation unless the user explicitly asks to run now.

## Evidence Files

Primary evidence used:

- `cron/output/f7201d6c1c57/2026-06-17_15-05-31.md`
- `state/binance-usds-futures-trend-testnet-runtime.jsonl`
- `state/binance-usds-futures-trend-testnet-orders.jsonl`
- Code paths:
  - `scripts/binance_usds_futures_testnet_hourly.py`
  - `scripts/binance_usds_futures_trend.py`
  - `scripts/binance_trend_core/strategy.py`
  - `scripts/binance_trend_core/execution.py`
  - `scripts/binance_trend_core/loop.py`

## Key Finding 1 — ETH/SOL Reductions Were Delta-Only Risk Rebalancing

At 15:05 北京时间（UTC+8）, ETHUSDT and SOLUSDT signals remained `hold_long`; they did not flip to bearish/flat.

The reduction happened because account-risk sizing recalculated a lower **target total position** than the current testnet exposure. The execution engine then reconciled by submitting only the negative delta:

```text
delta = desired_exposure - current_exposure
if delta < 0: submit SELL MARKET abs(delta)
```

Observed values:

- ETHUSDT:
  - current exposure: `0.497`
  - new target total position: `0.3486655`
  - delta: `-0.1483345`
  - action: `SELL MARKET`, exchange-adjusted quantity about `0.148`
  - postflight position: about `0.349`
- SOLUSDT:
  - current exposure: `9.43`
  - new target total position: `6.96428984`
  - delta: `-2.46571016`
  - action: `SELL MARKET`, exchange-adjusted quantity about `2.46`
  - postflight position: about `6.97`

The dominant sizing driver was larger ATR/stop distance under fixed account risk budget:

```text
risk_budget = account_equity * account_risk_fraction
qty_by_stop_risk = risk_budget / stop_distance
desired_qty = min(qty_by_stop_risk, qty_by_notional_cap)
```

Example comparison from the audit:

- ETH stop distance grew from about `30.12` at 14:05 to `43.02` at 15:05.
- SOL stop distance grew from about `1.53` at 14:05 to `2.1536` at 15:05.

With fixed `account_risk_fraction=0.003`, larger stop distance reduced target quantity.

## Key Finding 2 — “No Other Entries” Was Mostly Scope + Atomic Order Budget

The hourly hot path was not scanning the full configured universe. It only ran:

- BTC group: `BTCUSDT`
- Alt group: `ETHUSDT,SOLUSDT,BNBUSDT`

Therefore XRP, DOGE, LINK, AVAX, ADA, etc. were simply outside this run's execution scope.

### BTCUSDT

BTCUSDT had a `hold_long` signal and positive desired exposure, but no order was submitted.

Reason: empty-position entry requires an atomic entry/protection group of 4 instructions:

1. Entry market order.
2. Stop-loss order.
3. Take-profit tranche 1.
4. Take-profit tranche 2.

The BTC group configured `max_order_count=3`, so the full 4-order atomic group was skipped with:

```text
insufficient_order_budget_for_atomic_entry_protection_group
```

### BNBUSDT

BNBUSDT also had a `hold_long` signal and positive desired exposure, but no order was submitted.

Reason: Alt group configured `max_order_count=6`. ETH/SOL reductions and existing-position protection maintenance had higher priority and consumed the available order budget. BNB's 4-order atomic entry/protection group could not fit in the remaining budget and was skipped with the same reason:

```text
insufficient_order_budget_for_atomic_entry_protection_group
```

## Diagnostic Pattern for Future Sessions

When explaining a specific cron trading decision:

1. Identify the exact scheduled/completion time and label UTC and 北京时间（UTC+8）.
2. Read the matching cron output file first.
3. Locate the runtime JSONL record(s) by `run_id`, `generated_at_utc`, or order timestamps.
4. Compare:
   - signal `action`;
   - `position_size` / `account_risk_sizing.desired_position_size`;
   - broker/current position from preflight or loaded account snapshot;
   - desired order metadata: `current_exposure`, `desired_exposure`, `delta_exposure`;
   - order journal submit/lifecycle rows;
   - postflight positions and open algo order counts.
5. Distinguish:
   - trend exit vs risk-resized `hold_long` reduction;
   - target total exposure vs additive quantity;
   - skipped due to no signal vs skipped due to atomic order budget;
   - full-universe strategy scope vs fixed hourly group scope.

## Pitfalls

- Do not say “strategy turned bearish” when `action=hold_long` and the SELL order is only a negative delta from target-total-position reconciliation.
- Do not say “no other symbols qualified” unless the hourly wrapper actually evaluated the full universe. In this system, the current hot path only evaluates BTCUSDT, ETHUSDT, SOLUSDT, and BNBUSDT.
- Do not ignore atomic entry/protection order budgeting. A valid entry signal can be skipped if entry + SL + TP tranches cannot fit inside the group `max_order_count`.
- Do not treat order acknowledgements as fills. Check lifecycle rows and postflight positions.
