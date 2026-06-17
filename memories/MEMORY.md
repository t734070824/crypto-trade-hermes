当前 Hermes profile 工作目录 /root/.hermes/profiles/crypto-trade-hermes 是 crypto-trade-hermes 仓库根；远程仓库为 https://github.com/t734070824/crypto-trade-hermes.git，服务器 SSH keys 已配置。
§
crypto-trade-hermes 目标是用 Hermes Skills 构建 Binance USDS-M 合约实时交易系统；paper/testnet/live 应共享同一套实时交易引擎、状态、风控和执行接口，paper 只是 broker adapter/撮合模拟，不应变成报告型 scanner。
§
交易约束：不使用收费 API；可组合 K 线和其他免费数据源；周期至少 >=1h，不使用 1min/5min/10min/30min 等短周期。
§
交易标的范围：BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, LINKUSDT, AVAXUSDT, ADAUSDT, LTCUSDT, TRXUSDT, DOTUSDT, POLUSDT, BCHUSDT, APTUSDT, ARBUSDT, OPUSDT, SUIUSDT, INJUSDT, ATOMUSDT。
§
交易目标：获取 CAGR 30%，并追求 CAGR 100%；策略偏好是沿主趋势方向持续参与、持续持有、持续收割，避免过早离场；“持续持有”不等于只做多，空头主趋势也可持续持有 short；当前 short 已有信号/风控/执行 dry-run 闭环，但 signed testnet/live short 仍需显式授权和运行证据验证后再启用。
§
用户要求的仓库变更流程：config.yaml、plan/、plans/、memory、skills、cron 等相关变更后检查 git 状态；符合仓库策略的变更提交并 push；push 前经独立 agent 审核通过。
§
Binance API 密钥值属于敏感信息；当前 profile .env 中变量名为 LALA_KEY 和 LALA_SECRET，后续 Binance auth 应读取这些变量或映射为客户端所需变量。
§
crypto-trade-hermes 运行过程中必须记录运行时数据；未来会基于真实运行结果持续评估并进化策略。
§
crypto-trade-hermes 定时任务边界：小时级 testnet 热路径由 no_agent=true 的 script-owned cron 确定性执行；每日 runtime replay 诊断由 agent 型只读任务负责，分析 runtime evidence 和订单 journal，不下单、不取消订单、不泄露密钥。
§
crypto-trade-hermes 的当前仓位语义是：strategy 产出的 position_size 表示目标总持仓，由账户可用保证金/权益与止损距离计算；执行层用 current_exposure 与 desired_exposure 做 delta-only reconciliation，因此已有持仓不会自动再加，除非新的目标总仓位高于当前仓位且增量超过交易所最小下单约束。
§
crypto-trade-hermes 中已结束/亏损订单应作为带归因标签的 runtime evidence 使用：记录交易所最终成交/结束状态，聚合为 closed trades，分析 strategy/risk/execution/protection/testnet anomaly 归因，再决定是否修代码、调整策略候选或沉淀到 Skill。
§
crypto-trade-hermes 当前趋势信号使用已闭合 Binance K 线；major trend 仍以 close > EMA200 且 EMA50 > EMA200 判定 hold_long，但新增 long 由 add_allowed 单独控制：close < EMA50 或最近 6/12 根 K 线斜率为负时 add_allowed=false，执行层阻止正向 delta 加仓，同时允许持有、减仓和保护单修复。