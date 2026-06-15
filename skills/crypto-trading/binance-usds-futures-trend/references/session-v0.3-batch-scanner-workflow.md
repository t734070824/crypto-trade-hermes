# Session v0.3 Batch Scanner Workflow

Use this reference when extending the Binance USDS-M trend-following paper scanner beyond single-symbol decisions.

## Durable workflow learned

1. Keep v0.2 single-symbol decision logic as the source of truth:
   - validate symbol and interval first;
   - reject intervals below 1h;
   - generate `paper` decisions only;
   - public context factors adjust confidence/size, not the main trend participation rule.
2. Add portfolio-ranking behavior as an enrichment layer, not by changing the base decision contract.
3. Rank only after each symbol has a complete decision object. Useful fields:
   - `trend_strength`: ATR-normalized distance above EMA200 plus EMA50/EMA200 separation;
   - `extension_atr`: ATR-normalized distance above EMA50;
   - `rank_score`: `trend_strength * confidence_score * position_size`;
   - `ranking_bucket`: `top_trend`, `risk_high_trend`, `watchlist`, or `error`.
4. Preserve user reporting requirements in batch mode:
   - include UTC timestamp;
   - include 北京时间（UTC+8） timestamp;
   - output a compact Chinese `summary_zh` alongside machine-readable JSON.
5. Add input guardrails for ranking parameters:
   - `risk_unit` must be positive;
   - `top` must be `>= 1`;
   - invalid symbols/intervals should fail clearly.
6. Before push in this profile:
   - run unit tests and py_compile;
   - run a real free Binance public-data scan if network is available;
   - run static security scan over added lines;
   - request independent agent review;
   - if low-cost review suggestions are applied, rerun tests and request a fresh review on the final diff.

## Verification commands used

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py
scripts/binance_usds_futures_trend.py --all-symbols --interval 1h --limit 240 --context-limit 30 --top 5
```

## Pitfalls

- Do not let ranking override the main trend-following contract; ranking decides allocation priority, not whether to abandon a valid major trend.
- Do not allow negative or zero `risk_unit`; otherwise sizing and ranking semantics become misleading.
- Do not allow `top < 1`; Python slicing can silently produce surprising output.
- If `top_trends` includes `risk_high_trend` items, document that Top N means strongest trends by rank score, not necessarily lowest-risk candidates.
