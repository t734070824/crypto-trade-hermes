# Session v1.46 — Pullback add gate, cron pause/schedule, and short-side safety

## Durable lesson

When a long-only major-trend futures system emits `hold_long` during a local 1h pullback, do not automatically convert that into a short signal. First separate three meanings:

1. **Major-trend state** — e.g. `hold_long` from `close > EMA200` and `EMA50 > EMA200`.
2. **Add permission** — whether positive delta / new long adds are allowed in the current local structure.
3. **Short permission** — a separate strategy family requiring its own signal, risk, execution, protection orders, and testnet evidence.

The safe fix for a local pullback in a long-only system is usually to block new long adds, not to open shorts.

## Implementation pattern captured

- Use only closed Binance 1h candles for signal generation; discard the currently forming candle returned by the klines endpoint.
- Keep `hold_long` as the slow major-trend state.
- Add an explicit `add_allowed` flag and `add_blockers` list.
- Set `add_allowed=false` when any local pullback blocker appears, such as:
  - `close < EMA50`
  - recent 6 closed candles slope negative
  - recent 12 closed candles slope negative
- In execution, block only positive delta adds when `add_allowed=false`.
- Still allow:
  - holding existing exposure
  - reducing exposure
  - repairing/replacing protective stop/take-profit orders

## Verification pattern

Before reporting success, verify all of these:

- Unit tests pass.
- Python syntax/compile checks pass for changed scripts.
- Paper or dry-run path shows `add_allowed=false` and explicit blockers for pullback symbols.
- Testnet dry-run shows `real_orders_submitted=False` and `desired_orders=0` when pullback blockers prevent adds.
- Cron state is reported separately from cron schedule: a paused job may have the correct future schedule but will not run until resumed.

## User-facing explanation pattern

When explaining “why not short”:

- Say it is not a permanent ban; short behavior must be enabled only by code/config/tests, not by prompt prose.
- Distinguish the actual bug from a strategy expansion:
  - bug/fix: do not add long during pullback
  - strategy expansion: design and validate a short strategy separately
- After the short dry-run implementation, mention that the dry-run path has code coverage for:
  - bearish EMA200/EMA50 signal model
  - negative desired exposure
  - SELL entry/opening delta
  - BUY stop-loss / take-profit protection
  - side-aware protection verification
- Still do not claim signed short trading is approved until there is explicit current-turn authorization plus testnet runtime evidence for short fills/protection/loss attribution.
- Avoid implying prompt text alone enables short behavior; only code, config, tests, and cron/script flags define actual behavior.

## Cron reporting nuance

For this project, report time-sensitive cron facts with explicit timezone labels and distinguish:

- planned trigger time
- actual execution finish time
- message delivery time
- job duration when available

When a job is paused, state that schedule changes only apply after resume.
