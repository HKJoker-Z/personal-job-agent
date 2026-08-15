# Phase 3C Analyze Result Refinement Work Report

日期：2026-08-15

## 范围与基线

- 仓库不存在 `AGENTS.md`；已记录并按 README、现有代码和工作报告继续。
- Phase 3B PR #68 已按授权使用普通 merge commit 合并：merge SHA
  `54fa0b1d22767c398158ce1c7f61054cf1d174cf`。远程 Phase 3B 分支仍保留。
- 合并后的 main CI run `31867199640` 成功，Java Normalization Candidate run
  `31867199660` 成功。
- Phase 3C 基线为最新 `origin/main`：
  `54fa0b1d22767c398158ce1c7f61054cf1d174cf`。
- Phase 3C 功能代码最终 SHA：`9a6de79d77a995f2e3c5cf96e0eef3bc1d9434a7`。
- 功能代码 head 的 GitHub CI run `31868782841` 和 Java Normalization Candidate run
  `31868782844` 均成功；所有实际运行的 CI jobs 均通过。

## 提取内容

新增 `backend/app/analyze/result_refinement.py`，按原顺序提供少量直接函数：

- `sanitize_provider_result_narratives`：保留 Provider 结果解析后的 narrative grounding、warning
  和 `complete` 到 `partial` 的原有转换。
- `_validate_evidence_references`：验证 evidence IDs，处理未知/拒绝引用、warning、状态调整和
  `validate_evidence_references` workflow step。
- `_reconcile_evidence`：执行 RAG reconciliation、grounding、确定性评分和 narrative 修正，更新
  `retrieved_chunks` 相关公开字段、claim validation、evidence warnings 和 result state。
- `_recommend_next_action`：保留 next-action 计算及 workflow message。
- `_prepare_security_fields` 与 `_scan_final_output`：保留 security policy 字段、最终序列化扫描、
  blocked/error envelope、warning 和 workflow step。
- `refine_analyze_result` 只按原顺序协调这些步骤，并将现有 owner 的函数显式传入，避免循环导入。

`legacy_application.py` 的 Analyze handler 已删除对应的原实现，仅保留一次边界调用。现有
`validate_model_evidence_references`、reconciliation、grounding、deterministic scoring、next
action、source builder 和 scanner 实现仍由原 owner 提供；没有复制第二套实现，也没有新增
service class、状态机、registry、adapter 或通用框架。

## 明确保留的内容

- Provider 选择、调用、deadline、retry、repair、fallback 和 JSON parsing。
- 输入准备、repository/evidence retrieval 和 evidence preparation。
- Java normalization（包括 shadow/authoritative）、idempotency claim/replay/finalize。
- History 写入、application 事务、最终 response assembly、monitoring 和日志架构。
- `analysis_contract.py`、数据库/Alembic、环境变量、Redis、Worker、Outbox、Agent Run、前端、
  Docker 和生产拓扑。

## 代码指标

只统计生产代码和测试代码。分支数按 AST 中的 `if`、`for`、`async for`、`while` 和 `try`
构造统计。

| 项目 | 基线 | Phase 3C | 变化 |
| --- | ---: | ---: | ---: |
| `analyze` 代码行跨度 | 818 | 667 | -151 |
| `analyze` 分支数 | 47 | 35 | -12 |

新增生产函数：

| 函数 | 行数 | 分支数 |
| --- | ---: | ---: |
| `sanitize_provider_result_narratives` | 24 | 2 |
| `refine_analyze_result` | 64 | 0 |
| `_validate_evidence_references` | 41 | 3 |
| `_reconcile_evidence` | 83 | 4 |
| `_recommend_next_action` | 26 | 1 |
| `_prepare_security_fields` | 11 | 0 |
| `_scan_final_output` | 57 | 2 |

最长新增函数为 83 行；没有新增超大型函数。相对 Phase 3C 基线：

- 生产代码：`+381 / -175`，净变化 `+206`。增加来自明确的 post-provider 模块边界、显式
  callback 类型和逐步骤错误处理；handler 中原实现已删除。
- 测试代码：`+217 / -0`，净变化 `+217`。没有删除或弱化现有测试。

## 行为保持证据

- 修改前的同一组 Analyze/RAG/resilience/provider characterization suite 为 68/68 通过；
  修改后同一组仍为 68/68 通过，新增 Phase 3C characterization 为 6/6 通过。
- 新测试覆盖合法 evidence reference、unknown/rejected reference、RAG reconciliation、
  unsupported claim、`complete` 到 `partial`、fallback、next action、final-output scan 通过和
  blocked boundary，并断言 workflow step 顺序、status、warnings、公开 evidence、score 和
  security status。
- 现有 idempotency/completed replay、Provider/fallback、Java shadow/authoritative 测试继续通过；
  PostgreSQL 集成测试验证 History/idempotency 数据路径未被改变。
- RAG off 仍不制造 evidence source；RAG on 仍保留 reconciliation、grounding、公开 source 和
  deterministic scoring。最终扫描 blocked 时仍不调用后续 History/finalization。
- 代码只记录长度、类别和安全元数据，不新增 Resume、JD、Project Knowledge、密钥或 Provider
  响应到日志、warning 或错误响应。

## 实际验证

- `git diff --check`：通过。
- `.venv/bin/python -m compileall -q backend scripts`：通过。
- `python -m unittest -q test_analyze_result_refinement.py`：6 tests，全部通过。
- 基线同源 suite：68 tests，全部通过；当前同源 suite：68 tests，全部通过。
- Provider、fallback、idempotency、deadline、normalization shadow 和 Java authoritative 定向
  组合：85 tests，全部通过。
- 后端完整：`python -m unittest discover -v`，576 tests 全部通过；12 个 opt-in PostgreSQL
  tests 按预期 skipped。
- PostgreSQL 16.9 隔离集成：12 tests，全部通过；隔离容器已清理。
- 前端：9 个 test files、70 tests 全部通过；production Vite build 成功。
- Alembic 临时数据库 fresh `upgrade head`、`current`、`heads --verbose`：current/head 均为
  `20260730_07`。
- 使用合成环境变量执行 `docker compose config --quiet`：通过。
- backend/frontend `docker build --no-cache`：均成功。
- `PJA_SMOKE_MILESTONE=2.0.6 PJA_SMOKE_SKIP_BUILD=0 scripts/docker-smoke-v2.sh`：完整
  2.0.6 synthetic Mock LLM smoke 通过，包含 Alembic、auth/CSRF、Analyze、RAG/evidence、
  restart persistence、backup/restore 和 checksum；隔离资源已清理。
- GitHub CI run `31868782841`：backend、PostgreSQL、frontend、Docker build、Docker smoke、
  Compose、production runtime、script 和 repository safety jobs 全部成功。
- Java Normalization Candidate run `31868782844`：isolated synthetic candidate 和 cleanup 全部
  成功。

所有验证仅使用合成数据、本地 fixture、隔离数据库和 Mock Provider；未读取、输出或提交真实
密钥、Cookie、Resume、JD、Project Knowledge、Provider 响应或生产数据。

## 风险、回滚与下一阶段

- 新模块通过显式 callback 复用既有 owner，保持错误 envelope、workflow 副作用和测试 patch
  surface；callback 不改变 Provider、Java 或 History 生命周期。
- post-provider 结果处理仍需要较多现有领域函数参数，这是为避免循环导入和重复实现保留的
  直接边界；后续阶段不应再扩展本模块职责。
- 回滚功能代码可执行 `git revert 9a6de79d77a995f2e3c5cf96e0eef3bc1d9434a7`，不涉及数据库、
  配置、部署拓扑或 Phase 3B merge commit。
- 下一阶段应另行评估 History 写入、idempotency finalize 和最终 response assembly；本阶段未
  迁移这些职责。
