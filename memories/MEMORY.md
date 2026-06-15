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