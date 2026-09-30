# 数据来源语义与可验证适配边界

Task 1 证据基线；访问日期为 **2026-09-23（UTC）**。本文只定义后续适配边界，不表示当前代码已经符合该边界。权威设计见 `docs/superpowers/specs/2026-09-23-sporttery-football-scope-design.md`。

## 1. 证据登记

以下均为不带 token 的公开 HTTPS GET；时间取本机 UTC 请求开始时间，不是文档发布日期或供应商数据更新时间。HTTP 成功只证明页面可访问，不能证明实时覆盖、销售资格或字段语义。失败不代表来源不存在。

|编号|真实请求 URL（成功请求无跳转）|访问时间 UTC|结果与定位|
|---|---|---|---|
|S1|https://www.sporttery.cn/jc/zqjcgz/ |2026-09-23T16:55:35.404090Z|规则候选入口，HTTP 567；未取得正文，未核实其为当前有效规则页|
|S2|https://www.sporttery.cn/ |2026-09-23T16:55:37.944794Z|官方站首页 HTTP 567，无法由首页查找有效玩法规则链接|
|S3|https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?category=c&isFix=0&pcOrWap=1 |2026-09-23T16:55:40.545688Z|项目 `scripts/fetch_lottery_data.py:SPORTTERY_API_URL` 地址；HTTP 567（物理直连可通，返回当前在售）|
|S4|https://www.sporttery.cn/zqlszl/ |2026-09-28T14:51:04.000000Z|足球联赛资料主页，物理直连 HTTP 200（10723 bytes）；Vue3 前端载入 `zqIndex.js`|
|S5|https://webapi.sporttery.cn/gateway/uniform/football/league/getLeagueListV1.qry |2026-09-28T14:52:33.000000Z|官方联赛/赛季目录，物理直连 HTTP 200；提供全部热门/普通/国际联赛 uniformLeagueId 与 seasonId|
|S6|https://webapi.sporttery.cn/gateway/uniform/football/league/getMatchResultV1.qry |2026-09-28T14:53:04.000000Z|官方完赛赛果接口，物理直连 HTTP 200；`sectionsNo999` 提供常规 90 分钟整数比分|
|F1|https://docs.football-data.org/general/v4/match.html |2026-09-23T16:55:29.455624Z|HTTP 200；Match resource、Status workflow explained、示例 score/season/venue|
|F2|https://docs.football-data.org/general/v4/competition.html |2026-09-23T16:55:33.351652Z|HTTP 200；Matches、Available filters for Match Subresource、Teams|
|F3|https://docs.football-data.org/general/v4/overtime.html |2026-09-23T16:56:21.828550Z|HTTP 200；Dealing with scores / Regular finish / Extra Time / Penalty Shootout；从 F1 页面导航链接找到|
|F0|https://docs.football-data.org/general/v4/score.html |2026-09-23T16:55:31.961618Z|尝试的比分页路径 HTTP 404，不作为语义依据；实际说明为 F3|

成功页面原始响应体 SHA-256（便于辨认本次所读版本，不代替语义引用）：

- F1（33677 bytes）：`869ede494eeef31b9e89f821fba22d791c01ceb3e2db6d84881767eaaa56dae2`
- F2（58450 bytes）：`77268e6b3785fc8763995372b51047a77d2fc0885c7ed9f4e1fffd70c57f94c4`
- F3（11713 bytes）：`4b7d6dcfd9ba0cec6eb72168c9474f3343353f3bc66f608823c52458307e81ac`

### 可复核原文摘录

- F1，Status workflow explained：`The status field indicates the current phase a match is in.`；`the final whistle pushes the match to FINISHED.` 这是比赛阶段，不是体彩销售状态。
- F2，Matches：`by default the current season is used`；示例将 `season=2021` 对应 `2021/22`。过滤器表将 season 定义为 `An integer, like [\d]{4}`。不能从单个示例推出所有赛事统一七月换季。
- F3：`All score-related data is stored within the score node. All of it’s attributes default to null.`
- F3：`The score/fullTime attribute is key as it also acts as the running score.`
- F3：`When the match status changes to FINISHED, the score/fullTime attribute indicates the final score.`
- F3：duration 默认 REGULAR，还接受 EXTRA_TIME / PENALTY_SHOOTOUT，结束时表明结束阶段，进行中则是附加状态。
- F3：extraTime `count up (only) the goals scored within extratime`；penalties `will only contain the goals within the penalty shootout`。
- F3：`Since v4 there is also the score/regularTime attribute which holds the goals scored after 90 minutes`。
- F3 的德国比赛示例：fullTime=7:6、regularTime=1:1、extraTime=0:0、penalties=6:5，证明不能无条件使用 fullTime。示例使用 homeTeam/awayTeam，而 F1 score 示例使用 home/away；不能仅凭示例自动兼容两种键名。

## 2. 逐字段映射及关闭策略

证据编号关联上表的 URL 和访问日期。**未经官方确认 → unknown → 拒绝推荐** 是缺证默认值；“可记录”不等于“通过正式质量门槛”。本次没有任何已证实的体彩“在售”值映射。

|事项 / 来源|原始字段或候选字段|已确认语义与证据|允许的边界 / 未知时动作|
|---|---|---|---|
|体彩玩法常规时间含补时|玩法规则正文（不是 API 字段）|S1/S2 无正文；未经官方确认|设计目标是常规时间含伤停补时、不含加时点球；目前只能作为内部契约，不宣称已用官方规则核实；unknown → 拒绝推荐|
|提供方常规时间含补时|`score.regularTime`|F3 明确为 90 分钟后的进球数，但所读文档没有明确补时包含规则|可保留提供方原始含义；“包含补时”的精确口径未经官方确认 → unknown → 不作为正式建议的已验证输入|
|比赛已结束|`status=FINISHED`|F1 明确终场后进入 FINISHED|允许标记提供方比赛已结束；不是已开售、仍在售或可推荐证明；其他/缺失状态不作为完赛历史|
|最终比分|`score.fullTime`, `score.duration`|F3：fullTime 也是即时比分；FINISHED 时为最终比分，可能含加时点球|禁止无条件映射到常规时间。FINISHED + REGULAR 只支持“常规结束的最终比分”这个有限语义，补时口径仍待核实；不单凭 duration 默认值授信|
|常规比分与字段形状|`score.regularTime.{home,away}` 或文档示例 `{homeTeam,awayTeam}`|F3 确认 regularTime 含义；F1/F3 示例键名有差异|本次不授权两套键名自动回退。需提供方当前结构证据消除差异；缺失、null、键名不明 → unknown；不以字符串转数或截断小数修复|
|加时比分|`score.extraTime`, `score.duration=EXTRA_TIME`|F3 明确 extraTime 仅统计加时阶段进球；FINISHED + EXTRA_TIME 为120分钟结束、无点球|不得当作常规比分；存在加时且缺少可信常规比分时剔除历史记录并记录原因和数量；本次不授权从最终比分做减法重建|
|点球比分|`score.penalties`, `score.duration=PENALTY_SHOOTOUT`|F3 明确 penalties 仅统计点球大战进球|不得计入常规时间；缺少可信常规比分则剔除，不用 winner/fullTime 猜测|
|中立场|F1 示例 `venue`；中立场原始布尔字段未确认|F1 仅示例球场名称，未取得中立场字段权威定义|球场名、主客队顺序及杯赛类型都不证明中立/非中立；未经官方确认 → unknown → 拒绝推荐，不能默认普通主场|
|赛事赛季/届次|`competition.id/code`, `season.id/startDate/endDate`, 请求 `season`|F1/F2 示例提供赛事和赛季对象；F2 确认四位整数过滤器及默认当前赛季|可按来源保留 ID/日期并显式选择 season；不能将供应商赛事代码等同体彩标识；自然年/杯赛届次映射未确认时要求核实，不按七月猜测，未知拒绝推荐|
|官方赛事清单归属|S3 候选 `value.matchInfoList[].subMatchList[]`, `matchId`|字段来自现有代码，不是本次成功抓取或官方字典；未经官方确认|保留来源用于诊断，不以用户填写 ID、source_mode=live 或接口地址字符串证明官方资格；unknown → 拒绝推荐|
|比赛开售|候选 `sellStatus/saleStatus/matchStatus/status`|S3 无正文，无官方枚举字典；未经官方确认|任何数字/布尔/文本都不得自动映射为在售；缺失不是“官方列出即在售”；unknown → 拒绝推荐|
|玩法开售|候选 `had/hhad/ttg/crs` 及其状态字段（字段名未确认）|S3 无正文，无官方玩法级状态定义；未经官方确认|赔率存在不等于玩法开售；比赛开售也不证明玩法开售；逐玩法 unknown → 拒绝该玩法推荐；不扩展半全场|
|赔率更新时间|候选 `oddsUpdateTime/updateTime/lastUpdateTime`|S3 无正文；字段时区、单位、作用层级均未经官方确认|不能把抓取时间/文件 mtime 当赔率更新时间；fetched_at 只记录抓取动作；unknown → 拒绝推荐|
|销售截止时间|候选 `sellEndTime/saleEndTime/stopTime/endTime`|S3 无正文；字段语义、时区、玩法级别未经官方确认|不能把开球前5分钟估算当官方截止；unknown → 拒绝推荐；已过截止仍应关闭|

### 不得继承的现有实现假设（后续任务处理）

`scripts/fetch_lottery_data.py` 当前代码包含 `1/2/true/open/selling/on_sale/available/在售/销售中` 白名单、实时响应缺状态时返回可用、开球减5分钟推断截止、抓取时间回填赔率时间。这些都是本地实现行为，**不是权威证据**；本文不批准它们。关闭状态同样不凭名字宣称官方定义：不能识别时安全关闭，但原因应为未知而非伪称官方停售。

## 3. 后续适配准入

1. 分离官方清单资格、历史可分析性和可推荐性。来源可追溯与字段自述也必须分开，JSON 自述不是证明。
2. 除上述 F1/F2/F3 的有限语义，不增加可用状态或比分映射。未确认的补时、键名、中立场及销售元数据不得静默授信。
3. 供应商字段类型错误、负数/小数/布尔比分、缺失常规比分必须拒绝或剔除，并保留原因与数量；不能污染 ELO/泊松输入。这是内部安全契约，不是官方 API 声明。
4. 获取后续官方文档时，新增 URL、真实访问时间、定位/原文和字段层级、枚举、时区证据；再逐条审阅映射。真实接口样本只能证明观察到的形状和值，不能独自证明状态语义。
5. 本轮全部体彩允许使用/在售映射数为 **0**。unknown 不阻塞安全默认实现，但阻止正式投注建议。生产行为修复留给后续任务，本 Task 不修改脚本。

## 4. 测试来源

详见 `tests/fixtures/provider/README.md`。合成数据只测试内部契约及拒绝分支；真实响应必须脱敏并附来源。离线测试通过、页面 HTTP 200、真实响应字段存在均不等于已证明销售资格、比分口径或实时覆盖。此次未取得或新增任何真实接口 fixture，也没有调用需要 token 的 football-data.org 数据 API。
