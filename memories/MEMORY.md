当前 Hermes profile 的工作目录是 /root/.hermes/profiles/crypto-trade-hermes；用户希望该目录作为 crypto-trade-hermes 项目的 git 根目录。
§
用户的远程仓库是 https://github.com/t734070824/crypto-trade-hermes.git；服务器 SSH keys 已配置，可拉取项目到工作目录。
§
用户计划使用 Skills 进行 Binance 合约实时交易；不使用收费 API；可组合 K 线和其他免费数据源。
§
交易标的范围：BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, LINKUSDT, AVAXUSDT, ADAUSDT, LTCUSDT, TRXUSDT, DOTUSDT, POLUSDT, BCHUSDT, APTUSDT, ARBUSDT, OPUSDT, SUIUSDT, INJUSDT, ATOMUSDT。
§
交易目标：获取 CAGR 30%，并追求 CAGR 100%。
§
交易数据周期偏好：不要使用 1min、5min、10min、30min 等短周期；至少使用大于等于 1h 的周期数据。
§
在 crypto-trade-hermes profile 中，config.yaml、plan/、plans/ 已纳入仓库提交范围；任何可能修改已跟踪或可提交文件的操作（memory、skill_manage、write_file、patch、cron/home/hooks/plan/plans/config 文件生成或修改等）之后，应先检查 git 状态；若出现符合仓库策略的变更，应提交并 push。
§
实时交易策略目标偏好：在主趋势中持续参与、持续持有、持续收割；策略设计应优先避免过早离场，保持趋势跟随与分批收割能力。
§
Binance 相关 API 密钥配置在当前 profile 的 .env 中，变量名为 LALA_KEY 和 LALA_SECRET；不要暴露密钥值，后续如需 Binance auth 应读取这两个变量或映射为 Binance 客户端所需变量。
§
后续所有 git 提交流程在 push 之前，必须先用独立 agent 进行审核；审核不通过时，根据审核意见修改并再次审核，循环直到审核通过后才允许 push。
