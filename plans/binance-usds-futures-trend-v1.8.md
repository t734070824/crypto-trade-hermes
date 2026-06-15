# Binance USDS-M Futures Trend v1.8 Plan — Live Readiness Gates and Audit

Created: UTC 2026-06-15 15:44:10 / 北京时间（UTC+8）2026-06-15 23:44:10

## Goal

设计 live readiness gates 和审计流程；只有 paper/testnet 长期证据、风控、kill switch、人工授权全部满足后，才允许后续 live adapter 版本。

## Scope

- Add live-readiness checklist command/report.
- Verify required evidence windows exist for paper/testnet runtime records.
- Verify drawdown, turnover, error rate, slippage, and order reject limits.
- Verify kill switch and max loss caps are configured.
- Verify independent audit result is attached.
- Require explicit user confirmation before any future live adapter implementation.

## Non-Goals

- v1.8 不实现 live 下单。
- 不创建 mainnet signed endpoint calls。
- 不自动启用 live。

## TDD Tasks

1. Test readiness report fails when evidence window is missing.
2. Test readiness report fails when kill switch is absent.
3. Test readiness report fails when recent runtime errors exceed threshold.
4. Test readiness report passes only with all gates satisfied.
5. Test output labels UTC / 北京时间（UTC+8）。

## Verification

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
git diff --check
```

## Acceptance

- Live remains impossible by default.
- Readiness gates are explicit, testable, and auditable.
- Future live work requires a new version plan and user authorization.
