# Binance USDS-M Futures Trend v1.7 Plan — Binance Futures Testnet Adapter

Created: UTC 2026-06-15 15:44:10 / 北京时间（UTC+8）2026-06-15 23:44:10

## Goal

在长期 paper 证据可接受后，实现 Binance USDS-M futures testnet adapter，但仍与 paper 共享同一套 trading loop。

## Prerequisites

- v1.3 runtime recorder stable.
- v1.4 interfaces stable.
- v1.5 PaperBroker shared loop stable.
- v1.6 strategy-evolution review shows acceptable evidence.
- User explicitly authorizes testnet work.

## Scope

- Add `BinanceTestnetBroker` using signed testnet endpoints only.
- Credentials must come from env mapping; never print values.
- Add kill switch, max notional, max symbol exposure, max daily loss, and order count caps.
- Add dry-run mode that signs nothing.
- Runtime records isolate `environment=testnet`.

## Non-Goals

- 不接 live。
- 不使用 mainnet signed endpoint。
- 不绕过风险阈值。

## TDD Tasks

1. Test adapter endpoint base is testnet-only.
2. Test missing credentials fails closed.
3. Test risk cap blocks oversized orders before signing.
4. Test dry-run signs/submits nothing.
5. Test runtime record redacts order/account sensitive fields.

## Verification

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
git diff --check
```

Manual testnet verification only after user approval and with explicit UTC / 北京时间（UTC+8） report.

## Acceptance

- Testnet adapter is behind explicit CLI flag/config.
- Same trading loop can run paper or testnet by broker replacement.
- No live orders possible from this version.
