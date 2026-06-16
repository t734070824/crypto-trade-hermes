# Session v1.25 — Testnet cron endpoint and order-budget audit

## Context

A scheduled single-agent Binance USDS-M Futures testnet cron was instructed to operate only against `https://testnet.binancefuture.com`, including public K-line reads, and to run the conservative startup groups:

- BTC group: `BTCUSDT`, `--risk-unit 0.001`, `--account-risk-fraction 0.003`, `--target-leverage 2`, `--testnet-max-order-count 3`.
- Alt group: `ETHUSDT,SOLUSDT,BNBUSDT`, `--risk-unit 0.1`, `--account-risk-fraction 0.003`, `--target-leverage 2`, `--testnet-max-order-count 6`.
- Shared caps: `--testnet-max-order-notional 1000`, `--testnet-max-symbol-exposure 2000`, `--testnet-max-symbol-exposure-fraction 0.20`, `--testnet-max-daily-loss 10`.

## Durable lessons

1. For strict testnet-only operation, pass both:
   - `--base-url https://testnet.binancefuture.com` for public K-line reads; and
   - `--testnet-base-url https://testnet.binancefuture.com` for signed broker endpoints.

   Do not assume `--run-testnet-cycle` changes the public data base URL by itself.

2. The Telegram-safe summary should explicitly report whether actual accepted/submitted order counts stayed within each group budget. Count exchange-confirmed fills by `status in {submitted, submitted_confirmed}` and separately report attempted real orders. Do not rely on desired-order count or rejected count as proof of compliance.

3. A real run showed a subtle budget issue: the Alt group was configured with `--testnet-max-order-count 6`, but the cycle produced 10 exchange-confirmed submissions plus 3 broker rejections with `max_order_count_exceeded`. This means the current code path can exceed the user's intended group accepted/submitted budget before later rejecting remaining instructions. Treat this as a code defect/risk-control finding, not a successful budget-compliant run.

4. When the plan includes protection repairs, cancellations, entries, and TP tranches, pre-budget the full ordered submission plan before signing. If the configured budget cannot cover required protection work, prefer fail-closed behavior: submit no new exposure-increasing entry/add orders until the protection plan and order budget are reconciled.

5. Continue rebuilding reports from parsed cycle JSON plus fresh signed snapshots. Large raw cycle stdout can exceed 2 MB; never paste it directly into Telegram.

## Suggested fix direction

- Add pre-submit plan budgeting in the shared execution/broker boundary so the configured per-cycle order budget applies to all real signed submissions, not only to late broker-level rejections.
- Prioritize already-open-position protection repairs before entries/add-ons, but still hard-cap total real signed attempts and confirmed submissions to the configured group budget.
- Add regression coverage for: configured max order count N, planned instructions > N, and `exchange_confirmed_count <= N` for signed testnet mode.
