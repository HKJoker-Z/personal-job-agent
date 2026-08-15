# Analyze Input Preparation Extraction — Phase 3A Work Report

日期：2026-08-14
分支：`refactor/extract-analyze-input-preparation-phase-3a`

## Phase 2C 合并与 Phase 3A 基线

- 仓库中不存在 `AGENTS.md`；已按授权记录并继续。
- PR #66 合并前重新确认：状态 `OPEN`，base 为 `main`，head 为
  `refactor/simplify-analyze-provider-resolution-phase-2c`，head SHA 为
  `c872e64718b53039624905f998ddf8a5a0b0551a`，且为 `MERGEABLE/CLEAN`。
- PR #66 最终 head 的 11 个实际 checks 均已完成并成功，包括 CI 的
  `backend-tests`、`backend-postgres`、`frontend-build`、`docker-build`、
  `docker-smoke-v2`、`postgres16-backup-restore`、`compose-validation`、
  `production-runtime-regression`、`script-validation`、`repository-safety`，以及
  Java Normalization Candidate 的 `isolated-candidate`。
- PR #66 的代码 diff 仅修改 `backend/legacy_application.py` 中 Phase 2C Provider
  resolution 边界，另含对应 Work Report；没有发现超出 Phase 2C 报告范围的改动。
- PR #66 使用普通 merge commit 合并，没有 squash，也没有删除远程 Phase 2C 分支。
- Phase 2C merge commit：`0ccd3c8b5b88c009da035ac5762f9dd806ac73b7`。
- 合并后同一 merge SHA 的 main CI run `31859608814` 成功；Java Normalization
  Candidate run `31859608799` 成功。
- 重新 fetch 后，Phase 3A 基线固定为最新 `origin/main`：
  `0ccd3c8b5b88c009da035ac5762f9dd806ac73b7`。
- Phase 3A 最终代码 SHA：`1be00684a85e51e94ecef010e897b282fabe2f6b`。

## 提取边界与职责

新增 `backend/app/analyze/input_preparation.py`，只拥有 Analyze 的三个连续输入步骤：

- `validate_input`：Resume upload/Stored Resume Version 互斥、PDF/DOCX 扩展名和已知上传
  大小检查、JD text/JD URL 互斥、RAG mode 与 top-k 解析，以及
  `resume_filename`、`job_url`、`source_type` 等上下文字段。
- `parse_resume`：临时 PDF/DOCX 读取、大小与内容检查、文本提取和标准化、Stored Resume
  Version 鉴权/UUID/不存在/无可分析内容映射、长度限制和 truncation warning。
- `acquire_job_description`：pasted JD text 或 `SafeJobUrlFetcher` 获取、原 SSRF/重定向/
  压缩与解压响应大小/content-type 边界、长度限制和 truncation warning。

三个步骤的 start、complete、fail、warning 和原有 message 随逻辑一起移动。新增唯一的小型
`PreparedAnalyzeInput`，返回已经填充的 `WorkflowContext`、清理后的
`resume_version_id` 和输入 warnings，避免在 handler 与 helper 间重复传递准备结果。

从 `legacy_application.py` 删除了对应 handler 实现和只为该流程服务的 PDF/DOCX 提取、上传
解析、JD URL 获取、文本截断、RAG mode 解析代码。`clamp_rag_top_k` 和
`analyze_error_detail` 随职责移动后由 legacy 模块直接 import，没有增加转发包装层。

原 handler 保留并继续负责：

- Idempotency key 校验、claim/fingerprint/completed replay 和 execution binding。
- Security scan、Java normalization、RAG retrieval 和 evidence reconciliation。
- Provider、deadline、retry、repair、fallback 和结构化结果处理。
- History 保存、final output scan、result finalization 和监控记录。

没有修改 `analysis_contract.py`、Provider transport/deadline/retry/repair/fallback、Security
scan、RAG 实现、History finalization、Schema/Alembic、环境变量、Java、Redis、Worker、
Outbox、Agent Run、Compose、生产拓扑或前端。没有状态机、service class、抽象基类、注册
系统、通用框架或循环导入；原 handler 中对应实现已删除，不存在复制保留。

## 代码指标

统计范围为基线 `0ccd3c8...` 到最终代码 SHA `1be0068...`，只统计生产源代码和测试代码。

| 范围 | 增加 | 删除 | 净变化 |
|---|---:|---:|---:|
| 生产源代码 | 494 | 314 | +180 |
| 测试代码 | 462 | 1 | +461 |

测试的唯一删除是一条旧 mock target 路径，同时改为新模块的实际 owner；没有删除测试用例。
生产代码净增加来自独立模块边界、结构化结果、显式类型、逐步骤失败保持和清晰 helper；旧实现
已完整删除，因此不是重复实现。

AST 行跨度和主要控制分支按 `if`、`for`、`async for`、`while`、`try`、`match` 统计：

| 函数 | 行数 | 主要分支 |
|---|---:|---:|
| 基线 `analyze` | 1,148 | 76 |
| Phase 3A `analyze` | 961 | 59 |
| `prepare_analyze_input` | 56 | 0 |
| `_validate_input` | 51 | 1 |
| `_parse_resume` | 54 | 4 |
| `_acquire_job_description` | 51 | 4 |
| `_validate_resume_source` | 42 | 3 |
| `_validate_job_source` | 16 | 1 |
| `_extract_uploaded_resume` | 39 | 6 |
| `_load_stored_resume` | 43 | 3 |
| `_fetch_job_text` | 9 | 1 |
| `resolve_rag_mode` | 11 | 3 |
| `clamp_rag_top_k` | 2 | 0 |
| `_extract_pdf_text` / `_extract_docx_text` | 各 4 | 各 0 |
| `_input_error` / `analyze_error_detail` | 18 / 13 | 0 / 0 |

`analyze` 缩短 187 行并减少 17 个主要分支。新模块最长函数为 56 行，没有新超大型函数。

## 行为保持证据

新增 `test_analyze_input_preparation.py`。其中 5 组 API characterization tests 使用同一份
测试源码分别在基线 SHA 的临时 detached worktree 和 Phase 3A 实现上运行，两边均为 5/5
通过。该对比覆盖：

- 临时 DOCX、临时 PDF、Stored Resume Version、pasted JD text 和 JD URL 的成功输入。
- 成功结果的稳定 shape、fallback 状态、RAG mode，以及三个输入 step 的精确名称、顺序、
  status 和 message。
- 缺失/重复 Resume source、错误 Resume 类型、缺失/重复 Job source、非法 RAG mode、
  空上传和损坏 DOCX 的精确 HTTP status、错误 code/message、request ID、stage 和 field。
- loopback SSRF URL 的稳定安全错误 envelope；Provider 未接收 Resume/JD 原文。

另外两项结构测试直接断言 `PreparedAnalyzeInput` 与 `WorkflowContext` 的最终
`resume_filename`、`resume_text`、`job_text`、`job_url`、`source_type`、RAG mode、top-k 和
warnings 一致。Stored Resume + JD URL 保持原有 `source_type=saved_resume_version` 行为。

现有 Job pipeline 测试继续覆盖 DNS/IP SSRF、带凭据 URL、私网重定向、重定向循环、gzip
bomb、压缩/解压大小和 content-type；V2 Foundation 继续覆盖 PDF/DOCX 内容提取、空 PDF、
损坏 DOCX、MIME spoof 和上传大小。Analyze、RAG、Provider、fallback、idempotency 和
completed replay 的现有用例全部保持成功。

所有日志只记录长度、类别和安全元数据；新增代码不记录 Resume/JD 原文。所有验证仅使用
合成文本、本地 fixture、隔离数据库和 Mock Provider，没有读取、输出或提交真实密钥、
Cookie、Resume、JD、Provider 响应或生产数据。

## 验证命令与真实结果

- `git diff --check`：通过。
- `.venv/bin/python -m compileall -q backend scripts`：通过。
- Phase 3A 输入测试：`python -m unittest -v test_analyze_input_preparation.py`：7 tests，
  全部通过。
- 输入与错误核心组合：`test_analyze_input_preparation.py` 加
  `test_v203_analysis_resilience.py`：40 tests，全部通过。
- 基线/Phase 3A 同源 characterization：两边各 5 tests，全部通过。
- 定向组合：输入准备、V2 Foundation、Job pipeline、RAG、Provider acceptance、deadline、
  fallback、idempotency、normalization shadow 和 Java authoritative 共 209 tests，全部通过。
- 定向组合首次运行时，当前 shell 的 SOCKS proxy 使 6 个 Provider mock tests 在创建
  httpx transport 时因缺少 `socksio` 失败，Provider mock 尚未调用；不读取或输出代理值，
  仅从测试进程移除 proxy 环境变量后，失败模块 12/12 通过，完整定向组合 209/209 通过。
- 后端最终完整测试：`python -m unittest discover -v`，563 tests 全部通过；12 个
  PostgreSQL opt-in tests 按预期 skipped。
- 独立 PostgreSQL 16.9 容器：
  `PJA_RUN_POSTGRES_TESTS=1 python -m unittest -v test_v2_postgres_integration.py`，12 tests
  全部通过；隔离容器已删除。
- 前端 `npm run test -- --run`：9 files、70 tests，全部通过。
- 前端 `npm run build`：production Vite build 成功。
- Alembic fresh `upgrade head`、`current`、`heads --verbose`：current/head 均为
  `20260730_07`。
- 使用纯合成配置执行 `docker compose --env-file .env.example config --quiet`：通过。
- fresh Docker build 两次在读取 Docker Hub 基础镜像 metadata 时返回外部网络 `EOF`，
  尚未执行任何 Dockerfile step，隔离项目自动清理；公共只读镜像缓存也由同一网络层拒绝。
- 为完成本地运行验证，使用仓库已有 2.0.6 本地运行时镜像，只覆盖当前完整后端生产源码和
  当前前端 build，执行最终 `PJA_SMOKE_MILESTONE=2.0.6` 隔离 Mock LLM smoke：通过。
  覆盖 Alembic current=head、health/auth/CSRF、Profile/Resume/Analyze、RAG/evidence/
  grounding、restart persistence、backup/restore 和 checksum。隔离 Compose 项目、volumes、
  networks 和临时镜像均已清理。PR CI 必须用 fresh build 再确认该门禁。
- GitHub CI：Phase 3A PR head `80333980398226671fd1cec5af0d124de6acc5a5` 的 CI run
  `31861778801` 成功，实际 checks `backend-tests`、`backend-postgres`、`frontend-build`、
  `docker-build`、`docker-smoke-v2`、`postgres16-backup-restore`、`compose-validation`、
  `production-runtime-regression`、`script-validation` 和 `repository-safety` 全部成功；
  Java Normalization Candidate run `31861778768` 的 `isolated-candidate` 也成功。

## 已知风险与回滚

- 输入模块通过传入的既有 `fail_analysis_and_raise` 保持错误 envelope、workflow failure 和
  监控副作用；该 callback 按合同不会返回。新测试覆盖三个失败 stage。
- Stored Resume 成功后覆盖 `source_type` 为 `saved_resume_version`，包括搭配 JD URL 的情况；
  这是原行为，已显式锁定，后续若要拆分 Resume source 与 Job source 需另立行为变更阶段。
- Provider、security、RAG 与 finalization 仍在较长 handler 中；本阶段严格停在三个连续输入
  step，没有借机扩大重构范围。
- 本地 fresh image build 受外部 registry EOF 阻塞；源码覆盖 smoke 已通过，但最终权威证据
  是 Phase 3A PR head 的 fresh Docker build 和 `docker-smoke-v2` CI。
- Phase 3A PR 未获合并授权，交付时保持 OPEN。
- 回滚生产与测试代码可执行
  `git revert 1be00684a85e51e94ecef010e897b282fabe2f6b`；该操作不涉及数据库、Alembic、
  配置或 Phase 2C merge commit。
