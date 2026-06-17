# Session v1.32 — Prompt vs CLI Boundary in testnet-agent-hourly

## What was learned

The user explicitly noted that in `testnet-agent-hourly`, BTC group and Alt group commands are fixed. That means prompt prose can be partially or fully ineffective if it is not backed by:

- a CLI flag passed to `scripts/binance_usds_futures_trend.py`,
- a config value loaded by the script, or
- a code path in the Python trading engine.

## Classification rule

For any cron prompt clause, classify it into one of three buckets:

1. **Enforced by code/flag**
   - Example: `--testnet-base-url https://testnet.binancefuture.com`
   - Example: `--account-risk-fraction 0.003`
   - Example: `--target-leverage 2`

2. **Agent-orchestration guidance**
   - Example: “do preflight, reconcile, cycle, then summarize”
   - Useful for workflow ownership, but it does not change the trading math by itself.

3. **Weak/aspirational text**
   - Example: “low risk”, “avoid early exits”, “strategy evolution”
   - These matter only if translated into flags or engine logic.

## Practical takeaway

When reviewing or designing a cron/runner, do not assume every sentence in the prompt is operationally effective. In `no_agent=true` jobs, prompt/skills do not execute at all; in agent jobs, fixed BTC/Alt CLI blocks should still be treated as the actual run contract. If durable behavior is desired, move it into code, config, or the Skill itself.

## Evidence source

This note was derived from the June 2026 discussion where the user pointed out that BTC group and Alt group scripts were deterministic and asked whether some prompt content was effectively invalid.
