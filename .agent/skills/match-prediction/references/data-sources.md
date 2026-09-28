# 数据源与边界

## 生产 Connector

- `football-data.org v4`：当前代码使用 competitions、teams 和 matches 资源获取部分欧洲联赛球队 ID 与赛果。调用需要用户自己的 token，受账号覆盖范围和速率限制约束。
- 中国体育彩票官方接口：当前代码只读取官方实时在售列表（`official_listing` 与 `market_status`），不把接口失败替换成缓存或估算赔率。解析失败或未在售必须错误关闭。

## 离线快照与范围覆盖

- 系统架构支持中国体育彩票官方竞彩足球全部在售赛事（其他俱乐部联赛、杯赛、洲际比赛、国家队赛事）。
- 数据源覆盖不等于业务范围：对于外部实时 API 未覆盖的联赛或国家队比赛，需通过 `--history-file` 提供标准化历史快照，并声明合法来源凭证（`provenance_status`）与比分口径。

## 研究用途

- StatsBomb Open Data 可用于有限赛事的事件与阵容研究，但不能默认充当生产实时源。

## MLA 9 引用

football-data.org. “API Quickstart.” *football-data.org*, <https://www.football-data.org/documentation/quickstart>. Accessed 25 Aug. 2026.

StatsBomb. “StatsBomb Open Data.” *GitHub*, <https://github.com/statsbomb/open-data>. Accessed 25 Aug. 2026.

中国体彩网。“竞彩足球”。*中国体彩网*, <https://www.sporttery.cn/jc/jsq/zq/>. 访问日期：2026年9月28日。
