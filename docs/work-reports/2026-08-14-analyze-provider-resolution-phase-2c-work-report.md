# Analyze Provider Result Resolution Simplification — Phase 2C Work Report

日期：2026-08-14
分支：`refactor/simplify-analyze-provider-resolution-phase-2c`

## 基线、授权与范围

- 仓库中不存在 `AGENTS.md`；已按要求记录并继续。
- Phase 2B PR #65 在合并前重新确认：状态 OPEN，base 为 `main`，head 分支为
  `refactor/simplify-analysis-contract-phase-2b`，head SHA 为
  `e25de5815f19dea884a1b06276bee6bf04b2028e`，`MERGEABLE/CLEAN`，最终 head
  的所有实际检查成功，改动文件与 Phase 2B Work Report 一致。
- 仓库未配置带 required 标记的 branch check；`gh pr checks 65 --required`
  明确返回无 required checks，而最终 head 的全部 CI checks 均为 success。
- PR #65 使用普通 merge commit 合并；没有 squash，也没有删除远程分支。
- Phase 2B merge commit：`3b9a0b4065adc2ab9f02f52639d07c369b838efe`。
- 合并后 main CI：CI run `31797367497` success；Java Normalization Candidate
  run `31797367740` success。
- Phase 2C 基线：最新 `origin/main`，SHA
  `3b9a0b4065adc2ab9f02f52639d07c369b838efe`。
- Phase 2C 最终生产代码 SHA：
  `a471baba71314860f0b30596a9058aebc9480d18`。

本阶段只修改 `backend/legacy_application.py` 中 `/api/analyze` 的连续 Provider
结果处理流程及两个紧邻的专用 helper。没有修改 `analysis_contract.py`、Provider
transport、retry/repair/deadline 配置、AsyncOpenAI、History、RAG 实现、Resume、前端、
数据库、Alembic、Java、Redis、Worker、Outbox 或 Agent Run。

## 代码变化

保留的行为和结构：

- `run_llm_analysis`、`scan_llm_output`、`parse_model_json`、
  `validate_structured_output` 的 workflow step 顺序、状态和原有 message 不变。
- Provider 调用、输出安全扫描、一次 format repair、结构化校验、evidence grounding
  和后续 RAG reconciliation 的执行边界不变。
- complete、repaired、partial、fallback 状态以及 `provider_call_failed`、
  `minimum_safe_contract_failed`、`provider_deadline_exhausted`、
  `client_disconnected` fallback category 不变。
- 用户可见 warning、日志 message、HTTP 路径/状态码、JSON shape 和错误 envelope 不变。

删除或收敛的重复逻辑：

- 新增 `_select_provider_fallback`，由三类 fallback 路径共同使用；它只负责本地
  deterministic fallback、统一 warning，以及 `result_state`、`fallback_reason`、
  `deadline_exhausted`、`fallback_selected` 的安全 metadata。
- 新增 `_provider_deadline_exhausted`，统一 Provider failure 与 parse/repair failure
  对同一 deadline/exception metadata 的判断。
- Provider exception 的 ModelOutputError/普通 exception 两个 metadata 分支合并为一次
  `safe_model_metadata` 收尾，同时保留 ModelOutputError 已有的安全 metadata。
- 删除三处重复的 `local_fallback_result` 参数组、warning 和 fallback metadata 构造。
- 删除与 `analysis_status == "fallback"` 重复维护的 `provider_available` 状态；输出扫描和
  JSON 解析直接使用最终结果状态判断。
- Provider phase 最终 duration、remaining deadline bucket、result state 以及 History/
  idempotency/client-disconnect 的后续 metadata 收尾仍保留在原位置，因为这些字段在
  不同 workflow 边界才能确定，合并它们会改变观测时机。

没有引入状态机、注册系统、抽象基类、兼容包装层或新文件拆分。

## 代码统计与复杂度

统计范围为基线 `3b9a0b4...` 到最终生产代码 SHA `a471bab...`，仅统计代码；
完全排除 `docs/**`、Markdown、Work Report 和索引。

| 范围 | 增加 | 删除 | 净变化 |
|---|---:|---:|---:|
| 生产源代码 | 65 | 83 | -18 |
| 测试代码 | 0 | 0 | 0 |

没有删除测试。`backend/legacy_application.py` 从 4415 行降至 4397 行。

AST 行跨度和主要控制分支按 `if`、`for`、`async for`、`while`、`try`、`match`
统计：

| 函数 | 基线 | Phase 2C |
|---|---:|---:|
| `analyze` | 1196 行，77 分支 | 1148 行，76 分支 |
| `_provider_deadline_exhausted` | 不存在 | 3 行，0 分支 |
| `_select_provider_fallback` | 不存在 | 23 行，0 分支 |

`analyze` 减少 48 行并减少 1 个主要分支；新增 helper 均为本流程专用、无控制分支。

## complete / repaired / partial / fallback 行为证据

基线 main 和 Phase 2C 使用同一组未修改的测试断言。最终代码另外显式运行四个 API
场景，4 tests 全部通过：

- complete：Provider 正常返回后检测到 client disconnect，结果仍为 complete，
  `client_disconnected=true`，Provider 只调用一次，completed replay 与首次响应一致。
- repaired：primary 返回 malformed JSON，唯一 repair 返回可用结果；状态 repaired，
  primary 与 repair 各调用一次，completed replay 完全一致。
- partial：支持字段外包含额外 Provider 字段；HTTP 200，状态 partial，
  `parse_outcome=canonical`，安全 salvage category 保留，未选择 fallback。
- fallback：malformed Provider 输出且唯一 repair 不可用；HTTP 200，状态 fallback，
  category 为 `minimum_safe_contract_failed`，确定性 fallback shape 保留，Provider
  fragment 不出现在响应中。

额外 fallback 与边界证据：

- 普通 Provider exception 保持 `provider_call_failed`。
- deadline 在调用前耗尽时保持 `provider_deadline_exhausted`、
  `deadline_exhausted=true`，且不构造 Provider client。
- 请求在 Provider 前断开时保持 `client_disconnected`，Provider 不调用，fallback
  只 finalize 一次并可 completed replay。
- malformed/truncated/empty/oversized、安全扫描、evidence grounding、RAG on/off
  由 acceptance、resilience、deadline、RAG 和完整后端测试覆盖。
- DeepSeek acceptance 继续断言最多两次 primary；format repair 最多一次，因此总体最多
  两次 primary 加一次 repair。Phase 2C 没有修改调用函数、transport 或 deadline。

## 验证命令与真实结果

所有测试数据均为仓库 fixture、合成值或 Mock Provider。没有读取、输出或提交真实密钥、
Cookie、Resume、JD、Provider 原始响应或生产数据。

- `git diff --check`：通过。
- `.venv/bin/python -m compileall -q backend scripts`：通过。
- 定向组合：
  `python -m unittest -v test_provider_deadline_enforcement.py
  test_deepseek_provider_acceptance.py test_pragmatic_provider_acceptance.py
  test_v203_analysis_resilience.py test_v201_rag.py test_analyze_idempotency.py`：
  136 tests，全部通过。
- 四状态显式场景：complete、repaired、partial、fallback 共 4 tests，全部通过。
- 后端完整测试：`python -m unittest discover -v`，使用独立临时 SQLite；
  556 tests 全部通过，12 个 PostgreSQL opt-in tests 按预期 skip。
- PostgreSQL 16.9 隔离容器：
  `PJA_RUN_POSTGRES_TESTS=1 python -m unittest -v test_v2_postgres_integration.py`：
  12 tests，全部通过；容器已停止。
- 前端 `npm run test -- --run`：9 test files、70 tests，全部通过。
- 前端 `npm run build`：production Vite build 成功。
- Alembic fresh `upgrade head`、`current`、`heads`：current/head 均为
  `20260730_07`。
- `POSTGRES_TOOL_IMAGE=personal-job-agent-backend:ci@sha256:aaaa... docker compose
  --env-file .env.example config --quiet`：通过。
- `PJA_SMOKE_MILESTONE=2.0.6 PJA_APP_VERSION=2.0.6
  scripts/docker-smoke-v2.sh`：Version 2.0.6 isolated Mock LLM smoke 全部通过，覆盖
  Alembic current=head、health/auth/CSRF、Profile/Resume/Analyze、RAG/evidence/
  grounding、restart persistence、backup/restore 和 checksum；Compose 项目及 volumes
  已清理。

首次定向测试命令未设置 `APP_DATABASE_PATH`，被仓库 `APP_ENV=test` SQLite 安全门在
加载测试前拒绝，没有执行测试用例。随后所有 SQLite 测试均改用独立 `mktemp` 路径并
获得上述成功结果。

## 已知风险与回滚

- `analyze` 仍然很长；本阶段严格限制为 Provider resolution 连续流程，没有借机重写
  handler 的其他部分。
- `_select_provider_fallback` 依赖已经过输入扫描的 `WorkflowContext` 文本，与原有三处
  `local_fallback_result` 调用使用相同参数。后续若调整 fallback 输入边界，应同时更新
  三类 fallback 场景测试。
- timing metadata 本身具有运行时波动；字段、单位、边界和安全过滤保持不变，测试不把
  某次执行的具体毫秒值当作行为契约。
- 回滚生产代码可执行
  `git revert a471baba71314860f0b30596a9058aebc9480d18`；该操作不会回滚 Phase 2B
  merge commit，也不涉及数据库 schema 或部署状态。
- Phase 2C PR 未获合并授权；交付时必须保持 OPEN。
