---
name: binance-usds-futures-trend
description: Use when generating paper-only Binance USDS-M futures trend-following decisions from free public K-line data with >=1h intervals, ATR harvesting, and no paid APIs.
version: 0.1.0
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

The initial implementation is deliberately conservative: it emits a structured `paper` decision only; it never sends signed orders.

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

Output is JSON:

- `ok`: whether the run succeeded;
- `decision.mode`: always `paper` in this version;
- `decision.action`: `hold_long` or `flat`;
- `generated_at_utc`: ISO timestamp in UTC;
- `generated_at_beijing`: ISO timestamp in Beijing time (UTC+8);
- `ema50`, `ema200`, `atr14`: trend/risk indicators;
- `take_profit_1`, `take_profit_2`: ATR tranche harvesting references;
- `trailing_stop`: ATR trailing stop reference.

## Decision Logic v0.1

1. Validate symbol is in the configured trade universe.
2. Validate interval is >=1h; reject `1m`, `3m`, `5m`, `10m`, `15m`, `30m`.
3. Fetch free public K-lines from:

```text
https://fapi.binance.com/fapi/v1/klines
```

4. Require at least 200 candles.
5. Compute:
   - EMA50;
   - EMA200;
   - ATR14.
6. Main trend filter:
   - `close > EMA200`;
   - `EMA50 > EMA200`.
7. If the filter passes:
   - action: `hold_long`;
   - take-profit 1: close + 2 * ATR14;
   - take-profit 2: close + 4 * ATR14;
   - trailing stop: close - 3 * ATR14;
   - if price is extended > 4 ATR above EMA50, reduce paper size to 0.5 risk unit, not full exit.
8. If the filter fails:
   - action: `flat`;
   - size: 0.

## Testing

Run:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
```

The test suite verifies:

- short intervals are rejected;
- >=1h intervals are accepted;
- synthetic strong uptrend produces `hold_long`;
- synthetic downtrend produces `flat`.

## Verification Recipe

1. Run unit tests:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
```

2. Run one real free-data decision:

```bash
scripts/binance_usds_futures_trend.py --symbol BTCUSDT --interval 1h --limit 240
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

## Roadmap

- Add multi-symbol batch scan for the configured universe.
- Add higher-timeframe agreement, e.g. 4h + 1d trend filter.
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
