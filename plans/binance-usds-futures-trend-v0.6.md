# Binance USDS Futures Trend Paper Scanner v0.6

Created: UTC 2026-06-15 11:18:56 / 北京时间(UTC+8) 2026-06-15 19:18:56

## Objective

在 v0.5 组合层 paper 风险预算基础上，增强分配可解释性：让每个被分配或跳过的 symbol 都能说明原因，并把核心说明写入中文摘要，便于后续 Telegram 简报、人工复盘和 paper/live 闭环前的风险审核。

## Scope

- 继续保持 paper-only，不下真实订单。
- `portfolio_allocation.allocations[]` 新增：
  - `constraints_applied`：本次分配触发的约束，例如 `max_symbol_risk_cap`、`remaining_budget_cap`、`full_position_size`；
  - `allocation_explanation`：包含 rank_score、原始 position_size、最终 allocated、约束和 paper-only 标记的可读说明。
- `portfolio_allocation.skipped_details[]` 新增跳过明细：
  - `symbol`；
  - `skip_reason`，例如 `not_hold_long`、`non_positive_rank_score`、`non_positive_position_size`、`no_remaining_budget`；
  - `action`、`rank_score`、`position_size`。
- `summary_zh` 在组合预算行后新增 `分配说明`，展示前 3 个 allocation 的解释。
- 保留 UTC 和 北京时间（UTC+8）标签。

## v0.6 Logic

1. 先沿用 v0.5 的 rank-order capped greedy 分配。
2. 对不符合候选条件的 symbol：
   - 非 `hold_long` → `not_hold_long`；
   - `rank_score <= 0` → `non_positive_rank_score`；
   - `position_size <= 0` → `non_positive_position_size`。
3. 对候选但预算耗尽的 symbol：
   - 写入 `skipped_details`，`skip_reason=no_remaining_budget`。
4. 对被分配的 symbol：
   - 如果原始 `position_size` 被降低，记录 `position_size_reduced`；
   - 如果触发单标的上限，记录 `max_symbol_risk_cap`；
   - 如果触发剩余组合预算上限，记录 `remaining_budget_cap`；
   - 如果完全按原始 `position_size` 分配，记录 `full_position_size`。
5. 中文摘要只展示前 3 个分配解释，避免 Telegram 简报过长。

## CLI

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1
```

## Guardrails

- 禁止 `<1h` 周期。
- 不读取或暴露 `.env` 密钥值。
- 不下真实订单；输出仍为 `mode=paper`。
- 可解释性字段只解释 paper allocation，不应被误用为交易执行回报。
- push 前必须通过独立 agent 审核。

## Verification

- RED: 新增 allocation 解释字段与摘要展示测试，先因缺少 `constraints_applied` / `分配说明` 失败。
- GREEN: 实现后目标测试通过。
- Full suite: `python3 -m unittest tests/test_binance_usds_futures_trend.py -v`。
- Syntax: `python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py`。
- Real free-data check: 使用真实 Binance 免费公开数据跑全市场多周期扫描 + portfolio allocation。

## Next Steps

1. 增加 paper state persistence，记录连续扫描中的分配变化。
2. 增加定时扫描任务和 Telegram 简报。
3. 增加历史回测，评估 rank_score、多周期一致性和组合 cap 对 CAGR / 回撤 的贡献。
4. 长时间 paper 验证后，再单独设计 Binance testnet/live execution Skill。
