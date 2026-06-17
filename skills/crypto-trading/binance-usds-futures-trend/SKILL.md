---
name: binance-usds-futures-trend
description: Use when developing or operating the crypto-trade-hermes Binance USDS-M futures trend Skill. Current code supports paper diagnostics/shared paper cycles, runtime-evidence replay, and a hardened testnet adapter; future work must preserve shared strategy, state, risk, lifecycle, execution, and evidence paths across paper/testnet/live.
version: 1.10.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [binance, usds-m-futures, crypto-trading, trend-following, realtime-trading, paper-trading]
    related_skills: [test-driven-development]
---

# Binance USDS-M Futures Trend Trading Skill

## Overview

This Skill belongs to the `crypto-trade-hermes` profile and is the project knowledge base for Binance USDⓈ-M futures trend trading.

Current architecture target: **Skill-driven real-time trading**. Paper, testnet, and future live modes should share strategy, state transitions, risk checks, lifecycle management, execution reconciliation, and runtime evidence schema. Divergence belongs only inside broker/fill adapters and environment configuration. Paper mode is a safety/testing adapter, not a report-style scanner product.

Current implementation status: the CLI supports paper diagnostics, shared paper cycles, runtime-evidence replay, and a hardened Binance USDS-M futures **testnet** adapter with dry-run default, explicit signed-testnet gates, exchangeInfo/risk validation, account/order sync, clientOrderId/order journal, lifecycle polling, trade/PnL/slippage accounting, and redaction. Live/mainnet signed execution is not implemented and remains unauthorized.

## User Constraints

Hard constraints for this profile:

- market: Binance USDS-M futures;
- symbols: `BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, LINKUSDT, AVAXUSDT, ADAUSDT, LTCUSDT, TRXUSDT, DOTUSDT, POLUSDT, BCHUSDT, APTUSDT, ARBUSDT, OPUSDT, SUIUSDT, INJUSDT, ATOMUSDT`;
- no paid APIs;
- use free Binance public market data where possible;
- never use intervals below `1h` (`1m`, `3m`, `5m`, `10m`, `15m`, `30m` are invalid);
- all time-related output must label UTC or 北京时间（UTC+8）;
- strategy preference: stay with the main trend, avoid premature exits, and harvest in tranches;
- runtime data must be recorded during operation so future strategy changes can be evaluated against real paper/testnet/live evidence;
- target: seek CAGR 30%, pursue CAGR 100%, but never present paper/backtest output as achieved live returns;
- Binance auth secrets are in the active profile `.env` as `LALA_KEY` and `LALA_SECRET`; never expose values.

## When to Use

Use this Skill when the user asks for:

- Binance USDS-M futures trend strategy work;
- paper/testnet/live architecture decisions for the trading Skill;
- interpreting or improving the current trend signal, allocation, lifecycle, or backtest code;
- scheduled paper diagnostics or Telegram briefs;
- free-data research using >=1h K-lines and free Binance futures context endpoints;
- planning the transition from scanner-style diagnostics to a real-time trading engine.

Do not use this Skill for:

- spot trading;
- paid market-data APIs;
- sub-1h signals;
- unreviewed live trading;
- signed order placement without explicit testnet/live execution adapter, risk gates, kill switches, and user approval.

## Current Architecture Direction

Future work should converge on these components:

1. `MarketData` — fetches and normalizes free Binance public data and, later, account/exchange state for signed environments.
2. `Strategy` — converts market data into desired exposure or intents, using trend-following rules.
3. `SignalEngine` — wraps the current scanner/ranking/multi-timeframe logic as reusable signal generation.
4. `RiskManager` — applies leverage, max exposure, symbol caps, drawdown limits, cooldowns, and kill-switch rules.
5. `PortfolioState` — owns positions, orders, fills, lifecycle, realized/unrealized PnL, timestamps, and environment metadata.
6. `LifecycleManager` — manages entry/add/reduce/hold/exit, trailing stops, and take-profit tranches.
7. `ExecutionEngine` — reconciles desired state with current portfolio state and emits create/cancel/replace order instructions.
8. `BrokerAdapter` — isolates environment-specific execution:
   - `PaperBroker`: simulated fills, fees, slippage, balances;
   - `BinanceTestnetBroker`: signed Binance futures testnet execution;
   - `BinanceLiveBroker`: signed live execution behind stricter gates.
9. `RuntimeRecorder` — records run inputs, signals, decisions, risk checks, orders, fills, state transitions, errors, and performance snapshots for later evaluation.
10. `StrategyEvolution` — compares future strategy variants against recorded runtime evidence before promoting changes.
11. `Observability` — compact Telegram reports and logs around the same trading loop, not a separate decision path.
12. `PostRunSummary` — summarize signed testnet runs from runtime JSONL, order journals, replay JSON, and a fresh signed snapshot when CLI stdout is truncated or too verbose.

Architectural invariant: paper/testnet/live must share strategy, risk, lifecycle, state, execution orchestration, and runtime data schema. Divergence belongs only inside broker adapters and environment config.

## Current Capabilities

Primary script:

```bash
scripts/binance_usds_futures_trend.py
```

Current paper/testnet capabilities:

- lightweight core realtime interface package under `scripts/binance_trend_core/`;
- v1.5 shared paper trading loop via `scripts.binance_trend_core.loop.run_trading_cycle` and `PaperBroker` simulated fills;
- v1.6 runtime evidence replay via `scripts.binance_trend_core.evolution` and CLI `--replay-runtime-evidence`;
- v1.9-hardened Binance futures testnet adapter via `BinanceTestnetBroker` and CLI `--run-testnet-cycle`: dry-run default, explicit signed-testnet flag, exchangeInfo order rules, account/order sync helpers, clientOrderId/order journal, signed order lifecycle polling, trade/PnL/slippage accounting, risk config, and redaction;
- single-symbol trend decision from free K-lines;
- testnet signed account snapshots that reconcile positions, ordinary open orders, and open algo orders used for TP/SL protection;
- full-universe or selected-symbol scan;
- multi-timeframe confirmation, usually `1h,4h,1d`;
- rank scoring and grouping of strong/early/conflicting/watchlist trends;
- optional paper portfolio risk allocation;
- optional persisted scan state and state-change summaries;
- optional paper lifecycle state with entry/add/reduce/hold/exit intent;
- optional append-only runtime evidence records for strategy evolution;
- historical paper backtest metrics;
- evidence-based refinement comparison on identical fetched candle samples;
- compact Telegram diagnostic brief via wrapper script;
- post-run reconstruction from runtime JSONL + order journals + signed snapshots when terminal stdout is too large to trust directly.

Current safety boundary:

- paper scan/backtest/refinement outputs remain `mode=paper`;
- testnet cycle output uses `environment=testnet` and defaults to dry-run (`real_orders_submitted=false`);
- signed testnet submission requires explicit `--testnet-submit-signed` and is restricted to `https://testnet.binancefuture.com`;
- live/mainnet signed execution is not implemented and remains unauthorized.

## Recommended Commands

Run tests after any code or behavior change:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
```

Paper diagnostic scan for the configured universe:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1
```

Paper scan with persisted state, lifecycle diagnostics, and runtime evidence:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json --lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl
```

No-write lifecycle/runtime dry run for selected symbols:

```bash
scripts/binance_usds_futures_trend.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 3 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json --lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl --no-save-state --no-save-lifecycle --no-save-runtime-record
```

Shared paper trading cycle with simulated fills and no runtime write:

```bash
scripts/binance_usds_futures_trend.py --run-paper-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl --no-save-runtime-record
```

Shared testnet trading cycle dry-run (builds testnet events, signs nothing, submits nothing):

```bash
scripts/binance_usds_futures_trend.py --run-testnet-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl --no-save-runtime-record --testnet-dry-run
```

Signed testnet submission exists only behind explicit `--testnet-submit-signed`; do not run it unless the user specifically asks for real Binance futures testnet orders in the current turn and risk limits are set. When signed testnet is explicitly authorized, add `--testnet-track-order-lifecycle` only if the user also wants order/userTrades polling for lifecycle, PnL, fee, and slippage evidence.

Historical paper backtest:

```bash
scripts/binance_usds_futures_trend.py --backtest --all-symbols --interval 4h --limit 500
```

Evidence-based refinement comparison:

```bash
scripts/binance_usds_futures_trend.py --compare-refinements --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 500
```

Runtime-evidence strategy evolution replay:

```bash
scripts/binance_usds_futures_trend.py --replay-runtime-evidence --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl
```

Operational cron pattern:

- **Hourly testnet hot path:** when BTC/Alt groups, endpoints, risk parameters, runtime files, and report fields are fixed, use a deterministic `no_agent=true` script-owned cron. In this mode the script owns credential checks, signed preflight, account/position/open-order/open-algo reconciliation, gated signed testnet cycles, lifecycle/fill evidence, post-cycle snapshots, bounded stabilization, runtime/order-journal writes, secret redaction, and the final Chinese stdout summary. Prompt and skills do not execute in `no_agent=true`; stdout is delivered verbatim.
- **Current conservative startup scope:** BTC group (`BTCUSDT`) plus Alt group (`ETHUSDT,SOLUSDT,BNBUSDT`), `1h` interval, explicit risk limits, account sync, lifecycle tracking, open-algo TP/SL reconciliation, and testnet-only endpoint guards. For strict testnet crons, pass both `--base-url https://testnet.binancefuture.com` for public data reads and `--testnet-base-url https://testnet.binancefuture.com` for signed broker endpoints, then verify output shows `environment=testnet` and no mainnet host. Treat fixed `risk_unit` as compatibility/floor behavior; prefer account-risk sizing from equity, leverage target, exchange rules, current remote position, and exposure/daily-loss caps. Avoid obsolete micro-probe caps that dominate account-proportional sizing. See `references/session-v1.22-account-risk-sizing-cap-diagnosis.md`.
- **Agent mode:** keep `no_agent=false` jobs for read-only runtime replay diagnostics, order-journal interpretation, anomaly/root-cause analysis, strategy-evolution assessment, parameter-change proposals, and human-intervention recommendations. These jobs should load this Skill, avoid signed cycles/order placement/order cancellation, and report whether manual action is needed.
- **Split runner/analyzer by default:** hourly runner handles deterministic trading/execution; daily agent analyzer reads evidence and explains whether strategy or operations need attention. Do not re-run replay diagnostics in the hourly hot path unless explicitly needed.
- **Timing diagnostics are read-only by default:** when a cron notification seems late or appears at a non-scheduled minute, diagnose from existing evidence only. Allowed actions: inspect `cronjob(action="list")`, `cron/jobs.json`, `cron/output/<job_id>/*.md`, runtime/order JSONL, and gateway/cron logs. Forbidden unless the user explicitly asks to trigger execution now, e.g. “手动运行”, “立即运行”, “触发一次”, “manual run”, “run it now”, or “trigger once”: `cronjob(action="run")`, `hermes cron run`, `hermes cron resume` for the purpose of triggering, signed testnet cycles, order placement, or order cancellation.
- **Timing reports:** distinguish configured schedule/`next_run_at`, script evidence time, cron output/completion time, and Telegram delivery/display time. Non-schedule output files usually indicate an immediate/manual run-on-next-tick, not schedule drift. Default suspicion should be execution latency or extra manual trigger unless logs show a delivery error. See `references/session-v1.37-cron-manual-run-notification-timing.md`.

Telegram diagnostic brief wrapper:

```bash
scripts/binance_usds_futures_trend_brief.sh
```

## Current Trading Logic

Current signal model:

1. Validate symbol is in the configured universe.
2. Validate every interval is `>=1h` and reject duplicates.
3. Fetch free Binance USDS-M public K-lines from `/fapi/v1/klines`.
4. Optionally fetch free public context factors:
   - `/fapi/v1/markPriceKlines`;
   - `/fapi/v1/fundingRate`;
   - `/futures/data/openInterestHist`;
   - `/futures/data/globalLongShortAccountRatio`;
   - `/futures/data/takerlongshortRatio`.
5. Require enough candles for EMA200 and ATR14.
6. Compute EMA50, EMA200, ATR14, trend strength, extension, and context flags.
7. Main long-trend filter:
   - `close > EMA200`;
   - `EMA50 > EMA200`.
8. If the major trend is valid:
   - action is `hold_long`;
   - ATR references define take-profit tranches and trailing stop;
   - excessive extension reduces paper size rather than forcing a full exit;
   - context factors adjust confidence/size, not the core trend participation decision.
9. If the major trend is invalid:
   - action is `flat`;
   - existing open paper lifecycle state may emit `exit` intent.
10. In portfolio mode, allocate paper risk units by rank under total-budget and per-symbol caps.
11. In lifecycle mode, persist paper entry/add/reduce/hold/exit intent, monotonic long trailing stops, and take-profit tranche records.

Do not overfit this logic into a separate paper-only product. During the realtime-engine refactor, preserve the strategy rules as `Strategy`/`SignalEngine`, and move sizing/state/reconciliation into shared `RiskManager`, `PortfolioState`, and `ExecutionEngine` components.

## Output Contracts

Current outputs are diagnostic contracts for paper mode:

- `decision`: single-symbol paper decision;
- `scan`: multi-symbol paper scan and rankings;
- `portfolio_allocation`: paper risk allocation and skip reasons;
- `paper_state` / `state_change`: persisted scan snapshot and diff;
- `paper_lifecycle` / `lifecycle_change`: paper lifecycle state and intent changes;
- `runtime_record`: append-only paper runtime evidence schema for future strategy evolution;
- `paper_cycle`: v1.5 shared loop output containing signals, intents, desired orders, simulated fills, portfolio state, and runtime evidence;
- `testnet_cycle`: v1.9 shared loop output using `BinanceTestnetBroker`; dry-run by default with testnet environment markers, exchangeInfo/risk-rule evidence, optional signed account sync, optional signed order lifecycle/trade/PnL/slippage evidence, and redacted request evidence;
- `runtime_evolution`: v1.6 replay report comparing strategy variants on identical recorded runtime evidence, with no default promotion;
- `backtest`: paper historical performance diagnostics;
- `refinement`: paper-only baseline/candidate comparison;
- `summary_zh` or `--telegram-brief`: compact Chinese summaries with UTC and 北京时间（UTC+8） labels.

Required output invariants:

- include mode as `paper` for current paper commands;
- include `environment=testnet` for testnet cycle outputs and keep testnet state isolated from paper;
- include UTC and 北京时间（UTC+8） timestamps in reports;
- reject sub-1h intervals;
- do not include live order IDs, signed endpoint payloads, API key values, or paid API data;
- redact testnet request signatures/API-key headers in runtime evidence;
- do not claim paper/backtest metrics are live returns.

## State and Files

Important files:

- `scripts/binance_usds_futures_trend.py` — current paper-only signal/scanner/backtest/refinement/runtime-evidence CLI;
- `scripts/binance_usds_futures_trend_brief.sh` — scheduled Telegram diagnostic wrapper;
- `tests/test_binance_usds_futures_trend.py` — regression suite;
- `state/*.json` — ignored runtime paper state and lifecycle files;
- `state/*.jsonl`, `runtime/`, `runtime_data/` — ignored append-only runtime evidence datasets;
- `plans/binance-usds-futures-roadmap.md` — canonical tracked roadmap;
- `references/*.md` — historical workflow notes and architecture correction notes.

State-file rules:

- runtime state belongs under ignored `state/*.json`;
- runtime datasets for strategy evolution must be append-only or reproducibly versioned, with UTC and 北京时间（UTC+8） timestamps;
- tests should use temp directories;
- do not commit live runtime account/order/fill state;
- future testnet/live state must include environment markers and remain isolated from paper state.

## Development Roadmap

Current priority is documentation and architecture alignment, then implementation refactor:

1. Keep existing scanner/lifecycle/backtest code stable as paper-only diagnostics.
2. Reframe the scanner as `SignalEngine`, not the whole trading engine.
3. Design shared realtime interfaces: `Strategy`, `RiskManager`, `PortfolioState`, `LifecycleManager`, `ExecutionEngine`, `BrokerAdapter`.
4. Design the runtime data schema before implementing the first trading loop, including signals, decisions, risk checks, fills, state transitions, errors, and performance snapshots.
5. Use `PaperBroker` and the shared `run_trading_cycle` loop to run simulated fills while recording runtime evidence.
6. Use `StrategyEvolution` / `--replay-runtime-evidence` to compare candidate variants on recorded runtime evidence before promotion.
7. Add Binance futures testnet adapter using signed endpoints and isolated testnet credentials/config. ✅ v1.7 implemented with dry-run default and explicit signed-testnet flag; v1.8 hardened exchangeInfo rules, order journal, unknown-order confirmation, risk config, optional account sync, and hourly local dry-run evidence collection; v1.9 adds explicit signed order lifecycle polling and trade/PnL/slippage accounting.
8. Add live adapter only after testnet validation, explicit risk caps, kill switch, audit logs, runtime evidence review, and user approval.
9. Keep Telegram output as observability around the real trading loop, not as the source of trading state.
10. Use recorded runtime data to evaluate and evolve future strategy variants before promotion.

Do not add more report-only paper features unless they directly support the shared realtime engine, runtime data collection, strategy evolution, or diagnostics around it.

## Verification Recipe

For documentation-only edits to this Skill:

```bash
git diff --check
python3 - <<'PY'
from pathlib import Path
import re
p = Path('skills/crypto-trading/binance-usds-futures-trend/SKILL.md')
content = p.read_text(encoding='utf-8')
assert content.startswith('---\n')
assert '\n---\n' in content[4:]
assert len(content) <= 100_000
assert 'description:' in content.split('\n---\n', 1)[0]
assert '## Overview' in content
assert '## When to Use' in content
assert '## Common Pitfalls' in content
assert '## Verification Checklist' in content
print('skill markdown basic validation passed')
PY
```

For code or behavior edits, additionally run:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
scripts/binance_usds_futures_trend.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 3 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json --lifecycle-file state/binance-usds-futures-trend-paper-lifecycle.json --no-save-state --no-save-lifecycle
scripts/binance_usds_futures_trend.py --run-paper-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl --no-save-runtime-record
scripts/binance_usds_futures_trend.py --run-testnet-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl --no-save-runtime-record --testnet-dry-run
scripts/binance_usds_futures_trend.py --run-paper-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file /tmp/binance-v16-runtime.jsonl
scripts/binance_usds_futures_trend.py --replay-runtime-evidence --runtime-record-file /tmp/binance-v16-runtime.jsonl
```

Before committing or pushing repo changes:

- inspect `git status` and exclude runtime noise such as `cron/jobs.json`, `state/*`, logs, caches, and temporary files;
- get an independent agent review of the staged diff or final diff;
- resolve review findings, re-check the final diff, then commit and push by default when the work is complete.

Confirm:

- tests pass;
- real free-data run succeeds or blocker is reported honestly;
- intervals are `>=1h`;
- output remains paper-only;
- UTC and 北京时间（UTC+8） labels are present;
- no paid API or secret value is required;
- no runtime `state/*.json`, cron output, or editor swap file enters the commit.

## Common Pitfalls

1. **Leaving cron ownership ambiguous.** Script-owned hourly jobs should be explicit: `no_agent=true`, `skills: []`, and a script path resolved relative to the profile `scripts/` directory, e.g. `"binance_usds_futures_testnet_hourly.sh"`, not `"scripts/..."`. Agent-owned jobs should be read-only analyzer/reasoning jobs with `script: null` unless a pre-run data collection script is deliberately needed.
2. **Treating prompt prose as execution logic.** Fixed CLI commands and engine code are the real per-run contract. Prompt text is only effective when an agent executes it; it cannot override hard-coded command flags or missing code paths. See `references/session-v1.32-prompt-vs-cli-boundary.md`.
3. **Running signed testnet unintentionally.** `--run-testnet-cycle` defaults to dry-run. Only use `--testnet-submit-signed` after an explicit current-turn user request and after checking risk limits, kill switch, exact testnet hostname, credential presence, and secret redaction.
4. **Confusing testnet adapter with live permission.** Testnet code may exist, but live/mainnet signed execution remains unimplemented and unauthorized.
5. **Weak endpoint or signed-path safety.** Parse the hostname exactly as `testnet.binancefuture.com`; never rely on substring checks. If signed HTTP raises, do not store raw exception strings that may include signed URLs, signatures, or headers.
6. **Fail-open order numbers.** Reject missing/non-finite reference prices, quantities, notional caps, exposure caps, daily-loss caps, or exchangeInfo-adapted values before signing. Never allow `nan`, zero, or negative order parameters into signed requests.
7. **Mistaking acknowledgement or attempted requests for confirmed execution.** A signed submit acknowledgement is not a fill, and `submitted_unknown` is attempted but not exchange-confirmed. Separately report desired plan size, attempted real submissions, exchange-confirmed submissions, lifecycle tracked orders, fills, fees, PnL, and slippage.
8. **Trusting truncated stdout for signed results.** Reconstruct final reports from runtime JSONL, order journals, lifecycle tracking, replay diagnostics, and fresh signed snapshots; treat stdout as convenience only.
9. **Checking only ordinary open orders for protection.** Binance Futures TP/SL protection may live in open algo orders. Verify `/fapi/v1/openAlgoOrders` or broker open-algo reconciliation before claiming positions are protected; fail closed if the check fails.
10. **Overstating protection reconciliation.** Missing protection, wrong side/type, unsafe close-only semantics, stale trigger prices, duplicate stale groups, and orphan algo orders are distinct anomalies. Current repair handles missing SL/TP and upward stop replacement; do not claim broad stale-TP deduplication unless code supports it.
11. **Using fixed quantity as the primary sizing model.** `risk_unit` is a legacy/default floor for startup probes. Production testnet sizing should be based on equity × account-risk fraction, target leverage, exchange min/step/notional rules, current signed position, max symbol exposure, max order notional, max daily loss, and delta-only execution.
12. **Misreading risk-resized reductions as trend exits.** When a cron run submits `SELL MARKET` for an existing long, first check whether the signal is still `hold_long` and whether account-risk sizing lowered the target total position because ATR/stop distance changed. A negative `desired_exposure - current_exposure` is a rebalance, not automatically a bearish/flat strategy decision. See `references/session-v1.41-testnet-delta-rebalance-and-entry-budget.md`.
13. **Treating target position as additive quantity.** Strategy `position_size` means target total exposure, not “buy this much more”. Replan from `desired_exposure - current_exposure`; if existing exposure already equals target, emit no duplicate add-on.
14. **Under-budgeting order count for tranche plans.** Entry + stop-loss + multiple take-profit legs can exceed low `--testnet-max-order-count`. Enforce the per-cycle order budget before signing the ordered plan; treat `exchange_confirmed_count > max_order_count` as a risk-control defect.
15. **Expanding symbols without exchange minimum checks.** Binance Futures Testnet has per-symbol `minQty`, `stepSize`, and `MIN_NOTIONAL`. Dry-run against `exchangeInfo`, group symbols by compatible quantity floors, and keep notional/order-count limits explicit.
16. **Losing canonical evidence files.** Operational cron evidence should use `state/binance-usds-futures-trend-testnet-runtime.jsonl` and `state/binance-usds-futures-trend-testnet-orders.jsonl`. Reconcile near-miss legacy files when found, but prevent mismatches by passing file flags explicitly.
17. **Conflating evidence collection with strategy evaluation.** A `no_agent=true` cron collects and reports deterministic evidence; it does not judge strategy improvement. Pair it with a separate daily agent-mode analyzer for 24h/72h interpretation and promotion decisions.
18. **Treating a very fast hourly run as full lifecycle evidence.** If real or attempted orders occur, run bounded postflight stabilization snapshots and report attempts, stabilization seconds, attempted-vs-confirmed counts, lifecycle tracked/filled counts, and protection status.
19. **Using short intervals.** The user rejects intervals below `1h`; enforce this in CLI, code, tests, docs, cron schedules, and runtime replay validation fields (`market_inputs.primary_interval`, `market_inputs.intervals`, `signals[].interval`).
20. **Building a paper scanner instead of a trading engine.** Paper is an adapter for the shared trading loop, not the architecture itself. Telegram output is observability; canonical state belongs in portfolio/lifecycle/runtime evidence.
21. **Over-exiting trends.** The strategy preference is to keep participating in the main trend and harvest in tranches; extension should usually reduce size, not force a full exit while the major trend remains valid.
22. **Replaying with fresh samples.** Runtime-evidence replay must not fetch new K-lines; all variants must share captured input fingerprints.
23. **Overstating diagnostics.** Paper scans, backtests, and refinement comparisons are evidence, not live performance proof.
24. **Mixing environments or leaking state.** Keep paper/testnet/live credentials, balances, order IDs, fills, and state files isolated. Do not commit `state/*.json`, account/order/fill state, cron output, raw signed payloads, API keys, or secret values.
25. **Committing scheduler runtime noise.** Hermes cron may rewrite counters and timestamps in `cron/jobs.json`; restore/exclude runtime-only changes before review, commit, and push.
26. **Creating an extra run while diagnosing timing.** `cronjob(action="run")` and `hermes cron run` intentionally enqueue an immediate run on the next scheduler tick. If the user asks why a notification arrived at an odd minute, inspect existing job state and `cron/output/` only; do not trigger another run unless explicitly requested with execution-now intent such as “手动运行”, “立即运行”, “触发一次”, “run it now”, or “trigger once”. Do not treat generic words like “run result”, “运行结果”, or “runtime evidence” as authorization to execute.
27. **Skipping independent review or timezone labels.** This repo requires independent agent review before push, and every time-related output must label UTC or 北京时间（UTC+8）.

## References

Canonical current references:

- `references/session-v1.30-single-agent-hourly-regression-root-cause.md` — current boundary: explicit script-owned vs agent-owned cron semantics; avoid hidden wrapper ownership.
- `references/session-v1.31-pause-reset-after-manual-position-clear.md` — pause/reset workflow after manual testnet position clearing, including evidence archiving and UTC/北京时间（UTC+8） verification.
- `references/session-v1.32-prompt-vs-cli-boundary.md` — distinguish prompt prose, fixed CLI flags, and actual engine code paths.
- `references/session-v1.33-skill-boundary-curation.md` — curation checklist for keeping deterministic hourly cron ownership, Skill-library references, and memory/profile preferences aligned.
- `references/session-v1.34-trimming-memory-user-skill.md` — compact checklist for trimming MEMORY/USER/SKILL together without dropping durable trading constraints or executable CLI boundaries.
- `references/session-v1.35-cagr-plan-current-chain-review.md` — checklist for reviewing CAGR/hold-style optimization plans against the current chain: account-risk sizing already exists, `position_size` is target total exposure, hourly hot path is script-owned `no_agent=true`, and replay promotion must use real runtime/order-journal evidence.
- `references/session-v1.36-runtime-evidence-bootstrap-and-cron-resume.md` — when runtime/order-journal files are empty, first restore and verify cron evidence collection before doing CAGR bottleneck analysis or strategy optimization.
- `references/session-v1.37-cron-manual-run-notification-timing.md` — diagnose unexpected cron notification timing by separating schedule/next_run, script evidence time, cron completion/output time, and Telegram delivery/display time; avoid accidentally triggering another immediate run during diagnosis.
- `references/session-v1.38-independent-testnet-hourly-audit.md` — pattern for independent read-only review of `testnet-agent-hourly` results, including schedule classification, runtime/order journal checks, protection/rejection/submitted_unknown assessment, and UTC/北京时间 reporting.
- `references/session-v1.39-testnet-protection-reconciliation.md` — durable root causes and regression pattern for group-scoped protection reports plus Binance conditional algo order `submitted_unknown` confirmation/reconciliation via `clientAlgoId` and `open_algo_orders`.
- `references/session-v1.40-external-crypto-quant-skills-review.md` — comparison of external crypto/quant agent skills and frameworks; keep VectorBT/Hummingbot/AiCoin/Senpi ideas as references while excluding external trading skills from the deterministic testnet hot path.
- `references/session-v1.41-testnet-delta-rebalance-and-entry-budget.md` — read-only audit pattern for explaining a specific hourly testnet decision: distinguish hold_long risk-resized reductions from trend exits, fixed hourly group scope from full-universe scans, and skipped entries caused by atomic entry/protection order-budget limits.
- `references/session-v1.22-account-risk-sizing-cap-diagnosis.md` — diagnosing account-risk sizing that is dominated by fixed max-order/max-symbol exposure caps.
- `references/session-v1.24-testnet-order-budget-and-postrun-reconstruction.md` — order-count budget lesson for entry + stop + TP tranches and safe post-run reconstruction.
- `references/session-v1.25-testnet-cron-endpoint-and-order-budget-audit.md` — strict testnet endpoint arguments and order-budget enforcement.
- `references/session-v1.26-single-agent-cron-artifact-and-budget-audit.md` — canonical runtime/order journal paths, separate desired/attempted/confirmed/lifecycle counts, and zero-position open-algo anomaly reporting.
- `references/session-v1.27-stale-atomic-addon-replanning.md` — delta-only reconciliation for existing-position atomic add-ons.
- `references/protective-order-reconciliation.md` — protective-order reconciliation rules.

Historical notes retained for archaeology, not as the main operational path:

- `references/binance-skills-hub-usds-futures.md` — Binance USDS-M futures endpoint notes;
- `references/session-v0.2-public-factors-workflow.md` through `references/session-v1.6-runtime-evidence-strategy-evolution.md` — paper scanner, paper lifecycle, shared paper loop, and runtime-evidence evolution history;
- `references/session-v1.7-planning-authorization.md` and `references/session-v1.7-testnet-adapter.md` — signed-testnet planning/adapter authorization boundary;
- `references/session-v1.10-agent-cron-testnet-operations.md` through `references/session-v1.21-single-agent-cron-execution-summary.md` — older single-agent testnet cron runbooks and safe-summary patterns. These are superseded for hourly hot-path ownership by the current script-owned `no_agent=true` boundary, but still contain useful preflight, post-snapshot, protection, and summary-field details;
- `references/session-v1.23-single-agent-cron-default-and-sizing-cap-fix.md`, `references/session-v1.28-cron-latency-and-replay-splitting.md`, and `references/session-v1.29-hourly-postflight-stabilization-and-single-agent-ownership.md` — transitional ownership/latency notes superseded by the current split runner/analyzer model, except for their evidence and postflight-stabilization lessons.

Tracked plans:

- `plans/binance-usds-futures-roadmap.md` — canonical roadmap;
- `plans/binance-usds-futures-trend-v0.3.md` through `plans/binance-usds-futures-trend-v1.9.md` — historical implementation plans from scanner, paper lifecycle, runtime recorder, shared loop, testnet adapter, readiness hardening, and signed order lifecycle tracking.

## Verification Checklist

- [ ] Skill describes the current architecture direction, not only historical versions.
- [ ] Current code is described honestly as paper/testnet-only, with no live/mainnet implementation.
- [ ] Paper/testnet/live shared-engine invariant is explicit.
- [ ] Commands use intervals `>=1h`.
- [ ] UTC and 北京时间（UTC+8） requirements are preserved.
- [ ] No paid API or secret value is required.
- [ ] Runtime data recording and strategy-evolution evidence requirements are preserved.
- [ ] Runtime state stays ignored.
- [ ] Tests and/or appropriate documentation validation ran.
- [ ] Independent agent review passed before push.
