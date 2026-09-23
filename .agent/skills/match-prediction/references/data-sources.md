# 数据源

## 生产 connector

- `football-data.org v4`：当前代码使用 competitions、teams 和 matches 资源获取五大联赛球队 ID 与赛果。调用需要用户自己的 token，并受账号覆盖范围和速率限制约束。
- 中国体彩网竞彩接口：当前代码只读取官方实时列表，不把接口失败替换成缓存或估算赔率。接口字段和访问策略可能变化，解析失败必须错误关闭。

## 研究用途

- StatsBomb Open Data 可用于有限赛事的事件与阵容研究，但覆盖范围不等于五大联赛完整实时数据，不能默认充当生产实时源。

## MLA 9 引用

football-data.org. “API Quickstart.” *football-data.org*, <https://www.football-data.org/documentation/quickstart>. Accessed 25 Aug. 2026.

StatsBomb. “StatsBomb Open Data.” *GitHub*, <https://github.com/statsbomb/open-data>. Accessed 25 Aug. 2026.

中国体彩网。“竞彩足球”。*中国体彩网*, <https://www.sporttery.cn/jc/jsq/zq/。访问日期：2026年8月25日。>

