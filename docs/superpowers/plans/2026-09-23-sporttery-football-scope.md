# 全部竞彩足球赛事范围 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不放松来源、质量和销售门槛的前提下，将项目从五大联赛扩展到所有官方竞彩足球赛事。

**Architecture:** 官方清单负责资格，历史适配器负责常规时间赛果与上下文，通用模型负责诊断性概率；投注入口独立验证资格和质量后计算建议。复用当前 Python CLI，新增小型上下文与历史标准化模块，不引入服务或全球数据供应商。

**Tech Stack:** Python 3.9+、标准库 argparse/dataclasses/unittest、JSON Schema draft 2020-12、现有 ELO/泊松模型。

**Spec:** `docs/superpowers/specs/2026-09-23-sporttery-football-scope-design.md`（用户已于本轮批准）

## Global Constraints

- 不包含传统足彩胜负彩、任选九、篮球或自动下单。
- 本次扩大赛事范围，不新增半全场等当前模型未实现的玩法，也不承诺每场比赛都有数据或推荐。
- 赛事或玩法销售资格未经官方确认时不得输出正式投注建议。
- 文件修改时间不能代替可验证的数据观测时间用于正式建议。
- 场地未知时不得当成普通主场通过质量门槛。
- 稳定球队和比赛 ID 携带来源语义；来自不同供应商的同号 ID 不直接合并。
- 默认参数仍标记为待走步回测校准的基线，不声称扩展范围等于精度已得到验证。
- 不回退已有改动。执行基线为 `9e0c80d`；该提交是快照，不是测试通过的证据。
- 不新增运行时第三方依赖，不自动安装工具，不接触真实 token，不推送远端。

## 执行与验证方式

用户已明确：远程运行限制仅适用于 `/sandbox` 下的仓库。本项目位于 `/Users/liyingjin/projects/docker-project/football-lottery`，不受该限制；直接在本机运行下面的 Python unittest 命令，按任务执行 TDD 红→绿循环，无需远程流水线或再次确认运行权限。

本次为全新更新，只实现最新模型、当前统一数据契约和最新投注流程。不预设新的数字版本号，不维护历史版本读取或迁移分支，不以旧产物兼容为验收目标。不符合当前契约的已有预测/赔率必须重新生成；保留可追溯原始历史数据的导入能力不等于兼容旧预测产物。

开始功能实现前使用 using-git-worktrees 技能建立隔离工作区，读取对应分支/worktree reference；当前请求仅写计划，不创建或切换分支。按任务精确暂存，不使用 `git add -A` 混入其他工作。

---

## 文件与接口布局

| 文件 | 职责 |
|---|---|
| 新增 `scripts/match_context.py` | 上下文枚举校验、稳定 ID、样本池质量检查；不访问网络 |
| 新增 `scripts/history_adapter.py` | 供应商/文件历史转换、比分语义及来源审计；不计算概率 |
| 修改 `scripts/contracts.py`、`schemas/*.schema.json` | 当前统一契约；不分版本读取，不伪造缺失字段 |
| 修改 `scripts/model_core.py` | 通用样本、ELO、中立场和质量输出 |
| 修改 `scripts/fetch_match_data.py` | CLI 上下文与赛季选择、数据源调度 |
| 修改 `scripts/fetch_lottery_data.py` | 官方赛事/玩法证据与状态标准化 |
| 修改 `scripts/generate_betting_recommendation*.py` | 推荐准入、身份匹配与报告 |
| 修改 `scripts/backtest_model.py` | 按目标上下文走步回测 |
| 新增 `tests/test_scope_*.py` | 按任务隔离的新单元及集成测试 |
| 新增 `tests/scope_fixtures.py` | 纯合成、明确标注的固定测试数据，不冒充官方记录 |
| 新增 `docs/adr/0002-sporttery-football-scope.md` | 新范围决策及仅使用最新实现的约束 |
| 修改 README、流程、skills 和 references | 与实现一致的用户契约 |

测试文件遵循 `tests/test_scripts.py` 的 sys.path 设置，标准库 unittest，不假设 tests 是 Python 包。

## Task 1：确定来源语义与可验证适配边界

**Files:** 新增 `docs/data-mappings.md`；新增 `tests/fixtures/provider/README.md`。

**Interfaces:** 产出后续任务使用的“来源 URL、访问日期、原始字段、已确认语义、未知时动作”映射表。没有文档证据的字段不加入可用状态或比分映射。

- [ ] 阅读中国体彩官方竞彩足球玩法规则、项目现有官方接口地址及 football-data.org v4 官方比分/比赛资源文档。记录真实 URL 和访问日期，不将抓包中看到的名字解释为权威语义。
- [ ] 对以下项逐条填写证据：常规时间是否含补时；加时和点球字段；中立场字段；赛事赛季/届次；比赛开售和玩法开售标识；赔率更新时间与截止时间。遇到无文档或无法访问，填写“未经官方确认 → unknown → 拒绝推荐”，不要阻塞安全默认实现。
- [ ] 明确测试来源：纯合成测试覆盖内部规范化契约；真实接口 fixture 必须脱敏并附来源，且不因测试通过就认定状态语义正确。
- [ ] 审阅映射表：每条“允许使用/在售”映射都有引用；其余全部 fail closed。交付前运行 `git diff --check`。
- [ ] 提交：`git add docs/data-mappings.md tests/fixtures/provider/README.md && git commit -m "docs: 明确竞彩足球数据映射证据与拒绝边界"`。

## Task 2：通用上下文和当前统一数据契约

**Files:** 新增 `scripts/match_context.py`、`tests/test_scope_contracts.py`；修改 `scripts/contracts.py`、全部四个 `schemas/*.schema.json`。

**Interfaces:**

```python
# match_context.py
# context: team_type=club|national|unknown;
# competition_type=league|cup|other|unknown;
# venue=home|neutral|unknown; score_basis=regulation|unknown
validate_context(context: dict) -> dict
stable_id(provider: str, entity_id: str) -> str
context_reasons(context: dict) -> list
# contracts.py：保留当前调用签名
validate_model_prediction(prediction: dict) -> dict
validate_odds_snapshot(snapshot: dict) -> dict
```

所有输出遵守当前统一契约，不增加数字版本或按版本分派。移除现有 `schema_version` 数字校验及各生产者中的固定数字标记；Schema、测试 fixture 和读取器同步清理，不引入 `latest` 字符串冒充可审计版本。需要追溯时记录生成时间和实际实现修订标识，而不是据此选择历史实现。新增 `match.context`，球队 ID 使用 `provider:id`；`data_snapshot` 增加 `provenance_status=verified|unverified`、`sample_pool`。`verified` 表示适配器具备记录的来源证据，不是文件声明即可自动获信。赔率增加 `official_listing` 与 `market_status`（Task 6）。预测 `quality` 仍为 sufficient/insufficient。

- [ ] 写出失败测试（更新现有 fixture 为当前完整契约，不保留历史版本契约测试）：

```python
class ScopeContextTests(unittest.TestCase):
    def test_unknown_venue_is_not_home(self):
        from match_context import context_reasons
        reasons = context_reasons(dict(team_type="national", competition_type="cup",
                                      venue="unknown", score_basis="regulation"))
        self.assertIn("venue_unknown", reasons)

    def test_ids_do_not_collide(self):
        from match_context import stable_id
        self.assertNotEqual(stable_id("alpha", "1"), stable_id("beta", "1"))
```

更新 `make_prediction()`，补全上下文/来源/样本池，分别验证 `J1`、`CUP-X`、`INT-X` 接受，空白代码、非法枚举拒绝；缺少当前必填上下文的已有产物直接拒绝，不能通过数字标记绕过校验。

- [ ] 本地运行 `python3 -m unittest discover -s tests -p 'test_scope_contracts.py' -v`，记录缺失接口导致的失败。
- [ ] 实现独立枚举校验和非空字符串校验；名称映射不承担白名单职责。`stable_id` 必须要求 provider 与原 ID 非空，禁止不同来源自动消除前缀。

```python
# 唯一校验入口，无历史版本分支；缺失当前必填字段即拒绝。
context = require_mapping(match.get("context"), "prediction.match.context")
validate_context(context)
# JSON Schema 直接声明当前 required/properties，不使用多版本 oneOf。
```

- [ ] 重跑新测试和旧 `TestContracts` 相关测试。Schema 增加与运行时相同的 required/enum/pattern；若本地已有 JSON Schema 验证器，对同一批正反 fixture 双重验证，否则记录缺少工具，不宣称 Schema 执行验证通过。
- [ ] 精确暂存本任务文件，提交 `feat: 引入通用赛事上下文与统一数据契约`。

## Task 3：历史标准化与样本适用性

**Files:** 新增 `scripts/history_adapter.py`、`tests/test_scope_history.py`、`tests/scope_fixtures.py`；修改 `scripts/match_context.py`、`scripts/model_core.py` 历史标准化函数。

**Interfaces:**

```python
# history_adapter.py
normalize_history_record(raw: dict, provider: str, context: dict) -> dict
# 输出保留 match_id/kickoff_utc/home_team/away_team/home_score/away_score/context
prepare_history(records: list, provider: str, context: dict) -> tuple
# 返回 (normalized_records, rejected_records)，每个拒绝包含 match_id/reason
# match_context.py
sample_pool_reasons(matches: list, target: dict, sample_pool: dict) -> list
# sample_pool: pool_id, team_type, competition_codes（非空列表）
```

同一类型与声明赛事集合只是必要条件；目标两队必须在开球前样本的对阵图中连通，否则 `history_pools_disconnected`。连通性不是精度证明，报告保留跨赛事未校准限制。输入中未知类型、未声明赛事和俱乐部/国家队混用拒绝；不能偷偷过滤后仍宣称来源完整。

- [ ] 建立合成 fixtures：`regular_history(team_type="club", venue="home") -> list` 生成 12 场、三个带来源球队、非零进球、按日排序的标准历史；每条明确 context、competition_code。`target_match(...) -> dict` 生成第 13 天目标，`verified_snapshot() -> dict` 仅用于测试，URL 使用 `https://example.invalid/fixture`，标明 synthetic。
- [ ] 写失败测试：

```python
class HistoryScopeTests(unittest.TestCase):
    def test_fractional_score_is_rejected(self):
        from history_adapter import normalize_history_record
        from scope_fixtures import regular_history
        raw = regular_history()[0]
        raw["home_score"] = 1.5
        with self.assertRaises(ValueError):
            normalize_history_record(raw, "fixture", raw["context"])
```

增加：布尔/负数比分拒绝；含加时最终比分但无可核实常规比分拒绝；可信常规比分 1:1 与最终比分 2:1 同时存在时取 1:1；未知比分不推断；规范化两次结果不变；国家队/俱乐部混用拒绝；分离对阵图不通过。

- [ ] 运行 `python3 -m unittest discover -s tests -p 'test_scope_history.py' -v` 确认失败。
- [ ] 实现整数校验和 Task 1 已核实映射。未核实 provider 只能接受明确规范化数据作为诊断输入，来源未验证时不授予正式资格。历史归一化保留 context，避免 `finished_matches_before()` 的重复归一化丢失中立场字段。

```python
if isinstance(value, bool) or not isinstance(value, (int, float)):
    raise ValueError("invalid_regulation_score")
if not math.isfinite(value) or value < 0 or int(value) != value:
    raise ValueError("invalid_regulation_score")
```

- [ ] 重跑测试。断言每条剔除数据有可审计原因，零可用历史是错误，不生成默认赛果。
- [ ] 提交 `feat: 标准化常规时间历史与样本池质量检查`。

## Task 4：通用模型、中立场与质量门槛

**Files:** 修改 `scripts/model_core.py`；新增 `tests/test_scope_model.py`；必要时扩充 `tests/scope_fixtures.py`。

**Interfaces:** 保留 `create_prediction(history_matches, match, data_snapshot, parameters=None)` 和 `build_elo_ratings(...)` 签名；消费 Task 2/3 上下文与样本池；输出符合当前契约的预测及完整 `quality.missing_data`。`SUPPORTED_COMPETITIONS` 更名 `COMPETITION_NAMES`，只映射名称。模型名称改为 `football-elo-poisson`，移除旧的固定数字模型版本及其校验，只运行本次最新实现。

- [ ] 写失败测试：

```python
class NeutralModelTests(unittest.TestCase):
    def test_neutral_equal_strength_expectation(self):
        from model_core import expected_home_result
        self.assertEqual(expected_home_result(1500, 1500, 0), 0.5)
```

上述基础测试之外，必须构造对称历史，调用 `create_prediction`，断言 neutral 目标 `expected_goals.home == expected_goals.away`；单场 neutral 平局不会改变两队相等 ELO；同一历史换 home 场地后评级改变；unknown 场地为 insufficient；J1 和 national/cup 不被白名单拒绝。

- [ ] 运行 `python3 -m unittest discover -s tests -p 'test_scope_model.py' -v` 记录新场景失败。
- [ ] 改历史 ELO、目标期望、进球基准三处：

```python
advantage = 0.0 if context["venue"] == "neutral" else parameters.home_advantage_elo
if target_context["venue"] == "neutral":
    home_baseline = away_baseline = (total_home_goals + total_away_goals) / (2 * len(finished))
```

unknown 只可诊断，必须追加质量原因；不要因目标中立就将所有历史主场优势都清零。俱乐部/国家队分别选择并记录参数配置标识（club-baseline/national-baseline），即使暂用相同未校准数值也不共用评级池。输出记录样本组成、剔除数及跨赛事基线限制。

- [ ] 将 context、sample_pool、来源检查和队伍最少场数原因合并；来源缺失不覆盖其他原因；质量不合格不能在投注层绕过。
- [ ] 重跑模型、历史、旧模型回归测试；旧测试若假设未知数据 sufficient，改为明确上下文或断言拒绝，不能删除测试以获得通过。
- [ ] 提交 `feat: 支持通用足球预测与中立场建模`。

## Task 5：CLI、实时赛季选择与历史快照

**Files:** 修改 `scripts/fetch_match_data.py`；新增 `tests/test_scope_fetch.py`；修改 `scripts/README.md` 的输入格式说明。

**Interfaces:** `fetch_live_history(client, competition_code, kickoff, seasons, season=None)` 增加可选显式赛季；`load_history_file(path)` 保持二元返回 `(history, snapshot)`；新增 CLI `--competition-name`、`--team-type`、`--competition-type`、`--venue`、`--context-file`，各枚举允许 unknown，不允许用户参数直接声明 provenance verified。

- [ ] 写失败测试：

```python
class ScopeCliTests(unittest.TestCase):
    def test_any_competition_is_parseable(self):
        from fetch_match_data import parse_args
        args = parse_args(["--competition", "J1", "--list-teams"])
        self.assertEqual(args.competition, "J1")
```

另用 `unittest.mock` 验证 `--season 2025` 实际请求 2025 而不是从 kickoff 再推断；未知杯赛缺 season 时要求显式届次；旧数组快照不把 mtime 写成已验证观测时间；文件未给 match_id 不生成 `football-data:` 假来源；401/403/404/空历史为明确错误。

- [ ] 运行 `python3 -m unittest discover -s tests -p 'test_scope_fetch.py' -v` 确认失败。
- [ ] 删除 competition choices，用非空校验；名称 `COMPETITION_NAMES.get(code, explicit_name or code)`。所有路径将目标 context 传入模型。保留 `--list-teams`，输出 `team_registry` 和来源字段。

```python
if season is not None:
    start = season
elif competition_code in VERIFIED_JULY_SEASON_COMPETITIONS:
    start = season_start_year(kickoff)
else:
    raise ContractError("explicit_season_required")
```

`VERIFIED_JULY_SEASON_COMPETITIONS` 只来自 Task 1 核实记录，不直接复制旧白名单为“已核实”。单届杯赛不盲取连续年份，所需跨赛事历史通过明确快照输入。

- [ ] 更新快照文档：显式原始来源/时间、sample_pool/context；离线数组可诊断，无法确认来源时 insufficient；不要把本地绝对路径包装为远端来源。
- [ ] 重跑测试与 `--help` 烟测，提交 `feat: 开放赛事输入并明确历史来源与赛季选择`。

## Task 6：官方赛事、玩法销售状态和推荐准入

**Files:** 修改 `scripts/fetch_lottery_data.py`、`scripts/generate_betting_recommendation.py`、`scripts/generate_betting_recommendation_strict.py`、`scripts/contracts.py`、赔率/报告 Schema；新增 `tests/test_scope_betting.py`。

**Interfaces:**

```python
# 新标准字段，状态映射只能由 Task 1 已核实的适配逻辑生成
# match.official_listing = {"status": "confirmed|unknown", "source_url": str,
#                           "observed_at": str, "provider_match_id": str}
# match.market_status = {"had": "open|closed|unknown", ...}
# betting.py
recommendation_reasons(prediction: dict) -> list
market_reasons(match: dict, market: str) -> list
```

`analyze_daily`/`evaluate_match` 保持现有函数调用结构，但只接收当前契约。缺少当前必填字段的产物在加载时拒绝，并要求重新生成，不提供历史读取路径。当前 snapshot 的 `source_mode="live"` 或手写 official_listing 不构成来源真实性证明：实时入口只从固定官方地址取数；显式文件保留原始证据供校验，缺少可核对证据则拒绝。内部纯函数接受的是已校验快照，不能向用户宣称 JSON 字段本身具有防伪能力。

- [ ] 写失败测试：

```python
class MarketScopeTests(unittest.TestCase):
    def test_missing_market_status_is_unknown(self):
        from generate_betting_recommendation import market_reasons
        self.assertIn("market_sale_unknown", market_reasons({}, "had"))
```

增加端到端断言：官方列表无该场→无建议；比赛 open、HAD closed→不评估 HAD；unknown 同理；非五大联赛 confirmed+有效预测可进入评估（不保证 EV 足够）；缺当前上下文但标记 sufficient 的产物→拒绝；自填 lottery ID 不绕过官方清单；重复 ID、同名不同来源、时间不符均拒绝；过期赔率/停售/缺赔率/仓位上限回归。

- [ ] 运行 `python3 -m unittest discover -s tests -p 'test_scope_betting.py' -v` 确认失败。
- [ ] 移除 `_sale_state` 对 live 缺状态直接 open 的回退，除非 Task 1 有足够官方证据证明具体清单仅包含在售场次；即使比赛资格确认也不推断玩法状态。记录官方清单观测时间，保持比赛/赔率时间检查。
- [ ] 在 `evaluate_match` 各玩法计算前应用 `market_reasons`，并在报告中返回逐玩法拒绝；新增原因有中文说明。`recommendation_reasons` 检查当前契约、context、provenance、sample_pool 与 quality，不能只信任 `quality.status` 字符串。
- [ ] 收紧映射：命中官方 ID 后仍核对两队身份/显式映射和开球时间；不把不同供应商同号 ID 当成相等。默认开球容差改为 15 分钟并记录策略，超出需更新目标数据，不沿用当前 6 小时宽限。
- [ ] 新标题统一为“竞彩足球投注分析”；未知状态显示“未经官方确认”，不生成替代赔率。回归 JSON/Markdown 一致、默认串关关闭与风险参数不变。
- [ ] 重跑测试，提交 `feat: 按官方赛事与玩法资格执行推荐准入`。

## Task 7：按赛事上下文走步回测

**Files:** 修改 `scripts/backtest_model.py`、回测 Schema；新增 `tests/test_scope_backtest.py`；修改 `tests/test_scripts.py` 相关回归。

**Interfaces:** `run_walk_forward(history_matches, competition_code, min_training_matches=50, parameters=None, sample_pool=None)` 增加可选池描述；输出当前统一报告，模型指标 key 改为 `football_elo_poisson`；不实现旧报告兼容读取器。

- [ ] 写失败测试：

```python
class WalkForwardScopeTests(unittest.TestCase):
    def test_non_top_five_runs_without_future_data(self):
        from scope_fixtures import regular_history
        from backtest_model import run_walk_forward
        from model_core import ModelParameters
        report = run_walk_forward(regular_history(), "J1", min_training_matches=4,
                                  parameters=ModelParameters(min_team_matches=1))
        for item in report["audit"]:
            self.assertLess(item["latest_training_kickoff_utc"], item["target_kickoff_utc"])
```

fixture 中每条 J1、context 和 provider 均明确；pool=None 从单一明确赛事历史构建池，不能给未知输入默认有效池。另测目标 neutral 传递到模型和 `_simple_elo_probabilities`；相同开球时间不可互训；错误比分被审计；国家队独立池；无合格目标报错。

- [ ] 运行 `python3 -m unittest discover -s tests -p 'test_scope_backtest.py' -v` 记录失败。
- [ ] 删除白名单，按每条 target.context 预测；基线使用同一 neutral 主场优势规则。所有样本筛选和图连通性只使用目标开球之前的数据，不能以全量未来图判断当时可比性。
- [ ] 输出 target context、pool 组成、跳过/剔除原因、最新训练时间；无历史赔率仍不计算 ROI/CLV。Schema 与新指标 key 同步。
- [ ] 重跑回测和模型测试，提交 `feat: 扩展走步回测至通用足球赛事`。

## Task 8：文档、技能与最终集成验收

**Files:** 修改 `README.md`、`process.md`、`scripts/README.md`、`docs/adr/0001-club-league-data-contracts.md`、`.agent/skills/match-prediction/SKILL.md` 及全部现有 references、`.agent/skills/lottery-betting-recommendation/SKILL.md` 及 betting-methodology reference；新增 ADR 0002、`tests/test_scope_integration.py`。

**Interfaces:** 文档以最新 CLI/当前契约为唯一用法；旧 ADR 标注范围决策被 ADR 0002 替代，不删除历史。技能触发条件覆盖全部竞彩足球，不把数据不足说成不支持该赛事。

- [ ] 修改 skills 前读取 writing-skills 技能，依其要求验证触发与拒绝行为，不只机械替换“五大联赛”。
- [ ] 写 CLI 集成测试，使用 `tempfile.TemporaryDirectory` 和 `unittest.mock`，生成合成非五大联赛历史/赔率，经 `fetch_match_data.run` → `strict_betting.run` → Markdown 渲染；断言当前契约必填字段完整、任意赛事代码保留、未确认玩法无建议、neutral 元数据不丢失。不连接网络。

```python
# 集成拒绝用例的核心断言（report 为真实 run 返回结果）
self.assertEqual(report["recommendations"], [])
self.assertTrue(report["rejections"])
self.assertEqual(report["bankroll"]["staked"], 0.0)
```

- [ ] 本地运行 `python3 -m unittest discover -s tests -p 'test_scope_integration.py' -v`，定位真实断链，再修正文档/代码必要连接。
- [ ] README 支持范围改为“以官方竞彩足球清单为准”；保留 PL 示例，新增明确标注为合成的 J1/cup/national 离线示例。使用说明要求按最新实现重新生成预测与投注建议，说明 source/season/context 必要性；不编写版本间迁移或兼容指南。
- [ ] 更新模型文档、数据来源、引用、回测、契约和投注方法，明确尚未校准及数据覆盖不等于业务范围。Task 1 未核实的字段及受阻功能列入当前限制。
- [ ] 本地最终运行 `python3 -m unittest discover -s tests -p 'test*.py' -v`；运行 CLI `--help`、已有 Schema 验证工具、`git diff --check`。本项目无需远程 package 流程。
- [ ] 执行文本核对：`rg -n '五大|five-league|SUPPORTED_COMPETITIONS|不用于国家队|只处理' README.md process.md scripts schemas .agent docs`。历史 ADR、PL 示例和迁移说明可命中；运行时白名单和排除国家队规则不可残留。
- [ ] 使用 requesting-code-review 技能审阅安全边界及当前契约一致性；发现问题修复后重跑受影响测试。精确暂存，提交 `docs: 更新全部竞彩足球适用范围与迁移说明`。

## 依赖与交付

顺序：1 → 2 → 3 → 4 → 5 → 6 → 7 → 8。任务共享契约，不建议未经接口冻结就并行改同一文件。可委派只读来源核查或测试审阅，但最终实现按序交付。

最终交付必须分别列出：业务范围扩展结果、实际数据接入覆盖、无法确认的来源字段、测试命令及结果、未运行验证、最新流程的产物重新生成方法和实际提交。没有实时验证时只声明离线验证结果；不能声称已获得全部竞彩足球赛事的实时预测能力。

## 计划自检对照

| 设计要求 | 实现任务 |
|---|---|
| 官方范围、玩法不扩张、传统足彩排除 | 1、6、8 |
| 当前统一契约、任意赛事代码、无旧版兼容 | 2、5、8 |
| 来源、常规时间比分、样本池与稳定 ID | 1、2、3、5 |
| 中立场、国家队/俱乐部隔离、质量拒绝 | 3、4、6 |
| 显式赛季、供应商权限与覆盖限制 | 1、5 |
| 官方及玩法资格、映射、过期与风险门槛 | 6 |
| 无未来泄漏的回测及拒绝审计 | 7 |
| CLI、Schema、skills、历史 ADR 与集成验收 | 2、8 |

本项目本地测试权限已明确，不再设置远程环境确认门槛。提供方字段无法核实不是猜测实现的理由，对应能力保留 unknown 并拒绝正式推荐。
