# Binance USDS-M Futures Trend v1.3 Plan — Runtime Data Recorder

Created: UTC 2026-06-15 15:44:10 / 北京时间（UTC+8）2026-06-15 23:44:10

## Goal

把每次 paper 运行的关键输入、信号、风险、生命周期、执行意图和结果写入结构化 runtime evidence，为后续策略进化提供可复盘数据。

## Architecture

v1.3 不改变现有 scanner/backtest/brief 的行为，只在 scan/lifecycle 路径旁路增加 `RuntimeRecorder`。Runtime 数据默认写入 ignored 本地路径，格式使用 JSONL append-only，paper/testnet/live 未来共享 schema 并用 `environment` 隔离。

## Scope

- 新增 runtime data schema builder：`build_runtime_record(scan, environment, strategy_version, config_version, run_id)`。
- 新增 append-only recorder：`append_runtime_record(path, record)`。
- CLI 新增：
  - `--runtime-record-file PATH`；
  - `--runtime-environment paper`（当前只允许 paper）；
  - `--strategy-version TEXT`；
  - `--config-version TEXT`；
  - `--no-save-runtime-record`。
- scan 输出新增 `runtime_record` 摘要和 `runtime_record_change` / `runtime_record_saved` 状态。
- `.gitignore` 增加 runtime JSONL 路径，避免提交真实运行记录。

## Non-Goals

- 不接 testnet/live。
- 不下真实订单。
- 不实现策略自动进化。
- 不把 Telegram brief 作为证据源。
- 不保存 API key、secret、signed payload、真实账户敏感信息。

## Runtime Record Minimum Fields

- `schema_version`；
- `environment`；
- `run_id`；
- `strategy_version`；
- `config_version`；
- `generated_at_utc`；
- `generated_at_beijing`；
- `symbol_universe`；
- `intervals`；
- `market_inputs`：symbol、intervals、context period、freshness markers；
- `signals`：action、rank_score、confidence_score、factor_flags、trend refs；
- `risk`：portfolio allocation、skips、caps；
- `portfolio_state`：paper lifecycle snapshot if available；
- `execution_events`：current paper intents only, `real_orders_submitted=false`；
- `outcomes`：errors_count、open/closed positions、runtime summary。

## TDD Tasks

### Task 1 — Runtime record builder

**Test:** add `test_build_runtime_record_contains_evolution_fields` to `tests/test_binance_usds_futures_trend.py`.

Expected RED: importing/calling `build_runtime_record` fails.

Expected GREEN:

```bash
python3 -m unittest tests.test_binance_usds_futures_trend.BinanceUsdsFuturesTrendTests.test_build_runtime_record_contains_evolution_fields -v
```

Assertions:
- `environment == "paper"`；
- UTC and 北京时间（UTC+8） timestamps exist；
- `signals`, `risk`, `portfolio_state`, `execution_events`, `outcomes` exist；
- `execution_events.real_orders_submitted is False`。

### Task 2 — Append-only JSONL recorder

**Test:** add `test_append_runtime_record_writes_jsonl_append_only`.

Expected RED: `append_runtime_record` missing.

Expected GREEN: temp JSONL file has two lines after two writes; both lines parse as JSON dicts.

### Task 3 — CLI runtime recording

**Test:** add `test_cli_scan_can_write_runtime_record_file` using synthetic fixture / temp path.

Expected GREEN:
- CLI scan with `--runtime-record-file tmp.jsonl --no-save-state --no-save-lifecycle` writes exactly one JSONL record；
- record contains `environment=paper`；
- short interval still rejected。

### Task 4 — Git ignore runtime datasets

Modify `.gitignore`:

```gitignore
# Runtime evidence datasets (local/ignored by default).
/runtime/
/runtime_data/
/state/*.jsonl
```

### Task 5 — Docs

Update:
- `plans/binance-usds-futures-roadmap.md` status for v1.3；
- `skills/crypto-trading/binance-usds-futures-trend/SKILL.md` commands and verification if CLI args changed；
- reference note if behavior differs from this plan。

## Verification

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py
git diff --check
```

Real free-data smoke test:

```bash
scripts/binance_usds_futures_trend.py   --symbols BTCUSDT,ETHUSDT,SOLUSDT   --intervals 1h,4h,1d   --limit 240   --context-limit 30   --top 3   --portfolio-risk-budget 3   --max-symbol-risk 1   --state-file state/binance-usds-futures-trend-paper-state.json   --lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json   --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl   --no-save-state   --no-save-lifecycle   --no-save-runtime-record
```

Note: command above intentionally avoids writing runtime data; final write verification should use a temp path.

## Acceptance

- Existing CLI behavior remains backward compatible.
- Runtime record schema contains enough data for strategy-evolution comparison.
- Runtime records are local/ignored by default.
- All timestamps label UTC or 北京时间（UTC+8）。
- Tests pass and independent agent review passes before push。
