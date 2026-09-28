# SDD ledger — plan: docs/superpowers/plans/2026-09-23-sporttery-football-scope.md

## 隔离及授权
- 源仓库 main 保持原样，修订设计和计划已逐文件复制到隔离工作区。
- 工作区：/Users/liyingjin/projects/docker-project/football_lottery_sporttery_scope
- 分支：liyingjin/feature/football_lottery/sporttery_scope；基线 9e0c80d2f6951a3e6951b38aed55c970e3e37b47。
- 基线：python3 -m unittest discover -s tests -p 'test*.py' -v，30 tests，OK。
- Ruling: 计划内逐任务提交改为最终八专项通过后一次提交 — 编排规则优先；成本为任务间无提交快照，使用持久报告与 diff 留证。
- Ruling: 计划中“当前请求仅写计划”属于过期指令，以最新明确执行授权为准；不 push/merge，不安装依赖。
- Ruling: 保留全部执行记录，不按技能清除 scratch；满足用户持久记录要求。
- 工具不提供显式模型选择或 resume，使用已配置专业 agent；必要修复以文件恢复上下文。

## 预检
|任务|内部一致性/裁决|
|---|---|
|1|证据不可访问时 unknown，不能阻塞安全默认实现|
|2|当前唯一契约；生产者随后更新，阶段全量失败允许记录但最终必须全绿|
|3|规范化保留上下文；诊断输入不自动授信|
|4|三处中立语义一致，质量原因合并|
|5|明确 season，不能从旧白名单推定七月边界|
|6|身份和原始来源核验独立于 JSON 声明|
|7|池连通性只用过去样本|
|8|历史 ADR 保留，最新文档不写兼容实现；标题中的迁移解释为重新生成|

|共享任务|生产→消费接口|结论|
|---|---|---|
|1→2,3,5,6,8|证据→字段映射及限制|未知一律关闭|
|2→3,4,5,6,7,8|context/ID/snapshot/schema|顺序执行，最终生产者同步|
|3→4,5,7,8|标准历史/fixture/sample_pool|保留 source、context，幂等|
|4→5,6,7,8|预测/质量/参数|质量门槛不可绕过|
|5→6,8|文件入口、当前预测|输入文件声明不构成证明|
|6→8|赔率、推荐、报告/schema|集成同时核验拒绝与中文报告|
|7→8|回测/schema/文档|未来数据不得用于样本池判定|

## TODO
- [x] Task 1 来源语义（产出 `docs/data-mappings.md` 与 fixture 说明）
- [x] Task 2 统一契约（引入 `scripts/match_context.py`，更新 Schema 与 contracts）
- [x] Task 3 历史标准化（引入 `scripts/history_adapter.py`，90分钟常规时间比分与样本池隔离）
- [x] Task 4 通用模型（通用 `football-elo-poisson`，中立场双向消除优势，合并质量原因）
- [x] Task 5 CLI（开放任意赛事代码，新增 `--competition-name`、`--venue` 等参数）
- [x] Task 6 推荐准入（`official_listing` 与 `market_status` 官方核实，15分钟开球容差）
- [x] Task 7 走步回测（无未来泄漏，支持上下文透传与中立场基线）
- [x] Task 8 文档与集成（新增 ADR 0002，更新 README/process/skills，实现端到端集成测试）
- [x] 最终全量测试、八专项审阅、报告与提交

## 八专项审阅结论
1. **范围与边界**：官方竞彩足球全部在售赛事（五大联赛、其他联赛、杯赛、国家队赛事）；支持 HAD/HHAD/TTG/CRS 4 玩法；排除传统足彩、篮球与代投；明确区分业务范围与外部数据源覆盖限制。
2. **统一单一契约**：彻底废除五大联赛代码白名单硬限制；无历史兼容分支，要求产物重新生成；必填 context 语义完整。
3. **来源语义与不可伪造性**：JSON 声明不自动授信；未核实来源在推荐阶段拒绝（`data_provenance_unverified`）；证据链完整。
4. **比分口径与审计**：严格限定为常规时间 90 分钟整数比分；加时与点球大战予以剔除；异常比分审计并拒绝。
5. **样本池隔离与无前视泄漏**：俱乐部与国家队样本池隔离；图连通性只用目标开球前的数据，严禁未来图渗漏。
6. **中立场主场优势消除**：中立场双向取消 ELO 调整与进球基准加成；场地未知安全关闭。
7. **推荐准入与销售状态**：官方列表核验（`confirmed`）与玩法核验（`open`）双门槛；15 分钟赔率时效与 15 分钟开球容差；绝不编造赔率。
8. **文档与技能一致性**：文档与 2 个核心技能及其 references 全面更新；无运行时白名单残留；CLI 烟测与 `git diff --check` 全绿。

## 验收结果
- 测试套件：83 tests 全部通过（1 skipped 为未装外部可选 jsonschema，符合无外网/不装依赖约定）。
- `git diff --check`：无格式或空白问题。
- 本地单次提交完成，不 push，不 merge。
