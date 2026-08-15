# Phase 3D Analyze Boundary Consolidation Work Report

日期：2026-08-15

## 范围与基线

- 仓库不存在 `AGENTS.md`；已记录并按 README、现有代码和工作报告继续。
- Phase 3C PR #69 已按授权使用普通 merge commit 合并，未 squash、未 rebase、未删除远程分支。
  合并提交为 `a4e57d06a059db8089a22ff957630c27250775c1`，远程 Phase 3C 分支仍保留。
- 合并后的 main CI run `31871257101` 成功，Java isolated candidate run `31871256879` 成功。
- Phase 3D 基线为合并后最新 `origin/main`：
  `a4e57d06a059db8089a22ff957630c27250775c1`。
- Phase 3D 功能提交：`e18092be322b8e6be11824dc6b9b5d7b6bb8fe4c`。

## 删除的边界成本

本阶段只做能产生生产代码净减少的直接收敛：

- `result_refinement.py` 直接使用既有独立 owner 的
  `analysis_fallback.deterministic_scoring`、`recommendation_engine.generate_next_action` 和
  `security_utils.scan_llm_output`，删除对应的 callback 参数、handler 转发和三个 callback 类型别名。
- 将 post-provider 的 `sanitize_provider_narratives` 移到 `result_refinement.py`，并让
  `sanitize_provider_result_narratives` 直接调用它；删除 `legacy_application.py` 中的旧实现和
  narrative sanitizer callback。实现只保留一份。
- 更新测试和手工 candidate 入口去引用实际 owner；没有为历史 monkeypatch 路径增加生产兼容层。

## 明确保留的边界

以下 callback 仍有明确的运行时 owner 或生命周期原因，没有用包装对象替换：

- `failure_handler`：legacy owner 负责安全异常转换、workflow failure、monitoring observation 和
  原有 error envelope。
- `blocked_handler`：legacy owner 负责 request-scoped security 状态、blocked envelope 和观测。
- `skip_steps_after`：legacy owner 持有完整 workflow step 顺序及精确 skip message。
- evidence validator/reconciler、grounding enforcer、match-score calculator、narrative ensurer、
  RAG source builder 和 list normalizer：实现仍被 legacy 的 compact conversion、旧的
  `analyze_with_deepseek`/candidate 路径或共享 normalization helper 使用；将其强行直接导入会造成
  循环依赖、扩大迁移边界或增加重复实现，未能提供安全净减。

没有提取 History 写入、application transaction、idempotency claim/replay/finalize 或最终 response
assembly；它们仍是 handler 中紧密的事务收尾边界。

## 代码指标

只统计生产源代码和测试代码，排除文档、README、lockfile、生成文件和构建产物。分支数按 AST 中的
`if`、`for`、`async for`、`while` 和 `try` 构造统计。

| 项目 | PR #69 合并后 main | Phase 3D | 变化 |
| --- | ---: | ---: | ---: |
| `analyze` 代码行跨度 | 667 | 663 | -4 |
| `analyze` 分支数 | 35 | 35 | 0 |
| `refine_analyze_result` callback 参数 | 13 | 10 | -3 |

结果精炼模块中的主要函数：

| 函数 | 行数 | 分支数 |
| --- | ---: | ---: |
| `sanitize_provider_narratives`（迁移后的唯一实现） | 68 | 11 |
| `sanitize_provider_result_narratives` | 23 | 2 |
| `refine_analyze_result` | 58 | 0 |
| `_validate_evidence_references` | 41 | 3 |
| `_reconcile_evidence` | 82 | 4 |
| `_recommend_next_action` | 25 | 1 |
| `_prepare_security_fields` | 11 | 0 |
| `_scan_final_output` | 56 | 2 |

相对基线的代码变化：

- 生产代码：`+80 / -91`，净变化 `-11`。
- 测试代码：`+5 / -12`，净变化 `-7`。测试用例没有删除或弱化，仅移除已不存在的 callback setup 并
  更新实际 owner patch/import。
- 没有重复实现；`sanitize_provider_narratives` 只有一个生产定义，未产生循环导入。
- handler 中原有的三组 callback 转发已经删除；handler 没有为了数字继续拆分。

## 行为保持证据

- 输入准备、evidence preparation、result refinement 和 pragmatic provider characterization：27/27
  通过。
- RAG、evidence grounding、unsupported claim、final-output security、Provider/fallback：73/73
  通过。
- Java shadow/authoritative normalization：17/17 通过。
- Analyze idempotency/completed replay 与 provider deadline：56/56 通过。
- 测试仅使用 synthetic fixture、mock provider 和隔离数据库；没有新增敏感内容到日志、warning 或
  response。
- 直接 owner 变更不改变 workflow step 顺序、status/message、warning、evidence、score、narrative、
  next_action、security scan、Provider 调用次数、History 或 idempotency 行为。

## 验证命令与结果

- `git diff --check`：通过。
- `.venv/bin/python -m compileall -q backend`：通过。
- Phase 3A/3B/3C 定向测试：通过（27/27）。
- RAG/security/Provider/fallback 定向测试：通过（73/73）。
- Java shadow/authoritative：通过（17/17）。
- idempotency/deadline：通过（56/56）。
- 完整 backend：`python -m unittest discover -s backend -p 'test*.py' -q`，576 tests 全部通过，12 个
  PostgreSQL opt-in tests 按预期 skipped。
- PostgreSQL 16.9 isolated container：`PJA_RUN_POSTGRES_TESTS=1 python -m unittest -q
  backend.test_v2_postgres_integration`，12/12 通过；容器已清理。
- GitHub CI run `31872156774`：backend、PostgreSQL、frontend、Docker build/smoke、Compose、
  production runtime、script 和 repository safety checks 全部通过。
- Java Normalization Candidate run `31872156726`：isolated synthetic candidate 和 cleanup 全部通过。
- 本阶段未修改前端、Compose、Dockerfile 或部署配置，因此不重复运行本地 frontend build、fresh
  Docker build 和 smoke；这些对应 CI job 仍会检查。
- 首次带有环境 SOCKS proxy 的 Provider 测试因缺少 `socksio` 失败；清除 `HTTP_PROXY`、`HTTPS_PROXY`
  和 `ALL_PROXY` 后使用相同 synthetic/mock 测试重跑并通过，代码未改变 Provider 行为。

## 风险、回滚与下一阶段建议

- 风险限于直接 import owner 的依赖方向和测试 patch surface；compile、定向回归和后续 CI 用于发现
  循环依赖或 owner 偏差。
- 回滚可执行本分支 Phase 3D 提交的 `git revert`，不涉及数据库、配置、部署拓扑或 PR #69 merge
  commit。
- Phase 3D 已达到生产净减少；建议停止继续拆 Analyze 文件边界。若后续需要继续重构，应另立阶段审查
  History/idempotency/final response 事务边界，不在本阶段扩大范围。
