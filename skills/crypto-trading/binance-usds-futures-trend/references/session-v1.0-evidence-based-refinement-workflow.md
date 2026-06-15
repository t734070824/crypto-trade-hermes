# Session v1.0 Evidence-based Refinement Workflow

Created: UTC 2026-06-15 14:00:00 / 北京时间（UTC+8）2026-06-15 22:00:00

## Purpose

v1.0 adds a paper-only evidence comparison layer before changing strategy defaults. The goal is to compare baseline and conservative candidate variants with historical backtest evidence instead of changing parameters by intuition.

## Implemented Workflow

1. Created `plans/binance-usds-futures-trend-v1.0.md` with scope, guardrails, tests, and verification commands.
2. Followed TDD:
   - RED tests proved `compare_strategy_variants` and `--compare-refinements` were missing.
   - GREEN implementation added the minimal comparison pipeline.
3. Added `DEFAULT_REFINEMENT_VARIANTS`:
   - `baseline`: v0.9 behavior with `risk_unit=1.0`, `max_position_size=1.0`.
   - `trend_hold_bias`: diagnostic higher trend participation with `risk_unit=1.15`, `max_position_size=1.15`.
   - `risk_capped`: defensive cap with `risk_unit=0.75`, `max_position_size=0.75`.
4. The comparison fetches one candle sample per symbol and reuses that identical sample across baseline and all candidates, so live/current kline drift cannot create fake variant differences.
5. Added evidence scoring:
   - `evidence_score = cagr + 0.03*calmar + 0.02*sharpe`.
6. Added drawdown guardrail:
   - candidate is blocked when absolute max drawdown worsens beyond `max_drawdown_worsening_limit`.
7. Added CLI:

```bash
scripts/binance_usds_futures_trend.py --compare-refinements --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 500
```

## Guardrails

- Output is `paper` only.
- No signed endpoints, no paid APIs, no real orders.
- `<1h` intervals remain rejected by existing validation.
- v1.0 does not auto-promote selected candidates into scanner defaults; `selected_variant` is diagnostic evidence only.
- Candidate results must not be described as live returns or proof of target CAGR.

## Verification

Run:

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py
git diff --check
scripts/binance_usds_futures_trend.py --compare-refinements --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 500
```

Confirm:

- JSON parses.
- `refinement.mode=paper`.
- UTC and 北京时间（UTC+8） timestamps are present.
- `variants` include baseline and candidates.
- `selection_policy.auto_promote_defaults=false`.
- `errors_count=0` for successful real-data runs.
- No API key, paid API, or real order is required.
