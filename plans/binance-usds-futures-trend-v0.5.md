# Binance USDS Futures Trend Paper Scanner v0.5

Created: UTC 2026-06-15 11:05:28 / 北京时间(UTC+8) 2026-06-15 19:05:28

## Objective

在 v0.4 多周期趋势扫描基础上，新增组合层 paper 风险预算与持仓分配，避免单一趋势信号无限放大，并让输出更接近后续 paper/live 闭环需要的组合管理结构。

## Scope

- 仅做 paper allocation，不下真实订单。
- 支持总组合风险预算 `--portfolio-risk-budget`。
- 支持单标的风险上限 `--max-symbol-risk`。
- 只对 `hold_long` 且 `rank_score > 0`、`position_size > 0` 的结果分配 paper risk units。
- 分配方法先采用 rank-order capped greedy：按 `rank_score` 降序，在总预算和单币上限内依次分配。
- 输出 JSON 中新增 `scan.portfolio_allocation`。
- 中文摘要 `summary_zh` 增加组合纸面风险预算说明，并保留 UTC / 北京时间（UTC+8）标签。

## v0.5 Logic

1. v0.4 先完成多周期扫描、趋势分组和排序。
2. 当传入 `portfolio_risk_budget` 或 `max_symbol_risk` 时，启用组合分配。
3. 参数默认补齐：
   - 只给 `--max-symbol-risk` 时，总预算默认 `3.0` risk units。
   - 只给 `--portfolio-risk-budget` 时，单标的上限默认 `1.0` risk unit。
4. 风险约束：
   - `total_risk_budget > 0`；
   - `max_symbol_risk > 0`；
   - 单标的分配 `<= min(position_size, max_symbol_risk, remaining_budget)`；
   - 总分配 `<= total_risk_budget`。
5. 不符合分配条件的 symbol 写入 `skipped_symbols`，便于后续诊断。
6. 分配结果包含 UTC 和 北京时间（UTC+8）时间戳。

## CLI

多周期全市场扫描 + 组合 paper 风险分配：

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1
```

部分标的扫描 + 组合 paper 风险分配：

```bash
scripts/binance_usds_futures_trend.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 1h,4h,1d --limit 240 --top 3 --portfolio-risk-budget 2 --max-symbol-risk 1
```

## Guardrails

- 禁止 `<1h` 周期。
- 不读取或暴露 `.env` 密钥值。
- 不下真实订单；输出仍为 `mode=paper`。
- 组合分配不能超过总预算和单币上限。
- `position_size` 仍保留趋势延伸/二级因子影响，不因组合预算而强行放大。
- push 前必须通过独立 agent 审核。

## Verification

- RED: 新增 portfolio allocation 测试先因缺少 `allocate_portfolio_risk` 和 `portfolio_risk_budget` 参数失败。
- GREEN: 实现后新增测试通过。
- Full suite: `python3 -m unittest tests/test_binance_usds_futures_trend.py -v` 通过。
- Real free-data check: 使用 `--all-symbols --intervals 1h,4h,1d --limit 240 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1` 跑真实 Binance 免费公开数据。

## Next Steps

1. 增强 allocation explainability：说明每个 symbol 为什么被分配/跳过。
2. 增加 paper state persistence，记录连续扫描中的分配变化。
3. 增加定时扫描任务和 Telegram 简报。
4. 增加历史回测，评估 rank_score、多周期一致性和组合 cap 对 CAGR / 回撤 的贡献。
5. 长时间 paper 验证后，再单独设计 Binance testnet/live execution Skill。
