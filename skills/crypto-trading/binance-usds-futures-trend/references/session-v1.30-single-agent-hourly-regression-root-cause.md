# Session v1.30 — Cron ownership boundary regression root cause

## What happened

The hourly `testnet-agent-hourly` cron was previously changed into an ambiguous wrapper-driven shape:

- `script` was set to a wrapper path while `no_agent=false` remained;
- the prompt implied the script had already executed the trading harness;
- the agent was reduced to parsing sanitized JSON instead of owning a real decision loop.

That was unsafe because the cron metadata said “agent job”, but the actual trading owner was hidden in a wrapper.

## Revised durable lesson

Do not leave ownership ambiguous. Pick one explicit mode:

1. **Script-owned hot path** — use `no_agent=true`, `skills: []`, a script path resolved under the profile `scripts/` directory, and a short prompt stating that prompt/skills do not execute. This is appropriate when BTC/Alt groups, endpoints, risk parameters, runtime files, reconciliation, postflight checks, redaction, and report fields are all deterministic and implemented in the script.
2. **Agent-owned analysis/decision loop** — use `no_agent=false`, `script: null`, and load the Skill. This is appropriate for daily replay diagnostics, anomaly/root-cause analysis, strategy-evolution assessment, parameter-change proposals, and other non-deterministic reasoning.

A wrapper script is acceptable only when the job is explicitly script-owned. It is not acceptable to keep `no_agent=false` while the prompt merely parses wrapper output.

## Current fix pattern

For the fixed hourly testnet runner:

- Set `no_agent=true`.
- Set `skills: []` / `skill: null`.
- Set `script: "binance_usds_futures_testnet_hourly.sh"` rather than `"scripts/binance_usds_futures_testnet_hourly.sh"`, because Hermes resolves cron script paths relative to the profile `scripts/` directory.
- Keep the job paused unless the user explicitly asks to resume it.
- Keep daily replay diagnostics as a separate read-only agent job with `no_agent=false` and this Skill loaded.
- If the hourly script submits or attempts real testnet orders, it must do bounded postflight stabilization before final reporting.

## Reporting pattern

When summarizing hourly runs, explicitly distinguish:

- scheduled trigger time;
- actual completion time;
- delivery time;
- hot-path duration;
- postflight stabilization duration.

This prevents a few-second submission path from being mistaken for complete lifecycle verification.
