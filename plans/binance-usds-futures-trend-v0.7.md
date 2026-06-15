# Binance USDS Futures Trend Paper Scanner v0.7

Created: UTC 2026-06-15 12:36:44 / 北京时间(UTC+8) 2026-06-15 20:36:44

## Objective

在 v0.6 allocation explainability 基础上，新增 paper state persistence：保存连续扫描的核心快照，并计算本次与上次的变化，为 v0.8 Telegram 简报、复盘和后续 paper position lifecycle 打基础。

## Scope

- 继续保持 paper-only，不下真实订单。
- 新增状态快照构建函数，保存字段：
  - UTC / 北京时间（UTC+8）时间戳；
  - intervals / primary_interval；
  - top trends；
  - portfolio allocation；
  - skipped details；
  - errors_count；
  - per-symbol action、ranking_bucket、rank_score。
- 新增状态变化计算：
  - added_allocations；
  - removed_allocations；
  - changed_allocations（risk units 增减）；
  - ranking_changes；
  - action_changes；
  - bucket_changes。
- 新增状态文件读写：
  - 缺失状态文件视为首次运行；
  - 损坏 JSON 不崩溃，记录 error 并覆盖为最新可用快照；
  - 状态文件保存原子写入。
- CLI 新增：
  - `--state-file PATH`：扫描模式下启用 v0.7 state persistence；
  - `--no-save-state`：只计算变化，不写入状态文件。
- 输出 `scan.state_change` 与 `scan.paper_state`。

## State Path Policy

- 默认不自动写状态，只有显式传入 `--state-file` 才保存。
- 真实运行建议路径：`state/binance-usds-futures-trend-paper-state.json`。
- 新增 `.gitignore` 忽略 `state/*.json`，避免频繁变化的真实 paper state 入库。
- 测试使用临时目录；不保存 API key、secret、环境变量值。

## v0.7 Logic

1. 扫描完成后，从 `scan` 构建 `current_snapshot`。
2. 若 `--state-file` 存在且 JSON 可读，加载为 `previous_snapshot`。
3. 对比：
   - allocation symbol 集合变化；
   - paper_risk_units 数值变化；
   - `results` 排名序号变化；
   - `action` 变化；
   - `ranking_bucket` 变化。
4. 将变化写入 `scan.state_change`。
5. 将当前快照写入状态文件，除非 `--no-save-state`。
6. 所有状态内容必须标记 `mode=paper`。

## CLI

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json
```

Dry-run state change without writing:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json --no-save-state
```

## Guardrails

- 禁止 `<1h` 周期。
- 不读取或暴露 `.env` 密钥值。
- 不下真实订单；输出仍为 `mode=paper`。
- 状态文件只存 paper scan 摘要，不存 API key、secret、环境变量。
- push 前必须通过独立 agent 审核。

## Verification

- RED: 新增首次运行、连续运行、allocation 增减、损坏状态文件测试，先因缺少函数/CLI 字段失败。
- GREEN: 实现后目标测试通过。
- Full suite: `python3 -m unittest tests/test_binance_usds_futures_trend.py -v`。
- Syntax: `python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py`。
- Diff whitespace: `git diff --check`。
- Real free-data check: 使用真实 Binance 免费公开数据跑全市场多周期扫描 + portfolio allocation + state file，确认 JSON 可解析、`mode=paper`、UTC / 北京时间（UTC+8）、errors_count/state_change 存在。

## Next Steps

1. v0.8 Scheduled Scan + Telegram Briefing：基于 v0.7 state_change 输出简洁中文 Telegram 简报。
2. v0.9 Historical Backtest Framework。
3. v1.0 Evidence-based Strategy Refinement。
