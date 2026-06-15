# Session v1.3 — Runtime Data and Strategy Evolution

## Trigger

The user added a durable requirement: trading runs must record runtime data, and future strategy improvements should be driven by observed run results rather than isolated reports or subjective impressions.

## Durable Rule

Every future paper/testnet/live trading loop should produce structured runtime evidence that can be used to evaluate and evolve strategy behavior.

## Runtime Data to Capture

At minimum, preserve enough information to reconstruct why the system acted:

1. run metadata: environment, strategy version, config version, symbol universe, intervals, UTC timestamp, 北京时间（UTC+8） timestamp;
2. market inputs: candle window identifiers, public context factors, and data freshness markers;
3. signal outputs: trend state, score, confidence, extension, context adjustments, selected candidates;
4. risk checks: sizing inputs, caps, rejects/skips, drawdown/cooldown/kill-switch status;
5. portfolio state: positions, exposure, lifecycle stage, trailing stops, take-profit tranches;
6. execution events: desired orders, submitted/cancelled/replaced orders, simulated or real fills, fees, slippage assumptions;
7. outcomes: realized/unrealized PnL, drawdown, holding time, turnover, errors, retries, and post-run snapshots.

## Storage Principles

- Runtime datasets should be append-only or reproducibly versioned.
- Paper, testnet, and live data must be isolated by environment while sharing a compatible schema.
- Runtime state and datasets belong under ignored runtime paths unless deliberately exporting a sanitized research artifact.
- Never commit secrets, signed payloads, live account balances, raw live order IDs, or private account data unless explicitly sanitized.
- Time fields must label UTC or 北京时间（UTC+8）.

## Strategy Evolution Rule

Future strategy changes should be promoted only after comparison against recorded runtime evidence. Prefer comparisons that reuse the same captured inputs/events so differences are strategy-driven rather than caused by drifting market samples.

## Pitfall to Avoid

Do not let Telegram summaries become the evidence store. Telegram is observability; canonical evolution data should be structured runtime records that can support replay, comparison, audit, and regression tests.
