# 走步回测与校准

## 时间切分

按轮次或比赛日执行 walk-forward。每次预测只能使用当时已经结束且当时可获得的数据。不得随机切分赛季，也不得用最终观测天气替代赛前天气预测。

## 基线

至少比较：

1. 去抽水市场概率；
2. 只含主场优势的简单 ELO；
3. 当前 ELO + 动态进球 + 泊松模型；
4. 待验证的新特征或新模型。

## 指标

- 胜平负：Log Loss、Brier Score、Ranked Probability Score、校准曲线和 ECE。
- 比分：负对数似然、总进球误差。
- 投注：真实历史赔率下的 ROI、CLV、最大回撤、下注数和 bootstrap 区间。
- 分层：联赛、赛季阶段、主客场和升班马。

## 启用门槛

在评估前冻结样本范围、指标和阈值。新增特征只有在样本外稳定改善概率指标且没有明显破坏校准时才能启用。真实投注策略应单独验证赔率时点、交易成本和 CLV；单次高 ROI 不是通过依据。

## 项目命令

```bash
python3 scripts/backtest_model.py \
  --competition PL \
  --history-file data/PL_history.json \
  --output output/backtests/PL.json
```

报告中的 `audit` 必须满足 `latest_training_kickoff_utc < target_kickoff_utc`。缺少历史赔率时，报告必须保留 ROI/CLV 未计算的限制说明。
