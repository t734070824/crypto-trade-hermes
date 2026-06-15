# Binance USDS-M Futures Trend v1.0 Evidence-based Strategy Refinement Plan

Created: UTC 2026-06-15 14:00:00 / 北京时间(UTC+8) 2026-06-15 22:00:00

## Status

Implemented in current v1.0 change set.

## Goal

Add an evidence-based strategy refinement layer that compares paper-only historical backtest variants before changing strategy defaults. v1.0 must make it harder to overfit or change parameters by intuition.

## Scope

- Keep all execution `paper only`; no signed endpoints and no live orders.
- Use only free Binance USDS-M public K-line data via existing `/fapi/v1/klines` path.
- Reject `<1h` intervals through existing validation.
- Add a variant-comparison API and CLI mode that evaluates a baseline against conservative candidate variants using the same historical sample.
- Report before/after evidence with UTC / 北京时间（UTC+8） timestamps.
- Select a candidate only if it improves evidence metrics without breaching drawdown guardrails.
- Do not automatically change scanner defaults in v1.0; candidate output is diagnostic/paper-only.

## Initial Candidate Variants

1. `baseline`: existing v0.9 behavior.
2. `trend_hold_bias`: conservative trend-participation candidate that slightly increases paper `risk_unit` and max paper position in confirmed trends during backtest simulation.
3. `risk_capped`: defensive candidate with lower paper `risk_unit` and max paper position to compare drawdown trade-offs.

These variants are intentionally simple so the framework can prove evidence comparison first. More sophisticated higher-timeframe scoring / premium-index factor changes can be added after this comparison pipeline exists.

## Intended Test Interface

File: `tests/test_binance_usds_futures_trend.py`

1. `test_backtest_symbol_risk_unit_changes_paper_exposure`
   - Use deterministic candles.
   - Assert higher `risk_unit` changes actual paper exposure and total-return output.

2. `test_compare_strategy_variants_reports_evidence_and_guardrails`
   - Monkeypatch `fetch_klines` to deterministic per-symbol candles.
   - Call `trend.compare_strategy_variants([...], interval="1h", limit=260)`.
   - Assert each symbol is fetched exactly once, variants include baseline and candidates, `risk_unit` is reported, and best candidate is selected only when CAGR/Calmar improve and drawdown is not worse than guardrail.

3. `test_compare_strategy_variants_rejects_short_interval_and_does_not_select_overfit_drawdown`
   - Assert `30m` rejected.
   - Use a high-CAGR but excessive-drawdown candidate and assert it is not selected.

4. `test_main_can_emit_strategy_refinement_json_without_orders`
   - Monkeypatch `fetch_klines`.
   - Call CLI `--compare-refinements --symbols BTCUSDT,ETHUSDT --interval 1h --limit 500`.
   - Assert JSON contains `ok=true`, `refinement`, `paper only`, timestamps, and no live/signed/order/secret fields.

## Implementation Steps

1. RED: add tests above and run target tests to verify failure because `compare_strategy_variants` / `--compare-refinements` do not exist.
2. GREEN: add variant config helpers, evidence score calculation, guarded candidate selection, and CLI branch.
3. Docs: update Skill to v1.0.0, add v1.0 workflow reference, update roadmap status/default next step.
4. Verify:
   - `python3 -m unittest tests/test_binance_usds_futures_trend.py -v`
   - `python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py`
   - `git diff --check`
   - real data sample: `scripts/binance_usds_futures_trend.py --compare-refinements --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 1h --limit 500`
5. Independent Review: staged diff review before push; fail closed on secrets/live execution/paid API/<1h intervals/logic errors.
6. Commit and push after review passes.

## Risks / Guardrails

- Do not report candidate backtest output as live returns or proof of target CAGR.
- Do not auto-promote a candidate into scanner defaults in this version.
- Drawdown guardrail: a candidate with materially worse max drawdown is not selected even if CAGR improves.
- No short periods, no paid APIs, no API keys, no real orders.
