---
name: lottery-betting-recommendation
description: 查询当前仍可投注的中国体育彩票官方竞彩足球比赛（五大联赛、其他联赛、杯赛、国家队赛事等），并将真实未过期赔率与 match-prediction 结构化概率结合，计算去抽水市场概率、保守 EV、分数凯利仓位及可选跨场串关。适用于今日竞彩、赔率价值和资金建议；赔率未确认、停售、超期或预测不完整时输出无推荐。
---

# 竞彩足球投注建议

## 强制顺序

1. 先读取并执行 `match-prediction`，为候选比赛生成符合当前统一契约的 `model_prediction` JSON。
2. 拉取当日中国体育彩票官方竞彩快照，验证官方清单核验状态（`official_listing`）与玩法状态（`market_status`）：
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
4. 读取生成的 `*_betting.json` 作为唯一机器结果；Markdown（`*_betting.md`）用于展示。

## 决策与准入规则

- 官方清单确认：`official_listing.status == "confirmed"`，否则直接拒绝整场（`match_not_officially_listed`）。
- 玩法销售确认：`market_status[market] == "open"`，否则安全跳过该玩法（`market_closed` 或 `market_sale_unknown`）。
- 赔率时效校验：赔率快照默认最多 15 分钟（900 秒）；单场赔率观测时间也必须通过相同检查。
- 开球时间容差：预测开球时间与体彩开球时间容差不得超过 15 分钟，防止比赛改期风险。
- 来源凭证验证：预测快照来源状态必须为已验证（`provenance_status == "verified"`）。
- 预测质量门槛：`quality.status == "sufficient"`，历史样本图连通且场地上下文明确。
- 资金与风控：
  - 使用模型概率直接计算 EV，去抽水市场概率仅用于对照。
  - 使用 `conservative_probability = model_probability - haircut` 计算 `ev_low`（风险缓冲）。
  - 默认 `ev_low >= 5%` 且分数凯利为正才进入候选；每场只选保守 EV 最高的一项。
  - 半凯利，单项最高 5%，总敞口最高 20%，未分配资金保留为现金。
  - 串关默认关闭；显式启用时仅组合不同比赛并披露独立性假设。
- “无推荐”是正常结果，严禁降低门槛、生成估算赔率或篡改概率。

## 输出

输出真实赔率、模型概率、保守概率、去抽水市场概率、EV、保守 EV、凯利比例、实际金额、保留现金及完整拒绝记录。提醒用户彩票具有随机性，不承诺收益。

计算方法见 [references/betting-methodology.md](references/betting-methodology.md)。数据字段见 [data-contracts.md](../match-prediction/references/data-contracts.md)。
