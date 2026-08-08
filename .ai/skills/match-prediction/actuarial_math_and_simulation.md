# 足球双泊松与蒙特卡洛精算数学模型 (Actuarial Math and Simulation Model)

本手册详细规定了足球预测系统中从 ELO 攻防修正、双泊松分布、Dixon-Coles 概率计算到蒙特卡洛（Monte Carlo）随机扰动模拟的全套精算数学模型。

---

## 1. ELO 攻防参数（$Elo_{att}$ 与 $Elo_{def}$）量化修正

### 1.1 ELO 进攻参数 ($Elo_{att}$)
$$\text{修正后 } Elo_{att, 1} = Elo_{base, 1} + 100 \times \left( \frac{\text{np-xG}_{1}}{\text{np-xG}_{avg}} - 1 \right) + 50 \times \left( \frac{\text{射正数}_{1}}{\text{射正数}_{avg}} - 1 \right)$$
*(其中 $\text{np-xG}_{avg} = 1.25$，$\text{射正数}_{avg} = 4.0$；主力前锋伤停可扣减 50 ~ 100 分)*

### 1.2 ELO 防守参数 ($Elo_{def}$)
$$\text{修正后 } Elo_{def, 1} = Elo_{base, 1} + 100 \times \left( \frac{\text{xGA}_{avg}}{\text{xGA}_{1}} - 1 \right) + 150 \times \text{PSxG +/-}_{1} + 50 \times \left( \frac{\text{争顶成功率}_{1}}{50\%} - 1 \right)$$
*(其中 $\text{xGA}_{avg} = 1.25$；后防领袖伤停扣减 80 ~ 150 分)*

---

## 2. 加权优势分 $S$ 映射期望进球率 $\lambda$ 与 $\mu$

通过十因子总加权优势分 $S \in [-10, +10]$，结合 ELO 攻防差修正：
$$\lambda' = \max\left(0.1, \frac{txG_{proj} + k \cdot S}{2}\right) \times 10^{\frac{Elo_{att, 1} - Elo_{def, 2}}{800}}$$
$$\mu' = \max\left(0.1, \frac{txG_{proj} - k \cdot S}{2}\right) \times 10^{\frac{Elo_{att, 2} - Elo_{def, 1}}{800}}$$
*(默认总期望进球 $txG_{proj} = 2.40$，转换系数 $k = 0.30$)*

---

## 3. Dixon-Coles 修正的基础比分概率估计

引入 Dixon-Coles 低比分修正因子 $\tau(X, Y)$（设定 $\rho = -0.12$）：
$$P_{base}(X, Y) = \tau(X, Y) \times \frac{e^{-\lambda'} (\lambda')^X}{X!} \times \frac{e^{-\mu'} (\mu')^Y}{Y!}$$

---

## 4. 蒙特卡洛（Monte Carlo）随机扰动模拟模型

通过 10,000 次蒙特卡洛重采样，解决混沌爆冷与物理噪声问题：

### 4.1 物理运气高斯白噪声
每轮采样施加 Log-Normal 白噪声抖动（标准差 $\sigma = 15.0\%$）：
$$\lambda_j = \lambda' \cdot e^{\epsilon_{h, j}}, \quad \mu_j = \mu' \cdot e^{\epsilon_{a, j}}, \quad \epsilon_h, \epsilon_a \sim N(0, \sigma^2)$$

### 4.2 主裁判执法惩罚与红牌（Red Cards）扰动
单场基准红牌率设为 $6.0\%$：
$$P_{red, h, j} = \min\left(0.15, \frac{Y_{ref}}{4.5} \times \frac{F_{home}}{12.0} \times 0.06\right), \quad P_{red, a, j} = \min\left(0.15, \frac{Y_{ref}}{4.5} \times \frac{F_{away}}{12.0} \times 0.06\right)$$
- 主队触发红牌：客队期望进球 $\mu_j$ 飙升 $30\%$，主队期望 $\lambda_j$ 萎缩 $10\%$。
- 客队触发红牌：主队期望进球 $\lambda_j$ 飙升 $30\%$，客队期望 $\mu_j$ 萎缩 $10\%$。

### 4.3 禁区杀伤与点球判罚（Penalties）扰动
结合两队危险进攻频率 ($DA$) 与裁判点球率 ($P_{pen, ref}$)：
$$P_{penalty} = \min\left(0.40, P_{pen, ref} \times \frac{DA_{home} + DA_{away}}{75.0} \times 0.8\right)$$
- 伯努利试验判定归属（归属主队概率为 $\frac{DA_{home}}{DA_{home} + DA_{away}}$），罚入率 $76\%$。罚入直接记进球 $+1$。

### 4.4 模拟比分频数统计 ($P_{sim}$)
统计 10,000 次采样后精确比分频数：
$$P_{sim}(X, Y) = \frac{\text{频数}(X, Y)}{10000}$$
- **第一手推荐（首选）**：$\arg\max P_{sim}(X, Y)$。
- **第二手推荐（次选）**：高频次选比分。
- **第三手推荐（对冲/防冷）**：防护对冲比分或高概率极端比分。
