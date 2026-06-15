# v0.9 Historical Backtest Framework Workflow

Created: UTC 2026-06-15 13:24:50 / 北京时间(UTC+8) 2026-06-15 21:24:50

## Purpose

记录 v0.9 如何在现有 Binance USDS-M futures paper scanner 上新增历史回测框架，用免费历史 K-line 数据评估 CAGR、回撤与风险调整指标。该版本只提供 paper-only 诊断框架，不代表实盘收益，也不触发任何真实订单。

## Implementation Summary

- 新增 `backtest_symbol(candles, symbol, interval, ...)`：对单一 symbol 用现有 EMA50/EMA200 + ATR decision 逻辑做 paper-only long exposure simulation。
- 新增 `backtest_symbols(symbols, interval, limit, ...)`：通过免费 `/fapi/v1/klines` 抓取历史 K-line 后聚合多标的回测。
- 新增 CLI `--backtest`：输出 JSON `{ ok, backtest }`，不输出 Telegram briefing。
- 输出指标包括 CAGR、max drawdown、Calmar、Sharpe、win rate、average holding candles、turnover、total return、per-symbol contribution。
- 多标的指标基于 common-`close_time` aligned combined portfolio equity curve 计算；`per_symbol_contribution` 表示各标的对同一对齐 horizon 的组合 total return 贡献，而不是简单平均单标的 CAGR/Sharpe。
- 保留项目约束：周期必须 `>=1h`，不使用收费 API，不使用 API key，不调用 signed/live execution。

## Canonical Commands

Selected symbols:

```bash
scripts/binance_usds_futures_trend.py \
  --backtest \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --interval 1h \
  --limit 500
```

Full configured universe:

```bash
scripts/binance_usds_futures_trend.py \
  --backtest \
  --all-symbols \
  --interval 4h \
  --limit 500
```

## Output Contract

- `backtest.mode` must be `paper`.
- `generated_at_utc` and `generated_at_beijing` must both exist and be clearly labelled.
- `metrics` must include:
  - `cagr`;
  - `max_drawdown`;
  - `calmar`;
  - `sharpe`;
  - `win_rate`;
  - `average_holding_candles`;
  - `turnover`;
  - `total_return`;
  - `initial_equity`;
  - `final_equity`.
- `per_symbol_contribution` maps each tested symbol to its paper total-return contribution.
- `errors_count` and `errors` summarize failed symbol fetch/backtest attempts.
- `summary_zh` must contain `paper only` and must not present results as live returns.

## Guardrails

- Reject `<1h` intervals such as `1m`, `5m`, `10m`, `15m`, `30m`.
- Require more than 200 candles so EMA200 has enough warmup.
- Use only free Binance public K-line data.
- Never persist or print secrets.
- Never include live/signed order fields such as API keys, order IDs, signed execution, or live order language.
- Backtest results are evidence inputs for v1.0, not proof that CAGR targets are achieved.

## TDD Pattern

1. RED tests:
   - `backtest_symbol` missing;
   - `--backtest` CLI missing;
   - short interval and insufficient history rejected;
   - multi-symbol aggregate output expected.
2. GREEN implementation:
   - add interval annualization helper;
   - add max drawdown / Sharpe / aggregate metric helpers;
   - simulate exposure using current candle close after decision warmup;
   - add CLI branch before scan/decision branch.
3. Verification:
   - run target tests first;
   - run full suite;
   - run syntax checks;
   - run real free-data sample.

## Verification Checklist

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py
git diff --check
scripts/binance_usds_futures_trend.py --backtest --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 500
```

Confirm the real-data run includes UTC / 北京时间（UTC+8）、`mode=paper`、metrics、`errors_count` equivalent via `errors` list, and no live/signed/order/secret fields.

## Review and Push Gate

Before push, use an independent agent to review the diff. The review must fail closed if it finds secrets, live execution, paid APIs, `<1h` defaults, missing tests, broken docs, or metrics that overstate paper backtests as live returns.
