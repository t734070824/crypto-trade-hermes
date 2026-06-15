# v0.8 Scheduled Scan + Telegram Briefing Workflow

Created: UTC 2026-06-15 12:55:03 / 北京时间(UTC+8) 2026-06-15 20:55:03

## Purpose

记录 v0.8 如何在 v0.7 paper state persistence 之上生成 Telegram 友好的中文简报，并通过 Hermes cron 定时投递。

## Implementation Summary

- 新增 `build_telegram_briefing_zh(scan)`：将完整 scan JSON 压缩为 Telegram 文本。
- 新增 CLI 参数 `--telegram-brief`：扫描模式下输出纯文本简报，不输出完整 JSON。
- 保留 v0.7 `--state-file` / `--no-save-state`：简报可以展示连续扫描的新增、移除、risk unit 变化、rank/action/bucket 变化。
- 默认 no-change 策略为精简 heartbeat：即使没有新增/移除/变化，也发送一条 compact briefing，便于确认任务仍在运行。

## Canonical Command

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
  --lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json \
  --telegram-brief
```

## Expected Brief Fields

- `Binance USDS-M Paper Scan（paper only）`
- UTC timestamp。
- 北京时间（UTC+8）timestamp。
- intervals / universe count。
- Top trends。
- Portfolio allocation。
- State change:
  - added allocations；
  - removed allocations；
  - changed allocations；
  - rank/action/bucket change counts。
- Risk notes:
  - risk_high symbols；
  - conflicting symbols；
  - errors_count。
- Safety line: paper only、未下真实订单、未使用收费 API。

## Hermes Cron Prompt Pattern

Use Hermes cron with a self-contained prompt. Do **not** recursively create cron jobs inside the prompt.

```text
Run the Binance USDS-M futures paper scanner briefing from /root/.hermes/profiles/crypto-trade-hermes.
Execute:
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json --lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json --telegram-brief
Deliver the script stdout as the Telegram briefing.
If the command fails, report the failure concisely with UTC and Beijing time (UTC+8).
Never place live orders, never use paid APIs, never print secrets, and do not create/update/remove cron jobs from inside this run.
```

## Guardrails

- Schedule must be >=1h cadence; default is every 4h.
- Use only free Binance public endpoints.
- Runtime state stays under ignored `state/*.json`.
- For long-running paper scans, pair `--state-file` with `--lifecycle-file` so both scan state and per-symbol lifecycle persist across runs.
- Do not expose `.env` values, API keys, or secrets.
- Briefing should be compact; avoid raw full JSON in Telegram.
- `--telegram-brief` is scan-mode only (`--all-symbols` or `--symbols`).

## Cron Config Hygiene

When a Hermes cron job is created and manually run, `cron/jobs.json` can contain runtime metadata and delivery internals. Before staging/pushing scheduled trading changes:

- Use `deliver: "telegram"` for the home Telegram target when possible; avoid committing origin-specific `chat_id`, chat name, or thread metadata.
- If Hermes persists an `origin` block after a manual run, remove that block from the tracked JSON only after confirming `deliver` is still set and `cronjob list` can still load the job.
- Ignore runtime artifacts such as `cron/output/` and editor swap files (`cron/*.swp`); do not commit manual-run output transcripts.
- Keep the cron script path relative to the profile script directory for Hermes no-agent jobs, e.g. `script: "binance_usds_futures_trend_brief.sh"`.
- Record `last_status=ok` / next-run timestamps in the final user report, but do not rely on runtime status fields as source code semantics.

## Review and Push Gate

For this repository, push only after an independent agent reviews the staged diff. A useful fail-closed reviewer prompt should require JSON with `passed`, `security_concerns`, `logic_errors`, and `suggestions`, and should force `passed=false` when security or logic lists are non-empty. Include scanner-specific blockers: secrets/chat IDs, live/signed trading, paid API use, `<1h` defaults, recursive cron scheduling, raw JSON spam, and committed runtime outputs.

## Verification Checklist

1. RED: tests fail before `build_telegram_briefing_zh` and `--telegram-brief` exist.
2. GREEN: target tests pass.
3. Full suite passes:
   ```bash
   python3 -m unittest tests/test_binance_usds_futures_trend.py -v
   ```
4. Syntax check passes:
   ```bash
   python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py
   ```
5. Real free-data command outputs a compact Telegram briefing with UTC / 北京时间（UTC+8）、paper only、errors_count。
6. Hermes cron job can be manually run and delivers the briefing.
