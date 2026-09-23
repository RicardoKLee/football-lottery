# 数据契约

实际 JSON Schema 位于项目根目录 `schemas/`。

## ModelPrediction

- `schema_version`：固定为 `2.0`。
- `kind`：固定为 `model_prediction`。
- `model`：模型名、版本、完整参数和校准状态。
- `match`：稳定比赛 ID、联赛代码、开球 UTC、主客队稳定 ID 和别名。
- `data_snapshot`：provider、source URL 和抓取时间。
- `inputs`：历史样本数、联赛进球基准、ELO 和近期攻防。
- `expected_goals`：主客队进球期望。
- `probabilities`：HAD、完整比分网格和 TTG。
- `quality`：`sufficient` 或 `insufficient`，以及缺失原因。

## OddsSnapshot

- 必须记录抓取时间、赔率观测时间、开球 UTC、销售截止 UTC、销售状态和可用性原因。
- `listed_by_official_api` 只表示比赛刚刚出现在官方实时列表；从文件读取且缺少销售状态时必须标记为不可用。
- 估算截止时间必须以 `cutoff_is_estimated=true` 披露。

## BetEvaluation

- `probability`：模型概率。
- `conservative_probability`：模型概率减去显式风险缓冲；它不是置信下界。
- `market_probability`：去抽水市场概率，仅用于对照。
- `ev` 与 `ev_low`：原始和保守 EV。
- `kelly_fraction`、`raw_stake`、`stake`：资金计算轨迹。
- `rejections`：所有错误关闭和未推荐原因。

