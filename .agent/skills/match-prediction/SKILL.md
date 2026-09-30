---
name: match-prediction
description: 预测中国体育彩票官方竞彩足球全部在售赛事（五大联赛、其他俱乐部联赛、杯赛、国家队赛事等）比赛概率。使用稳定球队 ID、常规时间赛果（90分钟整数）、通用 ELO（中立场取消主场优势）、动态联赛进球基准、近期攻防和泊松比分分布生成结构化 JSON。适用于用户请求竞彩足球胜平负、比分、总进球或赛前概率分析；排除传统足彩（十四场/任九）、竞彩篮球或没有可追溯历史数据的比赛。
---

# 竞彩足球比赛预测

## 强制边界

- 支持中国体育彩票官方竞彩足球在售全部赛事，接受任意官方赛事代码；
- 必须包含标准 `match.context`：`team_type`（club/national）、`competition_type`（league/cup/other）、`venue`（home/neutral）、`score_basis`（regulation）；
- 比分必须为常规时间（90分钟含伤停补时）非负整数，加时赛和点球大战一律剔除；
- 中立场（`venue="neutral"`）比赛必须双向取消主客场优势；
- 俱乐部与国家队样本池严格物理隔离；跨赛事样本必须显式声明并校验图连通性；
- 使用 provider 稳定 `team_id` 和 `match_id`；名称只允许严格别名匹配；
- 把 `model_prediction` JSON 作为唯一机器结果，不得让下游解析 Markdown；
- 数据不足、未知或来源未经验证时输出 `quality.status=insufficient` 或拒绝，停止投注推荐。

## 参考资料路由

- 实现或核对公式时读取 [references/model-methodology.md](references/model-methodology.md)。
- 生成或消费 JSON 时读取 [references/data-contracts.md](references/data-contracts.md)。
- 选择或引用外部数据时读取 [references/data-sources.md](references/data-sources.md)。
- 调整参数或声称模型改善前读取 [references/backtesting.md](references/backtesting.md)。
- 输出来源列表时读取 [references/citation-guide.md](references/citation-guide.md)。

## 工作流

1. 明确赛事代码、赛事名称、开球 UTC、主客队 provider ID，以及对应的竞彩 `match_id`。
2. 获取球队稳定 ID：
   - 实时调用支持的联赛球队（需 `FOOTBALL_DATA_API_TOKEN`）：
     ```bash
     python3 scripts/fetch_match_data.py --competition PL --season 2026 --list-teams
     ```
   - 或从显式历史快照中查看球队：
     ```bash
     python3 scripts/fetch_match_data.py --competition J1 --history-file data/j1_history.json --list-teams
     ```
3. 生成预测 JSON。将竞彩中文名作为显式别名传入，并显式指定上下文与赛季：
   ```bash
   python3 scripts/fetch_match_data.py \
     --competition J1 \
     --competition-name "日职联" \
     --team-type club \
     --competition-type league \
     --venue neutral \
     --history-file data/j1_history.json \
     --home-team "fixture:Alpha" \
     --away-team "fixture:Beta" \
     --home-alias "阿尔法" \
     --away-alias "贝塔" \
     --kickoff "2026-09-13T12:00:00Z" \
     --lottery-match-id "sporttery:20260913001" \
     --season 2026 \
     --home-red-cards 0.10 \
     --away-red-cards 0.05 \
     --referee-cards 4.5 \
     --referee-name "主裁判" \
     --output "output/predictions/J1_20260913001.json"
   ```
   注：纪律性数据可通过命令行参数直接传入，或通过 `--disciplinary-file <json>` 批量注入权威数据源（如 FBref/Transfermarkt/WhoScored 的红黄牌均值与裁判尺度）。若未提供则标记为 `unobserved`。
4. 离线开发时只能通过 `--history-file` 显式指定赛果快照。快照必须包含合法来源信息与常规时间整数比分，系统不自动寻找或复用未经验证的缓存。
5. 检查 `data_snapshot`、`quality`、两队历史场次数和 `calibration_status`。任一关键条件不满足时明确说明无法形成可靠预测。
6. 如需模拟参数不确定性，只把模型已经计算的 xG 传给模拟器，并固定 seed 以便复现：
   ```bash
   python3 scripts/simulate_stochastic_prediction.py \
     --home "主队" --away "客队" --home-xg 1.60 --away-xg 1.05 --seed 42
   ```
7. 面向用户输出胜平负概率、期望进球、最高概率比分、总进球分布、数据质量和来源。明确区分模型输出与未经模型吸收的赛前信息。

## 质量规则

- 概率分布必须各自和为 1。
- 预测快照必须早于开球时间，历史样本严禁包含开球时间之后的未来赛果。
- 不把蒙特卡洛采样次数作为准确性证据。
- 不声称模型优于市场，除非按 backtesting 参考完成走步验证。
