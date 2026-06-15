# Session note: v0.2 public-factor expansion workflow

Use this reference when extending the Binance USDS-M futures trend skill with additional free data sources.

## Durable workflow lesson

- Preserve the primary trend-following contract: secondary factors should adjust confidence/position sizing, not force early exits from strong main trends.
- Keep data intervals at `>= 1h`; reject or avoid short-period intervals such as `1m`, `5m`, `10m`, and `30m`.
- Prefer free Binance public endpoints before adding paid APIs:
  - Mark price klines
  - Funding rate history
  - Open interest history
  - Global long/short account ratio
  - Taker buy/sell volume ratio
- Add factor outputs in a debuggable shape:
  - `confidence_score`
  - `factor_flags`
  - `market_context`
- Use TDD for strategy changes: add failing tests for new factor behavior first, implement, then run tests plus a real public-data probe.
- For this profile, after changing tracked skill/scripts/plans/config files, check git status; before any push, run an independent agent review and only push after approval.

## Verification pattern

1. Run unit tests for the strategy module.
2. Run a real Binance public-data paper-only probe on a liquid symbol such as `BTCUSDT` with `1h` or higher interval.
3. Report timestamps with both UTC and 北京时间（UTC+8）.
4. Confirm there is no real order placement path and no paid API dependency.
