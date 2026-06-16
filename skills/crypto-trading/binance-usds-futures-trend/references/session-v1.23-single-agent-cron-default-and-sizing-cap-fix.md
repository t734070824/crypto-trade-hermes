# Session v1.23 — Single-agent cron default and sizing-cap fix

## Durable lesson

When the user challenges “为什么不是一个 agent 型定时任务处理所有流程”, treat it as a workflow correction, not a request for more explanation. For this project, the preferred operational shape is:

- one Skill-loaded agent cron owns the end-to-end signed testnet trading loop;
- that cron performs credential/preflight checks, account/position/open-order/open-algo reconciliation, risk-gated signed testnet cycles, lifecycle tracking, runtime evidence recording, post-run signed snapshot verification, and a concise Chinese Telegram report;
- separate cron jobs are acceptable only for read-only diagnostics/replay or deterministic evidence collection, not for splitting the strategic trading decision path by habit.

## What was fixed in this session

The hourly testnet agent cron was already the correct single-agent orchestration shape, but its prompt still carried micro-probe sizing caps. The fix raised startup sizing caps so account-risk sizing can use current account margin/equity instead of being dominated by tiny absolute limits:

- `--testnet-max-order-notional 1000`
- `--testnet-max-symbol-exposure 2000`
- `--testnet-max-symbol-exposure-fraction 0.20`

This preserves testnet-only execution, exchange rule adaptation, delta-only reconciliation, order-count/daily-loss caps, lifecycle tracking, open-algo protection checks, runtime evidence, and post-run reporting.

## Future-agent guidance

If the user asks why the flow is not one agent cron:

1. Answer directly that for this repo it should normally be one agent cron for the operational trading loop.
2. Distinguish the separate daily replay diagnostic as read-only evidence analysis, not a second trading decision-maker.
3. Inspect the actual cron prompt/config before assuming architecture is wrong; the problem may be prompt parameters such as sizing caps, not job topology.
4. If editing cron definitions, add a regression test that checks the intended prompt invariants and prevents reintroducing micro-probe caps.
5. Before commit/push, exclude scheduler runtime noise, run tests, get independent review, then push by default.
