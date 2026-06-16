# Session v1.10 — Agent Cron for Testnet Operations

## Context

The user challenged the split collector/analyzer approach with: “为什么不是 一个 agent 型定时任务 处理所有流程”. Treat this as an architectural preference for testnet operations when reasoning is required.

## Durable lesson

For Binance USDS-M futures testnet operations, a single agent-type cron with this Skill loaded is often the right default when the scheduled workflow must:

- gather runtime evidence;
- inspect current state and recent errors;
- sync account/positions/orders from Binance Futures Testnet;
- decide whether signed submission is safe;
- run dry-run or signed testnet cycle according to gates;
- interpret credential/risk/API failures;
- report next actions in Chinese with UTC and 北京时间（UTC+8） labels.

Use `no_agent=true` scripts only for deterministic evidence collectors/watchdogs where no reasoning is wanted. Do not split the system into collector/analyzer/promoter cron jobs merely by habit; split only when reproducibility, cost, or isolation materially benefits from it.

## Signed testnet gate learned

A dry-run cycle passing and `.env` containing `LALA_KEY` / `LALA_SECRET` do not prove signed readiness. Before enabling recurring signed testnet cron:

1. run an explicit current-turn signed Futures Testnet probe or small cycle;
2. verify credentials against signed testnet endpoints;
3. sync remote positions/account state before calculating order deltas;
4. confirm order acknowledgement is not treated as a fill;
5. use order/userTrades lifecycle tracking for fills, fees, PnL, and slippage;
6. keep live/mainnet unauthorized unless separately implemented and approved.

In the session, signed testnet returned `HTTP Error 401: Unauthorized`; this is a setup/credential issue, not a reason to encode a permanent negative claim about the tool or endpoint.

## Git hygiene note

Hermes scheduler may update runtime fields in `cron/jobs.json` (`completed`, `next_run_at`, `last_run_at`, `updated_at`) during development. Unless the task intentionally edits cron definitions, restore/exclude those runtime-only changes before independent review, commit, and push.
