# Provider Deadline Simplification Phase 2A Work Report

## 交付摘要

- 日期：2026-08-14
- 仓库：https://github.com/HKJoker-Z/personal-job-agent
- Phase 1 PR：[＃63](https://github.com/HKJoker-Z/personal-job-agent/pull/63)
- Phase 1 merge commit：`7193cd01b9bf077a818e6ba9b7ee75b70bc0a35a`
- Phase 2A 基线 SHA：`7193cd01b9bf077a818e6ba9b7ee75b70bc0a35a`
- Phase 2A 运行时实现 SHA：`e5e4ae55d4cf3c0e262960e409eb90bc77573eb9`
- Phase 2A 分支：`refactor/simplify-provider-deadline-phase-2a`
- Phase 1 分支：合并时保留，未删除远程分支
- AGENTS.md：未发现（在仓库及 `/home/lighthouse/project` 项目范围搜索）
- 当前结论：代码实质减少且本地验证通过；待推送分支、创建 PR 后检查 GitHub CI，不能据此报告生产部署或真实 Provider 验收。

本报告只涉及 Analyze 的 Provider timeout/deadline 执行链路。没有修改
History、Project Knowledge、前端、数据库、Java normalization、Redis、Worker、
Outbox、Agent Run、Compose 或生产拓扑。

## 1. Phase 1 合并前置条件与新基线

PR #63 合并前核对结果：

- 状态 `OPEN`；base `main`；head
  `refactor/behavior-preserving-simplification-phase-1`。
- GitHub 报告 `mergeable=MERGEABLE`、`mergeStateStatus=CLEAN`。
- 实际文件 diff 只有 `backend/app/application.py`、`backend/main.py`、Phase 1
  Work Report 和 Work Report 索引；与 Phase 1 Work Report 一致。
- diff 中没有密钥、生产数据、二进制/生成文件、数据库 dump 或用户文档。
- 所有实际检查为 success；按仓库策略跳过的 publish image 检查没有作为失败。

使用普通 merge commit 合并，没有 squash，也没有删除 Phase 1 远程分支。合并后：

- `main` CI workflow：GitHub run `31779662016`，所有 job success。
- Java Normalization Candidate push workflow：GitHub run `31779661969`，
  isolated candidate success，耗时 5m28s。
- fetch 后 `origin/main` 为
  `7193cd01b9bf077a818e6ba9b7ee75b70bc0a35a`。
- 工作树干净后从该 SHA 创建 Phase 2A 分支。

没有执行 workflow_dispatch、部署、发布镜像、Tag 或 Release。

## 2. 修改内容

### 删除或合并的重复逻辑

1. `DeadlineHttpxClient` 的真实 Provider 路径是 OpenAI SDK 的 non-streaming
   completion。原实现先在线程中等待 response headers，再为 body 的每个 chunk
   建立线程并重复检查 absolute deadline。现在把完整 body read 放入同一个已经有
   deadline/close 保护的 worker，删除 `_DeadlineSyncByteStream` 和逐 chunk 线程
   包装。控制线程仍在 absolute deadline 到达时关闭 HTTPX client；活动网络操作
   不会因为删除 wrapper 而无界等待。
2. `ProviderAttemptTimeout.remaining_seconds` 没有仓库调用方，删除该未使用字段。
3. `ProviderDeadline.can_start()` 只是 `call_timeout() is not None` 的重复包装，
   删除并让调用方直接使用同一个 timeout calculation。
4. `call_deepseek_raw()` 循环入口已经计算 `attempt_timeout`；
   `_build_provider_client()` 不再重新调用 `deadline.call_timeout()`，而是消费这
   个已计算的 `ProviderAttemptTimeout`。这同时避免了重复 deadline 检查和未使用的
   返回值。
5. `call_deepseek_raw()` 将 `ModelOutputError` 和普通 Provider exception 的
   重复 metadata/attempt/retry 防御路径合并；错误码、timeout category、日志分支、
   retry 条件和安全 metadata 形状保持分开可读。
6. retry 结束判断不再额外检查已经由 `call_timeout()` 覆盖的 `remaining <= 0`，
   并删除最终 `can_start()` 的重复检查。
7. `call_deepseek_repair()` 不再先构造 deadline error、再立即捕获并重新转换该
   error；deadline 检查移动到 adapt 成功后的唯一转换点。成功 response 的两次
   `ProviderAnalysisResponse` metadata 构造也合并为一次。

### 明确保留的行为和安全边界

- 一个 monotonic absolute deadline 贯穿 primary retry 和单次 format repair。
- external client 180 秒契约、总 Analyze safety deadline 175 秒、Provider 默认
  130 秒、30 秒 fallback/finalization reserve、retry reserve、repair reserve 和
  1 秒 minimum call budget 均未修改。
- connect/read/write/pool timeout 仍分别受 5/attempt budget/10/5 秒组件限制，
  并再次被 absolute deadline 截断；SDK `max_retries=0` 保留。
- primary 最多两次、format repair 最多一次、一次新 Analyze 最多三次 Provider
  call；finish-length retry 仍使用原 output-token 上限。
- response body 的硬 total deadline、超时后关闭活动 HTTPX client、响应长度限制、
  本地解析、field salvage、security scan、evidence grounding 和确定性 fallback
  均保留。
- `complete`、`repaired`、`partial`、`fallback` 状态和 retry/repair/fallback、
  timeout category、attempt duration、remaining bucket、request correlation 等
  内部日志/metadata 字段保留。
- client disconnect 检查、idempotency claim/attempt token、History finalization
  和 completed replay 路径没有修改。
- 输入大小限制、Provider response 限制、secret/PII/Prompt injection 扫描和
  不向用户暴露原始 Provider exception 的边界没有修改。

当前 SDK `openai=2.44.0` 同时提供 `OpenAI` 和 `AsyncOpenAI`。本阶段没有把同步
Provider API 改成 async：仓库中真实调用链、offline candidate 和大量 contract/
RAG 测试仍以同步 `call_deepseek_raw`、`call_deepseek_repair` 和
`analyze_with_deepseek` 为入口；引入 async wrapper 或 `asyncio.run` 会改变这些
调用边界，并不能在本阶段安全地声称行为不变。保留同步边界的同时，已把实际
non-stream transport 的两个线程层级简化为一个总 deadline worker。

没有新增没有调用方的兼容层，也没有把原实现拆到更多文件。

## 3. 行数与复杂度

### 生产运行时代码

| 文件 | 基线行数 | Phase 2A 行数 | 增加 | 删除 | 净变化 |
|---|---:|---:|---:|---:|---:|
| `backend/provider_deadline.py` | 303 | 231 | 11 | 83 | -72 |
| `backend/legacy_application.py` | 4,445 | 4,415 | 64 | 94 | -30 |
| 修改范围合计 | 4,748 | 4,646 | 75 | 177 | **-102** |

数字来自 `git diff --numstat origin/main...e5e4ae55d4cf3c0e262960e409eb90bc77573eb9`
和 checkout 后的 `wc -l`；没有用删除测试或文档来抵消生产代码。

### 测试和文档

| 范围 | 基线 | Phase 2A | 净变化 |
|---|---:|---:|---:|
| `backend/test_provider_deadline_enforcement.py` | 406 | 406 | 0 |
| 测试代码改动 | 0 | 0 | 0 |
| Work Report 文件 | 0 | 287 | +287 |
| `docs/work-reports/README.md` | 基线行数 | 基线 + 1 | +1 |

`wc -l` 实测本报告 287 行；本阶段文档新增合计 288 行（报告 287 行、索引 1 行）。

测试没有为了数字而删除或改写；已有 transport、retry、repair、fallback 和
contract 测试直接验证简化后的路径。

### AST 函数长度与主要分支

以下是用 Python `ast` 对 `origin/main` 与工作树同名函数计算的结果。复杂度是
可审查的近似值：`1 + if/for/while/try/except/条件表达式/布尔分支`，不是将其
冒充为某个未安装工具的官方 cyclomatic 数字。

| 函数 | 基线行数/分支 | Phase 2A 行数/分支 | 变化 |
|---|---:|---:|---:|
| `call_deepseek_raw` | 281 / 40 | 262 / 36 | -19 / -4 |
| `call_deepseek_repair` | 163 / 20 | 157 / 20 | -6 / 0 |
| `_build_provider_client` | 28 / 4 | 22 / 3 | -6 / -1 |
| `ProviderDeadline.call_timeout` | 29 / 2 | 28 / 2 | -1 / 0 |
| `DeadlineHttpxClient._send_until_deadline` | 41 / 8 | 41 / 8 | 0 / 0 |
| `DeadlineHttpxClient.send` | 41 / 6 | 37 / 5 | -4 / -1 |
| `analyze`（整个 legacy 文件最大函数） | 1,196 / 170 | 1,196 / 170 | 0 / 0 |

最大函数仍是不在本阶段范围内的 Analyze handler，未为了 Phase 2A 同时拆分
History/Project Knowledge 或前端。Provider 主要执行函数长度和 raw retry 分支
已实际下降；repair 分支数量不增加。

## 4. 行为保持证据

- 基线定向集合：`Ran 145 tests in 89.950s — OK`。
- Phase 2A 定向集合：`Ran 145 tests in 88.387s — OK`。
- 最终 Provider deadline 定向回归：`Ran 23 tests in 3.004s — OK`。
- 后端完整测试：`Ran 555 tests in 256.009s — OK (skipped=12)`；12 项是明确
  opt-in 的 PostgreSQL 测试，不是失败。
- PostgreSQL 16 临时容器集成：`Ran 12 tests in 42.267s — OK`，完成后容器已
  清理。
- 前端：9 个 test files、70 tests passed；Vite production build passed。
- Docker smoke：2.0.6 isolated Mock LLM smoke passed，覆盖 fresh
  Alembic/current=head、authentication/CSRF、Analyze（知识库关闭与开启）、
  fallback、DOCX、History、重启持久化、backup/restore 和 readiness。
- Alembic 临时 SQLite：`current=20260730_07 (head)`，`heads=20260730_07 (head)`。
- Compose：production base、production override、test override 均 `config --quiet`
  通过。
- `git diff --check`、根目录 `python3 -m compileall -q backend scripts` 均通过。

这些测试只使用合成 Resume/JD/Provider fixture 或 Mock LLM。没有发送真实
DeepSeek 请求，没有读取或输出真实密钥、Cookie、简历、JD、Provider body 或生产
用户数据。路径、状态码、响应 shape、错误 envelope、数据库 schema、环境变量和
生产拓扑没有改动；RAG on/off、Stored Resume、PDF/DOCX、History on/off、首次
执行与 completed replay 的证据来自完整后端测试及 2.0.6 smoke。

## 5. 所有实际执行命令与结果

以下命令均在本阶段实际执行；命令中的 Provider、数据库和 smoke 凭据均为合成
测试值，敏感值不在报告中展开。

### 仓库、合并和基线

- `find /home/lighthouse/project -name AGENTS.md -print`：无输出；未发现。
- `git fetch origin main refactor/behavior-preserving-simplification-phase-1 --prune`：通过。
- `gh pr view 63 --json ...`、`gh pr checks 63`：状态/分支/diff/检查核对通过。
- `git diff --check origin/main...origin/refactor/behavior-preserving-simplification-phase-1`：通过。
- `gh pr merge 63 --merge --delete-branch=false ...`：普通 merge commit 成功，
  commit 为 `7193cd01b9bf077a818e6ba9b7ee75b70bc0a35a`。
- `git fetch origin main --prune`、`gh run view 31779662016`、
  `gh run view 31779661969`：合并后的 main workflows 全部 success。
- `git switch -c refactor/simplify-provider-deadline-phase-2a origin/main`：通过，
  基线为 `7193cd01b9bf077a818e6ba9b7ee75b70bc0a35a`，工作树干净。

### 基线和代码验证

- Provider/Analyze/Provider acceptance/RAG/idempotency/correlation 定向 unittest：
  `Ran 145 tests in 89.950s — OK`。
- 初次基线命令的日志收集尝试被本地安全规则拒绝了 `rm -f`；随后使用
  `mktemp` 重跑，测试结果如上。
- `python3 -m py_compile backend/provider_deadline.py backend/legacy_application.py`：
  通过。
- `git diff --check`：通过。
- `python3 -m compileall -q backend scripts`（第一次在 `backend` cwd 错用根路径）：
  输出 `Can't list 'backend'`/`Can't list 'scripts'`，不作为通过证据。
- 根目录重新执行 `python3 -m compileall -q backend scripts`：通过。
- Provider 定向测试：`Ran 23 tests in 3.004s — OK`。
- Phase 2A 定向集合：`Ran 145 tests in 88.387s — OK`。
- 后端完整：`env -u ... APP_ENV=test ... python -m unittest discover -v`：
  `Ran 555 tests in 256.009s — OK (skipped=12)`。
- PostgreSQL：临时 `postgres:16.9-alpine` 容器上执行
  `PJA_RUN_POSTGRES_TESTS=1 python -m unittest -v test_v2_postgres_integration.py`：
  `Ran 12 tests in 42.267s — OK`；容器退出并清理。
- `npm run test`：9 files、70 tests passed。
- `npm run build`：Vite production build passed，38 modules transformed。
- 临时 SQLite 上 `alembic upgrade head`、`alembic current`、`alembic heads`：
  `20260730_07 (head)` 与 `20260730_07 (head)`。
- `docker compose --env-file .env.production.example config --quiet`、生产
  override、test override：均 passed；仅使用合成进程环境覆盖。
- `PJA_SMOKE_MILESTONE=2.0.6 PJA_APP_VERSION=2.0.6
  PJA_TEST_PROJECT=pja-v2-final-phase2a-20260814 PJA_TEST_HTTP_PORT=18108
  PJA_TEST_POSTGRES_PORT=15468 scripts/docker-smoke-v2.sh`：通过；使用 Mock LLM，
  smoke Compose project 完成后清理。
- `git diff --name-only`：实现提交前只有两个 Provider 运行时代码文件。
- `git diff --numstat origin/main...HEAD`：`64/94` legacy、`11/83` deadline，
  合计 `75 additions / 177 deletions`，净 `-102`。
- AST measurement 初次脚本误用了不存在的 `ast.MatchCase`，失败后改为
  `ast.match_case` 重跑；表格中的函数长度/分支数字来自修正后的结果。
- `openai` SDK capability check：`openai=2.44.0 AsyncOpenAI=True OpenAI=True`；
  详见第 2 节未改 async 的原因。
- `git commit -m "refactor: simplify provider deadline execution chain"`：成功，
  runtime implementation SHA 为 `e5e4ae55d4cf3c0e262960e409eb90bc77573eb9`。

### 安全和范围检查

- 没有读取或输出任何真实 secret/Cookie/Resume/JD/Provider response。
- changed paths 只包含两个 backend Provider runtime 文件；没有 test fixture、
  generated artifact、database/schema、frontend、Java、Compose 或生产文件改动。
- 没有运行真实 Provider acceptance，没有访问生产 PostgreSQL/Redis，没有部署，
  没有创建 Tag/Release，没有发布镜像，没有触发 workflow_dispatch。

## 6. GitHub 交付状态

本报告写入时尚未推送 Phase 2A 分支；推送后将创建：

`Refactor: Simplify provider deadline execution without behavior changes`

PR。随后必须等待并检查该 PR 的 GitHub CI；Phase 2A PR 不授权合并，因此无论 CI
结果如何都不合并。由于本报告提交本身可能触发一次 PR CI，最终 handoff 会同时
核对报告提交后的最新 checks；不把本地结果冒充 GitHub CI 结果。

## 7. 未执行项目及原因

- 真实 DeepSeek/Provider acceptance：未执行。原因是禁止读取/输出真实凭据和
  Provider 原始响应；已有合成 SDK fixture、transport server、fallback 和完整
  smoke 足以验证本次执行链路。
- 生产部署、生产数据库、生产 Redis、生产用户数据：未执行；用户明确禁止。
- Tag、Release、镜像发布：未执行；用户明确禁止。
- `workflow_dispatch`：未执行；尤其没有触发任何生产或发布任务。
- async SDK 迁移：未执行。虽然 SDK 有 `AsyncOpenAI`，但当前真实同步调用方和
  测试契约需要先单独设计 async API 边界；本阶段不扩大范围。

## 8. 已知风险

- Provider transport 仍是同步 OpenAI-compatible SDK；保留 daemon worker 是为了
  在同步 HTTPX 调用无法被 Python 协作取消时仍能关闭活动连接。若底层 transport
  完全不响应 close，daemon worker 仍可能短暂存活，但请求线程和用户可观察路径
  仍受 absolute deadline 保护。
- 新 transport 为仓库唯一实际 Provider non-streaming 路径一次性读取 body；仓库
  没有 `stream=True` 的 `DeadlineHttpxClient` 调用方。未来若引入 streaming Provider
  调用，应先补充独立的 streaming contract，而不能直接复用本阶段假设。
- 没有真实 Provider 网络 cohort；网络代理、Provider 服务端行为和真实 response
  shape 的风险仍由既有 acceptance/candidate 流程管理。
- 最终 response deadline 到达边界附近的 timing 数字可能因调度变化，但 timeout
  category、attempt 数、fallback/repair/retry 语义和 safe metadata 字段保持不变。

## 9. 回滚方法

Phase 2A 尚未合并或部署。若 PR 审查发现问题，运行时改动可直接回滚：

```bash
git revert e5e4ae55d4cf3c0e262960e409eb90bc77573eb9
```

Work Report 和索引是独立文档改动，可单独保留作证据或按其文档提交 SHA 回滚；
没有生产 schema、镜像、配置或数据需要恢复。

## 10. 下一阶段建议

先完成本 PR 的 CI 审查，不合并。若要继续 async Provider，应先建立同步/异步
调用契约、disconnect/cancellation 语义、body size bound、retry/repair/fallback
状态快照和同步测试迁移计划，再以独立阶段评估 `AsyncOpenAI` + `asyncio.timeout`。
下一阶段不要同时处理 History、Project Knowledge、前端、Java normalization、
Redis、Worker、Outbox 或数据库迁移。
