# Binance USDS Futures Trend Paper Scanner v0.4

Created: UTC 2026-06-15 10:08:27 / 北京时间(UTC+8) 2026-06-15 18:08:27

## Objective

在 v0.3 多币种排名基础上，增加多周期趋势一致性过滤，优先保留被更高周期支持的趋势，减少单周期噪音和假突破。

## Scope

- 支持 `--intervals 1h,4h,1d` 形式的批量多周期扫描。
- 默认 primary interval 仍为 `1h`，但结果要带出各周期信号。
- 使用免费 Binance Futures 公共数据，不使用收费 API。
- 输出 JSON，包含机器可读结果和简洁中文摘要。
- 仍然 paper only，不下真实订单。

## v0.4 Logic

1. 对每个 symbol 分别计算多个周期的 v0.2/v0.3 纸面决策。
2. 以 primary interval（默认 `1h`）作为主决策输出。
3. 新增字段：
   - `timeframe_signals`: 各周期 decision 摘要。
   - `primary_trend`: 主周期方向。
   - `higher_timeframe_confirmed`: 更高周期是否都同向支持主趋势。
   - `timeframe_agreement_score`: 周期一致性分数。
4. 新增分组：
   - `strong_confirmed_trends`: 主趋势且被更高周期确认。
   - `early_trends`: 主趋势成立，但高周期尚未完全确认。
   - `conflicting_trends`: 低周期与高周期冲突。
5. 排名逻辑继续以趋势参与为核心，但 `timeframe_agreement_score` 会影响排序权重。
6. `summary_zh` 必须明确写出使用的周期列表，并保留 UTC / 北京时间（UTC+8）标签。

## CLI

单币种兼容模式：

```bash
scripts/binance_usds_futures_trend.py --symbol BTCUSDT --interval 1h --limit 240
```

多周期扫描：

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5
```

部分标的扫描：

```bash
scripts/binance_usds_futures_trend.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 1h,4h,1d --limit 240 --top 3
```

## Guardrails

- 禁止 `<1h` 周期。
- `top` 必须 `>= 1`。
- `risk_unit` 必须为正数。
- 不读取或暴露 `.env` 密钥值。
- 二级因子和多周期一致性只帮助排序和分组，不覆盖主趋势参与原则。
- push 前必须通过独立 agent 审核。

## Verification

- RED: 新增多周期测试先因缺少 `intervals` 参数失败。
- GREEN: 实现后 `python3 -m unittest tests/test_binance_usds_futures_trend.py -v` 通过。
- Real free-data check: 使用 `--all-symbols --intervals 1h,4h,1d --limit 240 --top 5` 跑真实 Binance 免费公开数据。

## Next Steps

1. 继续增强多周期一致性评分的可解释性。
2. 增加组合层风险预算与持仓分配。
3. 增加定时扫描任务和 Telegram 简报。
4. 增加历史回测，评估 rank_score 与一致性过滤对 CAGR / 回撤 的贡献。
5. 完成长时间 paper 验证后，再单独设计 Binance testnet/live execution Skill。
