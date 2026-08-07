# 通用足球体彩比赛预测精算流程与计算图

本文件详细记录了根据 `@.cursor/skills/match-prediction/SKILL.md` 实现的足球比赛结果定量加权预测与随机扰动蒙特卡洛（Monte Carlo）模拟精算流程。

---

## 一、 精算预测总体计算流程图 (Mermaid)

```mermaid
graph TD
    %% 1. Data Fetching & Preparation
    subgraph A [准备阶段：数据抓取与检索]
        A1[python3 scripts/fetch_match_data.py] -->|获取数据| A2[两队基础 ELO 积分 / 世界排名 / 历史总战绩 / ELO 理论概率]
        A3[WebSearch 多维度补充数据] -->|获取数据| A4[伤停名单 / 首发门将 PSxG +/- / 定位球攻防数据 / 身价 / 天气与海拔 / 裁判尺度]
    end

    %% 2. 10-Factor Quantitative Scoring
    subgraph B [第一阶段：十因子定量加权系统]
        A2 & A4 --> B1[评估十个维度优势分 A_i 范围 -10 到 +10]
        B1 --> B2[计算总加权优势分 S = Σ A_i * W_i]
        B2 --> B3{依据 S 确定走向分类}
        B3 -->|S > +2.5| B3a[主队独赢 T1 Win]
        B3 -->|-1.5 <= S <= +1.5| B3b[双方战平 Draw]
        B3 -->|S < -2.5| B3c[客队独赢 T2 Win]
        B3 -->|其他过渡带| B3d[首选双平/不败过渡预测]
    end

    %% 3. Poisson Base Expected Goals
    subgraph C [第二阶段：双泊松分布期望值计算]
        B2 -->|总加权优势分 S| C1[设定总基准期望进球 txG_proj 默认 2.4]
        C1 --> C2[计算主队基准期望 λ = max 0.1, txG_proj + k*S / 2]
        C1 --> C3[计算客队基准期望 μ = max 0.1, txG_proj - k*S / 2]
        note1[系数 k = 0.30]
    end

    %% 4. ELO Att/Def Correction
    subgraph D [第三阶段：ELO 攻防评级参数修正]
        C2 & C3 --> D1[根据 np-xG、射正率、前场创造力修正 Elo_att]
        C2 & C3 --> D2[根据防守深度、争顶率、门将 PSxG +/- 修正 Elo_def]
        D1 & D2 --> D3[主队期望修正：λ' = λ * 10^ Elo_att_1 - Elo_def_2 / 800]
        D1 & D2 --> D4[客队期望修正：μ' = μ * 10^ Elo_att_2 - Elo_def_1 / 800]
    end

    %% 5. Monte Carlo Simulation
    subgraph E [第四阶段：蒙特卡洛随机扰动模拟 10,000 次]
        D3 & D4 --> E1[模拟循环：执行 10,000 次独立采样]
        
        %% White Noise
        E1 --> E2[5.1 物理运气白噪声扰动]
        E2 --> E2a[对 λ' 与 μ' 注入 Log-Normal 白噪声: ε ~ N 0, σ^2, σ = 15%]
        E2a --> E2b[λ_j = λ' * e^ε_h,j,  μ_j = μ' * e^ε_a,j]
        
        %% Red Card
        E2b --> E3[5.2 主裁判红黄牌惩罚减员扰动]
        E3 --> E3a[根据 Y_ref 与队均犯规 F 计算两队红牌概率 P_red]
        E3a --> E3b[Bernoulli 试验判定减员]
        E3b -->|主队触发红牌| E3c[客队期望进球 μ_j 飙升 30%, 主队期望 λ_j 萎缩 10%]
        E3b -->|客队触发红牌| E3d[主队期望进球 λ_j 飙升 30%, 客队期望 μ_j 萎缩 10%]
        
        %% Penalty
        E3c & E3d & E3b --> E4[5.3 禁区点球判罚扰动]
        E4 --> E4a[根据 P_pen_ref 与联合危险进攻 DA 计算点球概率 P_penalty]
        E4a --> E4b[Bernoulli 试验判定点球发生与归属 76% 罚入率]
        E4b -->|罚入| E4c[对应球队模拟进球数直接 +1]
    end

    %% 6. Decision & Output
    subgraph F [第五阶段：决策推荐与结果输出]
        E4c --> F1[统计 10,000 次模拟精确比分频数, 得到最终模拟概率 P_sim X,Y]
        F1 --> F2[第一手推荐：P_sim 概率最高比分 argmax P_sim X,Y]
        F1 --> F3[第二手推荐：P_sim 概率次高比分]
        F1 --> F4[第三手推荐：高概率/高发生率对冲比分]
        F2 & F3 & F4 --> F5[生成 Markdown 预测报告并保存至 output/ 目录]
    end
```

---

## 二、 核心精算公式数学描述

### 1. 优势分转换进球期望
$$\lambda_{base} = \max\left(0.1, \frac{txG_{proj} + k \cdot S}{2}\right)$$
$$\mu_{base} = \max\left(0.1, \frac{txG_{proj} - k \cdot S}{2}\right)$$
*参数设定*：总期望进球 $txG_{proj} = 2.4$，转换系数 $k = 0.30$，优势分 $S \in [-10, 10]$。

### 2. ELO 攻防战力修正
$$\lambda' = \lambda_{base} \times 10^{\frac{Elo_{att, 1} - Elo_{def, 2}}{800}}$$
$$\mu' = \mu_{base} \times 10^{\frac{Elo_{att, 2} - Elo_{def, 1}}{800}}$$

### 3. 随机扰动机制（蒙特卡洛单次采样）
- **物理运气白噪声**：
  $$\lambda_j = \lambda' \cdot e^{\epsilon_{h, j}}, \quad \mu_j = \mu' \cdot e^{\epsilon_{a, j}}, \quad \epsilon \sim N(0, \sigma^2), \quad \sigma = 0.15$$
- **红牌减员因子**：
  $$P_{red, h} = \min\left(0.15, \frac{Y_{ref}}{4.5} \times \frac{F_{home}}{12.0} \times 0.06\right), \quad P_{red, a} = \min\left(0.15, \frac{Y_{ref}}{4.5} \times \frac{F_{away}}{12.0} \times 0.06\right)$$
- **点球判罚因子**：
  $$P_{penalty} = \min\left(0.40, P_{pen, ref} \times \frac{DA_{home} + DA_{away}}{75.0} \times 0.8\right)$$
  点球归属概率为：$P_{pen\_to\_home} = \frac{DA_{home}}{DA_{home} + DA_{away}}$，罚入率 $76\%$。
