# Analysis Contract Simplification — Phase 2B Work Report

日期：2026-08-14
分支：`refactor/simplify-analysis-contract-phase-2b`

## 基线与范围

- `AGENTS.md`：仓库中不存在；按任务要求记录后继续。
- Phase 2A PR：#64 已在重新确认 OPEN、`main` base、指定 head 分支和指定 head SHA、CLEAN/可合并、required checks 全部成功且改动范围符合 Work Report 后，以普通 merge commit 合并。
- Phase 2A merge commit：`3cafda4c6026e1a9828871a19ada98b5e815c530`。
- 合并后 main CI：`CI` run `31787278178` 成功；`Java Normalization Candidate` run `31787278227` 成功。
- Phase 2B 基线：最新 `origin/main`，SHA `3cafda4c6026e1a9828871a19ada98b5e815c530`。
- Phase 2B 实现代码最终 SHA：`744af06ec33f6b58517d8d2b50688d8cab23b1b5`。后续仅补充本报告和 PR CI 证据，不改变该生产/测试代码快照。

本阶段只修改了 `backend/analysis_contract.py`、其直接调用方 `backend/legacy_application.py`，以及直接 contract 测试。没有迁移 AsyncOpenAI，没有修改 Provider deadline transport，也没有修改 API、数据库、Java、Redis、Worker、Outbox、Compose、生产拓扑或前端实现。

## 代码变化

保留了旧 Provider shape、字段别名、wrapper、legacy skill/dimension/evidence 输入和安全 salvage 行为；活动 prompt 仍只要求 `job_summary`、`match_reasons`、`recommendations`、`resume_improvements` 四个字段。

主要变化：

- canonical Provider 字段和 legacy analysis 字段分别从 alias map 派生，Pydantic `AliasChoices`、顶层 salvage 和 warning normalization 使用同一组来源。
- 将 dimension value、dimension name、evidence reference 的重复 alias 表收敛到共享 map。
- 将字符串列表、evidence ID、skill 去重、score 解析/clamp 和 narrative 清理合并到少数明确 helper；保留 legacy empty scalar 的 rejected/action 语义。
- salvage 负责一次有界 normalization；`validate_compact_analysis` 接受已经 salvage 的对象，避免调用方再次把同一数据重新 salvage。Pydantic 保留 schema/meaningful-analysis 校验，不再重复承担相同 normalization。
- 删除未使用的 list/dict default helper、空 dimension helper、重复 field validators、named-dimension validator、重复 evidence/skill/string validators，以及重复 recommendation compatibility model validator。
- 对 legacy `concise_recommendations` 保留兼容处理；因为它与另一个 Pydantic 字段存在 alias overlap，在 salvage 中显式协调，不扩大 Pydantic 双字段 alias 冲突。

## 代码统计

统计基准为 `3cafda4...` 到 `744af06...` 的代码 diff；完全排除 `docs/**`、Work Report、Work Report 索引、Markdown 和说明文件。

| 范围 | 增加 | 删除 | 净变化 |
|---|---:|---:|---:|
| 生产源代码（analysis contract + 直接调用方） | 209 | 350 | -141 |
| 测试代码 | 13 | 0 | +13 |

没有删除测试制造减行。`backend/analysis_contract.py` 源文件总行数由 1333 降至 1192；该数字只用于源代码函数/实现检查，不包含文档。

主要函数的 AST 行跨度和主要控制分支（`if`/`for`/`while`/`try`/`match`）如下：

| 函数 | 基线 | Phase 2B |
|---|---|---|
| `salvage_compact_analysis` | 158 行，21 分支 | 174 行，24 分支 |
| `validate_compact_analysis` | 8 行，2 分支 | 17 行，5 分支 |
| `_salvage_dimension_value` | 78 行，16 分支 | 58 行，12 分支 |
| `_salvage_dimensions` | 55 行，9 分支 | 49 行，9 分支 |
| `_salvage_string_list` | 42 行，7 分支 | 46 行，8 分支 |
| `_salvage_evidence_references` | 71 行，15 分支 | 74 行，15 分支 |
| `compact_analysis_warnings` | 23 行，3 分支 | 24 行，3 分支 |

salvage 主函数略有增长，是因为原先分散在 salvage 与多个 Pydantic validator 中的唯一 normalization 现在集中在一个有界入口；生产源代码整体仍实质净减少 141 行，dimension/validator 重复结构被删除。

## 行为保持证据

所有输入均为仓库合成 fixture、确定性测试数据或 Mock Provider；没有读取、输出或提交真实密钥、Cookie、Resume、JD、Provider 原始响应或生产数据。

- DeepSeek Provider acceptance v1：23 个 fixture，期望分类为 complete 2、repaired 7、partial 9、fallback 4，另有 1 个 security rejection；逐 fixture 断言通过。
- Provider acceptance v2：22 个 fixture，期望分类为 complete 1、repaired 2、partial 14、fallback 5；逐 fixture 断言通过。
- v201 RAG fixture：8 个 Mock completion fixture，覆盖 valid compact、RAG disabled、unsupported/unknown evidence、schema extra field、truncated 和 finish reason length；测试通过。
- 基线模块与 Phase 2B 模块的逐项 comparator 对 canonical JSON、fenced JSON、outer wrapper、alias、missing/null、scalar/list、numeric string、score clamp、evidence mapping、malformed/truncated/empty、security 和 grounding 输入逐项比较；49 个去重后的 fixture content 结果全部 identical。
- 另以固定 seed 生成 5000 组仅含合成值的兼容 shape，最终模型、salvage action/rejected/accepted metadata 和 warning 列表均与基线一致。
- trailing comma、format repair 最多一次、Provider error code、安全 metadata、response size bound、complete/repaired/partial/fallback 规则由定向 resilience/acceptance/RAG/idempotency 测试覆盖。
- 新增 `test_provider_normalization_runs_once_before_validation`，确认 Analyze response 路径对 normalization 只调用一次。

## 验证命令与结果

本地 HTTPX 测试环境存在代理变量且 venv 未安装 SOCKS extra；最终网络相关测试均在去除大小写 HTTP/HTTPS/ALL proxy 环境变量后执行。该环境调整不涉及代码和 Provider 网络调用。

- `git diff --check`：通过。
- `.venv/bin/python -m compileall -q backend scripts`：通过。
- `python -m unittest -v test_v203_analysis_resilience.py test_deepseek_provider_acceptance.py test_pragmatic_provider_acceptance.py test_v201_rag.py test_analyze_idempotency.py`：113 tests，全部通过。
- `python -m unittest discover -v`，`APP_ENV=test`、独立临时 SQLite：556 tests，全部通过，12 个 PostgreSQL opt-in 项目按环境标记 skip。
- `PJA_RUN_POSTGRES_TESTS=1 python -m unittest -v test_v2_postgres_integration.py`，独立 PostgreSQL 16.9 synthetic container：12 tests，全部通过。
- Alembic fresh upgrade/current/heads：current `20260730_07`，heads `20260730_07 (head)`，一致。
- `POSTGRES_TOOL_IMAGE=personal-job-agent-backend:ci@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa docker compose --env-file .env.example config --quiet`：通过。
- `npm run test -- --run`：9 test files、70 tests，全部通过。
- `npm run build`：production Vite build 成功。
- `PJA_SMOKE_MILESTONE=2.0.6 PJA_APP_VERSION=2.0.6 scripts/docker-smoke-v2.sh`：Version 2.0.6 isolated Mock LLM smoke 通过，覆盖 Alembic current=head、health、auth/CSRF、Profile/Resume/Analyze、RAG/evidence/grounding、restart persistence、backup/restore 和 checksum；isolated Compose 项目已由脚本清理。
- Phase 2B PR #65 head `d68517e16d019c89c5a4e608e6378caff78350af` 的 CI run `31791194508`：`backend-tests`、`backend-postgres`、`frontend-build`、`docker-build`、`docker-smoke-v2`、`postgres16-backup-restore`、`compose-validation`、`production-runtime-regression`、`script-validation`、`repository-safety` 全部 pass。
- Phase 2B PR 的 `Java Normalization Candidate` run `31791194513`：`isolated-candidate` pass，清理检查通过。

## 已知风险与回滚

- legacy 兼容输入仍然存在，因本阶段明确禁止行为变更；旧 alias 的停止支持应另开行为变更评估。
- `salvage_compact_analysis` 的行跨度增加，原因是 normalization 责任从重复 validators 收敛到单一入口；其调用次数由测试锁定为一次。
- PR #65 已完成远端 CI，但当前 PR 仍未授权合并，保持 OPEN；本阶段不执行 merge。
- 若需要回滚 Phase 2B，实现代码可用 `git revert 744af06ec33f6b58517d8d2b50688d8cab23b1b5`；该方式不删除 Phase 2A merge commit，也不影响数据库 schema 或生产环境。
