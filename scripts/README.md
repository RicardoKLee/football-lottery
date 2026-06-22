# 2026届美加墨世界杯预测系统脚本目录说明文档 (scripts/README.md)

本目录（`scripts/`）包含了用于辅助 **2026届美加墨世界杯预测系统** 的核心计算、数据拉取以及蒙特卡洛随机噪声模拟的 Python 脚本。

---

## 一、 脚本列表与核心功能

### 1. `fetch_match_data.py` (数据检索与硬实力评估)
*   **主要作用**：
    *   通过对数经济学模型、大名单和模糊匹配技术，自动检索 ELO 理论积分及两队的硬实力数据。
    *   对接 `eloratings.net` 的实时世界 TSV 数据表，在线抓取并解析最新的世界排名、ELO 理论胜平负概率及球队历史交锋战绩。
    *   内置 `COUNTRY_METADATA` 数据库，包含了 2026 年美加墨世界杯各参赛队在 Transfermarkt 上的最新市场估价（身价）、小组对阵（Fixtures）、比赛球场海拔、温度及地理信息。
*   **运行命令**：
    ```bash
    python3 scripts/fetch_match_data.py "<主队名称>" "<客队名称>"
    ```

### 2. `simulate_stochastic_prediction.py` (蒙特卡洛随机噪声扰动模拟器)
*   **主要作用**：
    *   作为 **v4.0 (随机噪声与临场纪律扰动版)** 的核心计算引擎，通过 10,000 次蒙特卡洛（Monte Carlo）重采样，解决传统泊松分布无法预测物理运气乌龙球、临场掏牌减员、偶发点球判罚等混沌爆冷赛果的缺陷。
    *   **数学机制**：
        1.  **物理高斯白噪声 ($\sigma = 15.0\%$)**：通过 Log-Normal 分布，扰动两队的进球期望值 $\lambda$ 和 $\mu$。
        2.  **红牌减员惩罚 (Red Cards)**：结合裁判场均掏牌数与两队犯规率计算临场红牌概率，一旦某队触发红牌，其防线进球期望立刻上浮 $30\%$，自身进攻期望萎缩 $10\%$。
        3.  **点球杀伤判罚 (Penalties)**：根据裁判场均点球率与两队禁区危险进攻（Dangerous Attacks）占比，进行点球伯努利试验，罚入（标准胜率 $76\%$）直接累加至进球中。
*   **运行命令**：
    ```bash
    python3 scripts/simulate_stochastic_prediction.py
    ```

### 3. `generate_betting_recommendation_strict.py` (严格 EV 与半凯利投注生成)
*   **主要作用**：
    *   严格读取 `output/` 目录下由 `match-prediction` Skill 生成的 `.md` 格式单场预测分析报告，解析总加权优势分 $S$、胜平负（HAD）走向、精确比分（CRS）和总进球数（TTG）的前三梯度预测结论。
    *   对接中国体彩（China Sporttery）实时 API，在线拉取对应的赛事最新赔率。
    *   采用 **期望值 (Expected Value, EV) 理论**，寻找市场低估的正期望值（Value Bet）投注选项，并利用 **半凯利（Half-Kelly）控制公式** 科学推导推荐资金分配占比（最大上限 $10\%$），自动在 `output/` 下生成当日的《定量投注方案推荐报告》。
*   **运行命令**：
    ```bash
    python3 scripts/generate_betting_recommendation_strict.py --date "2026-06-20"
    ```

### 4. `generate_betting_recommendation.py` (常规性价比投注方案生成)
*   **主要作用**：
    *   无需依赖 `.md` 单场报告，直接根据 `fetch_match_data.py` 和 ELO 概率自适应转换，直接结合实时赔率 API 自动计算 2串1 串关总 EV、TTG 总进球、博冷高收益玩法，并生成常规的投注报告。

### 5. `fetch_lottery_data.py` (中国竞彩数据在线解析)
*   **主要作用**：
    *   解析并拉取中国竞彩官方最新足球计算器 API，提供底层数据。

***
*本 README 由 doc-agent 学术归档并发布。*
