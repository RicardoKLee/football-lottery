# 走步回测与校准

## 时间切分与样本隔离

按比赛时间严格递进执行 walk-forward 回测。每次预测只能使用目标比赛开球时间之前已经结束且当时可获得的数据。
图连通性与样本池可用性仅基于历史数据评估，严禁使用全量未来图判断当时连通性，彻底杜绝前视偏差。

## 基线

至少比较：
1. 去抽水市场概率；
2. 包含相同中立场规则的简单主场 ELO 基线；
3. 通用模型（`football_elo_poisson`）；
4. 待验证的新特征或新模型。

## 指标

- 胜平负：Log Loss、Brier Score、Ranked Probability Score、校准曲线和 ECE。
- 比分：负对数似然、总进球误差。
- 投注：真实历史赔率下的 ROI、CLV、最大回撤、下注数和 bootstrap 区间。
- 分层：赛事类型、球队类型、场地属性（主场/中立场）。

## 项目命令

```bash
python3 scripts/backtest_model.py \
  --competition J1 \
  --history-file data/synthetic_j1_history.json \
  --output output/backtests/J1.json
```

报告中的 `audit` 必须满足 `latest_training_kickoff_utc < target_kickoff_utc`。缺少历史赔率时，报告保留 ROI/CLV 未计算的说明。
