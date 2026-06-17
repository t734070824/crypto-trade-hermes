# Trading Chain CAGR Optimization Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Improve the current Binance USDS-M futures trading chain so it better supports the CAGR target while matching the desired long-hold / trend-participation style.

**Architecture:**
Keep the existing shared paper/testnet trading loop as the operational core. Live/mainnet execution remains unimplemented and unauthorized; any future live adapter would require a separate explicit approval path, stricter gates, and new review. The current chain is already stronger than a basic scanner: it has free K-line ingestion, signal generation, account-risk sizing, target-total exposure semantics, delta-only execution, protective-order reconciliation, runtime/order journals, and a script-owned testnet hot path. The next step is not to replace this chain, but to make it more regime-aware, more compounding-friendly, and better evidenced by real runtime results.

**Tech Stack:**
Python 3.11, current `scripts/binance_trend_core/*` modules, Binance public data endpoints, Binance Futures Testnet adapter, unittest, runtime JSONL evidence, cron jobs.

---

## Current chain, in one sentence

Current flow is roughly:
`public K-lines >=1h -> signal engine -> account-risk sizing -> target-total intent -> risk approval -> delta-only execution + protection reconciliation -> broker submit/reconcile -> runtime evidence -> daily replay analysis`.

This is already suitable for correctness, but still needs improvement for CAGR because:

- regime quality is not yet first-class in sizing and lifecycle decisions;
- add-on / harvest / trim behavior is not yet explicit enough for persistent trends;
- the current evidence loop still relies too much on proxy metrics and not enough on real testnet lifecycle and fill evidence;
- hourly hot-path execution and daily replay analysis are already separated, but the plan should reflect that separation more explicitly;
- the strategy still needs better compounding discipline so it can hold winners longer without turning every cycle into a full reset.

---

## Priority order

1. **Measure current bottlenecks from runtime/order-journal evidence before changing logic.**
2. **Add regime / persistence / trend-quality scoring as a first-class input.**
3. **Upgrade the existing account-risk sizing to be regime-aware and compounding-aware.**
4. **Make lifecycle management explicitly support entry / add / hold / trim / harvest / exit.**
5. **Refine delta-only execution so it handles minimum effective deltas and protection reconciliation cleanly.**
6. **Use runtime evidence, including real testnet lifecycle data, as the promotion gate.**
7. **Tighten observability and cron boundaries so the hot path stays deterministic and the analyzer stays read-only.**

---

## Plan

### Task 1: Measure current bottlenecks before changing logic

**Objective:** Identify what is currently limiting CAGR most: signal quality, regime filtering, sizing, lifecycle exits, protection friction, or no-op cycles.

**Files:**
- `scripts/binance_trend_core/loop.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/risk.py`
- `scripts/binance_trend_core/execution.py`
- `scripts/binance_trend_core/runtime.py`
- `scripts/binance_trend_core/evolution.py`
- `scripts/binance_usds_futures_trend.py`
- `scripts/binance_usds_futures_testnet_hourly.py`
- `state/binance-usds-futures-trend-testnet-runtime.jsonl`
- `state/binance-usds-futures-trend-testnet-orders.jsonl`
- `cron/output/f7201d6c1c57/*.md`

**What to extract:**
- how often signals produce `hold_long` vs `flat`;
- how often target exposure is above current exposure vs equal vs below;
- how often sizing is constrained by stop distance, margin, max order notional, max symbol exposure, or symbol exposure fraction;
- how often execution is skipped because delta is below the effective minimum after rounding or exchange rules;
- how often protection orders are already sufficient vs repaired vs duplicated;
- how often runtime evidence shows repeated no-op cycles or `correct no-op` cycles;
- how often real testnet fills, lifecycle tracking, fees, and slippage are actually observed.

**Deliverable:**
A short baseline note with 3–5 primary bottlenecks and evidence counts.

**Verification:**
- Use recent runtime JSONL, order journal, and cron outputs only.
- Do not infer from intuition when data is available.

---

### Task 2: Add regime / persistence / trend-quality scoring

**Objective:** Turn the current binary long-trend decision into a graded regime score that can drive sizing, adds, trims, and hold persistence.

**Files likely to change:**
- `scripts/binance_trend_core/signals.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/evolution.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- keep the current EMA/ATR core;
- add features such as:
  - trend persistence / slope;
  - normalized distance from EMA200 by ATR;
  - volatility compression then expansion;
  - multi-timeframe agreement score;
  - public context confirmation from funding / OI / long-short imbalance;
  - extension penalty only when trend is too stretched, not as an automatic exit trigger.
- convert the binary trend decision into a graded regime score;
- keep `hold_long` as the long-trend participation signal, but attach a `regime_score` or equivalent quality metric;
- make the score explicit enough to reuse in sizing and lifecycle rules.

**Tests:**
- strong aligned multi-timeframe trend should score higher than weak or conflicting trend;
- extension alone should not force exit;
- weak/noisy regime should reduce add aggression;
- regime score should be deterministic on identical input candles.

**Verification:**
- compare baseline vs candidate on the same candle set;
- inspect runtime replay results for fewer premature exits.

---

### Task 3: Upgrade existing account-risk sizing to be regime-aware and compounding-aware

**Objective:** Keep the current account-risk sizing model, but make it scale with regime quality and trend persistence so the engine can compound into strong trends instead of capping itself too early.

**Files likely to change:**
- `scripts/binance_usds_futures_trend.py`
- `scripts/binance_trend_core/risk.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/execution.py`
- `tests/test_binance_usds_futures_trend.py`

**Current reality:**
The project already has `apply_account_risk_sizing_to_signal()` and it already sizes from account equity / available balance / stop distance / leverage cap / max order notional / max symbol exposure / max symbol exposure fraction. So this task is **not** “add account-risk sizing from scratch.” It is “make the existing sizing regime-aware and compounding-aware.”

**Proposed behavior:**
- keep the current target-total `position_size` abstraction;
- scale base size by regime quality and persistence;
- reserve explicit headroom for future adds when trend quality remains strong;
- reduce size when equity falls, daily loss rises, or regime quality weakens;
- keep the hard caps: stop-distance risk budget, max order notional, max symbol exposure, max exposure fraction, and exchange minimums;
- ensure any scale-up still respects the current `position_size` meaning: target total exposure, not incremental add quantity.

**Tests:**
- strong regime should size larger than weak regime on the same account snapshot;
- repeated cycles should not increase size indefinitely;
- equity drawdown or regime decay should shrink target exposure;
- sizing should remain fail-closed on invalid stop distance or invalid account snapshot.

**Verification:**
- unit tests for sizing outputs;
- one dry-run paper cycle;
- one dry-run testnet cycle.

---

### Task 4: Make lifecycle management explicit: entry / add / hold / trim / harvest / exit

**Objective:** Make the engine behave like a trend holder that stays in the move, trims only when needed, and exits only when the trend actually fails or risk trips.

**Files likely to change:**
- `scripts/binance_trend_core/portfolio.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/execution.py`
- `scripts/binance_trend_core/loop.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- `hold_long` means stay in the trend while conditions remain valid;
- `add` only happens when:
  - trend remains healthy;
  - current exposure is below target total exposure;
  - the delta is meaningful after fees, rounding, and exchange constraints;
- `trim` or `harvest` happens on weakening momentum or excessive extension, not only on full invalidation;
- `exit` is reserved for true trend failure or hard risk stop;
- lifecycle state should track at least:
  - entry price;
  - current tranche count;
  - last add timestamp;
  - last trim timestamp;
  - trailing stop level;
  - next add threshold;
  - partial-harvest state.

**Important semantic rule:**
Strategy `position_size` remains the **desired total exposure**. The execution layer must always reconcile `desired_exposure - current_exposure`, not blindly add the full target again.

**Tests:**
- add-on should fire only when current exposure < target exposure;
- trim should not wipe the full position unless trend breaks;
- flat / exit only when major trend invalidates or risk trips;
- lifecycle state should preserve monotonic trailing-stop behavior.

**Verification:**
- lifecycle state diff tests;
- paper cycle with persistent trend;
- confirm add / hold / trim behavior in runtime record.

---

### Task 5: Refine delta-only execution and protection reconciliation

**Objective:** Improve capital efficiency and reduce wasted no-op cycles while keeping fail-closed safety.

**Files likely to change:**
- `scripts/binance_trend_core/execution.py`
- `scripts/binance_trend_core/brokers.py`
- `tests/test_binance_usds_futures_trend.py`

**Current reality:**
The execution path already does delta-only reconciliation and already handles protective orders, stale stop replacement, stale TP replacement, and order budget constraints. So this task is not “build reconciliation”; it is “make the existing reconciliation smarter and more observable.”

**Proposed behavior:**
- keep delta-only reconciliation for core position management;
- distinguish clearly between:
  - pure add delta;
  - pure reduce delta;
  - protection refresh;
  - duplicate-protection suppression;
  - below-minimum delta after rounding;
  - exchange-rule rejection;
  - risk-capped no-op;
  - already-at-target no-op;
- suppress repeated submission of tiny increments that fail exchange filters;
- preserve fail-closed protective orders on testnet-like adapter paths.

**Tests:**
- delta below minimum should be skipped with an explicit reason;
- protection orders should be recognized and not duplicated unnecessarily;
- target equal to current exposure should produce no position order;
- stale protection repair should not create a naked long position.

**Verification:**
- testnet dry-run should show fewer unnecessary orders;
- open-algo reconciliation should remain fail-closed.

---

### Task 6: Build a compounding policy for pyramiding and partial harvesting

**Objective:** Make the strategy fit the desired “持续参与主趋势、持续持有、持续收割” style.

**Files likely to change:**
- `scripts/binance_trend_core/portfolio.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/execution.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- define a maximum tranche count per symbol;
- define add levels based on ATR / volatility bands / regime score;
- define harvest levels that take partial gains without abandoning the trend;
- define a trailing stop that rises with the market instead of sitting too tight;
- let the last tranche ride until trend failure or hard risk stop.

**Implementation idea:**
- make tranche state explicit:
  - first entry,
  - add 1,
  - add 2,
  - harvest 1,
  - harvest 2;
- ensure harvest reduces size rather than forcing a full exit while the major trend is still valid;
- keep add rules compatible with current delta-only reconciliation and existing position semantics.

**Tests:**
- add-on levels must be monotonic and sensible;
- partial harvest should leave a residual position;
- trailing stop should never move backward.

**Verification:**
- simulate a long trending sequence and confirm the strategy stays involved;
- compare equity curve shape before/after.

---

### Task 7: Strengthen portfolio-level controls without killing compounding

**Objective:** Keep the engine safe enough for long-run survival while preserving upside participation.

**Files likely to change:**
- `scripts/binance_trend_core/risk.py`
- `scripts/binance_trend_core/portfolio.py`
- `scripts/binance_trend_core/loop.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- add portfolio correlation or concentration caps;
- cap total exposure per market regime;
- add cooldowns after losses or failed entries;
- add time-based de-risking only when the regime weakens, not on arbitrary timers;
- reduce only the weakest / most extended tranches first.

**Tests:**
- two highly concentrated positions should trigger a cap;
- daily loss limit should stop new adds;
- cooldown should prevent immediate revenge re-entry.

**Verification:**
- run portfolio-mode dry-run over multiple symbols;
- confirm no single symbol dominates risk unintentionally.

---

### Task 8: Use runtime evidence as the promotion gate

**Objective:** Only keep changes that improve actual recorded behavior, not just theory.

**Files likely to change:**
- `scripts/binance_trend_core/evolution.py`
- `scripts/binance_trend_core/runtime.py`
- `scripts/binance_usds_futures_trend.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- replay the same runtime evidence across candidate strategy versions;
- compare:
  - fewer premature exits;
  - better trend participation duration;
  - fewer no-op orders;
  - better realized vs unrealized capture;
  - lower protection-friction;
  - fewer skip reasons caused by exchange limits or order-budget pressure;
  - better net PnL after fees and slippage.

**Implementation idea:**
- define promotion metrics around trend capture and hold quality, not only raw win rate;
- incorporate real runtime artifacts, not only proxy returns:
  - runtime JSONL;
  - order journal;
  - lifecycle tracking;
  - lifecycle confirmations;
  - fees;
  - slippage;
  - rejected / skipped reasons;
  - actual order-count efficiency.

**Tests:**
- replay must use identical captured inputs;
- candidate scoring must be deterministic;
- no fresh market data should leak into replay.

**Verification:**
- one controlled runtime evidence replay per candidate;
- choose only the candidate that improves hold quality and risk-adjusted outcome.

---

### Task 9: Tighten observability and cron behavior for unattended operation

**Objective:** Make it easy to tell whether the strategy is doing the right thing over days, not just one cycle.

**Files likely to change:**
- `scripts/binance_usds_futures_testnet_hourly.py`
- `scripts/binance_usds_futures_testnet_hourly.sh`
- `scripts/binance_usds_futures_trend.py`
- `scripts/binance_usds_futures_trend_brief.sh`
- `cron/jobs.json` only if cron definitions themselves intentionally change

**Proposed behavior:**
- hourly hot path stays script-owned and deterministic (`no_agent=true`);
- the script, not prompt prose, is the operational contract for that job;
- daily replay diagnostics remain agent-owned and read-only;
- reports should summarize:
  - current exposure;
  - target exposure;
  - add / trim / hold reason;
  - protection status;
  - runtime errors;
  - whether the cycle helped compounding;
  - execution latency vs delivery latency when cron output is late.

**Important boundary:**
Do not treat prompt prose as execution logic. If a behavior must happen in the hourly hot path, it must be encoded in the script or trading-engine code path, not only described in the cron prompt.

**Verification:**
- cron output should show why the engine held, added, trimmed, or did nothing;
- no raw signed payloads or secrets in output;
- hot-path report and daily replay report remain separate concerns.

---

### Task 10: Validation and rollout sequence

**Objective:** Introduce changes in a safe order.

**Rollout order:**
1. baseline measurement from current runtime evidence;
2. regime / persistence score;
3. sizing upgrade on top of existing account-risk sizing;
4. lifecycle add / trim / hold / harvest rules;
5. execution delta refinement;
6. replay comparison using recorded runtime evidence;
7. paper and testnet dry-run validation;
8. signed testnet only if explicitly required and safe;
9. only then consider expanding scope; live/mainnet remains out of scope unless separately authorized.

**Baseline test commands:**
```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py
```

**Behavior validation commands:**
```bash
scripts/binance_usds_futures_trend.py --run-paper-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl --no-save-runtime-record
scripts/binance_usds_futures_trend.py --run-testnet-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl --no-save-runtime-record --testnet-dry-run
scripts/binance_usds_futures_trend.py --replay-runtime-evidence --runtime-record-file state/binance-usds-futures-trend-runtime.jsonl
```

---

## Risks / tradeoffs

- **More aggressive sizing can increase drawdown.**
  Mitigation: keep hard max loss, symbol cap, and concentration caps.

- **Better trend holding can delay exits.**
  Mitigation: use graded trims and hard invalidation rules.

- **More protective-order logic can increase complexity.**
  Mitigation: keep fail-closed protection handling simple and explicit.

- **Pyramiding can overfit to a small number of strong trends.**
  Mitigation: evaluate on multiple symbols and multiple market regimes.

- **Runtime evidence can mislead if replay inputs drift.**
  Mitigation: replay on identical captured data only.

---

## Suggested first implementation slice

If I were implementing next, I would do this order:

1. baseline measurement from current runtime evidence;
2. regime score;
3. sizing model upgrade on top of current account-risk sizing;
4. lifecycle add / trim / hold rules;
5. execution delta refinement;
6. replay comparison;
7. paper and testnet dry-run validation.

That gives the biggest chance of improving CAGR without breaking the current shared trading chain.
