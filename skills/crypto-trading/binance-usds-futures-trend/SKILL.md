---
name: binance-usds-futures-trend
description: Use when generating paper-only Binance USDS-M futures trend-following decisions from free public K-line data with >=1h intervals, ATR harvesting, and no paid APIs.
version: 0.4.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [binance, futures, crypto-trading, trend-following, paper-trading]
    related_skills: [test-driven-development]
---

# Binance USDS Futures Trend Paper Decisions

## Overview

This project Skill supports paper-only Binance USDS-M futures decision generation using free public Binance Futures K-line data. It is designed for the crypto-trade-hermes profile and respects the user's strategy constraints:

- trade universe: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, LINKUSDT, AVAXUSDT, ADAUSDT, LTCUSDT, TRXUSDT, DOTUSDT, POLUSDT, BCHUSDT, APTUSDT, ARBUSDT, OPUSDT, SUIUSDT, INJUSDT, ATOMUSDT;
- no paid APIs;
- never use short intervals below 1h;
- prefer staying with the main trend, avoiding premature exits, and harvesting in tranches.

The implementation is deliberately conservative: it emits structured `paper` decisions only; it never sends signed orders. v0.2 adds free Binance USDS-M public context factors while keeping EMA trend participation as the primary filter. v0.3 adds multi-symbol batch scanning and ranking so portfolio attention can focus on the strongest trends before any live execution work. v0.4 adds multi-timeframe confirmation (`1h,4h,1d`) to reduce single-period noise while preserving the primary trend-following contract.

## When to Use

Use this Skill when the user asks for:

- Binance USDS-M futures market-data decisions;
- real-time or scheduled paper trading checks;
- trend-following entries/holds/exits using >=1h K-lines;
- a safe baseline before adding live execution.

Do not use this for:

- spot trading order placement;
- paid market-data APIs;
- 1m/5m/10m/15m/30m signals;
- signed live trading until a separate risk/execution Skill is created and tested.

## Script

Primary script:

```bash
scripts/binance_usds_futures_trend.py --symbol BTCUSDT --interval 1h --limit 240
```

Batch scan the configured universe:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --interval 1h --limit 240 --context-limit 30 --top 5
```

Batch scan selected symbols:

```bash
scripts/binance_usds_futures_trend.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 240 --top 3
```

Multi-timeframe batch scan:

```bash
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5
```

Output is JSON:

- `ok`: whether the run succeeded;
- `decision.mode`: always `paper` in this version;
- `decision.action`: `hold_long` or `flat`;
- `generated_at_utc`: ISO timestamp in UTC;
- `generated_at_beijing`: ISO timestamp in Beijing time (UTC+8);
- `ema50`, `ema200`, `atr14`: trend/risk indicators;
- `confidence_score`: v0.2 public-factor confidence multiplier;
- `factor_flags`: diagnostic flags from mark trend, funding, open interest, long/short, and taker flow;
- `market_context`: fetched free public USDS-M context factors;
- `take_profit_1`, `take_profit_2`: ATR tranche harvesting references;
- `trailing_stop`: ATR trailing stop reference.

In v0.3 batch mode, output is `scan` JSON:

- `scan.mode`: always `paper`;
- `scan.results`: all symbols sorted by `rank_score`;
- `scan.top_trends`: strongest hold-long candidates;
- `scan.risk_high_trends`: symbols still in trend but with crowding, contraction, extension, or low-confidence flags;
- `scan.watchlist`: flat/error symbols to observe but not allocate to;
- `scan.summary_zh`: concise Chinese report with UTC and 北京时间（UTC+8） labels.

In v0.4 multi-timeframe mode, `scan` additionally includes:

- `scan.intervals`: interval list for batch scans, e.g. `1h,4h,1d`;
- `scan.primary_interval`: first interval in the list;
- `timeframe_signals`: per-interval decision summaries on each result;
- `timeframe_agreement_score`: how many intervals agree with the primary trend;
- `higher_timeframe_confirmed`: whether all higher intervals support the primary hold-long trend;
- `strong_confirmed_trends`, `early_trends`, and `conflicting_trends` groups.

## Decision Logic v0.4

1. Validate symbol is in the configured trade universe.
2. Validate interval is >=1h; reject `1m`, `3m`, `5m`, `10m`, `15m`, `30m`.
3. Fetch free public K-lines from:

```text
https://fapi.binance.com/fapi/v1/klines
```

4. Optionally fetch v0.2 public context factors from free Binance USDS-M endpoints:

```text
/fapi/v1/markPriceKlines
/fapi/v1/fundingRate
/futures/data/openInterestHist
/futures/data/globalLongShortAccountRatio
/futures/data/takerlongshortRatio
```

5. Require at least 200 K-line candles.
6. Compute:
   - EMA50;
   - EMA200;
   - ATR14.
7. Main trend filter:
   - `close > EMA200`;
   - `EMA50 > EMA200`.
8. If the filter passes:
   - action: `hold_long`;
   - take-profit 1: close + 2 * ATR14;
   - take-profit 2: close + 4 * ATR14;
   - trailing stop: close - 3 * ATR14;
   - if price is extended > 4 ATR above EMA50, reduce paper size to 0.5 risk unit, not full exit;
   - v0.2 context factors adjust `confidence_score` / `position_size`, not the trend participation decision.
9. If the filter fails:
   - action: `flat`;
   - size: 0.
10. In batch mode, scan all selected symbols and add ranking fields:
   - `trend_strength`: ATR-normalized major-trend strength;
   - `extension_atr`: ATR-normalized distance above EMA50;
   - `rank_score`: `trend_strength * confidence_score * position_size` (and multiplied by `timeframe_agreement_score` in multi-timeframe mode);
   - `ranking_bucket`: `top_trend`, `risk_high_trend`, `watchlist`, or `error`.
11. In multi-timeframe mode, evaluate each interval independently, use the first interval as primary, and add:
   - `timeframe_signals`;
   - `timeframe_agreement_score`;
   - `higher_timeframe_confirmed`;
   - `ranking_bucket`: `strong_confirmed_trend`, `early_trend`, `conflicting_trend`, `watchlist`, or `error`.
12. Input guardrails: every interval must be `>=1h`, `risk_unit` must be positive, and `top` must be `>= 1`.

## Testing

Run:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
```

The test suite verifies:

- short intervals are rejected;
- >=1h intervals are accepted;
- short public-factor periods are rejected;
- synthetic strong uptrend produces `hold_long`;
- synthetic downtrend produces `flat`;
- v0.2 public context factors adjust confidence/size without forcing premature trend exits;
- v0.2 context fetch uses free Binance USDS-M endpoints;
- v0.3 batch scanning ranks multi-symbol trend candidates and builds a Chinese summary;
- v0.4 multi-timeframe scanning confirms primary trends against higher timeframes and rejects short intervals in interval lists;
- input guardrails reject non-positive `risk_unit` and `top < 1`.

## Verification Recipe

1. Run unit tests:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
```

2. Run one real free-data decision or full-universe scan:

```bash
scripts/binance_usds_futures_trend.py --symbol BTCUSDT --interval 1h --limit 240
scripts/binance_usds_futures_trend.py --all-symbols --interval 1h --limit 240 --context-limit 30 --top 5
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5
```

3. Confirm:

- JSON parses;
- `mode` is `paper`;
- timestamps include both UTC and Beijing time (UTC+8);
- interval is not below 1h;
- no API key or paid API is required.

## Common Pitfalls

1. **Installing unrelated Binance skills blindly.** Some public Binance skills are spot-only or on-chain/web3 focused. For this project, prefer USDS-M futures and free K-line data.
2. **Using short intervals.** The user explicitly disallows short periods below 1h; reject them in code and tests.
3. **Confusing paper decisions with execution.** This Skill does not place orders. Live trading needs a separate signed-execution workflow, risk cap, kill switch, and testnet-first validation.
4. **Over-exiting trends.** The baseline reduces size when extended but does not flip to flat while the major trend filter remains valid.
5. **Omitting timezone labels.** Any run output or report must include UTC or Beijing time (UTC+8) labels.

## References

- `references/binance-skills-hub-usds-futures.md` — condensed notes from the fetched Binance Skills Hub repo for USDⓈ-M Futures public/auth endpoints used by this skill.
- `references/session-v0.2-public-factors-workflow.md` — workflow note for expanding free Binance public factors while preserving the primary trend-following contract.
- `references/session-v0.3-batch-scanner-workflow.md` — workflow note for adding multi-symbol batch scanning, ranking, guardrails, and verification.
- `references/session-v0.4-multi-timeframe-workflow.md` — workflow note for adding multi-timeframe confirmation and grouping.
- `plans/binance-usds-futures-trend-v0.3.md` — v0.3 batch scan and ranking implementation plan.
- `plans/binance-usds-futures-trend-v0.4.md` — v0.4 multi-timeframe confirmation implementation plan.

## Roadmap

- Refine higher-timeframe agreement scoring and explainability.
- Add free Binance USDS-M factors from the local Binance Skills Hub reference: mark-price Kline, funding, open interest, long/short ratios, taker buy/sell volume, and premium index Kline.
- Add volatility targeting and max portfolio risk constraints.
- Add paper state persistence under a tracked or intentionally ignored path after policy review.
- Only after long paper validation: design a separate live execution Skill with Binance testnet-first signed requests.

## Verification Checklist

- [ ] Tests pass.
- [ ] Real free Binance Futures K-line decision runs or blocker is reported honestly.
- [ ] Output is paper-only.
- [ ] Interval is >=1h.
- [ ] UTC and Beijing time (UTC+8) are both present.
- [ ] No paid API or API key is required.
