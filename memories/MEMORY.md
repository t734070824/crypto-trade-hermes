当前 Hermes profile 工作目录 /root/.hermes/profiles/crypto-trade-hermes 是 crypto-trade-hermes 仓库根；远程仓库为 https://github.com/t734070824/crypto-trade-hermes.git，服务器 SSH keys 已配置。
§
crypto-trade-hermes 目标是用 Hermes Skills 构建 Binance USDS-M 合约实时交易系统；paper/testnet/live 应共享同一套实时交易引擎、状态、风控和执行接口，paper 只是 broker adapter/撮合模拟，不应变成报告型 scanner。
§
交易约束：不使用收费 API；可组合 K 线和其他免费数据源；周期至少 >=1h，不使用 1min/5min/10min/30min 等短周期。
§
交易标的范围：BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, LINKUSDT, AVAXUSDT, ADAUSDT, LTCUSDT, TRXUSDT, DOTUSDT, POLUSDT, BCHUSDT, APTUSDT, ARBUSDT, OPUSDT, SUIUSDT, INJUSDT, ATOMUSDT。
§
交易目标：获取 CAGR 30%，并追求 CAGR 100%；策略偏好是在主趋势中持续参与、持续持有、持续收割，避免过早离场。
§
用户要求的仓库变更流程：config.yaml、plan/、plans/、memory、skills、cron 等相关变更后检查 git 状态；符合仓库策略的变更提交并 push；push 前经独立 agent 审核通过。
§
Binance API 密钥值属于敏感信息；当前 profile .env 中变量名为 LALA_KEY 和 LALA_SECRET，后续 Binance auth 应读取这些变量或映射为客户端所需变量。
§
crypto-trade-hermes 运行过程中必须记录运行时数据；未来会基于真实运行结果持续评估并进化策略。
§
用户强调 crypto-trade-hermes 的定时任务应服务于“用 Hermes Skills 构建 Binance USDS-M 合约实时交易”的总目标；偏好由一个加载 binance-usds-futures-trend Skill 的 agent 型 cron 处理 testnet 交易全流程，no_agent 脚本型 cron 只能定位为 runtime evidence collector。