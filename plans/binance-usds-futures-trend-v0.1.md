# Binance USDS Futures Trend Paper Decision v0.1

Created: UTC 2026-06-15 09:05:43 / 北京时间(UTC+8) 2026-06-15 17:05:43

## Objective

建立一个最小可验证的 Binance USDS-M 合约趋势跟随 paper 决策基线：只使用免费公开 K 线数据，周期不低于 1h，不下真实订单。

## Scope

- Symbol universe: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, LINKUSDT, AVAXUSDT, ADAUSDT, LTCUSDT, TRXUSDT, DOTUSDT, POLUSDT, BCHUSDT, APTUSDT, ARBUSDT, OPUSDT, SUIUSDT, INJUSDT, ATOMUSDT.
- Data: Binance Futures public K-line endpoint `/fapi/v1/klines`.
- Intervals: >= 1h only.
- Mode: paper only.

## v0.1 Logic

- EMA50 / EMA200 主趋势过滤。
- ATR14 风险与分批收割参考。
- `close > EMA200` 且 `EMA50 > EMA200`：`hold_long`。
- 趋势中如果价格相对 EMA50 超过 4 ATR，仅降低 paper size，不提前退出。
- 趋势过滤失败：`flat`。

## Files

- `scripts/binance_usds_futures_trend.py`
- `tests/test_binance_usds_futures_trend.py`
- `skills/crypto-trading/binance-usds-futures-trend/SKILL.md`

## Verification

- Unit tests: `python3 -m unittest tests/test_binance_usds_futures_trend.py -v`
- Real free-data check: `scripts/binance_usds_futures_trend.py --symbol BTCUSDT --interval 1h --limit 240`

## Next Steps

1. 批量扫描全部 20 个交易标的。
2. 增加 4h + 1d 多周期趋势一致性。
3. 增加 paper 状态记录、回撤约束、风险预算。
4. 至少完成 paper 验证后，再单独设计 Binance testnet/live execution Skill。
