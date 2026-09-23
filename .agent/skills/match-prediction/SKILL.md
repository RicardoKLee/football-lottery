---
name: match-prediction
description: 预测英超、西甲、德甲、意甲或法甲的俱乐部比赛。使用稳定球队 ID、历史赛果、主场 ELO、动态联赛进球基准、近期攻防和泊松比分分布生成结构化 JSON。适用于用户请求五大联赛胜平负、比分、总进球或赛前概率分析；不用于国家队、杯赛或没有可追溯数据的比赛。
---

# 五大联赛比赛预测

## 强制边界

- 只处理 `PL`、`PD`、`BL1`、`SA`、`FL1`。
- 使用 provider 稳定 `team_id` 和 `match_id`；名称只允许严格别名匹配。
- 把 `model_prediction` JSON 作为唯一机器结果。不得让下游解析 Markdown。
- 不得使用静态年龄、固定身价、国家队评级、主观十因子总分或无法追溯的默认值补数据。
- 数据不足时输出 `quality.status=insufficient`，停止投注推荐。

## 参考资料路由

- 实现或核对公式时读取 [references/model-methodology.md](references/model-methodology.md)。
- 生成或消费 JSON 时读取 [references/data-contracts.md](references/data-contracts.md)。
- 选择或引用外部数据时读取 [references/data-sources.md](references/data-sources.md)。
- 调整参数或声称模型改善前读取 [references/backtesting.md](references/backtesting.md)。
- 输出来源列表时读取 [references/citation-guide.md](references/citation-guide.md)。

## 工作流

1. 明确联赛代码、开球 UTC、主客队 provider ID，以及对应的竞彩 `match_id`。
2. 获取当前赛季球队注册表。实时调用需要 `FOOTBALL_DATA_API_TOKEN`：

   ```bash
   python3 scripts/fetch_match_data.py --competition PL --list-teams
   ```

3. 生成预测 JSON。把竞彩中文名作为显式别名传入：

   ```bash
   python3 scripts/fetch_match_data.py \
     --competition PL \
     --home-team 65 \
     --away-team 66 \
     --home-alias "竞彩主队名" \
     --away-alias "竞彩客队名" \
     --kickoff "2026-08-25T19:00:00Z" \
     --lottery-match-id "sporttery:1001" \
     --output "output/predictions/PL_1001.json"
   ```

4. 离线开发时只能通过 `--history-file` 显式指定赛果快照。不得自动寻找或复用缓存。
5. 检查 `data_snapshot`、`quality`、两队历史场次数和 `calibration_status`。任一关键条件不满足时明确说明无法形成可靠预测。
6. 如需模拟参数不确定性，只把模型已经计算的 xG 传给模拟器，并固定 seed 以便复现：

   ```bash
   python3 scripts/simulate_stochastic_prediction.py \
     --home "主队" --away "客队" --home-xg 1.60 --away-xg 1.05 --seed 42
   ```

7. 面向用户输出胜平负概率、期望进球、最高概率比分、总进球分布、数据质量和来源。明确区分模型输出与未经模型吸收的伤停、预计首发等赛前信息。

## 质量规则

- 概率分布必须各自和为 1。
- 预测快照必须早于开球时间，历史比赛不得包含未来赛果。
- 不把蒙特卡洛采样次数作为准确性证据。
- 不声称模型优于市场，除非按 backtesting 参考完成走步验证。

