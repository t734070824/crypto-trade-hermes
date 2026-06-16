---
name: binance-usds-futures-trend
description: Use when developing or operating the crypto-trade-hermes Binance USDS-M futures trend Skill. Current code provides paper-only signal, lifecycle, backtest, and diagnostic tools from free >=1h data; future work must evolve it into a real-time trading engine where paper/testnet/live share strategy, state, risk, and execution interfaces.
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

The intended architecture is **Skill-driven real-time trading**:

- paper, testnet, and live modes should share the same trading loop;
- strategy, state transitions, risk checks, lifecycle management, and execution reconciliation should stay on one code path;
- only the broker/fill adapter and environment configuration should change;
- paper mode is a safety/testing adapter, not a separate report-style scanner product.

Current implementation status: the CLI now supports paper diagnostics/shared paper cycles, runtime-evidence replay, and a v1.9-hardened Binance USDS-M futures **testnet** adapter. v1.5 adds the first shared trading loop wired to `PaperBroker` simulated fills, v1.6 adds runtime-evidence replay diagnostics for strategy evolution, v1.7 adds `BinanceTestnetBroker` with dry-run default/testnet endpoint guard/credential resolver/risk gates/redaction/CLI `--run-testnet-cycle`, v1.8 adds exchangeInfo rule adaptation, clientOrderId + append-only order journal, unknown-order confirmation, config-driven risk limits, optional signed account sync, and hourly local dry-run evidence collection, and v1.9 adds signed order lifecycle polling plus trade/PnL/slippage accounting. It does **not** implement live/mainnet execution. Treat existing scan/lifecycle/runtime-recording code as reusable signal, state, and evidence modules while the project is refactored toward a shared real-time trading engine.

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

- Prefer a single agent cron (`no_agent=false`) with this Skill loaded when the scheduled workflow must own the full testnet operation: credential presence check, signed account preflight, position/open-order reconciliation, gated signed testnet cycle, lifecycle/fill evidence, post-cycle account snapshot, and Chinese Telegram summary with explicit UTC and 北京时间（UTC+8） labels. For this user/project, default toward **one Skill-loaded agent cron owning the end-to-end testnet trading flow** instead of splitting orchestration across multiple agent jobs; use `no_agent=true` script cron only as a runtime evidence collector/watchdog, not as the strategic trading decision-maker.
- Current startup signed-testnet scope is multi-symbol but still conservative unless the user explicitly changes it: run a BTC group (`BTCUSDT`, legacy/default `--risk-unit 0.001`, `--account-risk-fraction 0.003`, `--target-leverage 2`, `--testnet-max-order-count 3`) plus an Alt group (`ETHUSDT,SOLUSDT,BNBUSDT`, legacy/default `--risk-unit 0.1`, `--account-risk-fraction 0.003`, `--target-leverage 2`, `--testnet-max-order-count 6`), both on `--interval 1h` with `--base-url https://testnet.binancefuture.com`, `--testnet-max-order-notional 200`, `--testnet-max-symbol-exposure 70`, `--testnet-max-daily-loss 10`, account sync, lifecycle tracking, open-algo TP/SL reconciliation, and testnet-only endpoint guard. Treat fixed `risk_unit` as compatibility/floor behavior; prefer account-risk sizing from equity, leverage target, exchange rules, current remote position, and exposure/daily-loss caps.
- Use `no_agent=true` only for deterministic collectors/watchdogs whose script is the whole job and no reasoning is wanted. Empty `skills: []` is expected in this mode because no LLM reasoning runs.
- Split collector/analyzer jobs only when reproducibility, cost, or isolation materially benefits from the split; do not split merely by habit when the user expects one agent-type task to handle the operational loop.
- Add/maintain a daily agent-mode runtime replay diagnostic cron when requested: load this Skill, run every 24h, execute `--replay-runtime-evidence` against the testnet runtime JSONL, optionally summarize the order journal, and report whether evidence/lifecycle/protection issues need human intervention. It must be read-only and explicitly prohibit signed cycles, order placement, order cancellation, raw signed request output, and secret disclosure.

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

1. **Defaulting to split cron workflows when an agent loop should own the process.** If the user asks why one agent-type scheduled task cannot handle the whole testnet workflow, treat that as a design correction: prefer a single agent cron with this Skill loaded when the job needs to gather evidence, inspect state, reconcile positions/orders, decide whether signed testnet is safe, run the cycle, interpret failures, and report next actions. Use separate `no_agent=true` collectors only when deterministic evidence capture must be isolated from LLM reasoning; otherwise avoid over-fragmenting the operational loop into collector/analyzer/promoter jobs.
2. **Trying signed testnet before credential validation and position reconciliation.** Before enabling recurring signed testnet operation, run a small explicit signed probe/cycle, verify Binance Futures Testnet credentials against signed endpoints, sync remote positions/account state, and confirm actual order/fill lifecycle evidence. A dry-run success plus locally present `LALA_KEY`/`LALA_SECRET` is not sufficient to enable signed cron.
3. **Committing scheduler runtime noise.** Hermes cron may rewrite fields such as `completed`, `next_run_at`, `last_run_at`, and `updated_at` in `cron/jobs.json` while you are working. Treat those as runtime noise unless the task intentionally changes cron definitions; restore/exclude them before review, commit, and push.
4. **Trusting truncated stdout for signed testnet results.** Large cycle outputs can be truncated in terminal capture. Rebuild the final report from runtime JSONL, order journals, replay diagnostics, and a fresh signed post-cycle snapshot instead of depending on stdout alone.
4. **Building a paper scanner instead of a trading engine.** Paper is an execution adapter for the future trading loop, not the architecture itself.
5. **Confusing safety with divergence.** Safety should come from adapter isolation, testnet-first validation, kill switches, strict risk caps, and explicit live gates — not from building a paper-only system that cannot become live.
6. **Using short intervals.** The user rejects intervals below `1h`; enforce this in CLI, code, tests, docs, and cron schedules.
7. **Over-exiting trends.** The strategy preference is to keep participating in the main trend and harvest in tranches; extension should usually reduce size, not force a full exit while the major trend remains valid.
8. **Committing runtime state.** Real state files belong under ignored `state/*.json`; do not commit account/order/fill state or local cron output.
9. **Leaking secrets.** Mention variable names only when needed; never expose values from `.env` or signed request payloads.
10. **Overstating diagnostics.** Paper scans, backtests, and refinement comparisons are evidence and diagnostics, not live performance proof.
11. **Letting Telegram briefs become the state machine.** Telegram output is observability; canonical state belongs in `PortfolioState` / lifecycle files / future execution logs.
12. **Comparing strategy variants on drifting live samples.** Fetch each symbol sample once and reuse it across baseline/candidates so differences are strategy-driven.
13. **Treating `PaperBroker` fills as live execution.** v1.5 fills are simulated; they prove loop plumbing and runtime evidence only.
14. **Skipping independent review before push.** This repo requires an independent agent review before every push.
15. **Forgetting timezone labels.** Any time-related output or report must explicitly label UTC or 北京时间（UTC+8）.
16. **Mixing environments.** Future paper, testnet, and live adapters must isolate credentials, balances, order IDs, fills, and state files while sharing core interfaces.
17. **Failing to preserve runtime evidence.** Strategy evolution must be based on recorded run data, not subjective impressions from Telegram summaries or isolated backtests.
   - For runtime-evidence replay interval safety, validate every interval-bearing field, not only the top-level `intervals`: include `market_inputs.primary_interval`, `market_inputs.intervals`, and `signals[].interval`. When review finds an uncovered interval location, add a RED regression test for that exact location before patching.
18. **Replaying with fresh samples.** v1.6 runtime-evidence replay must not fetch new K-lines; all variants must share the same captured input fingerprint.
19. **Treating v1.7 selection as signed-execution authorization.** If the user chooses “1.7” after being offered planning-only v1.7 work, do planning only. Do not implement signed testnet execution code until the user explicitly authorizes writing a testnet signed adapter; live/mainnet remains unauthorized.
20. **Confusing testnet adapter with live permission.** v1.7 testnet code may exist, but live/mainnet signed execution remains unimplemented and unauthorized.
21. **Running signed testnet unintentionally.** `--run-testnet-cycle` defaults to dry-run. Only use `--testnet-submit-signed` after an explicit current-turn user request and after checking risk limits, kill switch, endpoint host, and secret redaction.
22. **Weak endpoint validation.** Testnet URL checks must parse the hostname exactly as `testnet.binancefuture.com`; substring checks can be bypassed by lookalike hosts.
23. **Signed-path exception leaks.** If signed testnet HTTP raises, never store `str(exc)` because lower layers may include signed URLs, signatures, or headers. Record sanitized `submitted_unknown` metadata instead.
24. **Fail-open reference prices.** Testnet broker must not default missing `reference_price` / `entry_reference` to `1.0`; reject invalid/missing/non-finite prices before signing unless a global kill/order-count/loss gate already rejects.
25. **Treating risk-limit config as inherently safe.** Validate testnet risk-limit values as finite, positive numbers where applicable; a NaN/inf/negative max notional, exposure cap, daily-loss cap, or order-count limit can silently weaken fail-closed behavior.
26. **Fail-open exchange/order numbers.** Testnet broker must reject non-finite quantities and any exchangeInfo-adapted quantity/reference price that becomes invalid before signing; never allow `nan`, zero, or negative order parameters into signed POST URLs.
27. **Conflating evidence collection with strategy evaluation.** A `no_agent=true` cron with `skills: []` is appropriate for deterministic runtime evidence collection, but it will not analyze whether the strategy is improving. Pair it with a separate agent-mode analyzer cron using this Skill when the user asks for 24h/72h evidence interpretation or promotion decisions.
28. **Treating order acknowledgement as a fill, or treating attempted signed requests as accepted.** Signed testnet submit success only proves Binance acknowledged an order. Use `track_order_lifecycle` / `--testnet-track-order-lifecycle` to query `/fapi/v1/order` and `/fapi/v1/userTrades`, then compute lifecycle state, fills, fees, realized/net PnL, and slippage from exchange-confirmed data. If a signed request returns `submitted_unknown` and confirmation fails, report it as attempted but not exchange-confirmed; do not count it as accepted or filled even if `real_order_submitted=true`.
29. **Mistaking reconciliation no-ops for failed operation.** In the startup single-agent signed testnet cron, a successful cycle with `desired_orders=[]` and `real_orders_submitted=false` can be correct when signed preflight/account sync shows existing positions already equal desired exposure. Report it as duplicate-add prevention via position reconciliation, then verify with a post-cycle signed snapshot.
30. **Checking only ordinary open orders for TP/SL.** Binance USDS-M Futures testnet protective stops/take-profits may be algo orders, so `/fapi/v1/openOrders` alone can falsely imply an unprotected position. Verify `/fapi/v1/openAlgoOrders` or the broker's open-algo reconciliation before claiming whether a position has stop loss / take profit. If the open-algo query fails, fail closed instead of assuming no protection exists.
31. **Using fixed quantity as the primary sizing model.** `risk_unit` is acceptable as a legacy/default floor for startup probes, but production testnet sizing should be account/risk based: equity × account-risk fraction, target leverage, exchange min/step/notional rules, current signed position, max symbol exposure, max order notional, max daily loss, and delta-only execution.
32. **Pasting raw cycle JSON into Telegram reports.** For signed testnet cron output, parse JSON and summarize only safe fields: success, testnet-only environment, real-order-submitted flag, order/lifecycle counts, non-zero positions, open-order/open-algo counts, runtime record path, risk limits, and UTC/北京时间（UTC+8） timestamps. Never paste full raw JSON or signed request details.
33. **Expanding symbols without checking exchange minimums.** Binance Futures Testnet applies per-symbol `minQty`, `stepSize`, and `MIN_NOTIONAL`. A universal `risk_unit=0.001` works for BTC startup exposure but can make ETH/SOL/BNB/XRP orders reject as too small. Before adding recurring signed symbols, dry-run against `exchangeInfo`; group symbols by compatible `risk_unit` and keep `--testnet-max-order-notional` / `--testnet-max-order-count` tight.
34. **Overstating protection reconciliation.** A “保护单失配” can mean missing TP/SL, wrong side/type, unsafe close-only semantics, stale trigger prices, or duplicate stale groups. The current repair path handles missing protection by adding absent `STOP_MARKET` / layered `TAKE_PROFIT_MARKET` algo orders, and replaces an existing stop only when the newly computed trailing stop moves upward. It still does not broadly deduplicate stale TP groups or loosen stops. See `references/session-v1.16-protection-mismatch-and-bnb-repair.md`.
35. **Letting replay diagnostics mutate trading state.** Daily runtime replay diagnostics should be agent-mode for interpretation, but read-only in behavior: run `--replay-runtime-evidence`, inspect runtime/order journals safely, and report blockers/anomalies. Do not run signed testnet cycles, place/cancel orders, or expose raw signed payloads from a replay diagnostic job.

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
- `references/session-v1.10-agent-cron-testnet-operations.md` — preference and workflow notes for a single agent-type cron owning testnet operational reasoning, plus signed-testnet gating and cron runtime-noise hygiene.
- `references/session-v1.11-agent-testnet-cron-preflight-and-summary.md` — signed testnet cron runbook detail: read-only account preflight, post-cycle snapshot verification, position-reconciliation interpretation, and safe Chinese summary fields.
- `references/session-v1.12-agent-testnet-cron-json-summary-wrapper.md` — reusable wrapper pattern for preflight → signed cycle → JSON parsing → post-cycle snapshot → safe Chinese report without raw cycle JSON.
- `references/session-v1.13-agent-testnet-cron-post-verification.md` — post-run cross-check pattern for signed cron summaries: independently verify selected-symbol signed snapshot plus latest runtime/order-journal evidence before final Telegram-safe reporting.
- `references/session-v1.15-testnet-open-algo-and-account-risk-sizing.md` — durable lessons for open-algo TP/SL reconciliation, fail-closed protection checks, account-risk sizing, and post-run signed verification.
- `references/session-v1.14-agent-cron-wrapper-safe-summary.md` — reusable single-agent cron wrapper pattern: signed preflight, sequential BTC/Alt signed cycles, runtime-evolution replay, post-snapshot verification, evidence file checks, and Chinese Telegram-safe summaries without raw JSON.
- `references/session-v1.17-submitted-unknown-and-safe-cron-summary.md` — handling `submitted_unknown` signed requests as attempted but not exchange-confirmed, plus safe reporting and command-building pitfalls.
- `references/session-v1.18-single-agent-testnet-cron-json-harness.md` — reusable Python harness pattern for a scheduled single-agent signed testnet cron: signed preflight, sequential BTC/Alt cycles, runtime replay, post snapshot, safe Chinese summary, and fail-closed protection reporting.
- `references/session-v1.19-pause-and-reset-testnet-state.md` — operational reset workflow: pause mutating cron jobs, archive runtime/order journals with manifest hashes and UTC/北京时间（UTC+8） timestamps, clear local ignored evidence files, and avoid confusing local reset with exchange position state.
- `references/session-v1.20-testnet-post-run-summary-and-journal-summarization.md` — reconstruct signed testnet outcomes from runtime JSONL, order journals, replay JSON, and a fresh signed snapshot when CLI stdout is truncated.

Tracked plans:

- `plans/binance-usds-futures-roadmap.md` — canonical roadmap;
- `plans/binance-usds-futures-trend-v0.3.md` through `plans/binance-usds-futures-trend-v1.1.md` — historical implementation plans;
- `plans/binance-usds-futures-trend-v1.3.md` — runtime data recorder implementation plan;
- `plans/binance-usds-futures-trend-v1.4.md` — core realtime interface extraction plan;
- `plans/binance-usds-futures-trend-v1.5.md` — shared trading loop and PaperBroker plan;
- `plans/binance-usds-futures-trend-v1.6.md` — strategy evolution from runtime evidence plan;
- `plans/binance-usds-futures-trend-v1.7.md` — Binance futures testnet adapter plan;
- `plans/binance-usds-futures-trend-v1.8.md` — testnet readiness hardening plan: exchangeInfo, order journal, risk config, sync, dry-run evidence;
- `plans/binance-usds-futures-trend-v1.9.md` — signed testnet order lifecycle tracking plan: order/userTrades polling plus PnL, fee, and slippage evidence.

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
