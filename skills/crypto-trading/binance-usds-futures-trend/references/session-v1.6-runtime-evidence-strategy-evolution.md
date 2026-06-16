# v1.6 Runtime Evidence Strategy Evolution Workflow

Created: UTC 2026-06-16 00:34:02 / 北京时间（UTC+8）2026-06-16 08:34:02

## Goal

基于已经记录的 runtime evidence JSONL 回放候选策略，避免用漂移行情样本或主观判断调参。

## Implemented Scope

- 新增 `scripts/binance_trend_core/evolution.py`。
- 新增 runtime JSONL loader：
  - `load_runtime_records(path)`；
  - 校验 `schema_version`、`environment`、`generated_at_utc`、`generated_at_beijing`；
  - 拒绝 runtime evidence 中任意 interval 字段里的 `<1h` 短周期；
  - 空文件、非 JSONL、非 object、缺字段会失败。
- 新增 replay dataset builder：
  - `build_runtime_replay_dataset(records)`；
  - 对 captured runtime inputs 生成 deterministic SHA256 fingerprint；
  - baseline/candidate variants 都必须使用同一个 `captured_input_fingerprint`。
- 新增 runtime strategy comparison：
  - `compare_runtime_strategy_variants(records)`；
  - variants: `baseline`、`trend_hold_bias`、`risk_capped`；
  - 输出 return proxy、max drawdown、turnover、holding periods、missed-trend、premature-exit diagnostics、evidence score；
  - drawdown guardrail 可阻止高收益但更高回撤的 candidate。
- 新增 CLI：
  - `--replay-runtime-evidence --runtime-record-file PATH`。
- 明确不自动推广默认参数：
  - `selection_policy.auto_promote_defaults=false`；
  - `defaults_changed=false`。

## Command

```bash
scripts/binance_usds_futures_trend.py --replay-runtime-evidence --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl
```

## Safety / Guardrails

- 不抓取新的 Binance 样本；只读取已经记录的 JSONL runtime evidence。
- 不使用收费 API。
- 不真实下单。
- 不读取或输出 secret。
- 输出必须包含 UTC 与 北京时间（UTC+8）。
- runtime evidence 文件仍应位于 ignored `state/*.jsonl` / `runtime*` 路径。

## Verification

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
git diff --check
```

For a real free-data smoke path, first produce a no-network-replay runtime record using the existing free Binance paper cycle, then replay that captured evidence:

```bash
scripts/binance_usds_futures_trend.py --run-paper-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file /tmp/binance-v16-runtime.jsonl
scripts/binance_usds_futures_trend.py --replay-runtime-evidence --runtime-record-file /tmp/binance-v16-runtime.jsonl
```
