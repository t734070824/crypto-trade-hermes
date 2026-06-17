# Session v1.42 — TP Replanning on Reductions and Cron Runtime Template

## Context

A signed testnet audit found an ETHUSDT long was closed/reduced around 2026-06-17 08:37 UTC / 2026-06-17 16:37 北京时间（UTC+8）. The follow-up fix addressed two durable classes of problems:

1. protective take-profit coverage could remain sized to the pre-reduction position;
2. Hermes `cron/jobs.json` contained scheduler runtime fields that are unsafe/noisy to keep as the tracked durable cron definition.

## Durable execution lesson

When reconciling long-position protection after a reduction, do not use one shared target exposure for stop-loss and take-profit orders.

Correct split:

```python
stop_target_exposure = max(desired_exposure, current_exposure)
take_profit_target_exposure = desired_exposure
```

Rationale:

- stop-loss stays fail-closed: if the market reduction fails, the larger current position is still protected;
- take-profit follows the intended post-reduction target: overcovered TP legs should be canceled/replaced, including same-trigger-price TP orders whose quantity is too large;
- if desired exposure is zero/flat, remaining TP protection should be canceled rather than left as orphan reduce-only legs.

Regression coverage to add/keep:

- reduction replans TP total quantity to `desired_exposure`;
- reduction keeps SL sized to `max(current_exposure, desired_exposure)`;
- same-price overcovered TP is stale and gets cancel/replace;
- flat target cancels leftover TP protection.

## Durable cron-file lesson

Treat `cron/jobs.json` as live scheduler runtime state, not the canonical durable cron spec, because Hermes may rewrite timestamps/counters/status/origin fields.

Preferred repo pattern:

- ignore live `/cron/jobs.json`;
- track `cron/jobs.template.json` as the durable job definition;
- strip runtime-only fields from the template, especially:
  - root `updated_at`;
  - job `next_run_at`, `last_run_at`, `last_status`, `last_error`;
  - `repeat.completed`;
  - `origin.chat_id`, `origin.chat_name`, and other delivery/runtime identifiers.

Pitfall: do not blindly restore an active tracked `cron/jobs.json`; stale `next_run_at` can make the scheduler classify a run as missed and fast-forward the next tick.

## Verification pattern

For this class of change, require:

- targeted tests for protective-order behavior and cron template/runtime separation;
- full project test suite;
- dry-run signed-testnet path showing no signed submissions when dry-run is requested;
- `git diff --check`;
- independent diff review before commit/push;
- final `git status` clean and push completed by default for this repo.
