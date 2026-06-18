# Session v1.49 — 当前交易流程独立审计汇总

审计整合时间：

- UTC：2026-06-18 05:47:39 UTC
- 北京时间（UTC+8）：2026-06-18 13:47:39 UTC+8

范围：`/root/.hermes/profiles/crypto-trade-hermes`

本文件整合 3 个独立只读 agent 的审计汇报：

1. 运行证据审计：cron outputs、runtime JSONL、order journal、daily analyzer output。
2. 代码/架构审计：CLI、core loop、risk/execution/broker、hourly scripts、tests。
3. 定时任务/运营流程一致性审计：live cron、template、plan/reference/Skill 描述、prompt/CLI/engine 边界。

审计约束：所有独立 agent 均只读执行；未触发 `cronjob(action="run")`；未运行 signed testnet cycle；未下单、撤单或恢复任务；未修改文件。

## 总体结论

当前交易流程应判定为：**WARN / 局部 FAIL**。

更精确地说：

- **dry-run hourly evidence collection 当前正常：PASS**
  - `testnet-dry-run-hourly` 正在按小时运行。
  - `no_agent=true`，script-owned，wrapper 固定 `--dry-run`。
  - 最近成功输出显示 `signed_count=0`、`attempted_real_order_count=0`、`real_submitted_count=0`。
  - runtime evidence 持续写入 canonical testnet 文件。

- **signed testnet execution/protection 健康度：FAIL / degraded**
  - signed hourly job 当前暂停。
  - 最后一轮 signed evidence 显示存在非零仓位但保护状态不完整：`unprotected_symbols` 包含 `BTCUSDT`、`ETHUSDT`。
  - order journal 中存在多个 stop-loss `submitted_unknown`，与 protection degraded 互相印证。
  - 当前 dry-run job 跳过 signed preflight/postflight，不能证明现有 testnet 仓位和 open algo protection 实际健康。

- **架构/代码总体接近设计目标：PASS with WARN**
  - public data、`>=1h`、shared paper/testnet core loop、testnet broker 隔离、delta-only reconciliation、open algo TP/SL protection、runtime evidence、UTC/北京时间输出、脱敏等关键能力大体存在并有测试覆盖。
  - 但 live adapter 尚未实现；paper scanner 形态仍较突出；hourly Python harness 默认 signed，与“dry-run default / signed 需显式 gate”的目标存在语义偏差，虽然当前 dry-run wrapper 覆盖了该风险。

- **运营流程边界总体符合 split runner/analyzer 设计：PASS with WARN**
  - 小时 runner 是 `no_agent=true` script-owned。
  - daily analyzer 是 agent-mode read-only。
  - prompt prose、fixed CLI、engine logic 的边界在 Skill/References 中已有明确描述。
  - 但 live `cron/jobs.json` 与 tracked `cron/jobs.template.json` 不一致：当前运行的 `testnet-dry-run-hourly` 未进入 template。

## 关键判定

### 1. 是否偏离目标

目标包括：

- Binance USDS-M futures；
- 不使用收费 API；
- interval `>=1h`；
- paper/testnet/live 共享交易引擎，差异仅 broker adapter/env config；
- 小时 testnet hot path 为 deterministic `no_agent=true` script-owned；
- dry-run evidence job 不得 signed submit；
- signed testnet 需显式授权；
- runtime/order evidence 必须记录且 testnet 隔离；
- 策略目标为 CAGR 30%，追求 100%；偏好沿主趋势持续参与/持有/分批收割，避免过早离场；
- short 可作为主趋势方向，但 signed short 需显式授权。

审计结论：

- **未偏离基础数据和周期约束**：未见收费 API，runtime intervals 为 `1h`。
- **未偏离 dry-run evidence 任务边界**：当前启用 job 是 dry-run-only，没有 signed submit。
- **部分偏离“安全持续参与”的执行目标**：最后 signed 证据显示保护单确认失败与未保护仓位，当前 dry-run 又无法确认/修复 signed testnet protection。
- **部分偏离完整 shared engine 目标**：paper/testnet 已共享 core loop，但 live adapter 尚未实现；paper scanner 入口仍突出。
- **部分偏离运营模板一致性目标**：live cron 有 `testnet-dry-run-hourly`，tracked template 尚未包含。

因此：当前流程没有偏离“先 dry-run 收证据”的保守阶段目标；但若以“signed testnet hot path 正常维护仓位和保护单”为目标，则当前已偏离。

### 2. 是否满足设计要求

总体：**部分满足**。

满足的部分：

- script-owned dry-run hourly runner；
- read-only daily analyzer；
- >=1h；
- testnet evidence 隔离；
- signed short 未启用；
- 当前 dry-run 无 signed submit；
- 代码层多数核心交易引擎要求已实现并通过测试。

不满足/存在风险的部分：

- signed testnet 最近健康证据失败：`submitted_unknown` stop-loss、`unprotected_symbols`；
- dry-run job 不做 signed preflight/postflight，不能覆盖真实 testnet protection 状态；
- hourly harness 默认 signed，与“dry-run default”设计表述冲突；
- live adapter 未实现；
- `cron/jobs.template.json` 未同步当前 live dry-run job；
- 部分代码文档/docstring 仍停留在旧 agent cron 语义。

## 独立审计 1：运行证据

审计时间：

- UTC：2026-06-18 05:41:29 UTC
- 北京时间（UTC+8）：2026-06-18 13:41:29 UTC+8

### PASS：dry-run hourly 正常运行

文件：`cron/jobs.json`

- job：`testnet-dry-run-hourly`
- id：`172f71e2558b`
- `no_agent=true`
- script：`binance_usds_futures_testnet_hourly_dry_run.sh`
- schedule：`25 * * * *`
- `enabled=true`
- `state=scheduled`
- `last_status=ok`
- `last_run_at`：
  - UTC：2026-06-18 05:25:24 UTC
  - 北京时间（UTC+8）：2026-06-18 13:25:24 UTC+8

最新 dry-run output：`cron/output/172f71e2558b/2026-06-18_13-25-23.md`

- mode：`no_agent (script)`
- `dry_run=true`
- `ok=true`
- `preflight.reason=dry_run_skips_signed_preflight`
- `postflight.reason=dry_run_skips_signed_postflight`
- BTC 组：`signed_count=0`、`attempted_real_order_count=0`、`real_submitted_count=0`
- Alt 组：`signed_count=0`、`attempted_real_order_count=0`、`real_submitted_count=0`
- runtime file：`state/binance-usds-futures-trend-testnet-runtime.jsonl`
- order journal：`state/binance-usds-futures-trend-testnet-orders.jsonl`

runtime 文件：`state/binance-usds-futures-trend-testnet-runtime.jsonl`

- 28 条记录；JSON 解析错误 0。
- `environment` 全部为 `testnet`。
- `intervals` 全部为 `1h`。
- 最近记录：
  - UTC：2026-06-18 05:25:23 UTC
  - 北京时间（UTC+8）：2026-06-18 13:25:23 UTC+8
- 最近 dry-run 记录：
  - `portfolio_state.dry_run=true`
  - `execution_events.real_orders_submitted=false`
  - `outcomes.errors_count=0`

### WARN：当前只剩 dry-run，无法确认 signed protection

文件：`cron/jobs.json`

- job：`testnet-agent-hourly`
- id：`f7201d6c1c57`
- script：`binance_usds_futures_testnet_hourly.sh`
- schedule：`1 * * * *`
- `enabled=false`
- `state=paused`
- `last_run_at`：
  - UTC：2026-06-17 14:05:35 UTC
  - 北京时间（UTC+8）：2026-06-17 22:05:35 UTC+8

解释：signed hot path 当前暂停；当前启用的 dry-run hourly 只采集 dry-run evidence，不维护真实 testnet 仓位/保护单。

最新 dry-run output 中：

- `preflight.skipped=true`
- `postflight.skipped=true`
- `protection.all_positions_protected=null`

解释：这符合 dry-run 不访问 signed path 的安全要求，但不能证明真实 testnet 仓位仍受保护。

### FAIL：最后 signed evidence 显示保护状态失败

最后一轮 signed hourly output：`cron/output/f7201d6c1c57/2026-06-17_22-05-33.md`

时间：

- UTC：2026-06-17 14:05:18 UTC
- 北京时间（UTC+8）：2026-06-17 22:05:18 UTC+8

关键字段：

- `dry_run=false`
- BTC 组：
  - `fill_status_counts.submitted_unknown=1`
  - `protection.all_positions_protected=false`
  - `protection.unprotected_symbols=["BTCUSDT"]`
  - `nonzero_positions_after` 含 BTCUSDT `positionAmt=0.0153`
- Alt 组：
  - `fill_status_counts.rejected=1`
  - `fill_status_counts.skipped=6`
  - `protection.all_positions_protected=false`
  - `protection.unprotected_symbols=["ETHUSDT"]`
  - `nonzero_positions_after` 含 ETHUSDT `positionAmt=0.315`、BNBUSDT `positionAmt=1.28`

order journal：`state/binance-usds-futures-trend-testnet-orders.jsonl`

- 104 条记录；JSON 解析错误 0。
- 最近记录：
  - UTC：2026-06-17 14:05:22 UTC
  - 北京时间（UTC+8）：2026-06-17 22:05:22 UTC+8
- status 统计：
  - `submitted=89`
  - `FILLED=10`
  - `submitted_unknown=5`
- errors：5 条 `signed_testnet_submission_failed_sanitized` / `HTTPError` / `confirm_status=failed`。

`submitted_unknown` 明细均为 stop-loss 相关：

- SOLUSDT SELL STOP_MARKET stop_loss：2026-06-17 05:16:17 UTC / 2026-06-17 13:16:17 UTC+8
- SOLUSDT SELL STOP_MARKET stop_loss：2026-06-17 06:05:18 UTC / 2026-06-17 14:05:18 UTC+8
- ETHUSDT SELL STOP_MARKET stop_loss：2026-06-17 12:05:20 UTC / 2026-06-17 20:05:20 UTC+8
- BTCUSDT SELL STOP_MARKET stop_loss：2026-06-17 13:05:19 UTC / 2026-06-17 21:05:19 UTC+8
- BTCUSDT SELL STOP_MARKET stop_loss：2026-06-17 14:05:19 UTC / 2026-06-17 22:05:19 UTC+8

runtime signed 记录：`state/binance-usds-futures-trend-testnet-runtime.jsonl`

- line 21：BTCUSDT `STOP_MARKET` status `submitted_unknown`；`portfolio_state.positions.BTCUSDT.size=0.0153`。
- line 22：ETHUSDT reduction `MARKET` rejected，`reason=exchange_min_notional_not_met`；SOLUSDT entry/protection group skipped，`reason=insufficient_order_budget_for_atomic_entry_protection_group`。

### WARN：daily analyzer 不覆盖最新 signed 风险

文件：`cron/output/4666a4cbbdf8/2026-06-17_18-40-31.md`

报告时间范围：

- UTC：2026-06-17 10:37:33–10:39:51 UTC
- 北京时间（UTC+8）：2026-06-17 18:37:33–18:39:51 UTC+8

字段：

- `system_health.status=degraded`
- issues 包含 `submitted_unknown_orders`
- `submitted_unknown_count=2`
- `unprotected_symbols=[]`

解释：daily analyzer 存在且只读，但早于后续 2026-06-17 21:05/22:05 北京时间 signed evidence；不能覆盖最新风险状态。

## 独立审计 2：代码/架构

审计时间：

- UTC：2026-06-18 05:41:29 UTC
- 北京时间（UTC+8）：2026-06-18 13:41:29 UTC+8

### 验证命令

独立 agent 安全运行了：

```bash
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py scripts/binance_usds_futures_testnet_hourly.py
python3 -m pytest -q tests/test_binance_usds_futures_trend.py tests/test_binance_usds_futures_testnet_hourly.py tests/test_cron_trading_config.py
```

结果：

```text
153 passed, 29 subtests passed in 10.75s
```

`git status --short` 当时为空。

### PASS：核心实现满足多数架构要求

CLI / `scripts/binance_usds_futures_trend.py`：

- 使用 Binance USDS-M public base：`https://fapi.binance.com`。
- `validate_interval()` 拒绝 `1m/3m/5m/10m/15m/30m`，允许 `1h+`。
- CLI 包含 scan、backtest、compare refinements、`--run-paper-cycle`、`--run-testnet-cycle`、runtime replay/order analysis。
- `--run-testnet-cycle` 默认 dry-run：`dry_run=not args.testnet_submit_signed`。
- `--testnet-dry-run` 与 `--testnet-submit-signed` 互斥。
- `--allow-testnet-signed-short` 是 signed short 显式 gate。
- 顶层异常通过 `sanitize_error_message()` 输出，避免 signature/key/secret 泄露。
- 输出结构包含 UTC 和 Beijing timestamp。

Core loop / `scripts/binance_trend_core/loop.py`：

- 统一 `run_trading_cycle()`，broker adapter 决定 paper/testnet 行为。
- `validate_cycle_interval()` 强制 `>=1h`。
- runtime record 包含 `generated_at_utc`、`generated_at_beijing`、`market_inputs`、`signals`、`risk`、`portfolio_state`、`execution_events`、`outcomes`。
- 真实下单状态由 broker fill 的 `real_order_submitted` 汇总。
- 下单优先级：先减仓/平仓，再修复已有仓位保护，再新增/加仓。
- 对 atomic entry + protection group 做预算检查和 stale recheck，降低重复 full target 下单风险。

Execution / `scripts/binance_trend_core/execution.py`：

- `PositionReconciliationExecutionEngine` 使用 desired-current delta。
- `add_allowed=false` 会阻止新增/加仓，但允许持有、减仓和保护修复。
- cross-direction 时只回到 flat，不穿越开反向新仓。
- TP/SL protection 同时处理 long/short。
- open algo orders 被纳入 `_protection_rows()`。
- stale take-profit 会生成 `CANCEL_ALGO_ORDER` 后替换。
- short protection side 正确：short stop/TP 使用 BUY reduce/close。

Risk/Broker/Runtime：

- risk sizing 使用账户 equity、available balance、ATR/stop distance、notional caps、symbol exposure fraction。
- broker 使用 exchange rules 进行数量、价格、最小名义金额适配。
- runtime recorder 追加 evidence，支持后续 replay/evolution。
- signed path 具备 testnet endpoint gate 与 redaction。

### WARN：代码/架构偏差

1. **live adapter 尚未实现**

当前满足 paper/testnet 共享 core loop，但不满足 paper/testnet/live 完整共享 trading engine 的最终目标。

2. **hourly Python harness 默认 signed**

`binance_usds_futures_testnet_hourly.py` 中 `--dry-run` 是可选项；默认路径会在子命令加入 `--testnet-submit-signed`。核心 CLI 的 `--run-testnet-cycle` 是 dry-run default，但 hourly harness 把默认语义反转为 signed。

当前 cron 因使用 `binance_usds_futures_testnet_hourly_dry_run.sh` 并固定 `--dry-run`，所以运行上仍安全；但源码默认语义与“testnet dry-run default，signed submit 必须显式 gate”的设计要求不一致。

3. **paper scanner 产品形态仍较突出**

主脚本默认 scan 路径、`--symbols/--all-symbols`、paper state/lifecycle、Telegram brief 均仍以 “Paper Scan” 为中心。虽然已有 `--run-paper-cycle` 共享交易循环，但 paper 仍保留并突出 scanner 产品形态。

4. **RiskManager 仍较薄**

`apply_account_risk_sizing_to_signal()` 已较接近账户风险 sizing；broker 也有 exchange/risk limits；execution 做 delta-only reconciliation。但 `FunctionRiskManager` 仍基本是 approve pass-through，组合级 portfolio exposure 约束还不是独立一等风险引擎。

5. **文档/docstring 过时**

主脚本 docstring 仍偏 “paper decision helper / does not place orders”，但现在同文件已经包含 signed testnet cycle。hourly harness docstring 仍带旧 agent cron 语义。

6. **loop 层异常脱敏可进一步强化**

多数 signed HTTP 异常在 broker 内已脱敏，但 loop 捕获异常时仍可能 `str(exc)` 放入 `errors`。建议 loop 层也统一 sanitizer，避免未来底层异常含 signed query/header。

## 独立审计 3：定时任务/运营流程一致性

审计时间：

- UTC：2026-06-18 05:43:19 UTC
- 北京时间（UTC+8）：2026-06-18 13:43:19 UTC+8

### PASS：runner/analyzer 分离基本满足

`testnet-agent-hourly`：

- `no_agent=true`
- `skills=[]`
- script：`binance_usds_futures_testnet_hourly.sh`
- prompt/skill 不参与执行，符合 script-owned runner 语义。
- 当前 `paused`，不会自动下单。
- 脚本固定 CLI 参数清楚：testnet base URL、`1h`、BTC/Alt 分组、runtime/order journal 文件、risk limits、signed/dry-run gate。

`testnet-dry-run-hourly`：

- `no_agent=true`
- script：`binance_usds_futures_testnet_hourly_dry_run.sh`
- 当前启用，schedule：`25 * * * *`
- wrapper 强制 `--dry-run`。
- 最近输出：
  - `dry_run=true`
  - `signed_count=0`
  - `attempted_real_order_count=0`
  - `real_submitted_count=0`
- 符合 v1.48 “short path / bidirectional path 先用独立 dry-run evidence cron 收集证据，不恢复 signed job”的设计。

`replay-diagnostics-daily`：

- `no_agent=false`
- `script=null`
- `skills=["binance-usds-futures-trend"]`
- `enabled_toolsets=["terminal","file","skills"]`
- prompt 明确只读：
  - 不创建/修改/暂停/删除 cron；
  - 不触发立即运行；
  - 不下单、不撤单、不运行 signed testnet cycle；
  - 同时标注 UTC 和 北京时间（UTC+8）；
  - 优先 `--daily-analyze-runtime`；
  - replay 只作为候选策略对照。

Skill/References/Plans：

- `SKILL.md` 已明确：
  - 小时 runner 为 script-owned `no_agent=true`；
  - daily analyzer 为 agent-mode read-only；
  - prompt prose 不能替代 CLI/代码逻辑；
  - cron 时间异常诊断默认只读；
  - 禁止 `cronjob(action="run")`，除非用户明确要求立即运行；
  - commit/push 前需 `git status` 与 independent review。
- `plans/trading-chain-cagr-optimization.md` 与 references v1.32/v1.35/v1.37/v1.44/v1.48 基本一致。

### WARN：运营一致性偏差

1. **live cron 与 template 不一致**

live `cron/jobs.json` 有 3 个 job：

- `testnet-agent-hourly`
- `replay-diagnostics-daily`
- `testnet-dry-run-hourly`

tracked `cron/jobs.template.json` 只有 2 个 job：

- `testnet-agent-hourly`
- `replay-diagnostics-daily`

当前正在运行的 `testnet-dry-run-hourly` 未进入 template，与 v1.44/v1.48 的 sanitized template 同步要求不完全一致。

2. **hourly harness docstring 过时**

`scripts/binance_usds_futures_testnet_hourly.py` 顶部 docstring 仍写：

- “agent cron”
- “cron job stays agent-type (no_agent=false)”

这与当前 `no_agent=true script-owned` 设计冲突，可能误导后续维护者。

3. **当前 signed hot path 暂停**

如果当前阶段目标是“signed testnet hot path 正常运行”，则 `testnet-agent-hourly` paused 是偏离；如果当前阶段目标是 “signed 暂停、dry-run 先收证据”，则符合。

4. **Skill 顶部时间约束措辞略弱**

`SKILL.md` 用户约束处写的是 “all time-related output must label UTC or 北京时间（UTC+8）”，而用户偏好是同时标注 UTC 和 北京时间（UTC+8）。实际 job prompt/output 多数已同时标注，但 Skill 顶层可被理解为二选一。

## Prompt / CLI / Engine 边界

审计明确区分三层：

1. **Prompt 文字约束**
   - 对 `no_agent=true` runner 不参与执行。
   - 只作为配置说明或未来 agent-mode 任务约束。
   - 不应把 prompt 中的“只读/不下单/风险限制”等文字当作脚本真实行为。

2. **固定 CLI 参数**
   - 小时 hot path 的真实边界来自 wrapper 和 Python harness 拼出的 CLI。
   - 当前 dry-run runner 的真实安全边界是：`binance_usds_futures_testnet_hourly_dry_run.sh` 固定传入 `--dry-run`。
   - testnet endpoint、interval、symbols、runtime/order journal 文件也由脚本固定 CLI 决定。

3. **脚本/交易引擎逻辑**
   - `run_trading_cycle()`、execution engine、broker adapter、risk sizing、runtime recorder 才是真正执行逻辑。
   - 当前核心 CLI 的 `--run-testnet-cycle` 默认 dry-run，但 hourly Python harness 默认 signed，因此必须靠 dry-run wrapper 或显式参数避免误入 signed。

## 当前风险清单

按优先级：

1. **FAIL：最后 signed evidence 仍显示未保护仓位**
   - `BTCUSDT`、`ETHUSDT` 保护状态失败。
   - 多个 stop-loss `submitted_unknown`。
   - 当前 dry-run 不能确认现状是否已被交易所后续状态修复。

2. **WARN：signed hot path 暂停，当前只收 dry-run evidence**
   - 安全上保守；但无法继续验证 signed execution/protection lifecycle。

3. **WARN：dry-run evidence 正常但不能代替 signed account/open order/open algo snapshot**
   - `preflight/postflight skipped` 是安全行为，但意味着无法证明真实仓位状态。

4. **WARN：hourly harness 默认 signed**
   - 当前 wrapper 安全，但默认语义不符合 dry-run default 设计。

5. **WARN：template 未同步 live dry-run job**
   - 运维可复现性与 repo 记录不一致。

6. **WARN：daily analyzer 滞后于最新 signed failure**
   - 最新 daily analyzer 没有覆盖 2026-06-17 21:05/22:05 北京时间的风险事件。

7. **WARN：live adapter 未实现，paper scanner 形态仍突出**
   - 架构目标未完全完成。

## 建议后续动作

只读/文档类：

1. 更新 `cron/jobs.template.json`，加入 sanitized `testnet-dry-run-hourly` template。
2. 更新 `scripts/binance_usds_futures_testnet_hourly.py` docstring，删除旧 agent cron / no_agent=false 描述。
3. 修正 `SKILL.md` 顶层时间约束为“同时标注 UTC 和 北京时间（UTC+8）”。
4. 在 Skill/Reference 中明确当前状态：dry-run evidence 正常，但 signed protection evidence degraded，不能称整体交易流程完全正常。

代码安全类：

5. 将 hourly Python harness 默认改为 dry-run，signed 需显式参数/环境 gate，而不是依赖 wrapper 传 `--dry-run`。
6. loop 层异常统一 sanitizer。
7. 强化 portfolio-level risk manager，把组合级 exposure/daily loss/current exposure 作为一等约束。

运营/交易类，需要用户显式授权后才可做：

8. 对 testnet 当前真实仓位、open orders、open algo orders 做 signed 只读快照，确认 `BTCUSDT` / `ETHUSDT` 是否仍未保护。
9. 处理 5 条 stop-loss `submitted_unknown` 的最终状态归因。
10. 未确认 protection 前，不建议恢复 signed hourly cycle。

## 本次整合文档的状态

本文件只整合独立 agent 审计汇报。除写入本文件外，不包含代码修复、cron 修改、signed 运行、下单或撤单。
