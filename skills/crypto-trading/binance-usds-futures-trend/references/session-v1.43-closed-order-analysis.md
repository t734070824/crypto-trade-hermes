# Session v1.43 — Closed Order Analysis Evidence

## Context

亏损或已结束订单不能只作为“失败结果”看待；它们应被标准化为 runtime evidence，用于区分策略成本、风险再平衡、保护单行为、执行质量与系统缺陷。

## Implemented Boundary

新增 CLI：

```bash
scripts/binance_usds_futures_trend.py \
  --analyze-closed-orders \
  --testnet-order-journal-file state/binance-usds-futures-trend-testnet-orders.jsonl
```

该命令只读解析 order journal，不签名、不下单、不取消订单。

## Evidence Schema

每个结束订单标准化为 `closed_order.v1`，包括：

- `environment`
- `symbol`
- `client_order_id`
- `order_id`
- `side`
- `order_type`
- `status`
- `position_effect`
- `close_reason`
- `quantity`
- `average_fill_price`
- `realized_pnl`
- `fees`
- `net_pnl`
- `slippage_bps`
- `trade_count`
- `opened_or_submitted_at_utc`
- `opened_or_submitted_at_beijing`
- `closed_at_utc`
- `closed_at_beijing`
- `linked_signal_action`
- `current_exposure`
- `desired_exposure`
- `analysis_flags`

聚合报告为 `closed_order_analysis.v1`，包含 by-symbol、by-close-reason、loss count、PnL 汇总和 `strategy_evolution_inputs`。

## Attribution Rules

- `STOP_MARKET` / `STOP` 或 `protection_role=stop_loss` → `stop_loss`
- `TAKE_PROFIT_MARKET` / `TAKE_PROFIT` 或 `protection_role=take_profit_*` → `take_profit`
- `SELL MARKET` 且 signal action 仍为 `hold_long`、`delta_exposure < 0` → `risk_rebalance_reduction`
- `SELL` 且 action 为 `flat/exit` → `strategy_exit`
- `CANCELED/REJECTED/EXPIRED` 分别归为执行/重规划类别

## Important Pitfall

开仓 BUY 的 `net_pnl` 可能因为手续费为负，但它不是 closed losing trade。亏损样本标记应优先看 closing/reduction 订单的 realized PnL 或净损益，不应把普通开仓手续费误判成亏损策略样本。

## Verification

TDD 流程：

1. 先写失败测试：
   - `test_closed_order_analysis_classifies_losing_risk_rebalance_from_journal`
   - `test_cli_can_emit_closed_order_analysis_from_order_journal`
2. 确认 RED：缺少 `analyze_closed_orders` 和 CLI 参数。
3. 实现最小代码。
4. 运行验证：

```bash
python3 -m unittest tests.test_binance_usds_futures_trend.BinanceUsdsFuturesTrendTests.test_closed_order_analysis_classifies_losing_risk_rebalance_from_journal tests.test_binance_usds_futures_trend.BinanceUsdsFuturesTrendTests.test_cli_can_emit_closed_order_analysis_from_order_journal -v
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_usds_futures_testnet_hourly.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py tests/test_cron_trading_config.py
```

## Current Live Journal Observation

Against `state/binance-usds-futures-trend-testnet-orders.jsonl` at UTC 2026-06-17T09:57:04 / 北京时间（UTC+8）2026-06-17T17:57:04, analyzer reported:

- closed/ended order records loaded: 7
- loss samples: 3
- total realized PnL: -2.77575621
- total net PnL: -3.35550922
- close reasons:
  - `non_closing_or_opening_order`: 4
  - `risk_rebalance_reduction`: 3
- strategy evolution inputs:
  - `loss_attribution`
  - `risk_sizing_or_rebalance`

These numbers are from local journal evidence only. Exchange-triggered orders that are not yet backfilled into the journal still require a future signed-history backfill step.
