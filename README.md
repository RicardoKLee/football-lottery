# 五大联赛竞彩足球预测与投注分析

- 受众：需要查询英超、西甲、德甲、意甲或法甲比赛概率和竞彩价值的使用者
- 前置条件：Python 3.9+；实时俱乐部数据需要 football-data.org v4 token；实时投注分析需要访问中国体彩网接口

本项目使用俱乐部历史赛果建立主场 ELO 和动态进球参数，生成结构化比赛概率，再与真实、未过期且仍在售的竞彩赔率计算保守 EV 和凯利仓位。数据不完整时系统返回拒绝原因，不生成模拟赔率。

## 支持范围

| 联赛 | football-data.org 代码 |
|---|---|
| 英超 | `PL` |
| 西甲 | `PD` |
| 德甲 | `BL1` |
| 意甲 | `SA` |
| 法甲 | `FL1` |

## 1. 查询仍可投注的比赛

```bash
python3 scripts/fetch_lottery_data.py \
  --date "2026-08-25" \
  --available-only \
  --output "output/odds/20260825.json"
```

输出保存抓取时间、赔率观测时间、开球时间、销售截止时间、销售状态和拒绝原因。文件快照不会被自动加载。

## 2. 获取俱乐部稳定 ID

```bash
export FOOTBALL_DATA_API_TOKEN="your-token"
python3 scripts/fetch_match_data.py --competition PL --list-teams
```

## 3. 生成比赛预测

```bash
python3 scripts/fetch_match_data.py \
  --competition PL \
  --home-team 65 \
  --away-team 66 \
  --home-alias "曼城" \
  --away-alias "曼联" \
  --kickoff "2026-08-25T19:00:00Z" \
  --lottery-match-id "sporttery:1001" \
  --output "output/predictions/PL_1001.json"
```

`quality.status=insufficient` 表示历史场数不满足门槛。此状态可以用于检查模型输出，但不能产生投注建议。

## 4. 生成投注报告

```bash
python3 scripts/generate_betting_recommendation_strict.py \
  --date "2026-08-25" \
  --predictions output/predictions \
  --lottery-file "output/odds/20260825.json"
```

默认规则：赔率最多 15 分钟、预测数据最多 24 小时、概率折减 3%、保守 EV 至少 5%、单项仓位不超过 5%、总敞口不超过 20%。串关默认关闭，可用 `--include-parlays` 显式启用跨场 2 串 1。

输出包括：

- `output/YYYYMMDD_betting.json`：唯一机器结果；
- `output/YYYYMMDD_betting.md`：由 JSON 渲染的读者报告。

## 5. 走步回测

```bash
python3 scripts/backtest_model.py \
  --competition PL \
  --history-file "data/PL_history.json" \
  --output "output/backtests/PL.json"
```

回测按比赛时间推进，只使用目标比赛之前的数据，并同时报告当前模型与简单主场 ELO 基线的 Log Loss、Brier、RPS 和 ECE。没有历史赔率时不会输出 ROI 或 CLV。

## 离线开发

`fetch_match_data.py --history-file FILE` 可以读取显式历史赛果快照。`fetch_lottery_data.py --input FILE` 可以解析显式赔率快照。正式建议仍执行相同的来源、销售状态和新鲜度检查；文件缺少销售状态时会错误关闭。

## 架构与契约

- [计算流程](process.md)
- [架构决策](docs/adr/0001-club-league-data-contracts.md)
- [预测 JSON Schema](schemas/model-prediction.schema.json)
- [赔率 JSON Schema](schemas/odds-snapshot.schema.json)
- [投注报告 JSON Schema](schemas/betting-report.schema.json)
- [回测报告 JSON Schema](schemas/backtest-report.schema.json)

彩票结果具有随机性，模型输出和正 EV 估计都不保证收益。
