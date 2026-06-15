# Binance USDS-M Futures Trend v1.6 Plan — Strategy Evolution from Runtime Evidence

Created: UTC 2026-06-15 15:44:10 / 北京时间（UTC+8）2026-06-15 23:44:10

## Goal

基于 v1.3+ 记录的 runtime evidence，对候选策略进行可复盘比较，只有证据改善才允许后续推广。

## Architecture

`StrategyEvolution` 读取 recorded runtime records，构建 baseline/candidate replay。候选策略必须复用相同 market inputs/events，避免因为行情样本漂移导致虚假提升。

## Scope

- Add runtime JSONL loader with schema validation.
- Add replay dataset builder.
- Add candidate comparison report:
  - CAGR proxy / return proxy；
  - max drawdown；
  - turnover；
  - holding time；
  - missed-trend / premature-exit diagnostics；
  - evidence score。
- Add promotion gate: no auto-change of defaults; output `auto_promote_defaults=false`.

## Non-Goals

- 不自动修改 live 参数。
- 不把短样本 paper 数据当作实盘收益。
- 不使用收费数据。

## TDD Tasks

1. Test JSONL loader rejects records without schema_version/environment/timestamps.
2. Test replay uses identical captured inputs for baseline and candidate.
3. Test drawdown guardrail can block candidate despite higher return.
4. Test report includes UTC / 北京时间（UTC+8） timestamps.
5. Test no default parameter promotion occurs automatically.

## Verification

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
git diff --check
```

## Acceptance

- Strategy changes are evaluated against recorded runtime evidence.
- Reports are reproducible and paper/testnet/live environment-aware.
- No automatic default promotion.
