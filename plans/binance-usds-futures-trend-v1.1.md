# Binance USDS-M Futures Trend v1.1 Plan — Paper Trading Lifecycle

Created: UTC 2026-06-15 14:38:39 / 北京时间（UTC+8）2026-06-15 22:38:39

## Goal

把单次 paper scanner 输出升级为可连续运行的 paper 持仓生命周期：记录 entry / add / reduce / exit intent、trailing stop、take-profit tranche 与归因，但仍不触发任何真实下单。

## Scope

- 新增 `apply_paper_lifecycle(scan, lifecycle_file, save_lifecycle=True)`。
- 新增 `paper_lifecycle` snapshot：
  - UTC / 北京时间（UTC+8）时间戳；
  - intervals / primary_interval；
  - open / closed positions；
  - per-symbol `status`、`last_intent`、`current_size`、`entry_reference`、`last_reference`、`trailing_stop`、`take_profit_1/2`、`executed_tranches`、`reason`。
- 新增 `lifecycle_change`：
  - `first_run`；
  - `intent_changes`；
  - `status_changes`；
  - `tranche_events`；
  - `current_errors_count`。
- CLI：扫描模式支持 `--lifecycle-file` 与 `--no-save-lifecycle`。

## Non-Goals

- 不做真实订单。
- 不接 signed Binance endpoint。
- 不引入收费 API。
- 不使用 `<1h` 周期。
- 不把 paper lifecycle 称为实盘持仓。

## TDD Evidence

RED 已确认：

- `apply_paper_lifecycle` 缺失导致 entry / reduce / exit 测试失败。
- CLI 缺少 `--lifecycle-file` / `--no-save-lifecycle` 导致 argparse RED。

GREEN 范围：

- 首次扫描生成 entry intent 并原子保存 lifecycle snapshot。
- 连续扫描更新 trailing stop，记录 TP tranche，并标记 reduce intent。
- 趋势翻 flat 时把 open paper position 标记为 closed / exit。
- CLI scan 模式可附加 lifecycle，并支持 no-save dry run。

## Verification

- Unit tests: `python3 -m unittest tests/test_binance_usds_futures_trend.py -v`
- Syntax: `python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py`
- Real free-data check:

```bash
scripts/binance_usds_futures_trend.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --intervals 1h,4h,1d \
  --limit 240 \
  --context-limit 30 \
  --top 3 \
  --portfolio-risk-budget 3 \
  --max-symbol-risk 1 \
  --state-file state/binance-usds-futures-trend-paper-state.json \
  --lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json \
  --no-save-state \
  --no-save-lifecycle
```

Expected: JSON parses, `scan.mode=paper`, `paper_lifecycle.mode=paper`, `lifecycle_change` present, timestamps include UTC and 北京时间（UTC+8）, no live/signed/order secret fields.
