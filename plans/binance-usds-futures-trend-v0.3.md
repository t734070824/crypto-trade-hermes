# Binance USDS Futures Trend Paper Scanner v0.3

Created: UTC 2026-06-15 09:43:57 / 北京时间(UTC+8) 2026-06-15 17:43:57

## Objective

在 v0.2 单币种趋势决策基础上，增加多币种批量扫描和趋势排名，用于决定 paper 组合中优先关注和分配风险预算的标的。

## Scope

- 扫描配置交易池 20 个 USDS-M 合约标的。
- 周期仍必须 `>= 1h`，默认 `1h`，支持 `4h`、`1d` 等已允许周期。
- 使用免费 Binance Futures 公共数据，不使用收费 API。
- 输出 JSON，包含机器可读结果和简洁中文摘要。
- 仍然 paper only，不下真实订单。

## v0.3 Logic

1. 对每个 symbol 复用 v0.2：K-line + optional public context factors。
2. 对每个单币种 decision 增加：
   - `trend_strength`: 基于价格/EMA200 与 EMA50/EMA200 的 ATR 标准化趋势强度。
   - `extension_atr`: 价格相对 EMA50 的 ATR 扩展度。
   - `rank_score`: `trend_strength * confidence_score * position_size`。
   - `ranking_bucket`: `top_trend` / `risk_high_trend` / `watchlist` / `error`。
3. 批量结果按 `rank_score` 降序排列。
4. 输出：
   - `top_trends`: 最强趋势 Top N。
   - `risk_high_trends`: 仍在趋势内但 funding/OI/拥挤度/扩展度等风险偏高。
   - `watchlist`: 主趋势过滤失败或数据错误，暂不参与。
   - `summary_zh`: 含 UTC 与 北京时间(UTC+8) 的中文摘要。

## CLI

单币种兼容模式：

```bash
scripts/binance_usds_futures_trend.py --symbol BTCUSDT --interval 1h --limit 240
```

多币种扫描：

```bash
scripts/binance_usds_futures_trend.py --all-symbols --interval 1h --limit 240 --context-limit 30 --top 5
```

部分标的扫描：

```bash
scripts/binance_usds_futures_trend.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --top 3
```

## Guardrails

- 禁止 `<1h` 周期。
- `risk_unit` 必须为正数，`top` 必须 `>= 1`。
- 不读取或暴露 `.env` 密钥值。
- 二级因子和排名只帮助风险预算排序，不覆盖主趋势参与原则。
- push 前必须通过独立 agent 审核。

## Verification

- RED: 新增批量扫描测试先因缺少 `scan_symbols` 失败。
- GREEN: 实现后 `python3 -m unittest tests/test_binance_usds_futures_trend.py -v` 通过。
- Real free-data check: 使用 `--all-symbols --interval 1h --limit 240 --context-limit 30 --top 5` 跑真实 Binance 免费公开数据。

## Next Steps

1. 增加 4h + 1d 多周期趋势一致性。
2. 增加 paper 持仓状态持久化与组合风险预算。
3. 增加定时扫描任务和 Telegram 简报。
4. 增加历史回测，评估 `rank_score` 对 CAGR/回撤的贡献。
5. 完成长期 paper 验证后，再单独设计 Binance testnet/live execution Skill。
