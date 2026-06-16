# Binance USDS-M Futures Trend v1.7 Plan — Binance Futures Testnet Adapter

Created: UTC 2026-06-15 15:44:10 / 北京时间（UTC+8）2026-06-15 23:44:10

## Status

Implemented: UTC 2026-06-16 01:35:05 / 北京时间（UTC+8）2026-06-16 09:35:05

## Goal

在长期 paper 证据可接受后，实现 Binance USDS-M futures testnet adapter，但仍与 paper 共享同一套 trading loop。

## Implemented Scope

- Added `BinanceTestnetBroker` behind explicit `--run-testnet-cycle` CLI mode.
- Enforces Binance futures testnet host exactly: `https://testnet.binancefuture.com`; mainnet and lookalike hosts fail closed.
- Resolves credentials from `LALA_KEY` / `LALA_SECRET` and never prints values.
- Defaults to dry-run (`--testnet-dry-run` / no signed submit) so no signing or HTTP order submission occurs unless `--testnet-submit-signed` is explicitly supplied.
- Added fail-closed testnet risk gates: max order notional, max symbol exposure, max daily loss, max order count, kill switch.
- Signed-path HTTP exceptions are recorded as `submitted_unknown` with sanitized error metadata; raw signed URLs, signatures, and API-key headers must not enter runtime evidence.
- Testnet broker rejects missing, zero, negative, or non-finite `reference_price` / `entry_reference` before signing, except global kill/order-count/loss gates that reject earlier.
- Runtime evidence marks `environment=testnet`, preserves UTC / 北京时间（UTC+8） timestamps, and redacts sensitive request/response fields.
- Paper and testnet reuse `run_trading_cycle`; strategy, risk manager, execution planner, runtime record shape, and interval validation stay shared.

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
