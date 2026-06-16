# Binance USDS-M Futures Trend v1.8 Plan — Testnet Readiness Hardening

Created: UTC 2026-06-16 01:59:21 / 北京时间（UTC+8）2026-06-16 09:59:21
Status: implemented UTC 2026-06-16 02:29:30 / 北京时间（UTC+8）2026-06-16 10:29:30

## Goal

在已完成 v1.7 testnet adapter 的基础上，补齐 testnet readiness hardening：exchangeInfo 规则适配、账户/订单同步、order journal、未知状态确认、风险配置化和持续 dry-run 证据。

## Scope

- Add exchangeInfo-based order rule adaptation and validation.
- Add signed testnet account/order state sync and reconciliation.
- Add clientOrderId generation, append-only order journal, and unknown-state confirmation queries.
- Add config-driven risk limits and kill switch summary.
- Add runtime evidence checks and a dry-run cron cadence for 24-72h observation.
- Keep live/mainnet execution unimplemented and unauthorized.

## Non-Goals

- v1.8 不实现 live 下单。
- 不创建 mainnet signed endpoint calls。
- 不自动启用 live。

## TDD Tasks

1. Test readiness report fails when exchangeInfo rules are missing.
2. Test rule adaptation rejects invalid quantity/tick/step/minNotional combinations.
3. Test account/order reconciliation surfaces unknown states.
4. Test journal records clientOrderId and safe retry/confirm flow.
5. Test output labels UTC / 北京时间（UTC+8）。

## Verification

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
git diff --check
```

## Acceptance

- Live remains impossible by default.
- Testnet readiness gates are explicit, testable, and auditable.
- Future live work requires a new version plan and user authorization.
