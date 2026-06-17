# Session v1.23 — Single-agent cron default and sizing-cap fix

## Durable lesson

Earlier guidance treated “为什么不是一个 agent 型定时任务处理所有流程” as a workflow correction toward one agent-owned loop. The current refined boundary is:

- one deterministic `no_agent=true` script-owned hourly cron owns the fixed signed-testnet hot path when credential/preflight checks, account/position/open-order/open-algo reconciliation, risk-gated signed cycles, lifecycle tracking, runtime evidence recording, post-run signed snapshot verification, and the concise Chinese report are implemented in code;
- one Skill-loaded agent cron remains appropriate for daily read-only replay diagnostics, anomaly analysis, and strategy-evolution reasoning;
- separate cron jobs are acceptable when they separate deterministic execution from LLM analysis, not when they hide trading ownership behind an agent prompt that only parses wrapper output.

## What was fixed in this session

At the time, the hourly testnet agent cron carried micro-probe sizing caps. The enduring fix was to keep account-risk sizing from being dominated by tiny absolute limits:

- `--testnet-max-order-notional 1000`
- `--testnet-max-symbol-exposure 2000`
- `--testnet-max-symbol-exposure-fraction 0.20`

This preserves testnet-only execution, exchange rule adaptation, delta-only reconciliation, order-count/daily-loss caps, lifecycle tracking, open-algo protection checks, runtime evidence, and post-run reporting.

## Future-agent guidance

If the user asks why the flow is not one agent cron:

1. Answer directly that the current fixed hourly hot path is script-owned because the commands and behavior are deterministic.
2. Distinguish the separate daily replay diagnostic as read-only agent evidence analysis, not a second trading decision-maker.
3. Inspect the actual cron prompt/config before assuming architecture is wrong; the problem may be prompt parameters such as sizing caps, not job topology.
4. If editing cron definitions, add a regression test that checks the intended prompt invariants and prevents reintroducing micro-probe caps.
5. Before commit/push, exclude scheduler runtime noise, run tests, get independent review, then push by default.
