# Session v0.4 Multi-Timeframe Workflow

Use this reference when extending the Binance USDS-M trend-following paper scanner from multi-symbol ranking to multi-timeframe confirmation.

## Durable workflow learned

1. Keep the single-symbol decision function as the source of truth:
   - validate symbol and interval first;
   - reject intervals below 1h;
   - generate `paper` decisions only.
2. Add multi-timeframe behavior as an enrichment layer around the primary interval decision.
3. For v0.4, treat `1h` as the primary interval and `4h/1d` as higher-timeframe confirmation.
4. Preserve user reporting requirements in batch mode:
   - include UTC timestamp;
   - include 北京时间（UTC+8） timestamp;
   - output a compact Chinese `summary_zh` alongside machine-readable JSON.
5. Keep rankings readable:
   - `strong_confirmed_trends`: primary trend plus higher-timeframe confirmation;
   - `early_trends`: primary trend active but higher timeframes not fully aligned;
   - `conflicting_trends`: lower and higher timeframes disagree.
6. Keep CLI compatibility:
   - single-symbol mode still uses `--symbol` and `--interval`;
   - batch multi-timeframe mode uses `--intervals 1h,4h,1d`.
7. Before push in this profile:
   - run unit tests and py_compile;
   - run a real free Binance public-data scan if network is available;
   - run static security scan over added lines;
   - request independent agent review;
   - if review suggestions are applied, rerun tests and request a fresh review on the final diff.

## Verification commands used

```bash
python3 -m unittest tests/test_binance_usds_futures_trend.py -v
python3 -m py_compile scripts/binance_usds_futures_trend.py tests/test_binance_usds_futures_trend.py
scripts/binance_usds_futures_trend.py --all-symbols --intervals 1h,4h,1d --limit 240 --context-limit 30 --top 5
```

## Pitfalls

- Do not let higher-timeframe confirmation hide the original trend decision.
- Do not allow short intervals anywhere in the interval list.
- If the primary interval is valid but higher-timeframe data fails, surface the error clearly instead of silently downgrading to single-timeframe mode.
