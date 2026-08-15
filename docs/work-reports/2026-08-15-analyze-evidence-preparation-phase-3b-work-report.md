# Phase 3B Analyze Evidence Preparation Work Report

## 范围与基线

- `AGENTS.md` 不存在；已记录并继续执行。
- Phase 3A PR #67 已按授权以普通 merge commit 合并：merge SHA
  `b26ff3aad151a1153af557bb88951ab4df114e20`。远程 Phase 3A 分支仍保留。
- Phase 3A merge SHA 的 main CI run `31864305997` 成功，Java Normalization Candidate
  run `31864305978` 成功。
- Phase 3B 基线：`b26ff3aad151a1153af557bb88951ab4df114e20`（最新 `origin/main`）。
- Phase 3B 生产代码提交：`72decb5966ba3c07c3bc796cdc7e093d0d7b8a63`。
- 本报告只讨论生产代码和测试代码；不统计文档、Markdown、Work Report 或索引。

## 提取与保留的职责

### 已提取

新增 `backend/app/analyze/evidence_preparation.py`，由少量有明确边界的函数负责：

- `scan_untrusted_input`：Resume/JD 的 LLM-bound 脱敏、安全扫描、扫描合并、warning、
  blocked 判断和 `scan_untrusted_input` workflow step。
- `prepare_project_evidence`：按原顺序协调 Project Knowledge 检索、Project Knowledge
  安全扫描/过滤和 Safe Prompt 构建；同时负责 RAG off 的两个 skip step。
- `_retrieve_project_evidence`：更新 `retrieved_chunks`、公开 `rag_sources`、检索 warning
  和 retrieval workflow message。
- `_scan_project_evidence`：更新 `security_filtered_rag_sources`、过滤后的 chunks 和
  `rag_sources`，合并 security scan，处理 warning/blocked 和 workflow message。
- `_build_safe_prompt`：使用已扫描的 Resume/JD 和过滤后的 evidence 构建安全提示词。

现有的 Project Knowledge 查询、数据库索引和公开 source metadata owner 通过直接函数
参数传入，避免循环导入；没有新增 service class、状态机、注册系统、抽象基类或通用框架。
没有迁移 AsyncOpenAI。

### 明确保留

- Java normalization 的 local/shadow/authoritative 行为仍在 handler；特别是原有顺序
  `scan_untrusted_input → Java normalization → retrieve/scan evidence → build_safe_prompt`
  未改变。
- idempotency fingerprint、claim、execution binding、replay，以及 Provider、deadline、
  retry、repair、fallback 均保留在原 owner。
- LLM output security scan、JSON parse、evidence validation/reconciliation、History、
  finalization 和 monitoring 均未迁移。
- Phase 3A 输入准备模块、数据库/Alembic、环境变量、Java、Redis、Worker、Outbox、前端
  和生产拓扑均未修改。

## 代码指标

AST line span 和 workflow branch construct 统计如下：

| 项目 | 基线 | Phase 3B | 变化 |
| --- | ---: | ---: | ---: |
| `analyze` 长度 | 961 | 818 | -143 |
| `analyze` 分支数 | 59 | 47 | -12 |

新增主要函数：

| 函数 | 行数 | 分支数 |
| --- | ---: | ---: |
| `scan_untrusted_input` | 48 | 3 |
| `prepare_project_evidence` | 58 | 2 |
| `_retrieve_project_evidence` | 46 | 2 |
| `_scan_project_evidence` | 57 | 4 |
| `_build_safe_prompt` | 27 | 1 |

生产代码（不含 docs/**）为 `+304 / -163`，净变化 `+141`；测试代码为 `+405 / -0`，
净变化 `+405`。没有删除测试。

## 行为保持证据

- 同一组 7 个合成 characterization tests 在 Phase 3B 基线和当前代码各自全部通过（7/7、
  7/7）。测试覆盖 RAG off、RAG on 有 evidence、RAG on 空 evidence、untrusted warning、
  blocked input、filtered Project Knowledge，以及 Stored Resume。比较了 HTTP 状态、错误
  envelope、workflow evidence steps、公开 RAG 字段和 Provider 调用次数。
- RAG off 仍跳过 `retrieve_project_evidence` 与 `scan_project_evidence`，并继续构建 safe
  prompt；Provider 调用次数保持为一次。
- 有 evidence 时保留 `retrieved_chunks`、`retrieval_count`、公开 `rag_sources`、`[pk:<id>]`
  Safe Prompt evidence 标签和 grounding 行为；空 evidence 继续 warning 且不制造 source。
- Prompt injection 仍被替换为安全 placeholder，`security_status` 为
  `passed_with_warnings`；credential-like blocked input 仍返回 422 的
  `INPUT_SECURITY_BLOCKED`，Provider 调用次数为零，后续 steps 被 skip，且不保存 History。
- Project Knowledge 纯注入 chunk 仍被过滤，不出现在公开 `rag_sources`；Stored Resume 与
  上传 Resume 保持相同 evidence workflow contract。
- Java normalization shadow/authoritative、Analyze、Provider、fallback、idempotency 和
  completed replay 既有定向测试继续通过。

## 实际验证

- `git diff --check`：通过。
- `.venv/bin/python -m compileall -q backend scripts`：通过。
- Phase 3B evidence characterization：基线 7/7，当前 7/7。
- 定向组合（输入准备、evidence preparation、Foundation、Job pipeline、RAG、Provider、
  fallback、idempotency、normalization shadow、Java authoritative）：216 tests，全部通过。
- 后端完整：`python -m unittest discover -v`，570 tests 全部通过；12 个 PostgreSQL
  opt-in tests 按预期 skipped。
- PostgreSQL 16.9 隔离集成：`PJA_RUN_POSTGRES_TESTS=1 python -m unittest -q
  test_v2_postgres_integration.py`，12/12 通过；隔离容器已停止并删除。
- 前端：`npm run test -- --run`，9 files、70 tests 全部通过；`npm run build` production
  build 成功。
- Alembic fresh `upgrade head`、`current`、`heads --verbose`：current/head 均为
  `20260730_07`。
- 使用合成环境变量执行 `docker compose --env-file ... config --quiet`：通过。
- 本地 fresh Docker build：backend 成功；frontend 首次因容器内 npm optional native binding
  缺失失败，立即重试成功。随后以 fresh 构建的隔离 backend/frontend image 执行
  `PJA_SMOKE_MILESTONE=2.0.6 PJA_SMOKE_SKIP_BUILD=1 scripts/docker-smoke-v2.sh`：全部
  smoke steps 通过，包含 Alembic、auth/CSRF、Profile/Resume/Analyze、RAG/evidence/
  grounding、restart persistence、backup/restore 和 checksum。隔离容器、network、volume
  和临时 image tags 已清理；现有生产-like 服务未触碰。
- GitHub CI：Phase 3B PR 尚未创建，待最终 head checks 完成后补充 run ID 和结果。

所有测试仅使用合成数据、本地 fixture 和 Mock Provider；未读取、输出或提交真实密钥、Cookie、
Resume、JD、Project Knowledge、Provider 响应或生产数据。

## 已知风险与回滚

- 新模块使用既有 owner 的直接 callback 保持错误 envelope、workflow failure/blocked 副作用、
  检索实现和测试 patch surface；这些 callback 不负责改变 Java 或 Provider 生命周期。
- 本地 frontend Docker build 的首次 optional dependency 缺失是构建环境瞬态风险；第二次
  fresh build 和后续 smoke 均成功，PR CI fresh build 仍是最终权威证据。
- Provider 后处理、History 和 finalization 仍在较长 handler 中，本阶段未扩大边界。
- Phase 3B PR 未获合并授权，交付时必须保持 OPEN。
- 回滚代码可执行
  `git revert 72decb5966ba3c07c3bc796cdc7e093d0d7b8a63`；该操作不涉及数据库、Alembic、
  Phase 3A merge commit 或生产配置。
