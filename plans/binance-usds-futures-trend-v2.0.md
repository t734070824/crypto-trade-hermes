# Binance USDS-M Futures Trend v2.0 — Audit-Driven Recovery and Trading-Engine Hardening Plan

Created:

- UTC：2026-06-18 06:14:55 UTC
- 北京时间（UTC+8）：2026-06-18 14:14:55 UTC+8

Source audit:

- `skills/crypto-trading/binance-usds-futures-trend/references/session-v1.49-current-trading-flow-independent-audit.md`

> **For Hermes:** Use subagent-driven-development / independent-agent review for implementation. This plan is not authorization to run signed testnet cycles, place orders, cancel orders, resume cron, or touch live/mainnet.

## Goal

Turn the current post-audit state from **“dry-run evidence collection healthy, signed testnet protection degraded”** into a safe, evidence-driven trading engine path that can resume signed testnet only after protection health is proven, then continue toward the CAGR 30% target / CAGR 100% pursuit without weakening safety or architecture boundaries.

## Architecture

Keep the current shared trading chain:

`free Binance public data >=1h -> signal/strategy -> account-risk sizing -> target-total exposure -> delta-only execution + protection reconciliation -> broker adapter -> runtime/order evidence -> read-only analysis`

v2.0 is not a strategy-overhaul-first plan. It is a recovery and hardening plan:

1. First separate health domains and prevent false “all healthy” conclusions.
2. Then fix deterministic runner/config/documentation drift.
3. Then resolve signed testnet protection uncertainty using explicit signed read-only evidence and, only with user authorization, signed repair/resume.
4. Only after signed protection health is stable, implement CAGR-oriented lifecycle/risk improvements.

## Non-negotiable constraints

- Binance USDS-M futures only.
- No paid APIs.
- No intervals below `1h`.
- All time-related outputs must include both UTC and 北京时间（UTC+8）.
- Live/mainnet signed execution remains unimplemented and unauthorized.
- Signed testnet order placement, cancellation, cron resume, or manual run requires explicit current-turn user authorization.
- Short signed execution remains behind explicit `--allow-testnet-signed-short` and evidence review.
- Runtime and order evidence must remain isolated under testnet paths; do not commit `state/*.jsonl`, cron outputs, secrets, or signed payloads.
- `no_agent=true` hourly jobs execute script stdout only; prompt prose is not execution logic.
- Do not treat dry-run health as signed protection health.

## Current v1.49 baseline

### Healthy domains

- `testnet-dry-run-hourly` is healthy as dry-run evidence collection:
  - `no_agent=true`;
  - script-owned;
  - fixed dry-run wrapper;
  - recent successful outputs;
  - zero signed/attempted/real submissions;
  - testnet runtime evidence growing.

- Code architecture is mostly sound:
  - `--run-testnet-cycle` CLI default remains dry-run;
  - paper/testnet share `run_trading_cycle()`;
  - execution is target-total / delta-only;
  - `add_allowed=false` blocks expansion while allowing hold/reduce/protection repair;
  - open algo orders are considered in protection rows;
  - runtime evidence exists.

- Runner/analyzer split mostly exists:
  - hourly runner is script-owned no-agent;
  - daily analyzer is read-only agent-mode.

### Degraded / failing domains

- Last signed testnet evidence showed protection failure:
  - `BTCUSDT` and `ETHUSDT` reported unprotected;
  - multiple stop-loss orders were `submitted_unknown`;
  - signed hourly job is paused;
  - current dry-run skips signed preflight/postflight and cannot prove actual account/open-algo health.

- Operational drift exists:
  - live `cron/jobs.json` includes `testnet-dry-run-hourly`, but tracked `cron/jobs.template.json` does not;
  - hourly Python harness defaults to signed unless wrapper passes `--dry-run`;
  - harness docstring still describes old agent/no_agent=false semantics;
  - Skill time wording says UTC “or” 北京时间, weaker than current user preference for both.

- Architecture gaps remain:
  - live adapter is not implemented;
  - paper scanner entrypoints remain prominent;
  - portfolio-level risk manager is thin;
  - loop-level exception redaction can be stronger;
  - daily analyzer recency did not cover the latest signed failure.

## Health-domain model for all future reports

Every future audit, cron summary, or daily analyzer report should classify the system separately:

1. **Dry-run evidence collection**
   - schedule health;
   - output health;
   - runtime write health;
   - zero signed/attempted/real submissions.

2. **Signed execution/protection**
   - signed runner enabled/paused;
   - latest signed run time;
   - account positions;
   - ordinary open orders;
   - open algo orders;
   - protection completeness;
   - submitted_unknown / rejected / skipped counts;
   - lifecycle/fill evidence.

3. **Strategy/risk/lifecycle**
   - signal regime;
   - current vs desired exposure;
   - add_allowed / blockers;
   - sizing caps;
   - reduce/trim/add intent;
   - risk and exchange-rule skips.

4. **Operations/config/template consistency**
   - live cron vs tracked template;
   - no_agent/script semantics;
   - fixed CLI flags;
   - prompt vs execution logic boundary;
   - daily analyzer recency.

5. **Architecture/readiness**
   - shared engine boundary;
   - paper/testnet/live adapter status;
   - runtime evidence schema completeness;
   - tests and regression coverage.

A report may mark dry-run PASS while signed protection FAIL. This is required, not a contradiction.

## Phase 0 — Immediate safety boundary and evidence freeze

**Objective:** Prevent accidental signed activity while preserving the evidence needed to diagnose protection degradation.

**Files likely to change:**

- `skills/crypto-trading/binance-usds-futures-trend/SKILL.md`
- `plans/binance-usds-futures-trend-v2.0.md`
- possibly `references/session-v1.50-*.md` after implementation

**Actions:**

1. Keep `testnet-agent-hourly` paused until a separate explicit user authorization says otherwise.
2. Keep `testnet-dry-run-hourly` running only as dry-run evidence collection.
3. Do not run signed account snapshots, signed repairs, order cancellations, or cron resumes as part of documentation/planning turns.
4. Treat v1.49 artifacts as the baseline incident evidence:
   - last signed output path;
   - canonical runtime JSONL;
   - canonical order journal;
   - daily analyzer output recency.
5. Every future summary must say whether it is dry-run-only evidence or signed evidence.

**Acceptance:**

- No signed order/cancel/resume/manual-run occurred during the planning/documentation work.
- The plan explicitly says signed read-only snapshots require explicit authorization.

## Phase 1 — Documentation/config drift cleanup

**Objective:** Make the durable repo description match the live operational model so future agents do not misread the system.

**Files likely to change:**

- `cron/jobs.template.json`
- `scripts/binance_usds_futures_testnet_hourly.py`
- `skills/crypto-trading/binance-usds-futures-trend/SKILL.md`
- `plans/binance-usds-futures-roadmap.md`
- `tests/test_cron_trading_config.py`

**Tasks:**

1. Add sanitized `testnet-dry-run-hourly` to `cron/jobs.template.json`.
   - Include durable fields only: name, schedule, no_agent, script, skills/toolsets, deliver/workdir/profile if appropriate.
   - Exclude `next_run_at`, `last_run_at`, status/error, repeat counters, output paths, chat IDs, and other runtime fields.

2. Update `scripts/binance_usds_futures_testnet_hourly.py` docstring.
   - Remove old “agent cron / no_agent=false” wording.
   - State that the hourly harness is script-owned and may be invoked by signed or dry-run wrappers.
   - State that current dry-run wrapper is the active evidence collector.

3. Fix the Skill time wording.
   - Replace “UTC or 北京时间（UTC+8）” with “UTC and 北京时间（UTC+8）” for time-related outputs.

4. Repair any reference/pitfall numbering drift in `SKILL.md`.

5. Add tests or update existing tests so `testnet-dry-run-hourly` template coverage is explicit.

**Verification:**

```bash
python3 -m pytest -q tests/test_cron_trading_config.py tests/test_binance_usds_futures_testnet_hourly.py
python3 -m py_compile scripts/binance_usds_futures_testnet_hourly.py
git diff --check
```

**Acceptance:**

- Live-vs-template drift is eliminated without committing scheduler runtime fields.
- Documentation no longer claims the hourly job is agent-mode.
- Time output requirement is “both UTC and 北京时间（UTC+8）”.

## Phase 2 — Make hourly harness dry-run by default

**Objective:** Remove the current footgun where the Python hourly harness defaults to signed submission unless wrapped with `--dry-run`.

**Files likely to change:**

- `scripts/binance_usds_futures_testnet_hourly.py`
- `scripts/binance_usds_futures_testnet_hourly.sh`
- `scripts/binance_usds_futures_testnet_hourly_dry_run.sh`
- `tests/test_binance_usds_futures_testnet_hourly.py`
- `tests/test_cron_trading_config.py`

**Proposed behavior:**

- `scripts/binance_usds_futures_testnet_hourly.py` defaults to dry-run.
- Signed behavior requires an explicit flag, e.g. `--submit-signed-testnet`, or an equally explicit existing flag that is not default.
- The signed shell wrapper should pass the explicit signed flag.
- The dry-run shell wrapper should remain explicit and harmless.
- All summaries should include the effective mode and whether signed preflight/postflight ran or were skipped.

**Tests:**

- Running argument parser with no mode flag produces dry-run behavior.
- Dry-run wrapper appends `--testnet-dry-run` to child cycle calls.
- Signed wrapper or explicit signed flag appends `--testnet-submit-signed` only when explicitly requested.
- Dry-run mode never runs signed preflight/postflight.
- Signed mode still requires exact testnet hostname and credentials present, but tests must mock this path.

**Verification:**

```bash
python3 -m pytest -q tests/test_binance_usds_futures_testnet_hourly.py tests/test_cron_trading_config.py
python3 -m py_compile scripts/binance_usds_futures_testnet_hourly.py
git diff --check
```

**Acceptance:**

- The core CLI and the hourly harness both default to dry-run.
- Signed submission can no longer happen by simply forgetting `--dry-run`.

## Phase 3 — Signed read-only protection snapshot command

**Objective:** Provide a safe, explicit, signed read-only path to verify actual testnet positions and open algo protection without placing or canceling orders.

**Files likely to change:**

- `scripts/binance_usds_futures_trend.py`
- `scripts/binance_trend_core/brokers.py`
- `scripts/binance_trend_core/runtime.py`
- `scripts/binance_usds_futures_testnet_hourly.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**

Add or formalize a read-only snapshot mode that:

- requires explicit signed read-only authorization flag;
- uses only testnet base URL;
- calls account/position/open-order/open-algo read endpoints;
- writes no orders and cancels nothing;
- emits a compact JSON/Chinese summary with:
  - positions by symbol;
  - ordinary open orders;
  - open algo orders;
  - protection completeness;
  - orphan protection;
  - duplicate protection;
  - stale trigger prices;
  - submitted_unknown reconciliation hints by `clientOrderId` / `clientAlgoId` when possible;
  - UTC and 北京时间（UTC+8）.

**Important boundary:**

This phase creates the code path and tests. Running it against real signed testnet credentials still requires explicit current-turn user authorization.

**Tests:**

- Snapshot rejects mainnet hostname.
- Snapshot never calls order submit/cancel endpoints.
- Missing SL/TP is reported as fail-closed protection issue.
- Existing open algo SL/TP protects long and short correctly.
- Raw signatures/API keys are redacted from errors.

**Verification:**

```bash
python3 -m pytest -q tests/test_binance_usds_futures_trend.py
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py
git diff --check
```

**Acceptance:**

- A user can later authorize a signed read-only snapshot without authorizing order placement.
- The snapshot can answer whether `BTCUSDT` / `ETHUSDT` are still unprotected.

## Phase 4 — Submitted-unknown reconciliation and protection repair planning

**Objective:** Turn `submitted_unknown` from an ambiguous failure into a bounded recovery workflow.

**Files likely to change:**

- `scripts/binance_trend_core/brokers.py`
- `scripts/binance_trend_core/execution.py`
- `scripts/binance_trend_core/runtime.py`
- `scripts/binance_usds_futures_trend.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**

1. Reconcile unknown orders using durable client IDs:
   - `clientOrderId` for ordinary orders;
   - `clientAlgoId` or equivalent for open algo orders if available.
2. Classify unknown outcomes:
   - `resolved_acknowledged`;
   - `resolved_filled`;
   - `resolved_absent_safe_to_retry`;
   - `resolved_absent_needs_human`;
   - `still_unknown`.
3. Add a repair plan generator that is dry-run by default:
   - identifies missing SL/TP;
   - identifies stale TP/SL;
   - identifies duplicate/orphan protection;
   - emits proposed create/cancel/replace actions without executing them.
4. Keep actual repair execution behind explicit signed authorization.

**Tests:**

- Unknown stop-loss present in open algo orders becomes resolved.
- Unknown stop-loss absent while position exists remains protection FAIL.
- Repair plan is generated but not submitted in dry-run.
- Repair plan respects order-count budget and fail-closed stop-loss priority.

**Verification:**

```bash
python3 -m pytest -q tests/test_binance_usds_futures_trend.py
scripts/binance_usds_futures_trend.py --run-testnet-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file /tmp/v20-dry-run-runtime.jsonl --no-save-runtime-record --testnet-dry-run
git diff --check
```

**Acceptance:**

- The system can explain every `submitted_unknown` class before any signed repair is attempted.
- A signed repair run is not needed for diagnosis and is not automatically performed.

## Phase 5 — Daily analyzer recency and incident gating

**Objective:** Ensure the daily analyzer detects that it is stale relative to later signed failures and does not report outdated health as current.

**Files likely to change:**

- `scripts/binance_usds_futures_trend.py`
- `scripts/binance_trend_core/evolution.py` or a dedicated analyzer module if introduced
- `cron/jobs.template.json`
- `tests/test_binance_usds_futures_trend.py`
- `tests/test_cron_trading_config.py`

**Proposed behavior:**

Daily analyzer should report:

- analysis window start/end;
- newest runtime evidence timestamp;
- newest order journal timestamp;
- newest cron output timestamp considered;
- latest signed run timestamp;
- whether the analysis is stale relative to latest signed evidence;
- explicit incident gates:
  - `submitted_unknown_count > 0`;
  - `unprotected_symbols` non-empty;
  - signed runner paused after degradation;
  - dry-run-only evidence cannot clear signed incident.

**Tests:**

- Analyzer flags stale when order journal has newer signed failure than analyzer window.
- Analyzer distinguishes dry-run runtime growth from signed health recovery.
- Analyzer keeps read-only contract.

**Verification:**

```bash
python3 -m pytest -q tests/test_binance_usds_futures_trend.py tests/test_cron_trading_config.py
scripts/binance_usds_futures_trend.py --daily-analyze-runtime --runtime-record-file state/binance-usds-futures-trend-testnet-runtime.jsonl --testnet-order-journal-file state/binance-usds-futures-trend-testnet-orders.jsonl --analysis-window-hours 24
git diff --check
```

The last command reads local evidence only and must not place/cancel orders.

**Acceptance:**

- Daily analyzer cannot silently miss a later signed failure.
- Reports distinguish planned trigger time, evidence time, analysis completion time, and delivery/display limitations where relevant.

## Phase 6 — Portfolio-level risk manager

**Objective:** Move from mostly signal-level sizing plus broker caps to a first-class portfolio risk manager.

**Files likely to change:**

- `scripts/binance_trend_core/risk.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/loop.py`
- `scripts/binance_usds_futures_trend.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**

RiskManager should evaluate:

- total account equity and available balance;
- per-symbol exposure;
- total portfolio exposure;
- side exposure long/short;
- max daily loss;
- realized/unrealized drawdown where available;
- ATR/stop-distance risk;
- exchange min/max rules;
- current remote position;
- desired target total exposure;
- add_allowed and market regime.

It should output structured decisions:

- `approved` / `reduced` / `blocked`;
- final desired exposure;
- reason codes;
- caps applied;
- whether action is add/reduce/hold/protection-only.

**Tests:**

- Strong trend cannot exceed portfolio cap.
- Drawdown blocks new exposure expansion but allows reductions and protection repair.
- Current exposure above target produces reduction, not new short.
- Invalid stop distance fails closed.
- Add disallowed clips expansion but not protection repair.

**Verification:**

```bash
python3 -m pytest -q tests/test_binance_usds_futures_trend.py
scripts/binance_usds_futures_trend.py --run-paper-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file /tmp/v20-paper-runtime.jsonl
scripts/binance_usds_futures_trend.py --run-testnet-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file /tmp/v20-testnet-dry-run-runtime.jsonl --no-save-runtime-record --testnet-dry-run
git diff --check
```

**Acceptance:**

- Risk decisions are visible in runtime evidence.
- Sizing is suitable for compounding but cannot bypass drawdown/exposure caps.

## Phase 7 — Lifecycle and compounding policy after safety recovery

**Objective:** Improve CAGR potential only after execution/protection safety is credible.

**Files likely to change:**

- `scripts/binance_trend_core/portfolio.py`
- `scripts/binance_trend_core/strategy.py`
- `scripts/binance_trend_core/execution.py`
- `scripts/binance_trend_core/runtime.py`
- `tests/test_binance_usds_futures_trend.py`

**Proposed behavior:**

Implement explicit lifecycle states:

- `entry`;
- `hold`;
- `add`;
- `trim`;
- `harvest`;
- `protect_only`;
- `exit`.

Compounding rules:

- add only when major trend remains valid, add_allowed is true, current exposure is below target, and delta is meaningful after exchange rules;
- reserve headroom for later adds instead of spending the whole budget immediately;
- harvest partially at ATR/regime-based levels without abandoning the trend;
- keep a residual runner until trend failure or hard risk stop;
- never treat `position_size` as additive quantity; it remains desired total exposure.

**Tests:**

- Hold-long during pullback does not add when add_allowed=false.
- Strong persistent trend can add up to tranche limit.
- Harvest leaves residual exposure.
- Trim does not become full exit unless trend/risk gate says so.
- Protection target updates reflect post-harvest desired exposure while SL remains fail-closed.

**Verification:**

```bash
python3 -m pytest -q tests/test_binance_usds_futures_trend.py
scripts/binance_usds_futures_trend.py --run-paper-cycle --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --runtime-record-file /tmp/v20-lifecycle-paper.jsonl
scripts/binance_usds_futures_trend.py --replay-runtime-evidence --runtime-record-file /tmp/v20-lifecycle-paper.jsonl
git diff --check
```

**Acceptance:**

- Runtime evidence shows why the engine held, added, harvested, reduced, or exited.
- Strategy aligns better with “持续参与、持续持有、持续收割”.

## Phase 8 — Paper scanner demotion and shared-engine observability

**Objective:** Reduce architectural drift where paper looks like the product instead of an adapter around the shared trading loop.

**Files likely to change:**

- `scripts/binance_usds_futures_trend.py`
- `scripts/binance_usds_futures_trend_brief.sh`
- `scripts/binance_trend_core/*`
- `tests/test_binance_usds_futures_trend.py`
- `skills/crypto-trading/binance-usds-futures-trend/SKILL.md`

**Proposed behavior:**

- Keep old scanner/backtest commands for diagnostics, but make docs and cron defaults point to shared paper/testnet cycle outputs.
- Telegram summaries should be observability of trading-loop state, not a separate decision source.
- Runtime evidence should be canonical; summaries should be derived from it or include matching run IDs.

**Tests:**

- Existing scanner CLI remains backward-compatible.
- Shared paper cycle remains the recommended non-signed validation path.
- Telegram brief includes run ID, environment, runtime file, UTC and 北京时间（UTC+8）.

**Acceptance:**

- New users/agents see the trading loop as primary, not scanner output.

## Phase 9 — Live readiness checklist only, no live implementation

**Objective:** Define but do not implement the live/mainnet path.

**Files likely to change:**

- `plans/binance-usds-futures-live-readiness.md` or a reference document
- `skills/crypto-trading/binance-usds-futures-trend/SKILL.md`

**Checklist should require:**

- stable signed testnet operation over a meaningful window;
- zero unresolved `submitted_unknown` protection incidents;
- no unprotected nonzero positions;
- daily analyzer current and green;
- portfolio risk manager enforced;
- kill switch tested;
- account/order/fill evidence redaction verified;
- explicit user approval for live design;
- separate live credentials and environment isolation;
- mainnet signed code review by independent agents;
- staged rollout limits.

**Acceptance:**

- Live remains unauthorized until this checklist exists and is explicitly approved.

## Promotion gates

### Gate A — Docs/config cleanup complete

Required before any signed work:

- `cron/jobs.template.json` includes sanitized dry-run job.
- Hourly harness docstring is corrected.
- Skill time wording uses UTC and 北京时间（UTC+8）.
- Harness defaults are planned or implemented as dry-run default.

### Gate B — Signed read-only snapshot authorized and green

Requires explicit user authorization in that turn.

Green means:

- exact testnet hostname;
- no submit/cancel endpoints called;
- positions/open orders/open algo orders captured;
- no unprotected nonzero positions, or unprotected positions are explicitly reported with repair plan;
- `submitted_unknown` states are resolved or classified.

### Gate C — Signed repair/resume authorized

Requires explicit user authorization in that turn.

Preconditions:

- Gate B complete;
- repair plan produced in dry-run;
- order budget sufficient;
- risk caps explicit;
- signed short still disabled unless separately authorized;
- postflight stabilization planned.

### Gate D — CAGR optimization resumes

Allowed only after signed protection state is no longer unknown/degraded, or explicitly scoped to paper/dry-run simulation.

Required evidence:

- runtime records current;
- daily analyzer current;
- no unresolved protection incidents;
- risk manager outputs reason codes;
- replay uses recorded runtime evidence, not fresh samples.

## Implementation order summary

1. Phase 1 docs/config drift cleanup.
2. Phase 2 dry-run-default harness hardening.
3. Phase 3 signed read-only snapshot command.
4. Phase 4 submitted_unknown reconciliation and dry-run repair planning.
5. Phase 5 daily analyzer recency/incident gates.
6. Gate B: user-authorized signed read-only snapshot.
7. Gate C: only if needed and authorized, signed repair/resume.
8. Phase 6 portfolio-level risk manager.
9. Phase 7 lifecycle/compounding policy.
10. Phase 8 paper scanner demotion / shared observability.
11. Phase 9 live readiness checklist only.

## Validation strategy

For every code-changing phase:

```bash
python3 -m pytest -q tests/test_binance_usds_futures_trend.py tests/test_binance_usds_futures_testnet_hourly.py tests/test_cron_trading_config.py
python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_usds_futures_testnet_hourly.py scripts/binance_trend_core/*.py
git diff --check
```

For docs-only phases:

```bash
git diff --check
python3 - <<'PY'
from pathlib import Path
for path in [
    'plans/binance-usds-futures-trend-v2.0.md',
    'plans/binance-usds-futures-roadmap.md',
    'skills/crypto-trading/binance-usds-futures-trend/SKILL.md',
]:
    p = Path(path)
    assert p.exists(), path
    text = p.read_text(encoding='utf-8')
    assert text.strip(), path
    assert 'UTC' in text, path
print('docs validation passed')
PY
```

Before every commit/push:

- inspect `git status --short --branch`;
- exclude `state/*`, cron output, logs, caches, sessions, DB files, and live `cron/jobs.json` runtime noise unless specifically intended;
- run independent review on the exact staged diff;
- commit and push only after review approval.

## Non-goals for v2.0

- No live/mainnet trading implementation.
- No automatic resume of signed testnet cron.
- No signed order placement/cancellation as part of planning or docs cleanup.
- No short signed execution enablement without separate explicit authorization.
- No strategy parameter promotion from dry-run-only evidence.
- No claim that paper/backtest/dry-run metrics are achieved live returns.

## Expected outcome

At the end of v2.0, the project should have:

- clean operational docs/templates matching the live cron model;
- dry-run default behavior across both core CLI and hourly harness;
- a safe signed read-only snapshot path;
- deterministic submitted_unknown reconciliation and dry-run repair planning;
- daily analyzer recency gates;
- stronger portfolio risk manager and lifecycle/compounding policy ready for evidence-based testing;
- a clear live-readiness checklist that still keeps live/mainnet unauthorized.
