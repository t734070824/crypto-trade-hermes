# Trading Chain CAGR Optimization Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Improve the current Binance USDS-M futures trading chain so it better supports the CAGR target while matching the desired long-hold / trend-participation style.

**Architecture:**
Keep the existing shared paper/testnet trading loop as the operational core. Live/mainnet execution remains unimplemented and unauthorized; any future live adapter would require a separate explicit approval path, stricter gates, and new review. Upgrade the current paper/testnet flow from a basic signal → intent → delta execution path into a stronger trend-holding engine. The main improvements should come from better regime detection, better sizing and pyramiding, more disciplined lifecycle management, stronger execution reconciliation, and a tighter evidence loop driven by runtime records.

**Tech Stack:**
Python 3.11, current `scripts/binance_trend_core/*` modules, Binance public data endpoints, Binance Futures Testnet adapter, unittest, runtime JSONL evidence, cron jobs.

---

## Current chain, in one sentence

Current flow is roughly:
`public K-lines -> signal engine -> trend intent -> risk approval -> execution planning -> broker submit/reconcile -> runtime evidence`.

That is good for correctness, but still too simple for a CAGR-focused trend holder because:

- sizing is still mostly threshold-driven and not fully regime-aware;
- add-on logic is not strong enough to scale into persistent trends;
- exits can still be too mechanical relative to the "hold main trend, harvest in tranches" preference;
- execution/reconciliation is conservative, but not yet optimized for repeated long-run capital efficiency;
- there is not yet a complete feedback loop that turns runtime evidence into strategy upgrades.

---

## Priority order

1. **Fix portfolio sizing to be regime-aware and compounding-friendly.**
2. **Make lifecycle management explicitly support hold / add / trim / trail behavior.**
3. **Improve execution reconciliation so delta sizing is precise and not overly timid.**
4. **Add better regime filters and multi-timeframe persistence signals.**
5. **Use runtime evidence to promote only improvements that survive replay and testnet.**
6. **Tighten observability and ops so the strategy can run unattended with less manual intervention.**

---

## Plan

### Task 1: Measure current bottlenecks before changing logic

**Objective:** Identify which part of the chain is limiting CAGR most: signal quality, sizing, lifecycle exits, or execution friction.

**Files:**
- Read: `scripts/binance_trend_core/loop.py`
- Read: `scripts/binance_trend_core/strategy.py`
- Read: `scripts/binance_trend_core/risk.py`
- Read: `scripts/binance_trend_core/execution.py`
- Read: `scripts/binance_trend_core/runtime.py`
- Read: `scripts/binance_trend_core/evolution.py`
- Read: `cron/output/f7201d6c1c57/*.md`
- Read: `state/binance-usds-futures-trend-testnet-runtime.jsonl`
- Read: `state/binance-usds-futures-trend-testnet-orders.jsonl`

**What to extract:**
- how often signals produce `hold_long` vs `flat`;
- how often desired exposure is below current exposure, causing no add;
- how often increments are blocked by min quantity / step size / notional;
- how often protective orders exist, are duplicated, or fail-closed;
- how often runtime evidence shows repeated no-op cycles.

**Deliverable:**
A short baseline note with 3–5 primary bottlenecks and evidence counts.

**Verification:**
- Use recent runtime JSONL and cron outputs only.
- Do not infer from intuition when data is available.

---

### Task 2: Redesign sizing around account risk, trend strength, and headroom

**Objective:** Make position sizing support compounding during strong trends instead of only producing a fixed or near-fixed target.

**Files likely to change:**
- `scripts/binance_trend_core/risk.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/execution.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- base risk on account equity and risk fraction;
- scale size by trend strength / confidence / regime quality;
- introduce explicit headroom for add-ons when the trend is healthy;
- cap by symbol exposure, total portfolio risk, daily loss, and exchange limits;
- allow larger target exposure only when the market has proven persistence.

**Implementation idea:**
- keep the current `desired_exposure` abstraction;
- add a sizing component that computes:
  - base size,
  - add-on capacity,
  - max total target exposure,
  - minimum meaningful delta.

**Tests:**
- strong trend with good headroom should produce larger target size than weak trend;
- repeated cycles should not increase size indefinitely;
- if equity drops or daily loss grows, target exposure should shrink.

**Verification:**
- unit tests for sizing outputs;
- one dry-run paper cycle;
- one dry-run testnet cycle.

---

### Task 3: Turn lifecycle into explicit entry / add / hold / trim / exit policy

**Objective:** Make the engine behave like a trend holder instead of a one-shot entry/exit scanner.

**Files likely to change:**
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/portfolio.py`
- `scripts/binance_trend_core/execution.py`
- `scripts/binance_trend_core/loop.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- `hold_long` should mean "stay in the trend while conditions remain valid";
- `add` should happen only when:
  - trend remains healthy,
  - current exposure is below target,
  - increment is meaningful after fees and exchange constraints;
- `trim` should happen on weakening momentum or excessive extension, not only on full invalidation;
- `exit` should be reserved for actual trend failure or risk stop.

**Implementation idea:**
- extend lifecycle state to track:
  - entry price,
  - current tranche count,
  - last add timestamp,
  - last trim timestamp,
  - trailing stop level,
  - next add threshold;
- add rules for "do not re-enter too fast" and "do not trim too aggressively".

**Tests:**
- add-on should fire only when current exposure < target exposure;
- trim should not wipe the full position unless trend breaks;
- flat/exit only when major trend invalidates or risk trips.

**Verification:**
- lifecycle state diff tests;
- paper cycle with persistent trend;
- confirm add/hold/trim behavior in runtime record.

---

### Task 4: Upgrade execution from simple delta reconciliation to smarter delta + protection reconciliation

**Objective:** Improve capital efficiency and reduce wasted no-op cycles while keeping fail-closed safety.

**Files likely to change:**
- `scripts/binance_trend_core/execution.py`
- `scripts/binance_trend_core/brokers.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- keep delta-only reconciliation for core position management;
- but distinguish:
  - pure add delta,
  - pure reduce delta,
  - protection refresh,
  - duplicate-protection suppression;
- avoid repeatedly submitting tiny increments that fail exchange filters;
- preserve fail-closed protective orders on testnet-like adapter paths; live/mainnet remains out of scope.

**Implementation idea:**
- add a minimum effective delta after rounding to step size and notional;
- suppress repeated protection submissions when the exchange state is already sufficient;
- log why an add was skipped: below threshold, already at target, protection already present, or exchange limits.

**Tests:**
- delta below minimum should be skipped with an explicit reason;
- protection orders should be recognized and not duplicated unnecessarily;
- target equal to current exposure should produce no position order.

**Verification:**
- testnet dry-run should show fewer unnecessary orders;
- open-algo reconciliation should remain fail-closed.

---

### Task 5: Improve regime detection so the engine stays in trends longer

**Objective:** Reduce premature exits and avoid entering weak or noisy regimes.

**Files likely to change:**
- `scripts/binance_trend_core/signals.py`
- `scripts/binance_trend_core/strategy.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- keep the current EMA/ATR base,
- add regime features such as:
  - trend persistence / slope,
  - volatility compression then expansion,
  - distance from EMA200 normalized by ATR,
  - multi-timeframe agreement score,
  - context confirmation from funding / OI / long-short imbalance.
- use regime score to decide whether to:
  - hold aggressively,
  - hold but reduce size,
  - add,
  - wait.

**Implementation idea:**
- convert a binary signal into a graded regime score;
- use the score in sizing and lifecycle decisions;
- keep the existing long-trend core intact so logic remains understandable.

**Tests:**
- strong aligned multi-timeframe trend should score higher than weak or conflicting trend;
- extension alone should not cause forced exit;
- weak/noisy regime should suppress adds.

**Verification:**
- compare baseline vs candidate on the same candle set;
- inspect runtime replay results for fewer false exits.

---

### Task 6: Build a compounding policy for pyramid entries and partial harvesting

**Objective:** Make the strategy fit the desired "持续参与主趋势、持续持有、持续收割" style.

**Files likely to change:**
- `scripts/binance_trend_core/portfolio.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/execution.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**
- define a maximum tranche count per symbol;
- define add levels based on ATR or volatility bands;
- define trim levels that harvest part of gains without abandoning the trend;
- define a trailing stop that rises with the market instead of sitting too tight.

**Implementation idea:**
- add explicit tranche state:
  - first entry,
  - add 1,
  - add 2,
  - harvest 1,
  - harvest 2;
- keep the last tranche on until trend failure or hard risk stop.

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
- add time-based de-risking only when the regime weakens, not on arbitrary timers.

**Implementation idea:**
- track symbol clustering and portfolio heat;
- reject new adds when concentration is too high;
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
  - fewer premature exits,
  - better trend participation duration,
  - fewer no-op orders,
  - better realized vs unrealized capture,
  - lower protective-order friction.

**Implementation idea:**
- define promotion metrics around trend capture and hold quality, not only raw win rate;
- add a simple scorecard for candidate comparison.

**Tests:**
- replay must use identical captured inputs;
- candidate scoring must be deterministic;
- no fresh market data should leak into replay.

**Verification:**
- one controlled runtime evidence replay per candidate;
- choose only the candidate that improves hold quality and risk-adjusted outcome.

---

### Task 9: Tighten observability and cron behavior for unattended operation

**Objective:** Make it easier to tell whether the strategy is doing the right thing over days, not just one cycle.

**Files likely to change:**
- `scripts/binance_usds_futures_trend_brief.sh`
- `scripts/binance_usds_futures_trend.py`
- `cron/jobs.json`

**Proposed behavior:**
- summarize:
  - current exposure,
  - target exposure,
  - add/trim/hold reason,
  - protection status,
  - runtime errors,
  - whether the cycle helped compounding;
- keep reports compact and actionable;
- distinguish "correct no-op" from "failed to add because of an issue".

**Verification:**
- cron output should show why the engine held, added, or trimmed;
- no raw signed payloads or secrets in output.

---

### Task 10: Validation and rollout sequence

**Objective:** Introduce changes in a safe order.

**Rollout order:**
1. unit tests for sizing/lifecycle/execution rules;
2. paper dry-run validation on selected symbols;
3. paper multi-symbol validation;
4. testnet dry-run validation;
5. testnet signed cycle only if explicitly required and safe;
6. compare runtime evidence before and after;
7. only then consider continuing or expanding testnet scope; live/mainnet remains out of scope unless separately authorized.

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
2. sizing model upgrade;
3. lifecycle add/trim/hold rules;
4. execution delta refinement;
5. replay comparison;
6. paper and testnet dry-run validation.

That gives the biggest chance of improving CAGR without breaking the current shared trading chain.
