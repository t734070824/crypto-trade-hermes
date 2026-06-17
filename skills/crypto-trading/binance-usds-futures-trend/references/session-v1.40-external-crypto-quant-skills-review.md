# Session v1.40 — External crypto/quant agent skills review

## Context

Review time: 2026-06-17 08:00:20 UTC / 2026-06-17 16:00:20 北京时间（UTC+8）.

The user asked whether to search the network for cryptocurrency quantitative-trading skills, compare them, and keep a few suitable for the current `crypto-trade-hermes` stage.

Current local stage and constraints:

- market: Binance USDS-M futures;
- current execution stage: deterministic hourly Binance futures **testnet** hot path, plus read-only daily/runtime analyzers;
- data constraint: no paid APIs; free Binance public/signed testnet data is the default source;
- signal interval: `>=1h` only;
- architecture invariant: paper/testnet/live share strategy, risk, state, execution reconciliation, runtime evidence, and observability; divergence stays inside broker adapters/config;
- hot path must remain script-owned / deterministic; external agent skills must not silently replace fixed CLI flags or engine code;
- live/mainnet order placement remains unauthorized.

## Search method

GitHub repository search and raw README/SKILL.md inspection were used. GitHub code search API required authentication, so public repository search plus raw file reads were used instead.

Representative candidates reviewed:

- `marketcalls/vectorbt-backtesting-skills` — VectorBT backtesting agent skills;
- `hummingbot/skills` — Hummingbot connector/trading infrastructure skills;
- `aicoincom/coinos-skills` — AiCoin market, Freqtrade, CEX trading, on-chain/Hyperliquid skills;
- `Senpi-ai/senpi-skills` — Hyperliquid autonomous trading runtime and strategy skills;
- `mirror29/openfinclaw-cli` — hosted quant-research/backtest/paper-trade agent skill;
- `algoderiv/agent-skills` — China quant skills including NautilusTrader developer docs;
- `elfa-ai/claude-ai-trading-skill` and `Vyntral/arkham-intelligence-claude-skill` — social/on-chain intelligence API skills;
- `roman-rr/trading-skills`, `GMGNAI/gmgn-skills`, `gate/gate-for-ai` — live crypto signal/trading infrastructure skills.

## Evaluation criteria

A candidate is useful only if it helps current work without weakening constraints:

1. works with or can inform Binance USDS-M futures, not only spot/DEX/on-chain swaps;
2. supports backtest/replay/research without forcing live execution;
3. can use free or already-available data, or can be treated as design reference without API dependency;
4. respects `>=1h` signal intervals;
5. strengthens risk controls, exchange-rule discovery, order lifecycle, reconciliation, or runtime evidence;
6. can be isolated from the hourly signed testnet hot path unless intentionally integrated and tested;
7. has clear license/source and does not require blindly trusting hosted signals.

## Shortlist to keep as references

### 1. VectorBT backtesting skills — keep as a research/backtest pattern reference

Source: `marketcalls/vectorbt-backtesting-skills`

Useful ideas:

- agent-oriented workflow for generating reproducible backtest scripts;
- compare multiple strategies on the same data sample;
- produce side-by-side metrics and equity curves;
- separate setup/backtest/strategy-compare skills;
- explicit transaction cost assumptions and benchmark comparisons.

How it maps to this repo:

- Good fit for **offline strategy research and replay tooling**.
- Do not directly import its OpenAlgo/TA-Lib/Indian-market defaults.
- If used, adapt the pattern to our captured Binance runtime evidence and free Binance K-lines; never fetch fresh samples during runtime replay.
- Best future use: build a local strategy-comparison reference that evaluates candidate trend variants on identical captured `state/*runtime.jsonl` market inputs.

Decision: **keep as reference, not as runtime dependency**.

### 2. Hummingbot connector/rule skills — keep exchange-rule and connector-discovery ideas

Source: `hummingbot/skills`

Useful ideas:

- `connectors-available` skill fetches/searches trading rules such as min order size, tick size, supported order types;
- Hummingbot skill set separates connector discovery, core bot operations, arbitrage discovery, deployment, and development;
- emphasizes checking real connector availability before assuming an exchange/pair is tradable.

How it maps to this repo:

- Strong conceptual overlap with our Binance `exchangeInfo` preflight, minQty/stepSize/minNotional validation, and testnet endpoint safety.
- Useful as a design reference for richer exchange-rule reporting and future cross-exchange research.
- Not a fit for the hourly hot path unless we intentionally adopt Hummingbot infrastructure; current engine already has a direct Binance testnet broker and should stay simpler.

Decision: **keep as reference for exchange-rule and connector discovery patterns, not as a bot replacement**.

### 3. AiCoin market/Freqtrade skills — keep limited watch/reference status

Source: `aicoincom/coinos-skills`

Useful ideas:

- `aicoin-market` exposes market data, K-lines, funding, open interest, long/short ratios, liquidation, order book, news/social endpoints;
- `aicoin-freqtrade` separates bot daemon control from strategy/backtest deployment and warns not to spawn competing bot processes;
- `aicoin-trading` has strong confirmation-before-order safety language for CEX trading.

Fit and concerns:

- Some endpoints may have free built-in/key-limited access, but this is still a third-party API surface and should not become a hidden dependency for our no-paid-API Binance system.
- `aicoin-trading` is too broad and can place CEX orders; do **not** install or route testnet/live execution through it.
- Freqtrade is useful as a design comparison for strategy/backtest/dry-run separation, but our architecture already uses a custom shared engine and Binance testnet adapter.

Decision: **keep only as optional market-data/backtest architecture reference; do not install trading skill; do not add to hot path**.

### 4. Senpi trading runtime — keep DSL/risk/producer design ideas only

Source: `Senpi-ai/senpi-skills`

Useful ideas:

- explicit runtime YAML/config separation;
- producer pushes external signals into a runtime;
- declarative risk guard rails, daily caps, drawdown halts, and exit engine/trailing-stop phases;
- position tracker checks positions opened manually or by other tools.

Fit and concerns:

- It targets Hyperliquid/Senpi, not Binance USDS-M futures.
- It is designed for autonomous deployment on a funded wallet and therefore should not be installed into this repo's execution path.
- The design vocabulary is useful for future local config schemas: risk guard rails, producer/runtime boundary, and external/manual-position reconciliation.

Decision: **keep as architecture reference for risk DSL and producer/runtime boundary only**.

### 5. NautilusTrader / Freqtrade / OpenFinClaw — monitor, but not current shortlist for integration

Sources: `algoderiv/agent-skills` NautilusTrader docs, `aicoin-freqtrade`, `mirror29/openfinclaw-cli`.

- NautilusTrader is a serious trading engine, but adopting it would be a major architecture migration. Current priority is stabilizing the existing shared engine and testnet evidence chain.
- Freqtrade is useful for dry-run/backtest operational patterns, but it is mainly spot/perp bot infrastructure and would duplicate local engine responsibilities.
- OpenFinClaw depends on a hosted key/service for DeepAgent research/backtests and should not become a required component under the no-paid/no-hidden-dependency constraint.

Decision: **monitor only; revisit if the current custom engine becomes too costly to maintain**.

## Candidates rejected for current state

- Live signal feeds such as `roman-rr/trading-skills`: not suitable because they can introduce external opaque trade signals with leverage/SL/TP and may conflict with our own evidence/replay discipline.
- GMGN/Shuriken/Gate/DEX/on-chain swap skills: mostly token discovery, wallet/on-chain swaps, or broad trade infrastructure; not aligned with Binance USDS-M testnet hot path.
- Arkham/Elfa/social-intelligence skills: potentially useful for discretionary context, but they require API keys or paid/x402 access and are not needed for the current >=1h Binance futures engine.

## What to actually keep in this repo

Do not add external skills wholesale. Instead keep this reference and, if future work requires it, create narrowly scoped local references/scripts:

1. `external-backtest-patterns` — adapt VectorBT-style same-sample strategy comparison to local Binance runtime evidence;
2. `exchange-rule-discovery-patterns` — expand our Binance `exchangeInfo` reporting inspired by Hummingbot connector-rule discovery;
3. `risk-runtime-dsl-patterns` — future config design for declarative risk guard rails, drawdown halts, and producer/runtime boundaries inspired by Senpi, implemented locally rather than importing Senpi;
4. optional `third-party-market-data-watchlist` — document AiCoin-style endpoints as non-hot-path, optional, free-tier-only research inputs if later justified.

## Integration boundary

Current recommended action:

- **Do not install** external trading/order-execution skills into the active Hermes profile.
- **Do not route** hourly `testnet-agent-hourly` through external agent skills, hosted signals, Freqtrade, Hummingbot, Senpi, AiCoin trading, or OpenFinClaw.
- Keep the hourly hot path deterministic and script-owned.
- Use external skills only as design references for future local code, with tests and runtime evidence replay before adoption.

## Next practical follow-ups

Highest-value follow-ups for this repo:

1. Add a local runtime-evidence strategy comparison command that evaluates candidate trend variants on identical captured K-line samples, borrowing the VectorBT comparison workflow but not its dependencies.
2. Improve Binance exchange-rule reporting in the hourly summary: minQty, stepSize, minNotional, adapted quantity, and skip/reject reason per symbol.
3. Define a small local risk-config schema for daily loss caps, max drawdown pause, max symbol exposure, and kill switch, inspired by risk-guard-rail patterns but enforced in our own broker/risk layer.
4. Keep third-party data integrations opt-in and read-only until real runtime evidence shows Binance-free data alone is insufficient.
