# Binance USDS Futures Trend Paper Decision v0.2

Created: UTC 2026-06-15 09:27:59 / 北京时间(UTC+8) 2026-06-15 17:27:59

## Objective

在 v0.1 EMA50/EMA200 + ATR 趋势 paper 决策基础上，加入 Binance USDS-M 免费公共合约因子，提升趋势参与信心评估，但不因为二级因子过早退出主趋势。

## Added Free Factors

来自本地 `binance-skills-hub` 的 USDS-M Futures 参考：

- Mark Price Kline: `/fapi/v1/markPriceKlines`
- Funding Rate: `/fapi/v1/fundingRate`
- Open Interest History: `/futures/data/openInterestHist`
- Global Long/Short Account Ratio: `/futures/data/globalLongShortAccountRatio`
- Taker Buy/Sell Ratio: `/futures/data/takerlongshortRatio`

## Guardrails

- 周期仍然必须 >= 1h。
- 仍然是 paper only，不下真实订单。
- 不需要付费 API。
- 不读取或暴露 `.env` 中密钥值。
- 二级因子只调整 `confidence_score` 和 `position_size`，不覆盖主趋势过滤。

## v0.2 Logic

1. K-line 主趋势过滤：`close > EMA200` 且 `EMA50 > EMA200`。
2. 主趋势通过时保持 `hold_long`。
3. 二级因子：
   - mark trend 背离：降低信心。
   - funding 极端：降低信心。
   - OI 扩张：提高信心；OI 收缩：降低信心。
   - long/short 过度拥挤：降低信心。
   - taker buy pressure：提高信心；sell pressure：降低信心。
4. `confidence_score` 限制在 `0.25 ~ 1.25`。
5. `position_size = risk_unit * extension_multiplier * confidence_score`。

## Verification

- Unit tests: `python3 -m unittest tests/test_binance_usds_futures_trend.py -v`
- Real free-data check: `scripts/binance_usds_futures_trend.py --symbol BTCUSDT --interval 1h --limit 240 --context-limit 30`

## Next Steps

1. 批量扫描全部 20 个交易标的。
2. 增加 4h + 1d 多周期趋势一致性。
3. 增加 paper 状态记录、回撤约束、风险预算。
4. 增加因子历史回测，验证 confidence/size 调整是否改善 CAGR/回撤。
5. 至少完成 paper 验证后，再单独设计 Binance testnet/live execution Skill。
