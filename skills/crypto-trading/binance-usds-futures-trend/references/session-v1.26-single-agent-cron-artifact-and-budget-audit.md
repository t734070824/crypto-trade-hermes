# Session v1.26 — Single-agent cron artifact and order-budget audit

## Context

A scheduled single-agent Binance USDS-M Futures Testnet operation ran the required signed preflight, BTC group cycle, Alt group cycle, runtime-evidence replay, and post-run signed snapshot. The report was reconstructed from persisted runtime JSONL, order journal JSONL, replay output, and a fresh signed account snapshot rather than raw stdout.

## Durable lessons

1. **Use the configured evidence paths exactly.** The cron contract expects:
   - `state/binance-usds-futures-trend-testnet-runtime.jsonl`
   - `state/binance-usds-futures-trend-testnet-orders.jsonl`

   If a harness or wrapper accidentally writes similarly named files such as `state/binance-usds-futures-testnet-runtime.jsonl` or `state/binance-usds-futures-testnet-orders.jsonl`, merge/reconcile only after verifying JSONL line validity and then report the canonical `*-trend-*` paths. Prefer preventing the mismatch by passing `--runtime-record-file` and `--testnet-order-journal-file` explicitly to every cycle.

2. **Budget checks must distinguish desired plan size, attempted requests, exchange-confirmed orders, and fills.** In this run, BTC produced 5 desired/submission events while the configured BTC group budget was 3; Alt produced 17 events while its budget was 6. Much of the excess came from protective-order repair activity (cancel stale algo orders, then submit replacement TP/SL legs), not only entry orders. A safe summary should separately report:
   - `desired_orders` count from runtime evidence;
   - attempted real submission count from journal lines;
   - exchange-confirmed count (`submitted`/`submitted_confirmed`, excluding `submitted_unknown`);
   - lifecycle tracked/filled counts and net PnL.

3. **Do not treat `submitted_unknown` as accepted or filled.** Keep it in attempted count only. If confirmation failed, the safe report should say attempted-but-not-exchange-confirmed.

4. **Post-run protection verification must include zero-position symbols.** A zero position with open TP algo orders (for example BNBUSDT had zero position but 2 TAKE_PROFIT_MARKET algo orders) is not proof of protection; it is a stale/orphan-protection anomaly to report or repair under explicit rules.

5. **When final stdout is unavailable or too large, rebuild from durable artifacts.** Runtime JSONL gives desired orders and account-sync/lifecycle summaries; order journal gives attempted/submitted/unknown events; runtime replay gives baseline/candidate/selected; fresh signed snapshot gives current positions/open ordinary orders/open algo counts.

## Suggested safe Chinese report fields

- UTC and 北京时间（UTC+8） for preflight/cycle/replay/snapshot.
- Testnet-only endpoint statement; never mention or print secret values.
- BTC group and Alt group symbols and interval.
- `real_orders_submitted` per group.
- desired/attempted/exchange-confirmed/lifecycle tracked/lifecycle filled counts per group.
- Runtime replay: records loaded, baseline, selected candidate, guardrail flags, errors count.
- Current non-zero positions for BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT.
- Ordinary open-order counts and open-algo STOP/TP counts per selected symbol.
- Runtime record path and order journal path.
- Explicit anomaly notes for budget overrun, `submitted_unknown`, and zero-position symbols with open protective algos.
