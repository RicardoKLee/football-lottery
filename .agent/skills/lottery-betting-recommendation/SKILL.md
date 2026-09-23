---
name: lottery-betting-recommendation
description: 查询当前仍可投注的英超、西甲、德甲、意甲和法甲竞彩足球比赛，并把真实未过期赔率与 match-prediction 的结构化概率结合，计算去抽水市场概率、保守 EV、分数凯利仓位及可选跨场串关。适用于今日竞彩、赔率价值和资金建议；赔率或预测不完整时输出无推荐。
---

# 五大联赛竞彩足球建议

## 强制顺序

1. 先读取并执行 `match-prediction`，为每场候选比赛生成 `model_prediction` JSON。
2. 拉取当日官方竞彩快照，只保留仍在售且未过截止时间的比赛：

   ```bash
   python3 scripts/fetch_lottery_data.py \
     --date "YYYY-MM-DD" \
     --available-only \
     --output "output/odds/YYYYMMDD.json"
   ```

3. 运行严格推荐入口：

   ```bash
   python3 scripts/generate_betting_recommendation_strict.py \
     --date "YYYY-MM-DD" \
     --predictions output/predictions \
     --lottery-file "output/odds/YYYYMMDD.json"
   ```

4. 读取生成的 `*_betting.json` 作为结果；Markdown 仅用于展示。

## 决策规则

- 赔率快照默认最多 900 秒；单场赔率观测时间也必须通过相同检查。
- 预测质量必须为 `sufficient`，预测数据快照默认不超过 24 小时。
- 使用模型概率直接计算 EV，去抽水市场概率只作为对照。
- 使用 `conservative_probability = model_probability - haircut` 计算 `ev_low`。该值是风险缓冲，不得称为统计置信下界。
- 默认 `ev_low >= 5%` 才进入候选；每场只选保守 EV 最高的一项。
- 使用半凯利，单项最高 5%，总敞口最高 20%。按 2 元向下取整，剩余资金必须保留。
- 串关默认关闭。只有用户明确要求或传入 `--include-parlays` 时，才允许不同 `match_id` 的 2 串 1，并披露独立性假设。
- “无推荐”是正常结果，不得降低门槛、生成赔率或修改概率来制造建议。

## 错误关闭

以下任一条件成立时拒绝对应比赛：

- 赔率抓取失败、快照过期、赔率状态不明或已经停售；
- 截止时间已过，或比赛时间与预测相差超过六小时；
- 球队只能通过包含关系匹配，或映射出现多个候选；
- 预测 JSON 不符合契约、历史样本不足或关键数据缺失；
- 没有选项达到保守 EV 门槛。

## 输出

输出真实赔率、模型概率、保守概率、市场概率、EV、保守 EV、凯利比例、实际金额、保留现金和完整拒绝记录。提醒用户彩票具有随机性，不承诺收益。

计算方法见 [references/betting-methodology.md](references/betting-methodology.md)。数据字段见相邻 skill 的 [data-contracts.md](../match-prediction/references/data-contracts.md)。

