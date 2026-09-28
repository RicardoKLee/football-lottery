# 数据契约

实际 JSON Schema 位于项目根目录 `schemas/`。本项目执行单一统一契约，不维护向后兼容历史版本的读取分支。

## ModelPrediction

- `kind`：固定为 `model_prediction`。
- `model`：通用模型名（`football-elo-poisson`）、版本、完整参数和校准状态。
- `match`：稳定比赛 ID、任意赛事代码、赛事名称、开球 UTC、主客队稳定 ID、别名以及标准 `context`：
  - `team_type`：`club` 或 `national`；
  - `competition_type`：`league`、`cup`、`other` 或 `unknown`；
  - `venue`：`home`、`neutral` 或 `unknown`；
  - `score_basis`：`regulation`（常规时间 90 分钟非负整数比分）。
- `data_snapshot`：`provider`、`source_url`、`fetched_at`、`provenance_status`（`verified` 或 `unverified`）与 `sample_pool`（包含 `pool_id`、`team_type`、`competition_codes`）。
- `inputs`：历史样本数、赛事进球基准、ELO 和近期攻防。
- `expected_goals`：主客队进球期望（中立场时消除主场优势加成）。
- `probabilities`：HAD、完整比分网格和 TTG。
- `quality`：`sufficient` 或 `insufficient`，以及结构化缺失原因列表。

## OddsSnapshot

- 必须记录抓取时间、赔率观测时间、开球 UTC、销售截止 UTC、销售状态和可用性原因。
- 每场比赛包含 `official_listing`：官方清单核实状态（`status`: `confirmed` 或 `unknown`）、官方来源 URL、观测时间和供应商 ID。
- 每场比赛包含 `market_status`：逐玩法销售状态（`had`、`hhad`、`ttg`、`crs` 必须为 `open`、`closed` 或 `unknown`）。未确认在售的玩法严禁进入评估。
- 估算截止时间必须以 `cutoff_is_estimated=true` 披露。

## BetEvaluation

- `probability`：模型概率。
- `conservative_probability`：模型概率减去显式风险缓冲（非统计置信下界）。
- `market_probability`：去抽水市场概率，仅用于对照。
- `ev` 与 `ev_low`：原始和保守 EV。
- `kelly_fraction`、`raw_stake`、`stake`：资金计算轨迹。
- `rejections`：所有安全关闭和未推荐原因（包括 `match_not_officially_listed`、`market_closed` 等）。
