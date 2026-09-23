# 脚本说明

- 受众：维护和调用数据、预测与投注工具的开发者
- 前置条件：Python 3.9+；从项目根目录运行命令

## `contracts.py`

提供时间、名称标准化、JSON 读写以及 `model_prediction`、`odds_snapshot` 的运行时校验。所有正式数据路径应先通过这里的契约检查。

## `model_core.py`

实现五大联赛白名单、历史比赛标准化、稳定球队解析、主场 ELO、动态进球参数、双泊松比分网格及预测 JSON。默认参数标记为待走步回测基线。

## `fetch_match_data.py`

对接 football-data.org v4，或读取显式 `--history-file`。支持列出球队 ID 和为指定俱乐部比赛生成预测。

```bash
python3 scripts/fetch_match_data.py --competition PL --list-teams
python3 scripts/fetch_match_data.py --competition PL --home-team 65 --away-team 66 \
  --kickoff "2026-08-25T19:00:00Z" --output output/predictions/match.json
```

## `fetch_lottery_data.py`

拉取并标准化中国体彩当前竞彩足球列表。脚本不自动加载缓存，输出包含销售状态、截止时间和赔率观测时间。

```bash
python3 scripts/fetch_lottery_data.py --date "2026-08-25" --available-only
```

## `generate_betting_recommendation.py`

纯计算模块：去抽水概率、HAD/HHAD/TTG/CRS 评估、保守 EV、凯利仓位、资金分配、可选跨场串关和 Markdown 渲染。该模块不访问网络，也不生成赔率。

## `generate_betting_recommendation_strict.py`

正式编排入口。读取预测 JSON 和实时或显式赔率快照，执行新鲜度、销售状态、球队映射和预测质量检查，然后同时输出 JSON 与 Markdown 报告。

## `simulate_stochastic_prediction.py`

对既有 xG 注入可复现的对数正态扰动。没有观测参数时不模拟红牌、点球、裁判或天气事件。

```bash
python3 scripts/simulate_stochastic_prediction.py \
  --home "主队" --away "客队" --home-xg 1.6 --away-xg 1.0 --seed 42
```

## `backtest_model.py`

按比赛时间执行 walk-forward 回测，比较当前模型与简单主场 ELO 基线。输出 Log Loss、Brier、RPS、ECE 和每场训练截止审计，不在缺少历史赔率时生成 ROI。

```bash
python3 scripts/backtest_model.py \
  --competition PL --history-file data/PL_history.json \
  --output output/backtests/PL.json
```
