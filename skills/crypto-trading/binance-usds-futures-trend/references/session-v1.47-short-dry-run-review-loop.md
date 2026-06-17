# Session v1.47 — short dry-run review loop and safety fixes

Use this reference when extending the Binance USDS-M trend engine from long/flat into bidirectional dry-run behavior.

## Durable lessons

- Treat `hold_short` as a first-class signal only after verifying every layer: signal, sizing, strategy intent, execution reconciliation, broker simulation, protection validation, runtime evidence, and tests.
- Signed testnet short exposure must have a separate explicit gate from `--testnet-submit-signed`. Dry-run short support is not authorization to place signed short orders.
- When `add_allowed=false` and the desired exposure crosses direction, reconcile only toward flat. Do not flip from long to short or short to long in one cycle.
- If a cross-direction target is clipped to flat, do not generate protective orders from the opposite-side signal. The opposite signal's SL/TP prices are semantically wrong for the current exposure.
- Paper and testnet dry-run must both model negative exposure correctly:
  - paper short entry: `SELL` simulated fill with negative position size;
  - testnet dry-run short entry: `SELL` market entry with `BUY` stop-loss and `BUY` take-profit protection;
  - short entry price must be recorded just like long entry price.
- Independent review is valuable before commit/push. In this session review found two blockers that tests initially missed: signed short could be enabled too broadly, and cross-direction clipping could create wrong protective orders.

## Recommended verification probes

- Full test and syntax check:
  - `python3 -m unittest tests/test_binance_usds_futures_trend.py -v`
  - `python3 -m py_compile scripts/binance_usds_futures_trend.py scripts/binance_trend_core/*.py tests/test_binance_usds_futures_trend.py`
  - `git diff --check`
- Real dry-run smoke tests:
  - scan with `--no-save-state --no-save-lifecycle`;
  - paper cycle with `--no-save-runtime-record`;
  - testnet dry-run with `--testnet-dry-run --no-save-runtime-record`.
- Synthetic bidirectional probe: create one long, one flat, and one short signal in the shared loop and assert `real_orders_submitted=false` while short produces `SELL` entry plus `BUY` SL/TP.
- Cross-direction add-block probe: current long `0.4`, desired short `-1.0`, `add_allowed=false`, signal includes short SL/TP; expected result is only `SELL MARKET 0.4`, `effective_desired_exposure=0.0`, and no protective orders.

## Tests to keep when refactoring

- `test_generates_hold_short_decision_in_strong_downtrend`
- `test_account_risk_sizing_supports_short_stop_above_entry`
- `test_trend_participation_strategy_maps_hold_short_to_negative_exposure`
- `test_paper_execution_engine_turns_intents_into_broker_instructions`
- `test_position_reconciliation_execution_engine_plans_short_delta_and_buy_protection`
- `test_position_reconciliation_blocks_new_short_adds_when_signal_disallows_add`
- `test_position_reconciliation_add_blocker_never_crosses_through_flat`
- `test_testnet_broker_dry_run_tracks_short_entry_price`
- `test_run_testnet_trading_cycle_blocks_signed_short_by_default`
- `test_verify_position_protection_supports_safe_short_buy_protection`
