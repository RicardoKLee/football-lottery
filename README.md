# 竞彩足球预测与投注分析

- 受众：需要查询中国体育彩票官方竞彩足球全部在售赛事（五大联赛、其他俱乐部联赛、杯赛、国家队赛事等）比赛概率和竞彩价值的使用者
- 前置条件：Python 3.9+；单一当前契约；实时俱乐部数据需要 football-data.org v4 token；实时投注分析需要访问中国体彩网官方接口

本项目使用历史赛果建立通用 ELO 与动态进球参数模型（`football-elo-poisson`），生成结构化比赛概率，再与真实、未过期且官方在售的竞彩赔率结合，计算保守 EV 和分数凯利仓位。严格遵循 Fail-Closed 安全关闭原则：数据不完整、来源未核验或停售时系统返回拒绝原因，绝不生成模拟赔率。

## 支持范围与业务边界

1. **业务适用范围**：
   - 以中国体育彩票官方竞彩足球实际在售清单为准；
   - 涵盖全部在售的俱乐部联赛（英超、西甲、德甲、意甲、法甲、日职联、葡超等）、杯赛（如欧冠、足总杯）以及国家队赛事（如世界杯、欧洲杯预选赛）；
   - 支持竞彩足球四项主流玩法：HAD（胜平负）、HHAD（让球胜平负）、TTG（总进球）、CRS（比分）。
2. **排除范围**：
   - 不包含传统足彩（十四场胜负彩、任选九场）；
   - 不包含竞彩篮球；
   - 不提供任何形式的自动代投或自动下单。
3. **数据接入与覆盖限制**：
   - 官方业务范围不等于外部实时 API 的默认覆盖；
   - 实时数据源（如 football-data.org）根据订阅级别通常仅覆盖特定欧洲联赛（如 `PL`, `PD`, `BL1`, `SA`, `FL1`）；
   - 对于非五大联赛（如 `J1`）、杯赛或国家队比赛，支持通过 `--history-file` 提供标准化历史快照，并显式指定 `--season` 以及 `match.context`（`--team-type`, `--competition-type`, `--venue`）。
4. **单一契约与产物重新生成**：
   - 本项目执行单一当前契约，不维护向后兼容历史版本的读取分支；
   - 历史预测与赔率产物需使用最新 CLI 重新生成。

---

## 1. 查询仍可投注的比赛

```bash
python3 scripts/fetch_lottery_data.py \
  --date "2026-08-25" \
  --available-only \
  --output "output/odds/20260825.json"
```

输出保存抓取时间、赔率观测时间、开球时间、销售截止时间、官方清单核实状态（`official_listing`）与玩法销售状态（`market_status`）。文件快照不会被自动信任，未提供合法来源证据时不予采纳。

## 2. 获取球队稳定 ID

```bash
# 实时查询支持的联赛球队（需 API Token）
export FOOTBALL_DATA_API_TOKEN="your-token"
python3 scripts/fetch_match_data.py --competition PL --season 2026 --list-teams

# 或从离线历史数据快照中查看球队
python3 scripts/fetch_match_data.py --competition J1 --history-file "data/synthetic_j1_history.json" --list-teams
```

## 3. 生成比赛预测

### 示例 A：欧洲联赛主客场（实时数据源）

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

### 示例 B：非五大联赛中立场（合成历史离线示例）

```bash
# 显式指定赛事上下文（中立场 neutral、俱乐部 club、联赛 league）
python3 scripts/fetch_match_data.py \
  --competition J1 \
  --competition-name "日职联" \
  --team-type club \
  --competition-type league \
  --venue neutral \
  --history-file "data/synthetic_j1_history.json" \
  --home-team "fixture:Alpha" \
  --away-team "fixture:Beta" \
  --kickoff "2026-09-13T12:00:00Z" \
  --lottery-match-id "sporttery:20260913001" \
  --season 2026 \
  --output "output/predictions/J1_20260913001.json"
```

`quality.status=insufficient` 表示历史场数不足或图不连通。此状态仅用于检查模型输出，不能产生正式投注建议。

## 4. 生成投注报告

```bash
python3 scripts/generate_betting_recommendation_strict.py \
  --date "2026-09-13" \
  --predictions output/predictions \
  --lottery-file "output/odds/20260913.json"
```

默认规则：
- 赔率时效最多 15 分钟（超期拒绝）；
- 预测与开球时间容差最多 15 分钟（防比赛改期）；
- 预测快照数据最多 24 小时；
- 官方未在售（`official_listing.status != confirmed`）或玩法未在售（`market_status != open`）安全跳过；
- 概率折减 3%、保守 EV 至少 5%、单项仓位不超过 5%、总敞口不超过 50%。默认同时输出单关、2 串 1 与 4 串 1 投注建议（支持混合过关，可用 `--no-parlays` 仅输出单关）。

输出包括：
- `output/YYYYMMDD_betting.json`：唯一机器结果；
- `output/YYYYMMDD_betting.md`：由 JSON 渲染的“竞彩足球投注分析”读者报告。

## 5. 走步回测

```bash
python3 scripts/backtest_model.py \
  --competition J1 \
  --history-file "data/synthetic_j1_history.json" \
  --output "output/backtests/J1.json"
```

回测按比赛时间严格递进，仅使用目标比赛开球前的数据（杜绝未来泄漏），并同时报告当前模型（`football_elo_poisson`）与简单主场 ELO 基线的 Log Loss、Brier、RPS 和 ECE。没有历史赔率时不计算 ROI 或 CLV。

## 离线开发与数据规范

- `fetch_match_data.py --history-file FILE` 读取显式历史赛果快照；比分必须为常规时间整数比分（剔除点球/加时）。
- `fetch_lottery_data.py --input FILE` 解析显式赔率快照。
- 声明不构成证明：未核验来源（`provenance_status="unverified"`）在推荐阶段将被安全拒绝。

## 架构与契约

- [计算流程](process.md)
- [来源语义与适配边界](docs/data-mappings.md)
- [架构决策 ADR 0002（全部竞彩适用范围）](docs/adr/0002-sporttery-football-scope.md)
- [历史决策 ADR 0001（被 ADR 0002 替代）](docs/adr/0001-club-league-data-contracts.md)
- [预测 JSON Schema](schemas/model-prediction.schema.json)
- [赔率 JSON Schema](schemas/odds-snapshot.schema.json)
- [投注报告 JSON Schema](schemas/betting-report.schema.json)
- [回测报告 JSON Schema](schemas/backtest-report.schema.json)

彩票结果具有随机性，模型输出和正 EV 估计都不保证收益。
