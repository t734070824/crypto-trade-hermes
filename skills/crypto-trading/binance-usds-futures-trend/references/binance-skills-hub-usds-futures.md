# Binance Skills Hub USDS-M Futures Reference Notes

Use these notes when upgrading the `binance-usds-futures-trend` workflow beyond the v0.1 K-line-only baseline.

## Local upstream reference

The user placed Binance Skills Hub under the active profile root:

```text
/root/.hermes/profiles/crypto-trade-hermes/binance-skills-hub
```

Most relevant files:

```text
binance-skills-hub/skills/binance/binance/SKILL.md
binance-skills-hub/skills/binance/binance/references/futures-usds.md
binance-skills-hub/skills/binance/binance/references/futures-usds-streams.md
```

## What to borrow

For this project, treat the Hub as an endpoint/reference catalog, not as a mandatory runtime dependency. The Hub skill centers on `binance-cli` and many account/trade operations require auth. The current project baseline should remain simple and paper-only unless the user explicitly asks for signed execution.

Free/public USDS-M futures factors worth adding in v0.2:

- Kline / candlestick data
- Mark price and mark-price Kline
- Funding rate history / funding info
- Open interest and open-interest statistics
- Long/short ratio
- Top trader long/short ratio by accounts and positions
- Taker buy/sell volume
- Premium index Kline

## Guardrails

- Keep intervals >= 1h even when the upstream docs list shorter periods.
- Keep paper-only decision output separate from signed account/trade workflows.
- If auth is needed later, this profile stores Binance credential env vars as `LALA_KEY` and `LALA_SECRET`; do not expose values.
- Do not clone or vendor the full Binance Skills Hub into this skill; reference the local checkout and extract only the small durable endpoint lessons needed.

## Suggested v0.2 direction

Add a multi-factor confirmation layer while preserving trend participation:

1. EMA50/EMA200 main trend stays as the base filter.
2. Mark-price Kline confirms the futures reference price trend.
3. Funding rate avoids adding aggressively when crowded funding is extreme.
4. Open interest distinguishes trend participation from weak low-interest drift.
5. Long/short and taker buy/sell volume become secondary confidence inputs, not hard exits.
6. ATR tranche harvesting and trailing stop remain designed to avoid premature trend exits.
