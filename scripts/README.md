# 脚本说明

- 受众：维护和调用数据、预测与投注工具的开发者
- 前置条件：Python 3.9+；从项目根目录运行命令

## `match_context.py`

管理比赛上下文标准与规范化。提供 `validate_context`、`context_reasons` 以及跨系统无冲突的稳定标识符生成器 `stable_id(provider, raw_id)`。定义 `team_type`（club/national）、`competition_type`（league/cup/other）、`venue`（home/neutral）与 `score_basis`（regulation）的枚举规则。

## `history_adapter.py`

负责历史比赛标准化与数据完整性审计。确保比分为常规时间 90 分钟非负整数（剔除加时点球），校验俱乐部与国家队样本池隔离，并在目标比赛开球前构建历史图连通性检查（避免前视偏差）。

## `contracts.py`

提供时间格式检验、名称规范化、JSON 安全原子读写以及 `model_prediction`、`odds_snapshot` 的运行时严格契约校验。

## `model_core.py`

通用足球 ELO 与双泊松进球模型核心（`football-elo-poisson`）。支持任意赛事代码、中立比赛双向主场优势消除、动态主客场进球基准以及多维度质量拒绝原因合并。

## `fetch_match_data.py`

对接外部数据源（如 football-data.org）或显式读取 `--history-file`。开放任意赛事代码，支持指定 `--competition-name`、`--team-type`、`--competition-type`、`--venue`、`--season` 等上下文参数，生成标准化预测 JSON。

```bash
# 欧洲俱乐部比赛
python3 scripts/fetch_match_data.py --competition PL --season 2026 --home-team 65 --away-team 66 \
  --kickoff "2026-08-25T19:00:00Z" --output output/predictions/match.json

# 离线其他赛事（如中立场）
python3 scripts/fetch_match_data.py --competition J1 --competition-name "日职联" \
  --venue neutral --history-file data/j1_history.json \
  --home-team "fixture:Alpha" --away-team "fixture:Beta" \
  --kickoff "2026-09-13T12:00:00Z" --season 2026 --output output/predictions/j1.json
```

## `fetch_lottery_data.py`

抓取并标准化中国体育彩票官方竞彩足球列表。记录 `official_listing`（官方清单核实状态）与 `market_status`（HAD/HHAD/TTG/CRS 玩法销售状态），绝不推断未核实的在售状态。

```bash
python3 scripts/fetch_lottery_data.py --date "2026-08-25" --available-only
```

## `generate_betting_recommendation.py`

纯数学计算模块：逐玩法准入检查（`market_reasons`）、预测准入检查（`recommendation_reasons`）、去抽水概率计算、保守 EV、凯利仓位计算、资金分配、跨场串关与“竞彩足球投注分析”Markdown 报告渲染。

## `generate_betting_recommendation_strict.py`

正式投注报告编排入口。严格执行 15 分钟赔率时效与 15 分钟开球容差校验，未确认在售或停售玩法直接拒绝，同时输出 JSON 机器结果与 Markdown 读者报告。

## `simulate_stochastic_prediction.py`

对既有 xG 注入可复现的对数正态扰动。在没有观测参数时不模拟红牌、点球、裁判或天气事件。

```bash
python3 scripts/simulate_stochastic_prediction.py \
  --home "主队" --away "客队" --home-xg 1.6 --away-xg 1.0 --seed 42
```

## `backtest_model.py`

通用赛事走步回测引擎。按比赛时间递进，严格杜绝未来数据泄漏，支持上下文透传与中立场基线评测，输出统一的 `football_elo_poisson` 模型指标。

```bash
python3 scripts/backtest_model.py \
  --competition J1 --history-file data/j1_history.json \
  --output output/backtests/J1.json
```
