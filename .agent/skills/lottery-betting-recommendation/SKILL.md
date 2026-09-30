---
name: lottery-betting-recommendation
description: 查询当前仍可投注的中国体育彩票官方竞彩足球比赛（五大联赛、其他联赛、杯赛、国家队赛事等），并将真实未过期赔率与 match-prediction 结构化概率结合，计算去抽水市场概率、保守 EV、分数凯利仓位，同时生成单关、2 串 1 与 4 串 1 投注建议（支持混合过关，自动过滤官方未开通单关固定奖的注单并标注说明）。适用于今日竞彩、赔率价值和资金建议；赔率未确认、停售、超期或预测不完整时输出无推荐。
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
3. 运行严格推荐入口（默认包含单关、2 串 1 与 4 串 1 混合过关建议）：
   ```bash
   python3 scripts/generate_betting_recommendation_strict.py \
     --date "YYYY-MM-DD" \
     --predictions output/predictions \
     --lottery-file "output/odds/YYYYMMDD.json" \
     --include-parlays \
     --parlay-legs 2 4
   ```
4. 读取生成的 `*_betting.json` 作为唯一机器结果；Markdown（`*_betting.md`）用于展示。

## 决策与准入规则

- 官方清单确认：`official_listing.status == "confirmed"`，否则直接拒绝整场（`match_not_officially_listed`）。
- 玩法销售确认：`market_status[market] == "open"`，否则安全跳过该玩法（`market_closed` 或 `market_sale_unknown`）。
- 单关销售限制核验与过滤（`single_status`）：
  - 竞彩足球仅对部分比赛及玩法开放单关固定奖（比分 `CRS` 通常全开单关，但胜平负 `HAD`、让球胜平负 `HHAD`、总进球 `TTG` 大多数场次仅限串关过关）。
  - 生成单关建议时，必须严格识别官方快照中的 `single_status`，**自动过滤掉未开通单关固定奖的选项**，严禁向用户推荐终端无法单独出票的单关注单。
  - 对于达到 EV 门槛但被过滤的单关选项，必须在报告中明确标注说明已转入串关，并在拒绝记录中记录 `single_betting_not_allowed`。
  - 这些选项依然具备正期望，应优先保留在串关候选池中，在 **2 串 1** 与 **4 串 1** 混合过关中发挥价值。
- 赔率时效校验：赔率快照默认最多 15 分钟（900 秒）；单场赔率观测时间也必须通过相同检查。
- 开球时间容差：预测开球时间与体彩开球时间容差不得超过 15 分钟，防止比赛改期风险。
- 来源凭证验证：预测快照来源状态必须为已验证（`provenance_status == "verified"`）。
- 预测质量门槛：`quality.status == "sufficient"`，历史样本图连通且场地上下文明确。
- 投注类型覆盖与混合过关：
  - **单关建议**：仅筛选单场达到保守 EV 门槛与夏普比率、且官方明确支持单买（`single_allowed == True`）的选项。
  - **2 串 1 与 4 串 1 混合过关建议**：
    - 支持混合过关（胜平负 `HAD`、让球胜平负 `HHAD`、总进球 `TTG`、比分 `CRS` 跨玩法混合组合）。
    - 严格要求跨场组合：同一场比赛严禁选入多个选项（`len(set(match_ids)) == leg_count`）。
    - 遵守体彩官方关数上限约束：混合比分（`CRS`）或半全场（`HAFU`）最多 4 关；总进球最多 6 关；胜平负/让球最高 8 关（2 串 1 与 4 串 1 均合法支持）。
- 纪律性折减与裁判出牌尺度（Disciplinary Haircut）：
  - 自动从模型输入中读取球队历史红黄牌均值与当值主裁判出牌尺度（`disciplinary`）。
  - 若主队或客队红牌概率过高、或裁判出牌严厉，自动计算单向额外折减：$P_c = \max(0, P - (h_{base} + h_{disc}))$。
  - 对优势方向（胜平负/让球/比分胜负）施加额外纪律折减。若基础 EV 达标但被纪律折减淘汰，显式记录 `disciplinary_risk_rejected`，防止单场因红牌减员造成黑天鹅亏损。
- 串关分散式配对约束（`--max-match-repetition`）：
  - 针对 2 串 1 与 4 串 1 混合过关，支持限制单场比赛在推荐组合中的最大复用次数（如 `--max-match-repetition 1` 或 `2`）。
  - 杜绝强优势单场（如苏格兰）过度绑定所有串关注单，实现注单间的去中心化解耦。
- 容错系统过关（System Bets / 多串过关，`--include-system-bets`）：
  - 支持体彩官方多串过关结构：3 串 4（3注2串1 + 1注3串1，容错 1 场）、4 串 5（4注3串1 + 1注4串1，容错 1 场）、4 串 11（6注2串1 + 4注3串1 + 1注4串1，容错 2 场）等。
  - 自动计算方案总注数、投注成本、全中预期回报（ROI），以及错 1 场（保本/盈利）、错 2 场（挽回损失）的极端情景损益模拟。
- 资金与风控：
  - 使用模型概率直接计算 EV，去抽水市场概率仅用于对照。
  - 使用 `conservative_probability = model_probability - total_haircut` 计算 `ev_low`（风险缓冲）。
  - 默认 `ev_low >= 5%` 且分数凯利为正才进入候选；单关赔率上限 70.0 倍（`--max-single-odds 70`），市场概率分歧度上限 2.0x。支持单场最高夏普/EV 或跨玩法全量纳入（`--all-eligible`）。
  - 单关使用半凯利（$0.5 \times f^*$），单项最高 5%。
  - 串关使用四分之一凯利（$0.25 \times f^*$），单项最高 2%。基于跨场独立性假设计算联合保守 EV。
  - 总敞口最高 50%（`--max-total-exposure 0.50`），未分配资金保留为现金。
- “无推荐”是正常结果，严禁降低门槛、生成估算赔率或篡改概率。

## 输出

输出分为结构化机器结果（JSON）与分类展示报告（Markdown）：
1. **单关投注建议**：分项独立呈现 **胜平负 / 让球胜平负单关**、**总进球数单关 (TTG)** 与 **比分单关 (CRS)**。仅呈现官方支持单买的单场建议。若某玩法官方未开单关或暂无达标选项，附带明确说明标注（列出因官方未开单关而被过滤并转入串关池的优质选项）；
2. **2 串 1 混合过关建议**：呈现跨场跨玩法 2 串 1 组合方案（明确标注混合玩法如 `HHAD+TTG`、`CRS+HHAD`），呈现组合赔率、联合概率、保守 EV、凯利比例与分配金额（受分散式配对约束）；
3. **4 串 1 混合过关建议**：呈现跨场跨玩法 4 串 1 组合方案（明确标注混合玩法，如 `HHAD+TTG`、`CRS+HHAD`），呈现组合赔率、联合概率、保守 EV、凯利比例与分配金额；
4. **容错系统过关建议**（当开启 `--include-system-bets` 时）：呈现 3 串 4、4 串 11 等多串过关方案，展示注数、投注金、全中预期回报，以及错 1 场 / 错 2 场的情景返还；
5. 资金总览（本金、建议投注、保留现金）及完整拒绝记录（含 `single_betting_not_allowed` 与 `disciplinary_risk_rejected` 详细记录）。提醒用户彩票具有随机性，不承诺收益。

计算方法见 [references/betting-methodology.md](references/betting-methodology.md)。数据字段见 [data-contracts.md](../match-prediction/references/data-contracts.md)。
