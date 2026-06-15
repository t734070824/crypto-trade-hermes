# Binance USDS-M Futures Paper Trading Roadmap

Created: UTC 2026-06-15 12:30:18 / 北京时间(UTC+8) 2026-06-15 20:30:18

## Purpose

这是 crypto-trade-hermes 的 tracked 总路线图，用来约束后续开发顺序，避免因为 Context 压缩、临时想法或实现冲动而偏离目标。

目标：基于 Binance USDS-M Futures 免费公开数据，构建 >=1h 周期、多周期趋势跟随、组合风险控制、长期 paper 验证优先的交易系统；追求 CAGR 30%，并探索 CAGR 100% 的可行性。

## Non-Negotiable Constraints

1. **中文交流**：对用户输出默认中文，尽量简洁。
2. **时间标注**：所有时间必须明确标注 UTC 或 北京时间（UTC+8）。
3. **数据周期**：禁止使用 `<1h` 的短周期数据，包括 `1m`、`5m`、`10m`、`15m`、`30m`。
4. **API 成本**：不使用收费 API。
5. **交易安全**：当前 scanner 和 paper workflow 不允许真实下单。
6. **趋势目标**：优先在主趋势中持续参与、持续持有、分批收割，避免过早离场。
7. **提交流程**：任何 git push 前必须先通过独立 agent 审核；审核 FAIL 时必须修改后重新审核。
8. **验证要求**：代码变更必须有测试；涉及策略输出必须跑真实 Binance 免费公开数据验证，若网络/API 阻塞需如实报告。
9. **仓库同步**：符合仓库策略的 tracked 变更必须 commit 并 push。

## Canonical Development Loop

每个版本默认按以下顺序执行：

1. **Inspect**：读取本路线图、当前 Skill、上一版本 plan、git status。
2. **Plan**：创建 `plans/binance-usds-futures-trend-vX.md`，明确范围和禁止事项。
3. **TDD RED**：先写失败测试并确认失败原因符合预期。
4. **GREEN**：实现最小代码让目标测试通过。
5. **Docs**：更新 Skill、reference workflow、plan。
6. **Verify**：运行目标测试、全量测试、语法检查、`git diff --check`。
7. **Real Data Check**：使用真实 Binance 免费公开数据验证；输出 UTC / 北京时间（UTC+8）、`mode=paper`、errors_count。
8. **Independent Review**：用独立 agent 审核 diff、测试、paper-only 安全、密钥安全。
9. **Commit + Push**：审核 PASS 后提交并 push。
10. **Next Step Sync**：最终回复中说明下一版本默认方向。

## Version Roadmap

### v0.7 — Paper State Persistence ✅

**Status:** completed in `[verified] feat: add v0.7 paper state persistence`.

**Goal:** 保存连续扫描状态，记录组合分配变化，为 Telegram 简报、复盘和后续 paper position lifecycle 打基础。

**Scope:**
- 新增可配置 paper state 路径，默认使用仓库内受控或明确策略的路径。
- 保存每次扫描的核心快照：
  - UTC / 北京时间（UTC+8）时间戳；
  - intervals；
  - top trends；
  - portfolio allocation；
  - skipped details；
  - errors_count。
- 计算本次与上次的变化：
  - 新增 allocation；
  - 移除 allocation；
  - risk units 增减；
  - ranking 变化；
  - action 或 bucket 变化。
- 输出 `scan.state_change` 或同等结构。

**Guardrails:**
- 只保存 paper 状态，不做真实下单。
- 不保存 API key、secret、环境变量值。
- 状态文件路径必须经过策略评审：tracked 示例/测试数据可以入库；真实运行状态若易频繁变化，应放 ignored 路径。

**Acceptance:**
- 有 RED/GREEN 测试覆盖首次运行、连续运行、allocation 增减、状态文件损坏/缺失。
- 真实 Binance 免费数据扫描能生成状态变化摘要。

### v0.8 — Scheduled Scan + Telegram Briefing ✅

**Status:** implemented in current v0.8 change set: compact `--telegram-brief` output, safe wrapper script, scheduled Hermes cron delivery support.

**Goal:** 自动定时运行 paper scan，并把简洁中文结果发送到 Telegram。

**Scope:**
- 基于 cronjob 创建自包含任务。
- 默认周期只允许 >=1h，例如每 1h 或每 4h。
- 简报包括：
  - UTC / 北京时间（UTC+8）；
  - Top trends；
  - allocation；
  - state change；
  - risk notes；
  - errors_count。

**Guardrails:**
- 不启用真实下单。
- cron prompt 必须自包含，不能递归创建 cron。
- 若无变化，可选择静默或发送精简 heartbeat，需先明确策略。

**Acceptance:**
- 可手动 run cron job 验证输出。
- Telegram 简报不泄露密钥，不包含过长 JSON。

### v0.9 — Historical Backtest Framework

**Goal:** 用历史数据评估策略是否接近 CAGR 30% / 追求 CAGR 100%。

**Scope:**
- 使用免费历史 K-line 数据，周期 >=1h。
- 回测 EMA50/EMA200、ATR trailing、rank_score、多周期一致性、portfolio cap、分批收割。
- 输出指标：
  - CAGR；
  - max drawdown；
  - Calmar；
  - Sharpe；
  - win rate；
  - average holding time；
  - turnover；
  - per-symbol contribution。

**Guardrails:**
- 不使用短周期。
- 不用收费 API。
- 不把回测好结果误报为实盘收益。

**Acceptance:**
- 有小型 fixture 测试。
- 至少能跑一组真实历史数据样本并输出指标。

### v1.0 — Strategy Refinement from Evidence

**Goal:** 只基于 paper/backtest 证据调整策略，不凭感觉改参数。

**Candidate Work:**
- 优化 higher-timeframe agreement scoring。
- 增加 premium index Kline 等免费 public factor。
- 调整 funding / open interest / long-short / taker flow 权重。
- 改进趋势中持续持有逻辑，减少过早离场。
- 增强分批收割规则。

**Guardrails:**
- 每个策略调整必须有前后指标对比。
- 不因短期样本过拟合而提升默认风险。

### v1.1 — Paper Trading Lifecycle

**Goal:** 从“单次 scanner”升级为完整 paper 持仓生命周期。

**Scope:**
- paper position state；
- entry / add / reduce / exit intent；
- trailing stop 更新；
- take-profit tranche 执行记录；
- 持仓变化归因。

**Guardrails:**
- 仍然不真实下单。
- 所有 order intent 必须标记 `paper`。

### v2.0 — Binance Testnet Execution Skill

**Goal:** 只有长期 paper 验证后，单独设计 Binance testnet execution Skill。

**Prerequisites:**
- v0.9 回测指标可接受。
- v1.1 paper lifecycle 稳定运行。
- 有 kill switch、最大仓位、最大日亏损、异常处理。
- 独立 Skill，不能把 signed execution 混入当前 paper scanner。

**Guardrails:**
- testnet-first。
- live execution 需要另行明确授权。
- 不允许默认实盘。

## Default Next Step

当前默认下一步：**v0.9 Historical Backtest Framework**。

除非用户明确改变优先级，否则后续继续按本文件顺序推进：v0.9 → v1.0 → v1.1 → v2.0。

## Stop Conditions

遇到以下情况必须停止并汇报：

- 需要使用 `<1h` 周期；
- 需要收费 API；
- 需要真实下单或 signed live execution；
- 需要读取或展示 API secret；
- 测试失败且无法修复；
- Binance API / 网络不可用导致真实数据验证无法完成；
- 独立 agent 审核 FAIL 且暂未修复。
