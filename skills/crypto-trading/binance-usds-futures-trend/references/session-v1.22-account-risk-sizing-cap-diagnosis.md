# Session v1.22 — Account-risk sizing can be silently capped by fixed exposure limits

## Trigger

The user observed four testnet entry orders but noted that position size was obviously not based on current account margin.

## Durable lesson

When diagnosing apparent account-based sizing failures, do not stop at whether signed account sync succeeded. Inspect the full sizing constraint chain in runtime evidence:

- `account_risk_sizing.available_balance`
- `account_risk_sizing.account_equity`
- `account_risk_sizing.risk_budget`
- `account_risk_sizing.qty_by_stop_risk`
- `account_risk_sizing.max_notional_by_margin`
- `account_risk_sizing.effective_notional_cap`
- `account_risk_sizing.qty_by_notional_cap`
- `account_risk_sizing.desired_position_size`
- `account_risk_sizing.constraints_applied`

In this session, account sync was working and showed roughly 5,000 USDT equity / 4,936–5,000 USDT available balance. With `target_leverage=2`, margin-derived capacity was roughly 9,873–10,000 USDT. However, the cron prompt/risk config also set fixed caps:

- `max_order_notional=200`
- `max_symbol_exposure=70`

The fixed `max_symbol_exposure=70` dominated, so `effective_notional_cap=70` and each entry order became roughly 70 USDT notional despite account-risk sizing being active.

## Correct diagnosis pattern

1. Pause any recurring mutating testnet cron before debugging if the next run could continue placing incorrectly sized orders.
2. Read the latest runtime JSONL and order journal.
3. Compare account-derived capacity against final effective cap:
   - `max_notional_by_margin = available_balance * target_leverage`
   - `risk_budget = account_equity * account_risk_fraction`
   - `qty_by_stop_risk = risk_budget / stop_distance`
   - `qty_by_notional_cap = effective_notional_cap / entry_reference`
   - final `desired_position_size = min(qty_by_stop_risk, qty_by_notional_cap)`
4. If `effective_notional_cap` is much smaller than `max_notional_by_margin`, explain which fixed cap or fractional cap is dominating.
5. Distinguish between “account sync failed” and “account sync succeeded but fixed caps intentionally/accidentally throttled sizing.”

## Fix direction

For production-like account-based testnet sizing, avoid hardcoded tiny absolute per-symbol caps such as `max_symbol_exposure=70` unless intentionally running a micro-probe. Prefer account-proportional exposure controls, for example:

- use `--testnet-max-symbol-exposure-fraction` where supported;
- raise or remove the fixed `--testnet-max-symbol-exposure` so it does not dominate the fraction;
- keep `account_risk_fraction`, stop-distance sizing, exchange min/step/notional adaptation, current-position delta reconciliation, daily-loss limits, and kill switches.

If both fixed absolute caps and account-proportional caps are configured, document which one should dominate and verify runtime evidence confirms it.
