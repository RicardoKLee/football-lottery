# 足球数据源规范与抓取指南 (Data Sources Guide)

本指南作为 `match-prediction` Skill 的辅助参考手册，规定了在进行足球比赛预测时，数据检索必须遵循的权威专业机构、官方网站与抓取规范。

---

## 1. 战队硬实力与历史数据
- **ELO 积分系统**：
  - **来源**：World Football Elo Ratings (`https://www.eloratings.net/`)。
  - **特点**：比 FIFA 排名更能敏锐反映球队近期的真实战力动态与实力涨跌。
- **历史交锋与近期 20 场战绩**：
  - **来源**：11v11 (`https://www.11v11.com/`)、Flashscore (`https://www.flashscore.com/`)、Soccerway。
  - **特点**：重点考察近 5 年内直接对战战绩以及近 20 场分类比赛走势。

---

## 2. 战术风格、阵型与首发名单
- **战术特征与克制关系**：
  - **来源**：WhoScored (`https://www.whoscored.com/`)、SofaScore、FBref、The Athletic 战术专栏。
  - **特点**：提取球队的控球率（Possession %）、传球成功率（Passing %）、每场犯规数、抢断数、危险进攻（Dangerous Attacks）及角球数据。
- **预计首发与最新大名单**：
  - **来源**：FIFA/各大联赛官网（如欧冠、英超、西甲官网）、各国家足协/俱乐部官方新闻。

---

## 3. 球员市场价值与即时伤停
- **球员身价与伤病更新**：
  - **来源**：Transfermarkt (`https://www.transfermarkt.com/`)。
  - **特点**：伤病更新精确到缺席天数及错过的具体比赛场次；球队总身价估值是衡量纸面实力的客观经济学指标。

---

## 4. 气象与物理地理环境
- **球场地理坐标与海拔**：
  - **来源**：官方球场技术手册、各大地理百科。
- **气象预报**：
  - **来源**：AccuWeather、Weather.com 等，针对开球时段的温度、湿度及降水概率预测。

---

## 5. 主裁判执法记录
- **裁判历史数据**：
  - **来源**：WorldReferee (`https://www.worldreferee.com/`)、Transfermarkt 裁判板块。
  - **关键指标**：场均黄牌（Yellow cards/game）、红牌比率（Red cards/game）、场均点球率（Penalties/game）。
