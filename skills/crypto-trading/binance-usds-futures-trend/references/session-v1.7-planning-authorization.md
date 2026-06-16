# v1.7 Testnet Adapter Planning and Authorization Boundary

Created from session learning: when the roadmap marks v1.7 Binance Futures Testnet Adapter as locked behind explicit authorization, a user choosing “1.7” after being offered “v1.7 planning only” authorizes planning, not signed execution implementation.

## Durable workflow lesson

- If the user says “1.7” in response to a planning-only option, create/update a concrete implementation plan but do not write signed-order code yet.
- Before implementing `BinanceTestnetBroker` or any signed endpoint path, ask for explicit authorization in plain language: “允许我编写 testnet signed execution adapter 代码，但仍不执行 live/mainnet。”
- Keep v1.7 planning focused on safety boundaries:
  - testnet-only base URL;
  - no mainnet/live endpoint path;
  - credentials resolved from `LALA_KEY` / `LALA_SECRET` without printing values;
  - dry-run signs/submits nothing;
  - risk caps and kill switch before signing/submission;
  - runtime evidence redacts sensitive order/account fields;
  - `<1h` interval rejection still happens before broker execution.
- Treat this as a workflow guardrail, not a permanent block on v1.7 implementation. Once the user explicitly authorizes testnet signed execution adapter code, proceed with strict TDD and independent review before push.

## Suggested first implementation tests

- testnet broker uses testnet base URL only;
- missing credentials fail closed;
- dry-run never signs or submits;
- risk cap blocks oversized orders before signing;
- runtime record redacts sensitive fields;
- shared loop can swap paper/testnet broker without changing strategy logic;
- short intervals are rejected before broker execution.
