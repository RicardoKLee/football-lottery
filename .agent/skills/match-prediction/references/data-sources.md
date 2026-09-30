# 多源足球数据与资讯分层体系

不同数据平台各有侧重，系统根据具体业务需求与安全边界进行分层组合使用。

---

## 1. 核心基石：官方彩票与权威赛果（Trust Tier 1）

- **中国体育彩票官方网站（`https://www.sporttery.cn/`）**：
  - **在售列表与即时赔率**：`webapi.sporttery.cn` 实时接口，提供每日官方在售比赛清单、胜平负/让球/总进球/比分赔率、开球时间与销售截止时间。
  - **官方足球联赛资料（`https://www.sporttery.cn/zqlszl/`）**：提供热门联赛、各大洲国家联赛及国际大赛的官方统一 ID、赛季赛程赛果与积分榜。
  - **常规时间比分保证**：官方完赛赛果 `sectionsNo999` 字段严格记录 90 分钟常规时间整数比分，天然杜绝加时赛与点球大战污染。通过 [`fetch_sporttery_league_data.py`](file:///Users/liyingjin/projects/docker-project/football_lottery_sporttery_scope/scripts/fetch_sporttery_league_data.py) 直接生成经核验的 `history_snapshot`（`provenance_status="verified"`）。

---

## 2. 新闻、比分、即时动态与转会追踪

用于赛前信息搜集、阵容轮换、伤停与突发动态分析：

- **FlashScore**：全球比赛覆盖最全面的即时比分平台，涵盖主流联赛、小联赛、杯赛及各级国家队赛事，适合快速核验即时赛程与赛果。
- **Transfermarkt（德国转会市场）**：全球最权威的俱乐部球队阵容、伤病记录、停赛情况、转会身价与合同变动数据源。
- **Goal.com**：国际顶级足球媒体，提供一手深度战报、球队动态、战术前瞻与转会动态。
- **雷速体育**：国内领先的体育即时数据平台，提供极佳的国内访问延迟、即时动画直播、盘口走势与对阵情报。

---

## 3. 深度数据分析与球员/战术对比（进阶指标）

用于构建期望进球（xG）、射门质量、战术风格与攻防深层评估：

- **FBref（免费且专业）**：基于 Opta 数据体系，提供欧洲五大联赛及全球数十个联赛的详尽进阶数据（xG、xA、SCA 创造射门动作、传球网络分布、推进传球、防守压迫等）。
- **WhoScored**：基于 Opta 详细事件数据，提供球员技术评分、攻防技术特征标签、主客场战术风格以及预测首发阵容。
- **Understat**：专注于射门级 xG 模型的专业分析网站，提供欧洲主流联赛的射门地图（shot maps）、射门转换率以及预期积分（xPTS）模型。

---

## 4. 中国足球官方数据追踪

- **中国足协官网（CFA）**：国内职业联赛（中超、中甲、中乙、足协杯）与国家队赛事的官方赛历、纪律处罚公告、裁判选派与官方裁决。
- **雷速体育**：国内各级本土赛事、中超/中甲的即时数据、出场名单与事件时间轴。

---

## 5. 生产数据 Connector（机器接口）

- `china-sporttery`：中国体彩官方联赛资料与在售接口（原生支持常规时间比分与统一球队 ID）。
- `football-data.org v4`：欧洲五大联赛外部实时 API，受 API Token 与速率限制约束。

---

## 引用规范与文献出处

中国体彩网。“足球联赛资料”。*中国体彩网*, <https://www.sporttery.cn/zqlszl/>. 访问日期：2026年9月28日。

FBref. “Football Statistics and History.” *Sports Reference*, <https://fbref.com/>. Accessed 28 Sep. 2026.

Transfermarkt. “Football Transfers, Rumours and Market Values.” *Transfermarkt*, <https://www.transfermarkt.com/>. Accessed 28 Sep. 2026.

FlashScore. “Football Live Scores, Results.” *Flashscore*, <https://www.flashscore.com/>. Accessed 28 Sep. 2026.

Understat. “Expected Goals (xG) Statistics for Football Leagues.” *Understat*, <https://understat.com/>. Accessed 28 Sep. 2026.

WhoScored. “Football Statistics & Match Previews.” *WhoScored*, <https://www.whoscored.com/>. Accessed 28 Sep. 2026.
