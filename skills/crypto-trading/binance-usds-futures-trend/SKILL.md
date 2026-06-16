---
name: binance-usds-futures-trend
description: Use when developing or operating the crypto-trade-hermes Binance USDS-M futures trend Skill. Current code provides paper-only signal, lifecycle, backtest, and diagnostic tools from free >=1h data; future work must evolve it into a real-time trading engine where paper/testnet/live share strategy, state, risk, and execution interfaces.
version: 1.8.0
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

The intended architecture is **Skill-driven real-time trading**:

- paper, testnet, and live modes should share the same trading loop;
- strategy, state transitions, risk checks, lifecycle management, and execution reconciliation should stay on one code path;
- only the broker/fill adapter and environment configuration should change;
- paper mode is a safety/testing adapter, not a separate report-style scanner product.

Current implementation status: the CLI now supports paper diagnostics/shared paper cycles, runtime-evidence replay, and a v1.8-hardened Binance USDS-M futures **testnet** adapter. v1.5 adds the first shared trading loop wired to `PaperBroker` simulated fills, v1.6 adds runtime-evidence replay diagnostics for strategy evolution, v1.7 adds `BinanceTestnetBroker` with dry-run default/testnet endpoint guard/credential resolver/risk gates/redaction/CLI `--run-testnet-cycle`, and v1.8 adds exchangeInfo rule adaptation, clientOrderId + append-only order journal, unknown-order confirmation, config-driven risk limits, optional signed account sync, and hourly local dry-run evidence collection. It does **not** implement live/mainnet execution. Treat existing scan/lifecycle/runtime-recording code as reusable signal, state, and evidence modules while the project is refactored toward a shared real-time trading engine.

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
- v1.8-hardened Binance futures testnet adapter via `BinanceTestnetBroker` and CLI `--run-testnet-cycle`: dry-run default, explicit signed-testnet flag, exchangeInfo order rules, account/order sync helpers, clientOrderId/order journal, risk config, and redaction;
- single-symbol trend decision from free K-lines;
- full-universe or selected-symbol scan;
- multi-timeframe confirmation, usually `1h,4h,1d`;
- rank scoring and grouping of strong/early/conflicting/watchlist trends;
- optional paper portfolio risk allocation;
- optional persisted scan state and state-change summaries;
- optional paper lifecycle state with entry/add/reduce/hold/exit intent;
- optional append-only runtime evidence records for strategy evolution;
- historical paper backtest metrics;
- evidence-based refinement comparison on identical fetched candle samples;
- compact Telegram diagnostic brief via wrapper script.

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

Signed testnet submission exists only behind explicit `--testnet-submit-signed`; do not run it unless the user specifically asks for real Binance futures testnet orders in the current turn and risk limits are set.

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
- `testnet_cycle`: v1.8 shared loop output using `BinanceTestnetBroker`; dry-run by default with testnet environment markers, exchangeInfo/risk-rule evidence, optional signed account sync, and redacted request evidence;
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
7. Add Binance futures testnet adapter using signed endpoints and isolated testnet credentials/config. ✅ v1.7 implemented with dry-run default and explicit signed-testnet flag; v1.8 hardened exchangeInfo rules, order journal, unknown-order confirmation, risk config, optional account sync, and hourly local dry-run evidence collection.
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

1. **Building a paper scanner instead of a trading engine.** Paper is an execution adapter for the future trading loop, not the architecture itself.
2. **Confusing safety with divergence.** Safety should come from adapter isolation, testnet-first validation, kill switches, strict risk caps, and explicit live gates — not from building a paper-only system that cannot become live.
3. **Using short intervals.** The user rejects intervals below `1h`; enforce this in CLI, code, tests, docs, and cron schedules.
4. **Over-exiting trends.** The strategy preference is to keep participating in the main trend and harvest in tranches; extension should usually reduce size, not force a full exit while the major trend remains valid.
5. **Committing runtime state.** Real state files belong under ignored `state/*.json`; do not commit account/order/fill state or local cron output.
6. **Leaking secrets.** Mention variable names only when needed; never expose values from `.env` or signed request payloads.
7. **Overstating diagnostics.** Paper scans, backtests, and refinement comparisons are evidence and diagnostics, not live performance proof.
8. **Letting Telegram briefs become the state machine.** Telegram output is observability; canonical state belongs in `PortfolioState` / lifecycle files / future execution logs.
9. **Comparing strategy variants on drifting live samples.** Fetch each symbol sample once and reuse it across baseline/candidates so differences are strategy-driven.
10. **Treating `PaperBroker` fills as live execution.** v1.5 fills are simulated; they prove loop plumbing and runtime evidence only.
11. **Skipping independent review before push.** This repo requires an independent agent review before every push.
12. **Forgetting timezone labels.** Any time-related output or report must explicitly label UTC or 北京时间（UTC+8）.
13. **Mixing environments.** Future paper, testnet, and live adapters must isolate credentials, balances, order IDs, fills, and state files while sharing core interfaces.
14. **Failing to preserve runtime evidence.** Strategy evolution must be based on recorded run data, not subjective impressions from Telegram summaries or isolated backtests.
   - For runtime-evidence replay interval safety, validate every interval-bearing field, not only the top-level `intervals`: include `market_inputs.primary_interval`, `market_inputs.intervals`, and `signals[].interval`. When review finds an uncovered interval location, add a RED regression test for that exact location before patching.
15. **Replaying with fresh samples.** v1.6 runtime-evidence replay must not fetch new K-lines; all variants must share the same captured input fingerprint.
16. **Treating v1.7 selection as signed-execution authorization.** If the user chooses “1.7” after being offered planning-only v1.7 work, do planning only. Do not implement signed testnet execution code until the user explicitly authorizes writing a testnet signed adapter; live/mainnet remains unauthorized.
17. **Confusing testnet adapter with live permission.** v1.7 testnet code may exist, but live/mainnet signed execution remains unimplemented and unauthorized.
18. **Running signed testnet unintentionally.** `--run-testnet-cycle` defaults to dry-run. Only use `--testnet-submit-signed` after an explicit current-turn user request and after checking risk limits, kill switch, endpoint host, and secret redaction.
19. **Weak endpoint validation.** Testnet URL checks must parse the hostname exactly as `testnet.binancefuture.com`; substring checks can be bypassed by lookalike hosts.
20. **Signed-path exception leaks.** If signed testnet HTTP raises, never store `str(exc)` because lower layers may include signed URLs, signatures, or headers. Record sanitized `submitted_unknown` metadata instead.
21. **Fail-open reference prices.** Testnet broker must not default missing `reference_price` / `entry_reference` to `1.0`; reject invalid/missing/non-finite prices before signing unless a global kill/order-count/loss gate already rejects.
22. **Treating risk-limit config as inherently safe.** Validate testnet risk-limit values as finite, positive numbers where applicable; a NaN/inf/negative max notional, exposure cap, daily-loss cap, or order-count limit can silently weaken fail-closed behavior.
23. **Fail-open exchange/order numbers.** Testnet broker must reject non-finite quantities and any exchangeInfo-adapted quantity/reference price that becomes invalid before signing; never allow `nan`, zero, or negative order parameters into signed POST URLs.

## References

Historical workflow notes are intentionally kept out of the main operational path:

- `references/binance-skills-hub-usds-futures.md` — Binance USDS-M futures endpoint notes;
- `references/session-v0.2-public-factors-workflow.md` — free public context factors;
- `references/session-v0.3-batch-scanner-workflow.md` — batch scanning and ranking;
- `references/session-v0.4-multi-timeframe-workflow.md` — multi-timeframe confirmation;
- `references/session-v0.5-portfolio-risk-workflow.md` — portfolio paper risk allocation;
- `references/session-v0.6-allocation-explainability-workflow.md` — allocation/skip explanations;
- `references/session-v0.7-paper-state-persistence-workflow.md` — paper state snapshots and diffs;
- `references/session-v0.8-scheduled-telegram-briefing-workflow.md` — scheduled Telegram brief output;
- `references/session-v0.9-historical-backtest-workflow.md` — historical paper backtest framework;
- `references/session-v1.0-evidence-based-refinement-workflow.md` — paper-only refinement comparison;
- `references/session-v1.1-paper-lifecycle-workflow.md` — paper lifecycle state and intent;
- `references/session-v1.2-realtime-architecture-correction.md` — correction toward shared real-time trading architecture.
- `references/session-v1.3-runtime-data-strategy-evolution.md` — runtime data capture requirements for evidence-based strategy evolution.
- `references/session-v1.3-runtime-recorder-implementation.md` — implementation and verification workflow for the paper runtime JSONL recorder.
- `references/session-v1.4-core-interface-extraction.md` — implementation and verification workflow for extracting shared realtime core interfaces while preserving paper-only CLI behavior.
- `references/session-v1.5-shared-paper-loop.md` — implementation and verification workflow for the shared trading loop and PaperBroker simulated fills.
- `references/session-v1.6-runtime-evidence-strategy-evolution.md` — implementation and verification workflow for replaying runtime evidence to compare strategy variants.
- `references/session-v1.7-planning-authorization.md` — planning-only boundary and explicit authorization requirement before writing signed testnet adapter code.
- `references/session-v1.7-testnet-adapter.md` — implementation workflow for the Binance futures testnet adapter, dry-run default, endpoint guard, and risk gates.

Tracked plans:

- `plans/binance-usds-futures-roadmap.md` — canonical roadmap;
- `plans/binance-usds-futures-trend-v0.3.md` through `plans/binance-usds-futures-trend-v1.1.md` — historical implementation plans;
- `plans/binance-usds-futures-trend-v1.3.md` — runtime data recorder implementation plan;
- `plans/binance-usds-futures-trend-v1.4.md` — core realtime interface extraction plan;
- `plans/binance-usds-futures-trend-v1.5.md` — shared trading loop and PaperBroker plan;
- `plans/binance-usds-futures-trend-v1.6.md` — strategy evolution from runtime evidence plan;
- `plans/binance-usds-futures-trend-v1.7.md` — Binance futures testnet adapter plan;
- `plans/binance-usds-futures-trend-v1.8.md` — testnet readiness hardening plan: exchangeInfo, order journal, risk config, sync, dry-run evidence.

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
