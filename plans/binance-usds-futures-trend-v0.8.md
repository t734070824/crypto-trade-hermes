# Binance USDS Futures Trend Paper Scanner v0.8

Created: UTC 2026-06-15 12:52:10 / 北京时间(UTC+8) 2026-06-15 20:52:10

## Objective

在 v0.7 paper state persistence 基础上，新增 scheduled scan + Telegram briefing：定时运行 paper scan，把简洁中文结果发送到 Telegram，为长期 paper 观察和后续回测/生命周期开发积累连续证据。

## Scope

- 继续保持 paper-only，不下真实订单。
- 新增 Telegram 简报生成函数，基于 `scan` 输出短文本，不直接暴露完整 JSON。
- 简报必须包含：
  - UTC / 北京时间（UTC+8）；
  - Top trends；
  - portfolio allocation；
  - state change；
  - risk notes；
  - errors_count；
  - `paper only` 标记。
- 新增 CLI 输出模式：扫描完成后可输出 Telegram 简报文本。
- 新增 cron/script 支持：使用 >=1h 周期（默认每 4h 或手动 run），运行全市场多周期扫描并写入 ignored `state/*.json`。
- 默认无变化策略：发送精简 heartbeat（包含无新增/移除/变化），保持可观测性；后续如用户要求再改为静默。

## Out of Scope

- 不做真实下单、testnet 下单或 signed API。
- 不引入收费 API。
- 不使用 `<1h` 周期。
- 不做历史回测（留给 v0.9）。
- 不把运行态 state JSON 纳入 git。

## v0.8 Logic

1. 运行 v0.7 scan：默认 `--all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json`。
2. 生成/加载 paper state，计算 `state_change`。
3. 将 `scan` 压缩为 Telegram 简报：
   - 标题：Binance USDS-M Paper Scan；
   - 时间：UTC 与 北京时间（UTC+8）；
   - Top trends / allocation；
   - 变化：新增、移除、risk units 变化、action/bucket/rank 变化；
   - 风险提示：risk_high、conflicting、errors_count；
   - 安全提示：paper only，无真实下单。
4. CLI `--telegram-brief` 输出纯文本简报，便于 cron no-agent 或 agent cron 直接投递。
5. Hermes cron job 使用自包含 prompt，不递归创建 cron。

## CLI

```bash
scripts/binance_usds_futures_trend.py \
  --all-symbols \
  --intervals 1h,4h,1d \
  --limit 240 \
  --context-limit 30 \
  --top 5 \
  --portfolio-risk-budget 3 \
  --max-symbol-risk 1 \
  --state-file state/binance-usds-futures-trend-paper-state.json \
  --telegram-brief
```

## Cron Policy

- Schedule: every 4h by default（>=1h guardrail）。
- Delivery: Telegram origin/home chat。
- Mode: paper-only briefing；不递归创建 cron。
- No-change behavior: send compact heartbeat by default。

## Guardrails

- 禁止 `<1h` 周期。
- 不读取或展示 `.env` 密钥值。
- 不下真实订单；输出必须标记 `paper only`。
- Telegram 简报不包含过长 JSON，不包含 secret/key/env 值。
- `state/*.json` 是运行态 ignored 文件，不提交。
- push 前必须通过独立 agent 审核。

## Verification

- RED: 新增 Telegram 简报字段/格式测试，先因缺少函数或 CLI 参数失败。
- GREEN: 实现后目标测试通过。
- Full suite: `python3 -m unittest tests/test_binance_usds_futures_trend.py -v`。
- Syntax: `python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py`。
- Diff whitespace: `git diff --check`。
- Real free-data check: 使用真实 Binance 免费公开数据跑全市场多周期扫描 + portfolio allocation + state file + Telegram brief，确认文本含 UTC / 北京时间（UTC+8）、paper only、errors_count、state change。
- Cron: 创建/手动 run cron job 验证 Telegram 简报可投递。

## Next Steps

1. v0.9 Historical Backtest Framework。
2. v1.0 Evidence-based Strategy Refinement。
3. v1.1 Paper Trading Lifecycle。
