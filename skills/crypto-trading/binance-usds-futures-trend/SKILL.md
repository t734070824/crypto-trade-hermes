---
name: binance-usds-futures-trend
description: Use when generating paper-only Binance USDS-M futures trend-following decisions from free public K-line data with >=1h intervals, ATR harvesting, and no paid APIs.
version: 0.9.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [binance, futures, crypto-trading, trend-following, paper-trading]
    related_skills: [test-driven-development]
---

# Binance USDS Futures Trend Paper Decisions

## Overview

This project Skill supports paper-only Binance USDS-M futures decision generation using free public Binance Futures K-line data. It is designed for the crypto-trade-hermes profile and respects the user's strategy constraints:

- trade universe: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, LINKUSDT, AVAXUSDT, ADAUSDT, LTCUSDT, TRXUSDT, DOTUSDT, POLUSDT, BCHUSDT, APTUSDT, ARBUSDT, OPUSDT, SUIUSDT, INJUSDT, ATOMUSDT;
- no paid APIs;
- never use short intervals below 1h;
- prefer staying with the main trend, avoiding premature exits, and harvesting in tranches.

The implementation is deliberately conservative: it emits structured `paper` decisions only; it never sends signed orders. v0.2 adds free Binance USDS-M public context factors while keeping EMA trend participation as the primary filter. v0.3 adds multi-symbol batch scanning and ranking so portfolio attention can focus on the strongest trends before any live execution work. v0.4 adds multi-timeframe confirmation (`1h,4h,1d`) to reduce single-period noise while preserving the primary trend-following contract. v0.5 adds optional portfolio-level paper risk allocation with total-budget and per-symbol caps. v0.6 adds allocation explainability for allocated and skipped symbols and includes compact allocation notes in `summary_zh`. v0.7 adds optional paper state persistence, storing scan snapshots and reporting allocation/ranking/action/bucket changes between consecutive scans. v0.8 adds compact Telegram briefing output for scheduled Hermes cron delivery. v0.9 adds a paper-only historical backtest framework with CAGR, drawdown, Calmar, Sharpe, win rate, holding-time, turnover, and per-symbol contribution metrics.

## When to Use

Use this Skill when the user asks for:

- Binance USDS-M futures market-data decisions;
- real-time or scheduled paper trading checks;
- trend-following entries/holds/exits using >=1h K-lines;
- a safe baseline before adding live execution.

Do not use this for:

- spot trading order placement;
- paid market-data APIs;
- 1m/5m/10m/15m/30m signals;
- signed live trading until a separate risk/execution Skill is created and tested.

## Script

Primary script:

```bash
scripts/binance_usds_futures_trend.py --symbol BTCUSDT --interval 1h --limit 240
```

Batch scan the configured universe:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --interval 1h --limit 240 --context-limit 30 --top 5
```

Batch scan selected symbols:

```bash
scripts/binance_usds_futures_trend.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --top 3
```

Multi-timeframe batch scan:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5
```

Multi-timeframe scan with portfolio paper risk allocation:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1
```

Multi-timeframe scan with v0.7 paper state persistence:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json
```

State-change dry run without writing:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json --no-save-state
```

Telegram briefing output for scheduled Hermes cron delivery:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json --telegram-brief
```

Historical backtest for selected symbols:

```bash
scripts/binance_usds_futures_trend.py --backtest --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 500
```

Historical backtest for the full configured universe:

```bash
scripts/binance_usds_futures_trend.py --backtest --all-symbols --interval 4h --limit 500
```

Output is JSON by default:

- `ok`: whether the run succeeded;
- `decision.mode`: always `paper` in this version;
- `decision.action`: `hold_long` or `flat`;
- `generated_at_utc`: ISO timestamp in UTC;
- `generated_at_beijing`: ISO timestamp in Beijing time (UTC+8);
- `ema50`, `ema200`, `atr14`: trend/risk indicators;
- `confidence_score`: v0.2 public-factor confidence multiplier;
- `factor_flags`: diagnostic flags from mark trend, funding, open interest, long/short, and taker flow;
- `market_context`: fetched free public USDS-M context factors;
- `take_profit_1`, `take_profit_2`: ATR tranche harvesting references;
- `trailing_stop`: ATR trailing stop reference.

In v0.3 batch mode, output is `scan` JSON:

- `scan.mode`: always `paper`;
- `scan.results`: all symbols sorted by `rank_score`;
- `scan.top_trends`: strongest hold-long candidates;
- `scan.risk_high_trends`: symbols still in trend but with crowding, contraction, extension, or low-confidence flags;
- `scan.watchlist`: flat/error symbols to observe but not allocate to;
- `scan.summary_zh`: concise Chinese report with UTC and 北京时间（UTC+8） labels.

In v0.4 multi-timeframe mode, `scan` additionally includes:

- `scan.intervals`: interval list for batch scans, e.g. `1h,4h,1d`;
- `scan.primary_interval`: first interval in the list;
- `timeframe_signals`: per-interval decision summaries on each result;
- `timeframe_agreement_score`: how many intervals agree with the primary trend;
- `higher_timeframe_confirmed`: whether all higher intervals support the primary hold-long trend;
- `strong_confirmed_trends`, `early_trends`, and `conflicting_trends` groups.

In v0.5+ portfolio allocation mode, `scan` additionally includes:

- `portfolio_allocation.mode`: always `paper`;
- `portfolio_allocation.total_risk_budget`: total paper risk-unit budget;
- `portfolio_allocation.max_symbol_risk`: per-symbol paper risk-unit cap;
- `portfolio_allocation.allocations`: ranked paper allocations by symbol;
- `portfolio_allocation.total_allocated_risk` and `unallocated_risk`;
- `portfolio_allocation.skipped_symbols`: symbols not eligible or not reached by remaining budget.

In v0.6 allocation explainability mode, `portfolio_allocation` additionally includes:

- `allocations[].constraints_applied`: constraints applied to each paper allocation, such as `max_symbol_risk_cap`, `remaining_budget_cap`, or `full_position_size`;
- `allocations[].allocation_explanation`: compact human-readable paper-only allocation explanation;
- `skipped_details[]`: structured skip reasons for symbols that were flat, non-positive, or excluded by exhausted budget;
- `summary_zh` includes a compact `分配说明` line for the first 3 allocations.

In v0.7 paper state persistence mode, enabled by `--state-file`, `scan` additionally includes:

- `paper_state`: compact paper-only snapshot with timestamps, intervals, top trends, portfolio allocation, skipped details, `errors_count`, allocations by symbol, and per-symbol rank/action/bucket diagnostics;
- `state_change`: comparison between the previous state file and the current scan, including `first_run`, `added_allocations`, `removed_allocations`, `changed_allocations`, `ranking_changes`, `action_changes`, `bucket_changes`, and optional `state_file_error` for corrupted/unreadable state files;
- state files are written atomically when enabled, and `--no-save-state` computes changes without writing.

In v0.8 Telegram briefing mode, enabled by `--telegram-brief` in scan mode, stdout is compact text instead of JSON and includes:

- `paper only` title and safety line;
- UTC and 北京时间（UTC+8） timestamps;
- intervals, universe count, Top trends, and portfolio allocation;
- state-change summary: added, removed, changed paper allocations plus rank/action/bucket change counts;
- risk notes with risk-high/conflicting symbols and `errors_count`;
- no raw full JSON or endpoint error bodies.

In v0.9 historical backtest mode, enabled by `--backtest`, output is `backtest` JSON and includes:

- `backtest.mode`: always `paper`;
- UTC and 北京时间（UTC+8） timestamps;
- `metrics`: `cagr`, `max_drawdown`, `calmar`, `sharpe`, `win_rate`, `average_holding_candles`, `turnover`, `total_return`, `initial_equity`, and `final_equity`;
- `per_symbol_contribution`: total-return contribution by symbol;
- multi-symbol metrics are computed from a common-`close_time` aligned combined portfolio equity curve rather than averaging per-symbol CAGR/Sharpe;
- `errors_count` and `errors`: explicit free-data/backtest error summary;
- `symbol_results`: per-symbol paper backtest details, including trades and equity curve;
- `summary_zh`: compact Chinese paper-only summary; never report backtest results as live returns.

## Decision Logic v0.9

1. Validate symbol is in the configured trade universe.
2. Validate interval is >=1h; reject `1m`, `3m`, `5m`, `10m`, `15m`, `30m`.
3. Fetch free public K-lines from:

```text
https://fapi.binance.com/fapi/v1/klines
```

4. Optionally fetch v0.2 public context factors from free Binance USDS-M endpoints:

```text
/fapi/v1/markPriceKlines
/fapi/v1/fundingRate
/futures/data/openInterestHist
/futures/data/globalLongShortAccountRatio
/futures/data/takerlongshortRatio
```

5. Require at least 200 K-line candles.
6. Compute:
   - EMA50;
   - EMA200;
   - ATR14.
7. Main trend filter:
   - `close > EMA200`;
   - `EMA50 > EMA200`.
8. If the filter passes:
   - action: `hold_long`;
   - take-profit 1: close + 2 * ATR14;
   - take-profit 2: close + 4 * ATR14;
   - trailing stop: close - 3 * ATR14;
   - if price is extended > 4 ATR above EMA50, reduce paper size to 0.5 risk unit, not full exit;
   - v0.2 context factors adjust `confidence_score` / `position_size`, not the trend participation decision.
9. If the filter fails:
   - action: `flat`;
   - size: 0.
10. In batch mode, scan all selected symbols and add ranking fields:
   - `trend_strength`: ATR-normalized major-trend strength;
   - `extension_atr`: ATR-normalized distance above EMA50;
   - `rank_score`: `trend_strength * confidence_score * position_size` (and multiplied by `timeframe_agreement_score` in multi-timeframe mode);
   - `ranking_bucket`: `top_trend`, `risk_high_trend`, `watchlist`, or `error`.
11. In multi-timeframe mode, evaluate each interval independently, use the first interval as primary, and add:
   - `timeframe_signals`;
   - `timeframe_agreement_score`;
   - `higher_timeframe_confirmed`;
   - `ranking_bucket`: `strong_confirmed_trend`, `early_trend`, `conflicting_trend`, `watchlist`, or `error`.
12. Input guardrails: every interval must be `>=1h`, `risk_unit` must be positive, and `top` must be `>= 1`.
13. In portfolio allocation mode, allocate paper risk units only to positive `hold_long` decisions by rank order, capped by `total_risk_budget`, `max_symbol_risk`, and each decision's existing `position_size`; never place live orders.
14. In allocation explainability mode, each allocated symbol records applied constraints and a paper-only explanation; skipped symbols retain `skipped_symbols` and add structured `skipped_details` reasons such as `not_hold_long`, `non_positive_rank_score`, `non_positive_position_size`, and `no_remaining_budget`.
15. In paper state persistence mode, `--state-file` loads the previous paper snapshot if present, computes allocation/ranking/action/bucket changes, attaches `scan.state_change` and `scan.paper_state`, then atomically writes the current snapshot unless `--no-save-state` is set. Missing state files are treated as first run; corrupted JSON records `state_file_error` and is replaced by the current valid paper snapshot.
16. In Telegram briefing mode, `--telegram-brief` is scan-mode only and emits compact text for scheduled Hermes cron delivery, including UTC/北京时间（UTC+8）, top trends, allocation, state change, risk notes, `errors_count`, and a paper-only safety line without raw full JSON or secrets.
17. In historical backtest mode, `--backtest` fetches free K-lines, simulates paper-only long exposure from existing EMA/ATR decisions after each candle close, applies paper turnover fees, and reports performance metrics. It rejects `<1h` intervals and insufficient history; it does not use signed endpoints, live order fields, or paid APIs.

## Testing

Run:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
```

The test suite verifies:

- short intervals are rejected;
- >=1h intervals are accepted;
- short public-factor periods are rejected;
- synthetic strong uptrend produces `hold_long`;
- synthetic downtrend produces `flat`;
- v0.2 public context factors adjust confidence/size without forcing premature trend exits;
- v0.2 context fetch uses free Binance USDS-M endpoints;
- v0.3 batch scanning ranks multi-symbol trend candidates and builds a Chinese summary;
- v0.4 multi-timeframe scanning confirms primary trends against higher timeframes and rejects short intervals in interval lists;
- v0.5 portfolio allocation respects total budget, per-symbol cap, rank order, and invalid-constraint guardrails;
- v0.6 allocation explainability records applied constraints, allocation explanations, skipped details, and summary display;
- v0.7 paper state persistence covers first run, consecutive run changes, allocation add/remove/change, ranking/action/bucket changes, corrupted state files, and no-save dry runs;
- v0.8 Telegram briefing covers compact paper-only text output, state-change display, secret-safe omission of raw endpoint errors, scan-mode CLI output, and safe cron wrapper defaults;
- v0.9 historical backtest covers paper-only metric output, UTC / 北京时间（UTC+8） labels, `<1h` and insufficient-history rejection, multi-symbol aggregation, CLI JSON output, and omission of live/signed/order/secret fields;
- input guardrails reject non-positive `risk_unit` and `top < 1`.

## Verification Recipe

1. Run unit tests:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
```

2. Run one real free-data decision or full-universe scan:

```bash
scripts/binance_usds_futures_trend.py --symbol BTCUSDT --interval 1h --limit 240
scripts/binance_usds_futures_trend.py --all-symbols --interval 1h --limit 240 --context-limit 30 --top 5
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5 --portfolio-risk-budget 3 --max-symbol-risk 1 --state-file state/binance-usds-futures-trend-paper-state.json --telegram-brief
scripts/binance_usds_futures_trend.py --backtest --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 500
scripts/binance_usds_futures_trend_brief.sh
```

3. Confirm:

- JSON parses;
- `mode` is `paper`;
- timestamps include both UTC and Beijing time (UTC+8);
- interval is not below 1h;
- portfolio allocation, when enabled, does not exceed total budget or per-symbol cap;
- allocation explainability includes `constraints_applied`, `allocation_explanation`, and `skipped_details`;
- if `--state-file` is used, output includes `paper_state` and `state_change`, and true runtime state goes under ignored `state/*.json` rather than tracked files;
- if `--telegram-brief` is used, stdout is compact text with UTC / 北京时间（UTC+8）、`paper only`, allocation, state-change summary, risk notes, and no raw full JSON;
- if `--backtest` is used, output includes `backtest.mode=paper`, UTC / 北京时间（UTC+8）, CAGR/drawdown/Calmar/Sharpe/win-rate/holding/turnover/per-symbol metrics, `errors_count`, and no live/signed/order fields;
- tracked cron config does not include origin-specific Telegram chat IDs/names, while `cronjob list` still reports a valid scheduled job;
- `cron/output/` and editor swap files are ignored so manual-run artifacts do not enter commits;
- no API key or paid API is required.

## Common Pitfalls

1. **Installing unrelated Binance skills blindly.** Some public Binance skills are spot-only or on-chain/web3 focused. For this project, prefer USDS-M futures and free K-line data.
2. **Using short intervals or duplicate intervals.** The user explicitly disallows short periods below 1h; reject them in code and tests. Also reject duplicate `--intervals` entries because `timeframe_signals` is keyed by interval and duplicates would silently collapse.
3. **Ambiguous primary interval ordering.** In `--intervals`, the first interval is the primary interval. Document or enforce this when extending the scanner; if future logic relies on "higher timeframe" semantics, consider validating that later intervals are not lower than the primary interval.
4. **Confusing paper decisions with execution.** This Skill does not place orders. Live trading needs a separate signed-execution workflow, risk cap, kill switch, and testnet-first validation.
5. **Over-exiting trends.** The baseline reduces size when extended but does not flip to flat while the major trend filter remains valid.
6. **Omitting timezone labels.** Any run output or report must include UTC or Beijing time (UTC+8) labels.
7. **Breaking portfolio-output compatibility while adding explainability.** When adding richer allocation diagnostics, keep simple legacy fields such as `skipped_symbols` and add structured detail alongside them (for example `skipped_details`) rather than replacing them; update tests to prove both compatibility and the new explanations.
8. **Accidentally committing runtime state or overwriting repo ignore policy.** Real state files should live under ignored `state/*.json`; tests should use temporary directories, and only plan/reference/example docs should be tracked. This repo's `.gitignore` uses a broad default-deny plus allowlist policy, so never replace it wholesale when adding runtime ignore rules.
9. **Letting scheduled briefing drift into raw JSON spam or secret leakage.** Use `--telegram-brief` / `scripts/binance_usds_futures_trend_brief.sh` for Telegram delivery; do not paste `.env` values, API keys, or raw full scan JSON into chat unless explicitly debugging a redacted fixture.
10. **Committing cron delivery internals.** Hermes cron `jobs.json` may include runtime/delivery metadata after manual runs. Before committing scheduled trading jobs, prefer `deliver: "telegram"` (home channel) over persisted origin-specific chat IDs, scrub `origin.chat_id` / chat names from tracked config when safe, ignore `cron/output/` and swap files, then verify `cronjob list` still reads the job.
11. **Skipping the user's push gate.** For this repo, any push must be preceded by an independent agent review of the staged diff. Treat non-empty security or logic findings as blocking, revise, rerun verification, and re-review before pushing.
12. **Overstating backtest results.** v0.9 backtests are paper-only historical simulations. Report them as framework/diagnostic output, not live returns or proof that CAGR targets are achieved. Strategy refinement belongs to v1.0 and must compare before/after evidence.

## References

- `references/binance-skills-hub-usds-futures.md` — condensed notes from the fetched Binance Skills Hub repo for USDⓈ-M Futures public/auth endpoints used by this skill.
- `references/session-v0.2-public-factors-workflow.md` — workflow note for expanding free Binance public factors while preserving the primary trend-following contract.
- `references/session-v0.3-batch-scanner-workflow.md` — workflow note for adding multi-symbol batch scanning, ranking, guardrails, and verification.
- `references/session-v0.4-multi-timeframe-workflow.md` — workflow note for adding multi-timeframe confirmation and grouping.
- `references/session-v0.5-portfolio-risk-workflow.md` — workflow note for adding portfolio-level paper risk allocation.
- `references/session-v0.6-allocation-explainability-workflow.md` — workflow note for adding allocation and skip explanations.
- `references/session-v0.7-paper-state-persistence-workflow.md` — workflow note for adding paper state snapshots and state-change reporting.
- `references/session-v0.8-scheduled-telegram-briefing-workflow.md` — workflow note for scheduled scanner delivery and Telegram briefing output.
- `references/session-v0.9-historical-backtest-workflow.md` — workflow note for the paper-only historical backtest framework and verification.
- `plans/binance-usds-futures-trend-v0.3.md` — v0.3 batch scan and ranking implementation plan.
- `plans/binance-usds-futures-trend-v0.4.md` — v0.4 multi-timeframe confirmation implementation plan.
- `plans/binance-usds-futures-trend-v0.5.md` — v0.5 portfolio paper risk allocation implementation plan.
- `plans/binance-usds-futures-trend-v0.6.md` — v0.6 allocation explainability implementation plan.
- `plans/binance-usds-futures-trend-v0.7.md` — v0.7 paper state persistence implementation plan.
- `plans/binance-usds-futures-trend-v0.8.md` — v0.8 scheduled scan and Telegram briefing implementation plan.
- `plans/binance-usds-futures-trend-v0.9.md` — v0.9 historical backtest framework implementation plan.

## Roadmap

Canonical tracked roadmap: `plans/binance-usds-futures-roadmap.md`.

Default sequence unless the user explicitly reprioritizes:

1. v1.0 evidence-based strategy refinement, including higher-timeframe scoring and additional free public factors.
2. v1.1 paper trading lifecycle.
3. v2.0 separate Binance testnet execution Skill only after long paper validation.

## Verification Checklist

- [ ] Tests pass.
- [ ] Real free Binance Futures K-line decision runs or blocker is reported honestly.
- [ ] Output is paper-only.
- [ ] Interval is >=1h.
- [ ] UTC and Beijing time (UTC+8) are both present.
- [ ] No paid API or API key is required.
